"""Admin routes."""

from datetime import datetime
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import func
from flask_login import current_user, login_required
from projectdivert.extensions import db
from projectdivert.models.audit import AuditEvent
from projectdivert.models.user import User
from projectdivert.models.waste import WasteRemovalRequest, WasteRemovalVehicleLocation
from projectdivert.services.audit import _build_audit_events_query, _serialize_audit_event
from projectdivert.services.auth import _current_user_is_admin
from projectdivert.services.compliance import _driver_dispatch_eligibility_error
from projectdivert.services.dispatch import _build_dispatch_request_timeline, _dispatch_incident_severity, _dispatch_location_stale_minutes, _dispatch_pending_match_sla_minutes, _dispatch_unassigned_match_sla_minutes, _get_dispatch_incident_context, _record_dispatch_incident_event, _serialize_dispatch_driver, _serialize_dispatch_queue_item, _serialize_waste_request, _serialize_waste_request_snapshot
from projectdivert.services.events import _publish_waste_request_event
from projectdivert.services.notifications import _notify_mobile_push_for_waste_event
from projectdivert.services.utils import _parse_optional_bool_query, _parse_optional_int_query, _to_int_or_none

bp = Blueprint('admin', __name__)



@bp.route('/admin/dispatch', methods=['GET'])
@login_required
def admin_dispatch_board():
    if not _current_user_is_admin():
        flash('Admin access is required.')
        return redirect('/login'), 403

    status_options = [
        'pending_match',
        'matched',
        'accepted',
        'en_route',
        'arrived',
        'collected',
        'completed',
        'cancelled',
    ]
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
        selected_statuses = [part.strip() for part in statuses_raw.split(',') if part.strip()]
        invalid_statuses = sorted({status for status in selected_statuses if status not in status_options})
        if invalid_statuses:
            flash('Ignoring invalid statuses: {}.'.format(', '.join(invalid_statuses)))
            selected_statuses = [status for status in selected_statuses if status in status_options]
    else:
        selected_statuses = list(default_statuses)
    if not selected_statuses:
        selected_statuses = list(default_statuses)

    try:
        assigned_filter = _parse_optional_bool_query(request.args.get('assigned'), 'assigned')
        incidents_only = bool(_parse_optional_bool_query(request.args.get('incidents_only'), 'incidents_only'))
        incident_state_filter = (
            str(request.args.get('incident_state') or '').strip().lower() or 'all'
        )
        if incident_state_filter not in {'all', 'open', 'acknowledged', 'resolved'}:
            raise ValueError('incident_state must be one of all, open, acknowledged, resolved')
    except ValueError:
        flash('Invalid filters supplied. Showing default queue.')
        assigned_filter = None
        incidents_only = False
        incident_state_filter = 'all'

    drivers = (
        User.query.filter(func.lower(User.role) == 'driver', User.is_active_user.is_(True))
        .order_by(func.lower(func.coalesce(User.name, User.email)).asc(), User.id.asc())
        .all()
    )
    admins = (
        User.query.filter(func.lower(User.role) == 'admin', User.is_active_user.is_(True))
        .order_by(func.lower(func.coalesce(User.name, User.email)).asc(), User.id.asc())
        .all()
    )

    query = WasteRemovalRequest.query.filter(WasteRemovalRequest.status.in_(selected_statuses))
    if assigned_filter is True:
        query = query.filter(WasteRemovalRequest.assigned_driver_user_id.isnot(None))
    elif assigned_filter is False:
        query = query.filter(WasteRemovalRequest.assigned_driver_user_id.is_(None))

    rows = query.order_by(WasteRemovalRequest.created_at.asc(), WasteRemovalRequest.id.asc()).all()

    now = datetime.utcnow()
    queue_items = []
    status_counts = {}
    incident_counts = {}
    for booking in rows:
        status_key = (booking.status or '').strip().lower() or 'unknown'
        status_counts[status_key] = status_counts.get(status_key, 0) + 1
        driver = db.session.get(User, booking.assigned_driver_user_id) if booking.assigned_driver_user_id else None
        latest_location = (
            WasteRemovalVehicleLocation.query.filter_by(waste_removal_request_id=booking.id)
            .order_by(WasteRemovalVehicleLocation.recorded_at.desc(), WasteRemovalVehicleLocation.id.desc())
            .first()
        )
        queue_item = (
            _serialize_dispatch_queue_item(
                booking,
                driver=driver,
                latest_location=latest_location,
                now=now,
            )
        )
        for flag in queue_item.get('incident_flags') or []:
            incident_counts[flag] = incident_counts.get(flag, 0) + 1
        queue_items.append(queue_item)
    if incidents_only:
        queue_items = [item for item in queue_items if item.get('incident_flags')]
    if incident_state_filter != 'all':
        queue_items = [
            item
            for item in queue_items
            if (item.get('incident') or {}).get('state') == incident_state_filter
        ]

    # Prioritize incident rows for triage.
    def _incident_sort_key(item):
        flags = item.get('incident_flags') or []
        pickup_due = item.get('pickup_due_minutes')
        overdue_rank = pickup_due if isinstance(pickup_due, int) and pickup_due > 0 else -1
        age = item.get('age_minutes') or 0
        return (-len(flags), -overdue_rank, -age, item.get('request', {}).get('id') or 0)

    queue_items = sorted(queue_items, key=_incident_sort_key)
    incident_rows = [item for item in queue_items if item.get('incident_flags')][:20]
    requests_overdue = sum(
        1
        for item in queue_items
        if isinstance(item.get('pickup_due_minutes'), int) and item['pickup_due_minutes'] > 0
    )
    requests_with_incidents = len([item for item in queue_items if item.get('incident_flags')])
    incident_total = sum(len(item.get('incident_flags') or []) for item in queue_items)
    incident_state_counts = {}
    incident_severity_counts = {}
    for item in queue_items:
        state = (item.get('incident') or {}).get('state')
        severity = (item.get('incident') or {}).get('severity')
        if state:
            incident_state_counts[state] = incident_state_counts.get(state, 0) + 1
        if severity:
            incident_severity_counts[severity] = incident_severity_counts.get(severity, 0) + 1

    return render_template(
        'pages/admin_dispatch.html',
        queue_items=queue_items,
        incident_rows=incident_rows,
        summary={
            'total_rows': len(queue_items),
            'requests_with_incidents': requests_with_incidents,
            'incident_total': incident_total,
            'requests_overdue': requests_overdue,
            'status_counts': status_counts,
            'incident_counts': incident_counts,
            'incident_state_counts': incident_state_counts,
            'incident_severity_counts': incident_severity_counts,
        },
        drivers=[_serialize_dispatch_driver(row) for row in drivers],
        admins=[_serialize_dispatch_driver(row) for row in admins],
        statuses=selected_statuses,
        status_options=status_options,
        assigned_filter=assigned_filter,
        incidents_only=incidents_only,
        incident_state_filter=incident_state_filter,
        filter_query_string=(request.query_string or b'').decode('utf-8'),
        sla_thresholds={
            'pending_match_minutes': _dispatch_pending_match_sla_minutes(),
            'unassigned_match_minutes': _dispatch_unassigned_match_sla_minutes(),
            'location_stale_minutes': _dispatch_location_stale_minutes(),
        },
    )



