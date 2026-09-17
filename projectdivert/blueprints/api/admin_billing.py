"""Admin billing routes."""

import io
import csv
from flask import Blueprint, Response, current_app, jsonify, request
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from projectdivert.extensions import db
from projectdivert.models.waste import WasteRemovalRequest, WasteRequestCommunicationLog
from projectdivert.services.auth import _request_access_allowed, jwt_required
from projectdivert.services.billing import COMMUNICATION_CHANNELS, COMMUNICATION_DIRECTIONS, COMMUNICATION_TEMPLATE_DEFINITIONS, OFFLINE_BILLING_STATES, _build_admin_billing_requests_query, _build_admin_communications_query, _collect_admin_billing_followups, _create_request_communication_log, _normalize_offline_billing_state, _publish_request_communication_log_event, _run_offline_billing_followup_maintenance, _serialize_communication_template
from projectdivert.services.billing_core import BILLING_FOLLOWUP_STATES, _billing_summary, _communication_logs_for_request, _effective_billing_followup_state, _normalize_billing_followup_state, _serialize_request_billing_followup_workflow, _serialize_request_communication_log, _serialize_request_communication_summary
from projectdivert.services.dispatch import _serialize_admin_billing_queue_item, _serialize_request_billing_workflow, _serialize_waste_request, _serialize_waste_request_snapshot
from projectdivert.services.events import _publish_waste_request_event
from projectdivert.services.payments import _financial_summary_for_request
from projectdivert.services.utils import _current_jwt_email, _current_jwt_role, _current_jwt_user_id, _parse_datetime_or_error, _parse_optional_bool_query, _parse_optional_int_query, utcnow

bp = Blueprint('api_admin_billing', __name__)



