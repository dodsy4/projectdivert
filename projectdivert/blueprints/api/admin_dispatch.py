"""Admin dispatch routes."""

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import SQLAlchemyError
from projectdivert.extensions import db
from projectdivert.models.user import User
from projectdivert.models.waste import WasteRemovalDispatchOffer, WasteRemovalRequest
from projectdivert.services.audit import record_audit_event
from projectdivert.services.auth import jwt_required
from projectdivert.services.compliance import _driver_dispatch_eligibility_error
from projectdivert.services.dispatch import _accept_dispatch_offer, DispatchQueueContext, _build_dispatch_request_timeline, _dispatch_incident_auto_assign_enabled, _dispatch_incident_auto_resolve_test_enabled, _dispatch_incident_severity, _dispatch_location_stale_minutes, _dispatch_pending_match_sla_minutes, _dispatch_summary_for_request, _dispatch_unassigned_match_sla_minutes, _get_dispatch_incident_context, _record_dispatch_incident_event, _run_dispatch_incident_maintenance, _serialize_dispatch_driver, _serialize_dispatch_offer, _serialize_waste_match, _serialize_waste_request, _serialize_waste_request_snapshot
from projectdivert.services.events import _publish_waste_request_event
from projectdivert.services.notifications import _notify_mobile_push_for_waste_event
from projectdivert.services.utils import _current_jwt_email, _current_jwt_user_id, _is_truthy, _normalize_email, _parse_optional_bool_query, _parse_optional_int_query, _to_int_or_none, utcnow

bp = Blueprint('api_admin_dispatch', __name__)



@bp.route('/api/v1/admin/dispatch/queue', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_dispatch_queue():
    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=500)
        offset = _parse_optional_int_query(request.args.get('offset'), 'offset', min_value=0)
        assigned = _parse_optional_bool_query(request.args.get('assigned'), 'assigned')
        incidents_only = _parse_optional_bool_query(request.args.get('incidents_only'), 'incidents_only')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    limit = limit or 50
    offset = offset or 0
    incidents_only = bool(incidents_only)
    incident_state = (str(request.args.get('incident_state') or '').strip().lower() or 'all')
    if incident_state not in {'all', 'open', 'acknowledged', 'resolved'}:
        return jsonify({'error': 'incident_state must be one of all, open, acknowledged, resolved'}), 400
    allowed_statuses = {
        'pending_match',
        'matched',
        'accepted',
        'rejected',
        'en_route',
        'arrived',
        'collected',
        'completed',
        'cancelled',
    }
    default_statuses = [
        'pending_match',
        'matched',
        'accepted',
        'en_route',
        'arrived',
        'collected',
    ]

    statuses_raw = str(request.args.get('statuses') or '').strip().lower()
    if statuses_raw:
        statuses = [part.strip() for part in statuses_raw.split(',') if part.strip()]
        invalid_statuses = sorted({status for status in statuses if status not in allowed_statuses})
        if invalid_statuses:
            return jsonify(
                {
                    'error': 'Invalid status value(s).',
                    'invalid_statuses': invalid_statuses,
                    'allowed_statuses': sorted(allowed_statuses),
                }
            ), 400
    else:
        statuses = default_statuses

    try:
        query = WasteRemovalRequest.query.filter(WasteRemovalRequest.status.in_(statuses))
        if assigned is True:
            query = query.filter(WasteRemovalRequest.assigned_driver_user_id.isnot(None))
        elif assigned is False:
            query = query.filter(WasteRemovalRequest.assigned_driver_user_id.is_(None))

        total = query.count()
        rows = (
            query.order_by(
                WasteRemovalRequest.created_at.asc(),
                WasteRemovalRequest.id.asc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
    except SQLAlchemyError:
        current_app.logger.exception('Failed to query dispatch queue.')
        return jsonify({'error': 'Failed to query dispatch queue'}), 500

    now = utcnow()
    items = []
    status_counts = {}
    incident_counts = {}
    incident_state_counts = {}
    incident_severity_counts = {}
    queue_context = DispatchQueueContext(rows)
    for booking in rows:
        status_key = (booking.status or '').strip().lower() or 'unknown'
        status_counts[status_key] = status_counts.get(status_key, 0) + 1

        queue_item = queue_context.serialize(booking, now=now)
        for flag in queue_item['incident_flags']:
            incident_counts[flag] = incident_counts.get(flag, 0) + 1
        state = (queue_item.get('incident') or {}).get('state')
        severity = (queue_item.get('incident') or {}).get('severity')
        if state:
            incident_state_counts[state] = incident_state_counts.get(state, 0) + 1
        if severity:
            incident_severity_counts[severity] = incident_severity_counts.get(severity, 0) + 1
        items.append(queue_item)

    if incidents_only:
        items = [item for item in items if item.get('incident_flags')]
    if incident_state != 'all':
        items = [item for item in items if (item.get('incident') or {}).get('state') == incident_state]

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
                'statuses': statuses,
                'assigned': assigned,
                'incidents_only': incidents_only,
                'incident_state': incident_state,
            },
            'sla_thresholds': {
                'pending_match_minutes': _dispatch_pending_match_sla_minutes(),
                'unassigned_match_minutes': _dispatch_unassigned_match_sla_minutes(),
                'location_stale_minutes': _dispatch_location_stale_minutes(),
            },
            'summary': {
                'status_counts': status_counts,
                'incident_counts': incident_counts,
                'incident_state_counts': incident_state_counts,
                'incident_severity_counts': incident_severity_counts,
            },
        }
    )