@bp.route('/admin/dispatch/override', methods=['POST'])
@login_required
def admin_dispatch_override_form():
    if not _current_user_is_admin():
        flash('Admin access is required.')
        return redirect('/login'), 403

    request_id = _to_int_or_none(request.form.get('request_id'))
    return_query = str(request.form.get('return_query') or '').strip()
    redirect_target = url_for('admin.admin_dispatch_board')
    if return_query:
        redirect_target = '{}?{}'.format(redirect_target, return_query.lstrip('?'))

    if request_id is None:
        flash('request_id is required.')
        return redirect(redirect_target)

    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        flash('Waste request not found.')
        return redirect(redirect_target)

    raw_driver_user_id = str(request.form.get('driver_user_id') or '').strip()
    if not raw_driver_user_id:
        new_driver_user_id = None
        driver = None
    else:
        new_driver_user_id = _to_int_or_none(raw_driver_user_id)
        if new_driver_user_id is None:
            flash('driver_user_id must be an integer or empty.')
            return redirect(redirect_target)
        driver = db.session.get(User, new_driver_user_id)
        if not driver:
            flash('Driver not found.')
            return redirect(redirect_target)
        if (driver.role or '').strip().lower() != 'driver':
            flash('Selected user is not a driver.')
            return redirect(redirect_target)
        if not driver.is_active_user:
            flash('Selected driver is inactive.')
            return redirect(redirect_target)
        eligibility_error, missing_types = _driver_dispatch_eligibility_error(new_driver_user_id)
        if eligibility_error:
            flash(
                '{}: {}'.format(
                    eligibility_error,
                    ', '.join(missing_types) if missing_types else 'missing required records',
                )
            )
            return redirect(redirect_target)

    previous_driver_user_id = booking.assigned_driver_user_id
    if previous_driver_user_id == new_driver_user_id:
        flash('No assignment change.')
        return redirect(redirect_target)

    reason = (str(request.form.get('reason') or '').strip()[:255] or None)
    now = datetime.utcnow()
    booking.assigned_driver_user_id = new_driver_user_id
    _record_dispatch_incident_event(
        booking.id,
        event_type='dispatch_override',
        actor_user_id=getattr(current_user, 'id', None),
        actor_email=getattr(current_user, 'email', None),
        source='web_admin_dispatch',
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
        current_app.logger.exception('Failed admin dispatch override form for request %s.', request_id)
        flash('Failed to update dispatch assignment.')
        return redirect(redirect_target)

    metadata = {
        'previous_assigned_driver_user_id': previous_driver_user_id,
        'assigned_driver_user_id': booking.assigned_driver_user_id,
        'admin_user_id': getattr(current_user, 'id', None),
        'reason': reason,
    }
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

    if booking.assigned_driver_user_id:
        flash('Driver assignment updated for request #{}.'.format(booking.id))
    else:
        flash('Driver assignment removed for request #{}.'.format(booking.id))
    return redirect(redirect_target)



@bp.route('/admin/dispatch/timeline/<int:request_id>', methods=['GET'])
@login_required
def admin_dispatch_timeline(request_id):
    if not _current_user_is_admin():
        flash('Admin access is required.')
        return redirect('/login'), 403

    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        flash('Waste request not found.')
        return redirect(url_for('admin.admin_dispatch_board'))

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
    except ValueError:
        flash('Invalid timeline filters. Showing defaults.')
        include_actor_auth = None
        auth_window_hours = None
        limit = None

    include_actor_auth = True if include_actor_auth is None else bool(include_actor_auth)
    auth_window_hours = auth_window_hours or 168
    limit = limit or 200
    timeline_rows, timeline_summary = _build_dispatch_request_timeline(
        booking,
        include_actor_auth=include_actor_auth,
        auth_window_hours=auth_window_hours,
        limit=limit,
    )
    return render_template(
        'pages/admin_dispatch_timeline.html',
        booking=_serialize_waste_request(booking),
        timeline_rows=timeline_rows,
        timeline_summary=timeline_summary,
        filters={
            'include_actor_auth': include_actor_auth,
            'auth_window_hours': auth_window_hours,
            'limit': limit,
        },
    )



@bp.route('/admin/dispatch/incident', methods=['POST'])
@login_required
def admin_dispatch_incident_form():
    if not _current_user_is_admin():
        flash('Admin access is required.')
        return redirect('/login'), 403

    request_id = _to_int_or_none(request.form.get('request_id'))
    action = (str(request.form.get('action') or '').strip().lower() or '')
    notes = (str(request.form.get('notes') or '').strip()[:1000] or None)
    return_query = str(request.form.get('return_query') or '').strip()
    redirect_target = url_for('admin.admin_dispatch_board')
    if return_query:
        redirect_target = '{}?{}'.format(redirect_target, return_query.lstrip('?'))

    if action not in {'ack', 'resolve'}:
        flash('Unsupported incident action.')
        return redirect(redirect_target)
    if request_id is None:
        flash('request_id is required.')
        return redirect(redirect_target)

    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        flash('Waste request not found.')
        return redirect(redirect_target)

    queue_item = _get_dispatch_incident_context(booking)
    flags = queue_item.get('incident_flags') or []
    if action == 'ack' and not flags:
        flash('No active incident to acknowledge for request #{}.'.format(request_id))
        return redirect(redirect_target)

    now = datetime.utcnow()
    if action == 'ack':
        booking.incident_state = 'acknowledged'
        booking.incident_severity = _dispatch_incident_severity(flags)
        booking.incident_owner_admin_user_id = getattr(current_user, 'id', None)
        booking.incident_acknowledged_at = now
        booking.incident_resolved_at = None
        booking.incident_updated_at = now
    else:
        booking.incident_state = 'resolved'
        booking.incident_owner_admin_user_id = getattr(current_user, 'id', None)
        booking.incident_resolved_at = now
        booking.incident_updated_at = now
        if not booking.incident_acknowledged_at:
            booking.incident_acknowledged_at = now
        if not flags:
            booking.incident_severity = None

    if notes:
        existing = (booking.incident_notes or '').strip()
        prefix = '[{} {}] '.format(now.isoformat(), action.upper())
        booking.incident_notes = (existing + '\n' if existing else '') + prefix + notes

    _record_dispatch_incident_event(
        booking.id,
        event_type='incident_{}'.format(action),
        actor_user_id=getattr(current_user, 'id', None),
        actor_email=getattr(current_user, 'email', None),
        source='web_admin_dispatch',
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
        current_app.logger.exception('Failed admin incident action %s for request %s.', action, request_id)
        flash('Failed to update incident state.')
        return redirect(redirect_target)

    metadata = {
        'action': action,
        'admin_user_id': getattr(current_user, 'id', None),
        'incident_state': booking.incident_state,
        'incident_severity': booking.incident_severity,
        'notes': notes,
    }
    _publish_waste_request_event(
        booking.id,
        'admin_dispatch_incident_{}'.format(action),
        payload=_serialize_waste_request_snapshot(booking),
        metadata=metadata,
    )
    _notify_mobile_push_for_waste_event(
        booking,
        'admin_dispatch_incident_{}'.format(action),
        metadata=metadata,
    )

    if action == 'ack':
        flash('Incident acknowledged for request #{}.'.format(request_id))
    else:
        flash('Incident resolved for request #{}.'.format(request_id))
    return redirect(redirect_target)



@bp.route('/admin/dispatch/incident-owner', methods=['POST'])
@login_required
def admin_dispatch_incident_owner_form():
    if not _current_user_is_admin():
        flash('Admin access is required.')
        return redirect('/login'), 403

    request_id = _to_int_or_none(request.form.get('request_id'))
    raw_owner_user_id = str(request.form.get('owner_admin_user_id') or '').strip()
    notes = (str(request.form.get('notes') or '').strip()[:1000] or None)
    return_query = str(request.form.get('return_query') or '').strip()
    redirect_target = url_for('admin.admin_dispatch_board')
    if return_query:
        redirect_target = '{}?{}'.format(redirect_target, return_query.lstrip('?'))

    if request_id is None:
        flash('request_id is required.')
        return redirect(redirect_target)

    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        flash('Waste request not found.')
        return redirect(redirect_target)

    if not raw_owner_user_id:
        new_owner_user_id = None
        owner_user = None
    else:
        new_owner_user_id = _to_int_or_none(raw_owner_user_id)
        if new_owner_user_id is None:
            flash('owner_admin_user_id must be an integer or empty.')
            return redirect(redirect_target)
        owner_user = db.session.get(User, new_owner_user_id)
        if not owner_user:
            flash('Owner admin user not found.')
            return redirect(redirect_target)
        if (owner_user.role or '').strip().lower() != 'admin':
            flash('Selected user is not an admin.')
            return redirect(redirect_target)
        if not owner_user.is_active_user:
            flash('Selected admin user is inactive.')
            return redirect(redirect_target)

    previous_owner_user_id = booking.incident_owner_admin_user_id
    if previous_owner_user_id == new_owner_user_id:
        flash('No owner change.')
        return redirect(redirect_target)

    now = datetime.utcnow()
    booking.incident_owner_admin_user_id = new_owner_user_id
    booking.incident_updated_at = now
    if notes:
        existing = (booking.incident_notes or '').strip()
        prefix = '[{} OWNER] '.format(now.isoformat())
        booking.incident_notes = (existing + '\n' if existing else '') + prefix + notes

    _record_dispatch_incident_event(
        booking.id,
        event_type='incident_owner_reassign',
        actor_user_id=getattr(current_user, 'id', None),
        actor_email=getattr(current_user, 'email', None),
        source='web_admin_dispatch',
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
        current_app.logger.exception('Failed incident owner reassignment for request %s.', request_id)
        flash('Failed to update incident owner.')
        return redirect(redirect_target)

    metadata = {
        'action': 'owner_reassign',
        'previous_owner_admin_user_id': previous_owner_user_id,
        'owner_admin_user_id': booking.incident_owner_admin_user_id,
        'admin_user_id': getattr(current_user, 'id', None),
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

    if booking.incident_owner_admin_user_id:
        flash('Incident owner updated for request #{}.'.format(request_id))
    else:
        flash('Incident owner cleared for request #{}.'.format(request_id))
    return redirect(redirect_target)



@bp.route('/admin/audit', methods=['GET'])
def admin_audit_log():
    if not _current_user_is_admin():
        flash('Admin access required.')
        return redirect('/login')

    try:
        page = max(1, int(request.args.get('page', '1')))
    except (TypeError, ValueError):
        page = 1
    per_page = 50

    query = _build_audit_events_query(request.args)
    total = query.count()
    rows = (
        query.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return render_template(
        'pages/admin_audit.html',
        events=[_serialize_audit_event(row) for row in rows],
        total=total,
        page=page,
        per_page=per_page,
        has_more=(page * per_page) < total,
        filters={
            'action': request.args.get('action', ''),
            'entity_type': request.args.get('entity_type', ''),
            'entity_id': request.args.get('entity_id', ''),
            'actor_user_id': request.args.get('actor_user_id', ''),
            'actor_email': request.args.get('actor_email', ''),
            'source': request.args.get('source', ''),
        },
    )