@bp.route('/api/v1/admin/billing/requests', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_list_billing_requests():
    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=500)
        offset = _parse_optional_int_query(request.args.get('offset'), 'offset', min_value=0)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    limit = limit or 50
    offset = offset or 0

    state = _normalize_offline_billing_state(request.args.get('state'), default='all')
    if state != 'all' and state not in OFFLINE_BILLING_STATES:
        return jsonify({'error': 'Invalid billing state filter', 'allowed_states': ['all'] + sorted(OFFLINE_BILLING_STATES)}), 400

    request_status = (str(request.args.get('request_status') or '').strip().lower() or 'all')
    reference = str(request.args.get('reference') or '').strip() or None
    search = str(request.args.get('search') or '').strip() or None

    try:
        query = _build_admin_billing_requests_query(
            state=state,
            request_status=request_status,
            reference=reference,
            search=search,
        )
        total = query.count()
        rows = (
            query.order_by(
                func.coalesce(WasteRemovalRequest.billing_updated_at, WasteRemovalRequest.created_at).desc(),
                WasteRemovalRequest.created_at.desc(),
                WasteRemovalRequest.id.desc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
        state_counts = {
            row[0] or 'pending_offline_invoice': row[1]
            for row in (
                query.with_entities(
                    func.coalesce(func.lower(WasteRemovalRequest.billing_state), 'pending_offline_invoice'),
                    func.count(WasteRemovalRequest.id),
                )
                .group_by(func.coalesce(func.lower(WasteRemovalRequest.billing_state), 'pending_offline_invoice'))
                .all()
            )
        }
    except SQLAlchemyError:
        current_app.logger.exception('Failed to query admin billing requests.')
        return jsonify({'error': 'Failed to query billing requests'}), 500

    return jsonify(
        {
            'items': [_serialize_admin_billing_queue_item(row) for row in rows],
            'pagination': {
                'limit': limit,
                'offset': offset,
                'returned': len(rows),
                'total': total,
                'has_more': (offset + len(rows)) < total,
            },
            'filters': {
                'state': state,
                'request_status': request_status,
                'reference': reference or '',
                'search': search or '',
            },
            'summary': {
                'state_counts': state_counts,
            },
        }
    )



@bp.route('/api/v1/admin/billing/requests/export', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_export_billing_requests():
    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=5000)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    limit = limit or 1000
    state = _normalize_offline_billing_state(request.args.get('state'), default='all')
    if state != 'all' and state not in OFFLINE_BILLING_STATES:
        return jsonify({'error': 'Invalid billing state filter', 'allowed_states': ['all'] + sorted(OFFLINE_BILLING_STATES)}), 400

    request_status = (str(request.args.get('request_status') or '').strip().lower() or 'all')
    reference = str(request.args.get('reference') or '').strip() or None
    search = str(request.args.get('search') or '').strip() or None

    try:
        rows = (
            _build_admin_billing_requests_query(
                state=state,
                request_status=request_status,
                reference=reference,
                search=search,
            )
            .order_by(
                func.coalesce(WasteRemovalRequest.billing_updated_at, WasteRemovalRequest.created_at).desc(),
                WasteRemovalRequest.created_at.desc(),
                WasteRemovalRequest.id.desc(),
            )
            .limit(limit)
            .all()
        )
    except SQLAlchemyError:
        current_app.logger.exception('Failed to export admin billing requests.')
        return jsonify({'error': 'Failed to export billing requests'}), 500

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            'request_id',
            'request_status',
            'billing_state',
            'billing_reference',
            'billing_notes',
            'requester_name',
            'requester_email',
            'pickup_postcode',
            'assigned_driver_user_id',
            'charged_minor',
            'refunded_minor',
            'paid_out_minor',
            'platform_net_minor',
            'billing_updated_at',
            'created_at',
        ]
    )
    for row in rows:
        financials = _financial_summary_for_request(row.id)
        totals = financials.get('totals') or {}
        workflow = _serialize_request_billing_workflow(row) or {}
        writer.writerow(
            [
                row.id,
                row.status or '',
                workflow.get('state') or 'pending_offline_invoice',
                row.billing_reference or '',
                row.billing_notes or '',
                row.requester_name or '',
                row.requester_email or '',
                row.pickup_postcode or '',
                row.assigned_driver_user_id or '',
                totals.get('charged_minor', 0),
                totals.get('refunded_minor', 0),
                totals.get('paid_out_minor', 0),
                totals.get('platform_net_minor', 0),
                row.billing_updated_at.isoformat() + 'Z' if row.billing_updated_at else '',
                row.created_at.isoformat() + 'Z' if row.created_at else '',
            ]
        )

    filename = 'offline_billing_requests_{}.csv'.format(utcnow().strftime('%Y%m%d_%H%M%S'))
    response = Response(buffer.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename={}'.format(filename)
    return response



@bp.route('/api/v1/admin/billing/followups', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_list_billing_followups():
    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=500)
        due_only = _parse_optional_bool_query(request.args.get('due_only'), 'due_only')
        reminder_after_hours = _parse_optional_int_query(
            request.args.get('reminder_after_hours'),
            'reminder_after_hours',
            min_value=0,
            max_value=24 * 365,
        )
        repeat_hours = _parse_optional_int_query(
            request.args.get('repeat_hours'),
            'repeat_hours',
            min_value=1,
            max_value=24 * 365,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    search = str(request.args.get('search') or '').strip() or None
    report = _collect_admin_billing_followups(
        search=search,
        reminder_after_hours=reminder_after_hours,
        repeat_hours=repeat_hours,
        limit=limit,
        due_only=True if due_only is None else bool(due_only),
    )
    return jsonify(report)



@bp.route('/api/v1/admin/billing/followups/maintenance', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_run_billing_followup_maintenance():
    payload = request.get_json(silent=True) or {}
    limit = payload.get('limit')
    reminder_after_hours = payload.get('reminder_after_hours')
    repeat_hours = payload.get('repeat_hours')
    dry_run = bool(payload.get('dry_run', False))
    log_reminders = bool(payload.get('log_reminders', True))
    search = str(payload.get('search') or '').strip() or None

    try:
        if limit is not None:
            limit = _parse_optional_int_query(limit, 'limit', min_value=1, max_value=500)
        if reminder_after_hours is not None:
            reminder_after_hours = _parse_optional_int_query(
                reminder_after_hours,
                'reminder_after_hours',
                min_value=0,
                max_value=24 * 365,
            )
        if repeat_hours is not None:
            repeat_hours = _parse_optional_int_query(
                repeat_hours,
                'repeat_hours',
                min_value=1,
                max_value=24 * 365,
            )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    try:
        result = _run_offline_billing_followup_maintenance(
            search=search,
            reminder_after_hours=reminder_after_hours,
            repeat_hours=repeat_hours,
            limit=limit,
            dry_run=dry_run,
            log_reminders=log_reminders,
            actor_user_id=_current_jwt_user_id(),
            actor_email=_current_jwt_email(),
            source='api_admin_billing_followups',
        )
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Billing follow-up maintenance failed.')
        return jsonify({'error': 'Failed to run billing follow-up maintenance'}), 500
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Billing follow-up maintenance failed.')
        return jsonify({'error': 'Failed to run billing follow-up maintenance'}), 500

    return jsonify(result)



@bp.route('/api/v1/admin/waste-requests/<int:request_id>/billing', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_update_waste_request_billing(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404

    payload = request.get_json(silent=True) or {}
    billing_state = str(payload.get('state') or '').strip().lower().replace('-', '_').replace(' ', '_')
    if billing_state not in OFFLINE_BILLING_STATES:
        return jsonify(
            {
                'error': 'Invalid billing state',
                'allowed_states': sorted(OFFLINE_BILLING_STATES),
            }
        ), 400

    billing_reference = str(payload.get('reference') or '').strip()
    next_reference = billing_reference[:120] if billing_reference else None

    billing_notes = str(payload.get('notes') or '').strip()
    next_notes = billing_notes[:2000] if billing_notes else None

    previous_state = (booking.billing_state or '').strip().lower() or 'pending_offline_invoice'
    updated = False
    if previous_state != billing_state:
        booking.billing_state = billing_state
        updated = True
    if booking.billing_reference != next_reference:
        booking.billing_reference = next_reference
        updated = True
    if booking.billing_notes != next_notes:
        booking.billing_notes = next_notes
        updated = True

    if updated:
        booking.billing_updated_at = utcnow()
        booking.billing_updated_by_user_id = _current_jwt_user_id()
        if billing_state == 'invoice_sent':
            current_followup_state = _normalize_billing_followup_state(booking.billing_followup_state)
            if current_followup_state not in BILLING_FOLLOWUP_STATES:
                booking.billing_followup_state = 'open'
                booking.billing_followup_updated_at = booking.billing_updated_at
                booking.billing_followup_updated_by_user_id = _current_jwt_user_id()
        elif booking.billing_followup_state != 'closed':
            booking.billing_followup_state = 'closed'
            booking.billing_followup_updated_at = booking.billing_updated_at
            booking.billing_followup_updated_by_user_id = _current_jwt_user_id()

    if not updated:
        return jsonify(
            {
                'updated': False,
                'previous_state': previous_state,
                'request': _serialize_waste_request(booking),
                'billing': _billing_summary(),
                'financials': _financial_summary_for_request(booking.id),
            }
        )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to update billing workflow for request %s.', request_id)
        return jsonify({'error': 'Failed to update billing workflow'}), 500

    metadata = {
        'billing_state': billing_state,
        'billing_reference': next_reference,
        'updated_by_user_id': booking.billing_updated_by_user_id,
    }
    _publish_waste_request_event(
        booking.id,
        'admin_billing_updated',
        payload=_serialize_waste_request_snapshot(booking),
        metadata=metadata,
    )

    return jsonify(
        {
            'updated': True,
            'previous_state': previous_state,
            'request': _serialize_waste_request(booking),
            'billing': _billing_summary(),
            'financials': _financial_summary_for_request(booking.id),
        }
    )



@bp.route('/api/v1/admin/waste-requests/<int:request_id>/billing-followup', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_update_waste_request_billing_followup(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404

    payload = request.get_json(silent=True) or {}
    followup_state = _normalize_billing_followup_state(payload.get('state'))
    if followup_state not in BILLING_FOLLOWUP_STATES:
        return jsonify(
            {
                'error': 'Invalid billing follow-up state',
                'allowed_states': sorted(BILLING_FOLLOWUP_STATES),
            }
        ), 400

    billing_state = (booking.billing_state or '').strip().lower() or 'pending_offline_invoice'
    if billing_state != 'invoice_sent' and followup_state in {'open', 'acknowledged'}:
        return jsonify(
            {
                'error': 'Billing follow-up can only remain open or acknowledged while the request is invoice_sent',
                'billing_state': billing_state,
            }
        ), 400

    next_notes = str(payload.get('notes') or '').strip()
    next_notes = next_notes[:2000] if next_notes else None
    previous_state = _effective_billing_followup_state(booking)
    updated = False

    if booking.billing_followup_state != followup_state:
        booking.billing_followup_state = followup_state
        updated = True
    if booking.billing_followup_notes != next_notes:
        booking.billing_followup_notes = next_notes
        updated = True

    if updated:
        booking.billing_followup_updated_at = utcnow()
        booking.billing_followup_updated_by_user_id = _current_jwt_user_id()

    if not updated:
        return jsonify(
            {
                'updated': False,
                'previous_state': previous_state,
                'request': _serialize_waste_request(booking),
                'followup': _serialize_request_billing_followup_workflow(booking),
            }
        )

    outcome_map = {
        'open': 'billing_followup_reopened',
        'acknowledged': 'billing_followup_acknowledged',
        'closed': 'billing_followup_closed',
    }
    log_entry = _create_request_communication_log(
        booking,
        direction='internal',
        channel='manual',
        subject='Billing follow-up {} for request #{}'.format(followup_state, booking.id),
        message=next_notes
        or 'Billing follow-up marked {} by admin for request #{}.'.format(followup_state, booking.id),
        outcome=outcome_map.get(followup_state),
        customer_visible=False,
        created_by_user_id=_current_jwt_user_id(),
    )
    db.session.add(log_entry)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to update billing follow-up workflow for request %s.', request_id)
        return jsonify({'error': 'Failed to update billing follow-up workflow'}), 500

    metadata = {
        'previous_state': previous_state,
        'followup_state': followup_state,
        'updated_by_user_id': booking.billing_followup_updated_by_user_id,
    }
    _publish_waste_request_event(
        booking.id,
        'admin_billing_followup_updated',
        payload=_serialize_waste_request_snapshot(booking),
        metadata=metadata,
    )
    _publish_request_communication_log_event(
        booking,
        log_entry,
        metadata={
            'source': 'admin_billing_followup_update',
            'followup_state': followup_state,
        },
    )

    return jsonify(
        {
            'updated': True,
            'previous_state': previous_state,
            'request': _serialize_waste_request(booking),
            'followup': _serialize_request_billing_followup_workflow(booking),
            'communication': _serialize_request_communication_log(log_entry),
        }
    )



@bp.route('/api/v1/waste-requests/<int:request_id>/communications', methods=['GET'])
@jwt_required(roles={'customer', 'driver', 'admin'})
def api_get_waste_request_communications(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_access_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403

    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=200)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    limit = limit or 50
    customer_visible_only = _current_jwt_role() in {'customer', 'driver'}
    entries = _communication_logs_for_request(
        request_id,
        customer_visible_only=customer_visible_only,
        limit=limit,
    )
    return jsonify(
        {
            'request_id': request_id,
            'communications': [_serialize_request_communication_log(row) for row in entries],
            'summary': _serialize_request_communication_summary(entries),
            'filters': {
                'customer_visible_only': customer_visible_only,
                'limit': limit,
            },
        }
    )



@bp.route('/api/v1/admin/waste-requests/<int:request_id>/communications/templates', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_get_waste_request_communication_templates(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404

    return jsonify(
        {
            'request_id': request_id,
            'templates': [
                _serialize_communication_template(template, booking)
                for template in COMMUNICATION_TEMPLATE_DEFINITIONS
            ],
        }
    )



@bp.route('/api/v1/admin/waste-requests/<int:request_id>/communications', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_create_waste_request_communication(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404

    payload = request.get_json(silent=True) or {}
    direction = str(payload.get('direction') or '').strip().lower()
    channel = str(payload.get('channel') or '').strip().lower()
    if direction not in COMMUNICATION_DIRECTIONS:
        return jsonify({'error': 'Invalid direction', 'allowed_directions': sorted(COMMUNICATION_DIRECTIONS)}), 400
    if channel not in COMMUNICATION_CHANNELS:
        return jsonify({'error': 'Invalid channel', 'allowed_channels': sorted(COMMUNICATION_CHANNELS)}), 400

    message = str(payload.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'message is required'}), 400

    subject = (str(payload.get('subject') or '').strip()[:255] or None)
    outcome = (str(payload.get('outcome') or '').strip()[:120] or None)
    contact_name = (str(payload.get('contact_name') or '').strip()[:120] or None)
    contact_email = (str(payload.get('contact_email') or '').strip()[:255] or None)
    contact_phone = (str(payload.get('contact_phone') or '').strip()[:120] or None)
    customer_visible = bool(payload.get('customer_visible', False))

    occurred_at_raw = payload.get('occurred_at')
    if occurred_at_raw:
        try:
            occurred_at = _parse_datetime_or_error(occurred_at_raw, 'occurred_at')
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
    else:
        occurred_at = utcnow()

    entry = _create_request_communication_log(
        booking,
        direction=direction,
        channel=channel,
        subject=subject,
        message=message,
        outcome=outcome,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_phone=contact_phone,
        customer_visible=customer_visible,
        created_by_user_id=_current_jwt_user_id(),
        occurred_at=occurred_at,
    )

    try:
        db.session.add(entry)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to create communication log for request %s.', request_id)
        return jsonify({'error': 'Failed to create communication log'}), 500

    _publish_request_communication_log_event(booking, entry)

    entries = _communication_logs_for_request(
        request_id,
        customer_visible_only=False,
        limit=50,
    )
    return jsonify(
        {
            'created': True,
            'communication': _serialize_request_communication_log(entry),
            'communications': [_serialize_request_communication_log(row) for row in entries],
            'summary': _serialize_request_communication_summary(entries),
            'request': _serialize_waste_request_snapshot(booking),
        }
    ), 201



@bp.route('/api/v1/admin/communications/report', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_communications_report():
    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=500)
        offset = _parse_optional_int_query(request.args.get('offset'), 'offset', min_value=0)
        customer_visible = _parse_optional_bool_query(request.args.get('customer_visible'), 'customer_visible')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    limit = limit or 50
    offset = offset or 0

    state = _normalize_offline_billing_state(request.args.get('state'), default='all')
    if state != 'all' and state not in OFFLINE_BILLING_STATES:
        return jsonify({'error': 'Invalid billing state filter', 'allowed_states': ['all'] + sorted(OFFLINE_BILLING_STATES)}), 400

    direction = str(request.args.get('direction') or '').strip().lower() or 'all'
    if direction != 'all' and direction not in COMMUNICATION_DIRECTIONS:
        return jsonify({'error': 'Invalid direction filter', 'allowed_directions': ['all'] + sorted(COMMUNICATION_DIRECTIONS)}), 400

    channel = str(request.args.get('channel') or '').strip().lower() or 'all'
    if channel != 'all' and channel not in COMMUNICATION_CHANNELS:
        return jsonify({'error': 'Invalid channel filter', 'allowed_channels': ['all'] + sorted(COMMUNICATION_CHANNELS)}), 400

    search = str(request.args.get('search') or '').strip() or None

    try:
        query = _build_admin_communications_query(
            state=state,
            direction=direction,
            channel=channel,
            customer_visible=customer_visible,
            search=search,
        )
        total = query.count()
        rows = (
            query.order_by(
                WasteRequestCommunicationLog.occurred_at.desc(),
                WasteRequestCommunicationLog.id.desc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
        direction_counts = {
            row[0] or 'unknown': row[1]
            for row in (
                query.with_entities(
                    func.coalesce(func.lower(WasteRequestCommunicationLog.direction), 'unknown'),
                    func.count(WasteRequestCommunicationLog.id),
                )
                .group_by(func.coalesce(func.lower(WasteRequestCommunicationLog.direction), 'unknown'))
                .all()
            )
        }
        channel_counts = {
            row[0] or 'unknown': row[1]
            for row in (
                query.with_entities(
                    func.coalesce(func.lower(WasteRequestCommunicationLog.channel), 'unknown'),
                    func.count(WasteRequestCommunicationLog.id),
                )
                .group_by(func.coalesce(func.lower(WasteRequestCommunicationLog.channel), 'unknown'))
                .all()
            )
        }
    except SQLAlchemyError:
        current_app.logger.exception('Failed to query communications report.')
        return jsonify({'error': 'Failed to query communications report'}), 500

    items = []
    for row in rows:
        booking = db.session.get(WasteRemovalRequest, row.waste_removal_request_id)
        items.append(
            {
                'communication': _serialize_request_communication_log(row),
                'request': _serialize_waste_request(booking) if booking else None,
            }
        )

    return jsonify(
        {
            'items': items,
            'pagination': {
                'limit': limit,
                'offset': offset,
                'returned': len(items),
                'total': total,
                'has_more': (offset + len(items)) < total,
            },
            'filters': {
                'state': state,
                'direction': direction,
                'channel': channel,
                'customer_visible': customer_visible,
                'search': search or '',
            },
            'summary': {
                'direction_counts': direction_counts,
                'channel_counts': channel_counts,
            },
        }
    )



@bp.route('/api/v1/admin/communications/export', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_communications_export():
    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=5000)
        customer_visible = _parse_optional_bool_query(request.args.get('customer_visible'), 'customer_visible')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    limit = limit or 1000
    state = _normalize_offline_billing_state(request.args.get('state'), default='all')
    if state != 'all' and state not in OFFLINE_BILLING_STATES:
        return jsonify({'error': 'Invalid billing state filter', 'allowed_states': ['all'] + sorted(OFFLINE_BILLING_STATES)}), 400
    direction = str(request.args.get('direction') or '').strip().lower() or 'all'
    if direction != 'all' and direction not in COMMUNICATION_DIRECTIONS:
        return jsonify({'error': 'Invalid direction filter', 'allowed_directions': ['all'] + sorted(COMMUNICATION_DIRECTIONS)}), 400
    channel = str(request.args.get('channel') or '').strip().lower() or 'all'
    if channel != 'all' and channel not in COMMUNICATION_CHANNELS:
        return jsonify({'error': 'Invalid channel filter', 'allowed_channels': ['all'] + sorted(COMMUNICATION_CHANNELS)}), 400
    search = str(request.args.get('search') or '').strip() or None

    try:
        rows = (
            _build_admin_communications_query(
                state=state,
                direction=direction,
                channel=channel,
                customer_visible=customer_visible,
                search=search,
            )
            .order_by(
                WasteRequestCommunicationLog.occurred_at.desc(),
                WasteRequestCommunicationLog.id.desc(),
            )
            .limit(limit)
            .all()
        )
    except SQLAlchemyError:
        current_app.logger.exception('Failed to export communications report.')
        return jsonify({'error': 'Failed to export communications report'}), 500

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            'communication_id',
            'request_id',
            'request_status',
            'billing_state',
            'billing_reference',
            'direction',
            'channel',
            'customer_visible',
            'subject',
            'message',
            'outcome',
            'contact_name',
            'contact_email',
            'contact_phone',
            'occurred_at',
        ]
    )
    for row in rows:
        booking = db.session.get(WasteRemovalRequest, row.waste_removal_request_id)
        writer.writerow(
            [
                row.id,
                row.waste_removal_request_id,
                booking.status if booking else '',
                (booking.billing_state if booking and booking.billing_state else 'pending_offline_invoice'),
                booking.billing_reference if booking and booking.billing_reference else '',
                row.direction,
                row.channel,
                bool(row.customer_visible),
                row.subject or '',
                row.message or '',
                row.outcome or '',
                row.contact_name or '',
                row.contact_email or '',
                row.contact_phone or '',
                row.occurred_at.isoformat() + 'Z' if row.occurred_at else '',
            ]
        )

    filename = 'communications_report_{}.csv'.format(utcnow().strftime('%Y%m%d_%H%M%S'))
    response = Response(buffer.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename={}'.format(filename)
    return response