@bp.route('/api/v1/admin/dispatch/incidents', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_dispatch_incidents():
    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=500)
        offset = _parse_optional_int_query(request.args.get('offset'), 'offset', min_value=0)
        active_only = _parse_optional_bool_query(request.args.get('active_only'), 'active_only')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    limit = limit or 50
    offset = offset or 0
    active_only = True if active_only is None else bool(active_only)
    incident_state = (str(request.args.get('incident_state') or '').strip().lower() or 'all')
    if incident_state not in {'all', 'open', 'acknowledged', 'resolved'}:
        return jsonify({'error': 'incident_state must be one of all, open, acknowledged, resolved'}), 400

    allowed_statuses = {
        'pending_match',
        'matched',
        'accepted',
        'rejected',
        'en_route',
        'arrived',
        'collected',
        'completed',
        'cancelled',
    }
    statuses_raw = str(request.args.get('statuses') or '').strip().lower()
    if statuses_raw:
        statuses = [part.strip() for part in statuses_raw.split(',') if part.strip()]
        invalid_statuses = sorted({status for status in statuses if status not in allowed_statuses})
        if invalid_statuses:
            return jsonify(
                {
                    'error': 'Invalid status value(s).',
                    'invalid_statuses': invalid_statuses,
                    'allowed_statuses': sorted(allowed_statuses),
                }
            ), 400
    else:
        statuses = ['pending_match', 'matched', 'accepted', 'en_route', 'arrived', 'collected']

    try:
        query = WasteRemovalRequest.query.filter(WasteRemovalRequest.status.in_(statuses))
        rows = query.order_by(WasteRemovalRequest.created_at.asc(), WasteRemovalRequest.id.asc()).all()
    except SQLAlchemyError:
        current_app.logger.exception('Failed to query dispatch incidents.')
        return jsonify({'error': 'Failed to query dispatch incidents'}), 500

    now = utcnow()
    items = []
    for booking in rows:
        queue_item = _get_dispatch_incident_context(booking, now=now)
        has_flags = bool(queue_item.get('incident_flags'))
        state = (queue_item.get('incident') or {}).get('state')
        if active_only and (not has_flags or state == 'resolved'):
            continue
        if incident_state != 'all' and state != incident_state:
            continue
        items.append(queue_item)

    def _incident_sort_key(item):
        flags = item.get('incident_flags') or []
        incident_state_value = (item.get('incident') or {}).get('state') or ''
        state_rank = {'open': 0, 'acknowledged': 1, 'resolved': 2}.get(incident_state_value, 3)
        pickup_due = item.get('pickup_due_minutes')
        overdue_rank = pickup_due if isinstance(pickup_due, int) and pickup_due > 0 else -1
        age = item.get('age_minutes') or 0
        return (state_rank, -len(flags), -overdue_rank, -age, item.get('request', {}).get('id') or 0)

    items = sorted(items, key=_incident_sort_key)
    total = len(items)
    page_items = items[offset : offset + limit]
    return jsonify(
        {
            'items': page_items,
            'pagination': {
                'limit': limit,
                'offset': offset,
                'returned': len(page_items),
                'total': total,
                'has_more': (offset + len(page_items)) < total,
            },
            'filters': {
                'statuses': statuses,
                'active_only': active_only,
                'incident_state': incident_state,
            },
        }
    )



@bp.route('/api/v1/admin/dispatch/incidents/maintenance', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_dispatch_incident_maintenance():
    payload = request.get_json(silent=True) or {}
    raw_limit = payload.get('limit')
    raw_resolve_test_minutes = payload.get('resolve_test_minutes')
    raw_owner_admin_user_id = payload.get('owner_admin_user_id')
    owner_admin_email = _normalize_email(payload.get('owner_admin_email'))

    limit = _to_int_or_none(raw_limit)
    resolve_test_minutes = _to_int_or_none(raw_resolve_test_minutes)
    owner_admin_user_id = _to_int_or_none(raw_owner_admin_user_id)

    if raw_limit not in (None, '') and limit is None:
        return jsonify({'error': 'limit must be an integer >= 1'}), 400
    if limit is not None and limit < 1:
        return jsonify({'error': 'limit must be an integer >= 1'}), 400
    if raw_resolve_test_minutes not in (None, '') and resolve_test_minutes is None:
        return jsonify({'error': 'resolve_test_minutes must be an integer >= 1'}), 400
    if resolve_test_minutes is not None and resolve_test_minutes < 1:
        return jsonify({'error': 'resolve_test_minutes must be an integer >= 1'}), 400
    if raw_owner_admin_user_id not in (None, '') and owner_admin_user_id is None:
        return jsonify({'error': 'owner_admin_user_id must be an integer'}), 400

    if 'auto_assign' in payload:
        auto_assign = _is_truthy(payload.get('auto_assign'))
    else:
        auto_assign = _dispatch_incident_auto_assign_enabled()

    if 'auto_resolve_test' in payload:
        auto_resolve_test = _is_truthy(payload.get('auto_resolve_test'))
    else:
        auto_resolve_test = _dispatch_incident_auto_resolve_test_enabled()

    dry_run = _is_truthy(payload.get('dry_run'))
    if not auto_assign and not auto_resolve_test:
        return (
            jsonify(
                {
                    'error': 'No maintenance actions enabled.',
                    'hint': 'Set auto_assign and/or auto_resolve_test to true.',
                }
            ),
            400,
        )

    try:
        result = _run_dispatch_incident_maintenance(
            auto_assign=auto_assign,
            auto_resolve_test=auto_resolve_test,
            resolve_test_minutes=resolve_test_minutes,
            owner_admin_user_id=owner_admin_user_id,
            owner_admin_email=owner_admin_email,
            limit=limit,
            dry_run=dry_run,
            actor_user_id=_current_jwt_user_id(),
            actor_email=_current_jwt_email(),
            source='api_admin_dispatch_incident_maintenance',
        )
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Dispatch incident maintenance failed.')
        return jsonify({'error': 'Failed to run dispatch incident maintenance'}), 500

    return jsonify(result)



@bp.route('/api/v1/admin/dispatch/incidents/<int:request_id>/ack', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_dispatch_incident_ack(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404

    payload = request.get_json(silent=True) or {}
    notes = (str(payload.get('notes') or '').strip()[:1000] or None)
    now = utcnow()
    queue_item = _get_dispatch_incident_context(booking, now=now)
    flags = queue_item.get('incident_flags') or []
    if not flags:
        return jsonify({'error': 'No active incident to acknowledge'}), 409

    booking.incident_state = 'acknowledged'
    booking.incident_severity = _dispatch_incident_severity(flags)
    booking.incident_owner_admin_user_id = _current_jwt_user_id()
    booking.incident_acknowledged_at = now
    booking.incident_resolved_at = None
    booking.incident_updated_at = now
    if notes:
        existing = (booking.incident_notes or '').strip()
        prefix = '[{} ACK] '.format(now.isoformat())
        booking.incident_notes = (existing + '\n' if existing else '') + prefix + notes

    _record_dispatch_incident_event(
        booking.id,
        event_type='incident_ack',
        actor_user_id=_current_jwt_user_id(),
        actor_email=_current_jwt_email(),
        source='api_admin_dispatch',
        details={
            'incident_state': booking.incident_state,
            'incident_severity': booking.incident_severity,
            'notes': notes,
            'incident_flags': flags,
        },
        occurred_at=now,
    )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to acknowledge incident for request %s.', request_id)
        return jsonify({'error': 'Failed to acknowledge incident'}), 500

    metadata = {
        'action': 'ack',
        'admin_user_id': _current_jwt_user_id(),
        'incident_state': booking.incident_state,
        'incident_severity': booking.incident_severity,
        'notes': notes,
    }
    _publish_waste_request_event(
        booking.id,
        'admin_dispatch_incident_ack',
        payload=_serialize_waste_request_snapshot(booking),
        metadata=metadata,
    )
    _notify_mobile_push_for_waste_event(
        booking,
        'admin_dispatch_incident_ack',
        metadata=metadata,
    )
    refreshed_item = _get_dispatch_incident_context(booking)
    return jsonify(
        {
            'updated': True,
            'request': _serialize_waste_request_snapshot(booking),
            'incident': refreshed_item.get('incident'),
            'incident_flags': refreshed_item.get('incident_flags'),
        }
    )



@bp.route('/api/v1/admin/dispatch/incidents/<int:request_id>/resolve', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_dispatch_incident_resolve(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404

    payload = request.get_json(silent=True) or {}
    notes = (str(payload.get('notes') or '').strip()[:1000] or None)
    now = utcnow()
    queue_item = _get_dispatch_incident_context(booking, now=now)
    flags = queue_item.get('incident_flags') or []

    booking.incident_state = 'resolved'
    booking.incident_owner_admin_user_id = _current_jwt_user_id()
    booking.incident_resolved_at = now
    booking.incident_updated_at = now
    if not booking.incident_acknowledged_at:
        booking.incident_acknowledged_at = now
    if not flags:
        booking.incident_severity = None
    if notes:
        existing = (booking.incident_notes or '').strip()
        prefix = '[{} RESOLVE] '.format(now.isoformat())
        booking.incident_notes = (existing + '\n' if existing else '') + prefix + notes

    _record_dispatch_incident_event(
        booking.id,
        event_type='incident_resolve',
        actor_user_id=_current_jwt_user_id(),
        actor_email=_current_jwt_email(),
        source='api_admin_dispatch',
        details={
            'incident_state': booking.incident_state,
            'incident_severity': booking.incident_severity,
            'notes': notes,
            'incident_flags': flags,
        },
        occurred_at=now,
    )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to resolve incident for request %s.', request_id)
        return jsonify({'error': 'Failed to resolve incident'}), 500

    metadata = {
        'action': 'resolve',
        'admin_user_id': _current_jwt_user_id(),
        'incident_state': booking.incident_state,
        'incident_severity': booking.incident_severity,
        'notes': notes,
    }
    _publish_waste_request_event(
        booking.id,
        'admin_dispatch_incident_resolve',
        payload=_serialize_waste_request_snapshot(booking),
        metadata=metadata,
    )
    _notify_mobile_push_for_waste_event(
        booking,
        'admin_dispatch_incident_resolve',
        metadata=metadata,
    )
    refreshed_item = _get_dispatch_incident_context(booking)
    return jsonify(
        {
            'updated': True,
            'request': _serialize_waste_request_snapshot(booking),
            'incident': refreshed_item.get('incident'),
            'incident_flags': refreshed_item.get('incident_flags'),
        }
    )



@bp.route('/api/v1/admin/dispatch/incidents/<int:request_id>/owner', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_dispatch_incident_owner(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404

    payload = request.get_json(silent=True) or {}
    if 'owner_admin_user_id' not in payload:
        return jsonify({'error': 'owner_admin_user_id is required (set null to unassign)'}), 400

    raw_owner_user_id = payload.get('owner_admin_user_id')
    if raw_owner_user_id in (None, ''):
        new_owner_user_id = None
        owner_user = None
    else:
        new_owner_user_id = _to_int_or_none(raw_owner_user_id)
        if new_owner_user_id is None:
            return jsonify({'error': 'owner_admin_user_id must be an integer or null'}), 400
        owner_user = db.session.get(User, new_owner_user_id)
        if not owner_user:
            return jsonify({'error': 'Owner admin user not found'}), 404
        if (owner_user.role or '').strip().lower() != 'admin':
            return jsonify({'error': 'Selected user is not an admin'}), 400
        if not owner_user.is_active_user:
            return jsonify({'error': 'Selected admin user is inactive'}), 409

    notes = (str(payload.get('notes') or '').strip()[:1000] or None)
    previous_owner_user_id = booking.incident_owner_admin_user_id
    if previous_owner_user_id == new_owner_user_id:
        queue_item = _get_dispatch_incident_context(booking)
        return jsonify(
            {
                'updated': False,
                'message': 'No owner change',
                'request': _serialize_waste_request_snapshot(booking),
                'incident': queue_item.get('incident'),
                'incident_flags': queue_item.get('incident_flags'),
                'previous_owner_admin_user_id': previous_owner_user_id,
                'owner_admin_user_id': booking.incident_owner_admin_user_id,
            }
        )

    now = utcnow()
    booking.incident_owner_admin_user_id = new_owner_user_id
    booking.incident_updated_at = now
    if notes:
        existing = (booking.incident_notes or '').strip()
        prefix = '[{} OWNER] '.format(now.isoformat())
        booking.incident_notes = (existing + '\n' if existing else '') + prefix + notes

    _record_dispatch_incident_event(
        booking.id,
        event_type='incident_owner_reassign',
        actor_user_id=_current_jwt_user_id(),
        actor_email=_current_jwt_email(),
        source='api_admin_dispatch',
        details={
            'previous_owner_admin_user_id': previous_owner_user_id,
            'owner_admin_user_id': new_owner_user_id,
            'notes': notes,
        },
        occurred_at=now,
    )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to update incident owner for request %s.', request_id)
        return jsonify({'error': 'Failed to update incident owner'}), 500

    metadata = {
        'action': 'owner_reassign',
        'previous_owner_admin_user_id': previous_owner_user_id,
        'owner_admin_user_id': booking.incident_owner_admin_user_id,
        'admin_user_id': _current_jwt_user_id(),
        'notes': notes,
    }
    _publish_waste_request_event(
        booking.id,
        'admin_dispatch_incident_owner_reassign',
        payload=_serialize_waste_request_snapshot(booking),
        metadata=metadata,
    )
    _notify_mobile_push_for_waste_event(
        booking,
        'admin_dispatch_incident_owner_reassign',
        metadata=metadata,
    )
    refreshed_item = _get_dispatch_incident_context(booking)
    return jsonify(
        {
            'updated': True,
            'request': _serialize_waste_request_snapshot(booking),
            'incident': refreshed_item.get('incident'),
            'incident_flags': refreshed_item.get('incident_flags'),
            'previous_owner_admin_user_id': previous_owner_user_id,
            'owner_admin_user_id': booking.incident_owner_admin_user_id,
        }
    )



@bp.route('/api/v1/admin/dispatch/telemetry', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_dispatch_telemetry():
    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=200)
        assigned = _parse_optional_bool_query(request.args.get('assigned'), 'assigned')
        incidents_only = _parse_optional_bool_query(request.args.get('incidents_only'), 'incidents_only')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    limit = limit or 50
    incidents_only = bool(incidents_only)
    incident_state = (str(request.args.get('incident_state') or '').strip().lower() or 'all')
    if incident_state not in {'all', 'open', 'acknowledged', 'resolved'}:
        return jsonify({'error': 'incident_state must be one of all, open, acknowledged, resolved'}), 400
    allowed_statuses = {
        'pending_match',
        'matched',
        'accepted',
        'rejected',
        'en_route',
        'arrived',
        'collected',
        'completed',
        'cancelled',
    }
    default_statuses = ['pending_match', 'matched', 'accepted', 'en_route', 'arrived', 'collected']

    statuses_raw = str(request.args.get('statuses') or '').strip().lower()
    if statuses_raw:
        statuses = [part.strip() for part in statuses_raw.split(',') if part.strip()]
        invalid_statuses = sorted({status for status in statuses if status not in allowed_statuses})
        if invalid_statuses:
            return jsonify(
                {
                    'error': 'Invalid status value(s).',
                    'invalid_statuses': invalid_statuses,
                    'allowed_statuses': sorted(allowed_statuses),
                }
            ), 400
    else:
        statuses = list(default_statuses)

    try:
        query = WasteRemovalRequest.query.filter(WasteRemovalRequest.status.in_(statuses))
        if assigned is True:
            query = query.filter(WasteRemovalRequest.assigned_driver_user_id.isnot(None))
        elif assigned is False:
            query = query.filter(WasteRemovalRequest.assigned_driver_user_id.is_(None))
        rows = query.order_by(WasteRemovalRequest.created_at.asc(), WasteRemovalRequest.id.asc()).all()
    except SQLAlchemyError:
        current_app.logger.exception('Failed to query dispatch telemetry.')
        return jsonify({'error': 'Failed to query dispatch telemetry'}), 500

    now = utcnow()
    items = []
    status_counts = {}
    incident_counts = {}
    incident_state_counts = {}
    incident_severity_counts = {}
    ack_latency_values = []
    resolve_latency_values = []
    queue_context = DispatchQueueContext(rows)
    for booking in rows:
        status_key = (booking.status or '').strip().lower() or 'unknown'
        status_counts[status_key] = status_counts.get(status_key, 0) + 1

        queue_item = queue_context.serialize(booking, now=now)
        for flag in queue_item.get('incident_flags') or []:
            incident_counts[flag] = incident_counts.get(flag, 0) + 1
        incident_info = queue_item.get('incident') or {}
        state = incident_info.get('state')
        severity = incident_info.get('severity')
        if state:
            incident_state_counts[state] = incident_state_counts.get(state, 0) + 1
        if severity:
            incident_severity_counts[severity] = incident_severity_counts.get(severity, 0) + 1
        if booking.incident_acknowledged_at and booking.created_at:
            ack_latency_values.append(
                max(0, int((booking.incident_acknowledged_at - booking.created_at).total_seconds() // 60))
            )
        if booking.incident_resolved_at and booking.created_at:
            resolve_latency_values.append(
                max(0, int((booking.incident_resolved_at - booking.created_at).total_seconds() // 60))
            )
        items.append(queue_item)

    if incidents_only:
        items = [item for item in items if item.get('incident_flags')]
    if incident_state != 'all':
        items = [item for item in items if (item.get('incident') or {}).get('state') == incident_state]

    def _incident_sort_key(item):
        flags = item.get('incident_flags') or []
        pickup_due = item.get('pickup_due_minutes')
        overdue_rank = pickup_due if isinstance(pickup_due, int) and pickup_due > 0 else -1
        age = item.get('age_minutes') or 0
        return (-len(flags), -overdue_rank, -age, item.get('request', {}).get('id') or 0)

    items = sorted(items, key=_incident_sort_key)
    requests_overdue = sum(
        1
        for item in items
        if isinstance(item.get('pickup_due_minutes'), int) and item['pickup_due_minutes'] > 0
    )
    requests_with_incidents = len([item for item in items if item.get('incident_flags')])
    incident_total = sum(len(item.get('incident_flags') or []) for item in items)

    return jsonify(
        {
            'items': items[:limit],
            'summary': {
                'total_rows': len(items),
                'requests_with_incidents': requests_with_incidents,
                'incident_total': incident_total,
                'requests_overdue': requests_overdue,
                'status_counts': status_counts,
                'incident_counts': incident_counts,
                'incident_state_counts': incident_state_counts,
                'incident_severity_counts': incident_severity_counts,
                'ack_latency_minutes_avg': (
                    round(sum(ack_latency_values) / len(ack_latency_values), 1) if ack_latency_values else None
                ),
                'resolve_latency_minutes_avg': (
                    round(sum(resolve_latency_values) / len(resolve_latency_values), 1)
                    if resolve_latency_values
                    else None
                ),
            },
            'filters': {
                'statuses': statuses,
                'assigned': assigned,
                'incidents_only': incidents_only,
                'incident_state': incident_state,
                'limit': limit,
            },
            'sla_thresholds': {
                'pending_match_minutes': _dispatch_pending_match_sla_minutes(),
                'unassigned_match_minutes': _dispatch_unassigned_match_sla_minutes(),
                'location_stale_minutes': _dispatch_location_stale_minutes(),
            },
        }
    )



@bp.route('/api/v1/admin/waste-requests/<int:request_id>/dispatch/override', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_dispatch_override(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404

    payload = request.get_json(silent=True) or {}
    if 'driver_user_id' not in payload:
        return jsonify({'error': 'driver_user_id is required (set null to unassign)'}), 400

    raw_driver_user_id = payload.get('driver_user_id')
    if raw_driver_user_id in (None, ''):
        new_driver_user_id = None
        driver = None
    else:
        new_driver_user_id = _to_int_or_none(raw_driver_user_id)
        if new_driver_user_id is None:
            return jsonify({'error': 'driver_user_id must be an integer or null'}), 400
        driver = db.session.get(User, new_driver_user_id)
        if not driver:
            return jsonify({'error': 'Driver not found'}), 404
        if (driver.role or '').strip().lower() != 'driver':
            return jsonify({'error': 'Selected user is not a driver'}), 400
        if not driver.is_active_user:
            return jsonify({'error': 'Selected driver is inactive'}), 409
        eligibility_error, missing_types = _driver_dispatch_eligibility_error(new_driver_user_id)
        if eligibility_error:
            return jsonify(
                {
                    'error': eligibility_error,
                    'missing_document_types': missing_types,
                }
            ), 409

    reason = (str(payload.get('reason') or '').strip()[:255] or None)
    previous_driver_user_id = booking.assigned_driver_user_id
    if previous_driver_user_id == new_driver_user_id:
        current_driver = db.session.get(User, booking.assigned_driver_user_id) if booking.assigned_driver_user_id else None
        return jsonify(
            {
                'updated': False,
                'message': 'No assignment change',
                'request': _serialize_waste_request_snapshot(booking),
                'driver': _serialize_dispatch_driver(current_driver),
                'previous_assigned_driver_user_id': previous_driver_user_id,
                'assigned_driver_user_id': booking.assigned_driver_user_id,
            }
        )

    now = utcnow()
    booking.assigned_driver_user_id = new_driver_user_id
    _record_dispatch_incident_event(
        booking.id,
        event_type='dispatch_override',
        actor_user_id=_current_jwt_user_id(),
        actor_email=_current_jwt_email(),
        source='api_admin_dispatch',
        details={
            'previous_assigned_driver_user_id': previous_driver_user_id,
            'assigned_driver_user_id': new_driver_user_id,
            'reason': reason,
        },
        occurred_at=now,
    )
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed admin dispatch override for request %s.', request_id)
        return jsonify({'error': 'Failed to update dispatch assignment'}), 500

    metadata = {
        'previous_assigned_driver_user_id': previous_driver_user_id,
        'assigned_driver_user_id': booking.assigned_driver_user_id,
        'admin_user_id': _current_jwt_user_id(),
        'reason': reason,
    }
    record_audit_event(
        action='dispatch.override',
        entity_type='waste_request',
        entity_id=booking.id,
        summary='Admin reassigned dispatch driver' + (' ({})'.format(reason) if reason else ''),
        changes={'assigned_driver_user_id': [previous_driver_user_id, booking.assigned_driver_user_id]},
        status_code=200,
    )
    _publish_waste_request_event(
        booking.id,
        'admin_dispatch_override',
        payload=_serialize_waste_request_snapshot(booking),
        metadata=metadata,
    )
    _notify_mobile_push_for_waste_event(
        booking,
        'admin_dispatch_override',
        metadata=metadata,
    )

    assigned_driver = db.session.get(User, booking.assigned_driver_user_id) if booking.assigned_driver_user_id else None
    return jsonify(
        {
            'updated': True,
            'request': _serialize_waste_request_snapshot(booking),
            'driver': _serialize_dispatch_driver(assigned_driver),
            'previous_assigned_driver_user_id': previous_driver_user_id,
            'assigned_driver_user_id': booking.assigned_driver_user_id,
            'reason': reason,
        }
    )



@bp.route('/api/v1/admin/waste-requests/<int:request_id>/timeline', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_waste_request_timeline(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404

    try:
        include_actor_auth = _parse_optional_bool_query(
            request.args.get('include_actor_auth'),
            'include_actor_auth',
        )
        auth_window_hours = _parse_optional_int_query(
            request.args.get('auth_window_hours'),
            'auth_window_hours',
            min_value=1,
            max_value=24 * 30,
        )
        limit = _parse_optional_int_query(
            request.args.get('limit'),
            'limit',
            min_value=1,
            max_value=500,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    include_actor_auth = True if include_actor_auth is None else bool(include_actor_auth)
    auth_window_hours = auth_window_hours or 168
    limit = limit or 200

    timeline_rows, timeline_summary = _build_dispatch_request_timeline(
        booking,
        include_actor_auth=include_actor_auth,
        auth_window_hours=auth_window_hours,
        limit=limit,
    )
    return jsonify(
        {
            'request': _serialize_waste_request_snapshot(booking),
            'timeline': timeline_rows,
            'summary': timeline_summary,
            'filters': {
                'include_actor_auth': include_actor_auth,
                'auth_window_hours': auth_window_hours,
                'limit': limit,
            },
        }
    )



@bp.route('/api/v1/waste-requests/<int:request_id>/dispatch/accept', methods=['POST'])
@jwt_required(roles={'driver'})
def api_accept_dispatch_offer(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404

    payload = request.get_json(silent=True) or {}
    offer_token = str(payload.get('offer_token') or '').strip()

    if offer_token:
        # A provider following the link from their notification email, which
        # identifies the specific offer that was sent to them.
        offer = WasteRemovalDispatchOffer.query.filter_by(
            waste_removal_request_id=booking.id,
            offer_token=offer_token,
        ).first()
        if not offer:
            return jsonify({'error': 'Dispatch offer not found'}), 404
    else:
        # A driver claiming from the job board, where there is no token to
        # quote -- the board lists the request, not the offer. Take the best
        # ranked offer still open. Requiring a token here made the claim button
        # in the web dashboard fail with a 400 every time.
        offer = (
            WasteRemovalDispatchOffer.query
            .filter_by(waste_removal_request_id=booking.id, status='offered')
            .order_by(
                WasteRemovalDispatchOffer.offer_rank.asc(),
                WasteRemovalDispatchOffer.id.asc(),
            )
            .first()
        )
        if not offer:
            return jsonify({'error': 'No open dispatch offer for this request'}), 409

    driver_user_id = _current_jwt_user_id()
    if driver_user_id is None:
        return jsonify({'error': 'Token missing valid user id claim'}), 401
    eligibility_error, missing_types = _driver_dispatch_eligibility_error(driver_user_id)
    if eligibility_error:
        return jsonify(
            {
                'error': eligibility_error,
                'missing_document_types': missing_types,
            }
        ), 409

    match_row, outcome = _accept_dispatch_offer(
        booking,
        offer,
        assigned_driver_user_id=driver_user_id,
    )
    if outcome == 'accepted':
        _publish_waste_request_event(
            booking.id,
            'dispatch_offer_accepted',
            payload=_serialize_waste_request_snapshot(booking),
            metadata={
                'accepted_offer_id': offer.id,
                'accepted_offer_rank': offer.offer_rank,
                'assigned_driver_user_id': booking.assigned_driver_user_id,
            },
        )
        _notify_mobile_push_for_waste_event(
            booking,
            'dispatch_offer_accepted',
            metadata={
                'accepted_offer_id': offer.id,
                'accepted_offer_rank': offer.offer_rank,
            },
        )
        return jsonify(
            {
                'request': _serialize_waste_request(booking),
                'match': _serialize_waste_match(match_row),
                'accepted_offer': _serialize_dispatch_offer(offer),
                'dispatch': _dispatch_summary_for_request(booking.id),
            }
        )
    if outcome == 'already_matched':
        return (
            jsonify(
                {
                    'error': 'Request already matched',
                    'match': _serialize_waste_match(match_row),
                    'dispatch': _dispatch_summary_for_request(booking.id),
                }
            ),
            409,
        )
    if outcome == 'driver_mismatch':
        return jsonify({'error': 'Request is assigned to a different driver'}), 409
    if outcome == 'offer_unavailable':
        return (
            jsonify(
                {
                    'error': 'Dispatch offer is no longer available',
                    'offer': _serialize_dispatch_offer(offer),
                }
            ),
            409,
        )
    return jsonify({'error': 'Invalid dispatch offer'}), 400
