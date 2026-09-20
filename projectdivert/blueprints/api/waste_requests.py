"""Waste requests routes."""

import queue
from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context
from projectdivert.extensions import db
from sqlalchemy import select

from projectdivert.models.waste import WasteRemovalDispatchOffer, WasteRemovalRequest, WasteRemovalVehicleLocation
from projectdivert.services.audit import record_audit_event
from projectdivert.services.auth import _request_access_allowed, _request_driver_mutation_allowed, jwt_required
from projectdivert.services.compliance import COMPLIANCE_COMPLETION_REQUIRED_TYPES, _compliance_documents_for_request, _compliance_missing_required_document_types, _compliance_summary_for_documents
from projectdivert.services.dispatch import _get_latest_match_for_request, _serialize_vehicle_location, _serialize_waste_request, _serialize_waste_request_snapshot
from projectdivert.services.events import _format_sse_event, _parse_waste_request_last_event_id, _publish_waste_request_event, _subscribe_waste_request_events, _unsubscribe_waste_request_events, _waste_request_replay_events_since
from projectdivert.services.geo import PostcodeLookupUnavailable
from projectdivert.services.notifications import _notify_mobile_push_for_waste_event
from projectdivert.services.reports import DEFAULT_REPORT_LIMIT, collection_report
from projectdivert.services.waste_requests import INITIAL_STATUS, WasteRequestError, create_waste_request
from projectdivert.services.utils import _current_jwt_email, _current_jwt_role, _current_jwt_user_id, _parse_datetime_or_error, _to_float_or_none, utcnow

bp = Blueprint('api_waste_requests', __name__)



@bp.route('/api/v1/waste-requests', methods=['POST'])
@jwt_required(roles={'customer', 'admin'})
def api_create_waste_request():
    data = request.get_json(silent=True) or {}
    try:
        payload = dict(data)
        # A customer may only raise a request as themselves; an admin may name
        # someone else. This is the one part of creation that is specific to
        # being called over the token-authenticated API.
        if _current_jwt_role() == 'customer':
            token_email = _current_jwt_email()
            if not token_email:
                return jsonify({'error': 'Token missing email claim'}), 403
            payload['requester_email'] = token_email

        created = create_waste_request(payload)
    except WasteRequestError as exc:
        db.session.rollback()
        body = {'error': str(exc)}
        if exc.fields:
            body['fields'] = exc.fields
        return jsonify(body), 400
    except PostcodeLookupUnavailable as exc:
        # Upstream is down, so this is not the caller's fault and retrying later
        # may well work -- reporting it as a 400 would say the opposite.
        db.session.rollback()
        return jsonify({'error': str(exc)}), 503
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    except Exception:
        db.session.rollback()
        current_app.logger.exception('API waste request creation failed.')
        return jsonify({'error': 'Failed to create waste request'}), 500

    return (
        jsonify(
            {
                'request': _serialize_waste_request(created.booking),
                'match': None,
                'drive_time': created.drive_time,
                'dispatch': {
                    'offers_created': created.offers_created,
                    'provider_notifications_sent': created.provider_notifications_sent,
                    'closest_candidate': created.closest_candidate,
                },
            }
        ),
        201,
    )



@bp.route('/api/v1/reports/collections', methods=['GET'])
@jwt_required(roles={'customer', 'driver', 'admin'})
def api_collection_report():
    """Totals across the collections the caller can see.

    Scoped exactly as the list endpoint is, so a report can never total rows
    the caller is not allowed to read: a customer sees their own, a driver the
    ones assigned to them, an admin everything.
    """
    role = _current_jwt_role()
    email = (_current_jwt_email() or '').lower()
    user_id = _current_jwt_user_id()

    query = WasteRemovalRequest.query
    if role == 'customer':
        if not email:
            return jsonify({'error': 'Token missing email claim'}), 403
        query = query.filter(WasteRemovalRequest.requester_email == email)
    elif role == 'driver':
        query = query.filter(WasteRemovalRequest.assigned_driver_user_id == user_id)

    try:
        limit = max(1, min(int(request.args.get('limit') or DEFAULT_REPORT_LIMIT), 2000))
    except (TypeError, ValueError):
        return jsonify({'error': 'limit must be an integer'}), 400

    return jsonify(collection_report(query, limit=limit))



@bp.route('/api/v1/waste-requests/<int:request_id>', methods=['GET'])
@jwt_required(roles={'customer', 'driver', 'admin'})
def api_get_waste_request(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_access_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403

    return jsonify(_serialize_waste_request_snapshot(booking))



@bp.route('/api/v1/waste-requests/<int:request_id>/events', methods=['GET'])
@jwt_required(roles={'customer', 'driver', 'admin'})
def api_stream_waste_request_events(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_access_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403

    heartbeat_seconds = int(current_app.config.get('WASTE_REQUEST_STREAM_HEARTBEAT_SECONDS') or 20)
    heartbeat_seconds = max(5, heartbeat_seconds)
    channel = _subscribe_waste_request_events(request_id)
    last_event_id = _parse_waste_request_last_event_id(
        request.args.get('last_event_id') or request.headers.get('Last-Event-ID')
    )
    replay_events = _waste_request_replay_events_since(request_id, last_event_id)
    initial_event = {
        'event': 'snapshot',
        'request_id': request_id,
        'occurred_at': utcnow().isoformat() + 'Z',
        'payload': _serialize_waste_request_snapshot(booking),
        'metadata': {},
    }

    @stream_with_context
    def _event_stream():
        try:
            yield _format_sse_event('waste_request', initial_event)
            for replay_event in replay_events:
                replay_event_id = _parse_waste_request_last_event_id(replay_event.get('event_id'))
                yield _format_sse_event('waste_request', replay_event, event_id=replay_event_id)
            while True:
                try:
                    event_payload = channel.get(timeout=heartbeat_seconds)
                    event_id = _parse_waste_request_last_event_id(event_payload.get('event_id'))
                    yield _format_sse_event('waste_request', event_payload, event_id=event_id)
                except queue.Empty:
                    yield ': keepalive\n\n'
        except GeneratorExit:
            pass
        finally:
            _unsubscribe_waste_request_events(request_id, channel)

    response = Response(_event_stream(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Connection'] = 'keep-alive'
    response.headers['X-Accel-Buffering'] = 'no'
    return response



@bp.route('/api/v1/waste-requests/<int:request_id>/status', methods=['POST'])
@jwt_required(roles={'driver', 'admin'})
def api_update_waste_request_status(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_driver_mutation_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403

    payload = request.get_json(silent=True) or {}
    new_status = str(payload.get('status') or '').strip().lower()
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
    if new_status not in allowed_statuses:
        return jsonify({'error': 'Invalid status', 'allowed_statuses': sorted(allowed_statuses)}), 400

    requires_match_statuses = {'matched', 'accepted', 'en_route', 'arrived', 'collected', 'completed'}
    if new_status in requires_match_statuses:
        match_row = _get_latest_match_for_request(booking.id)
        if not match_row:
            return jsonify({'error': 'No provider has accepted this request yet'}), 409

    if new_status == 'completed':
        compliance_documents = _compliance_documents_for_request(booking.id)
        compliance_summary = _compliance_summary_for_documents(compliance_documents)
        missing_types = _compliance_missing_required_document_types(
            compliance_summary,
            COMPLIANCE_COMPLETION_REQUIRED_TYPES,
        )
        if missing_types:
            return jsonify(
                {
                    'error': 'Compliance review incomplete for request completion',
                    'missing_document_types': missing_types,
                    'compliance': compliance_summary,
                }
            ), 409

    previous_status = booking.status
    booking.status = new_status
    db.session.commit()
    record_audit_event(
        action='waste_request.status_change',
        entity_type='waste_request',
        entity_id=booking.id,
        summary='Status {} -> {}'.format(previous_status, new_status),
        changes={'status': [previous_status, new_status]},
        status_code=200,
    )
    _publish_waste_request_event(
        booking.id,
        'status_updated',
        payload=_serialize_waste_request_snapshot(booking),
        metadata={
            'previous_status': previous_status,
            'new_status': new_status,
        },
    )
    _notify_mobile_push_for_waste_event(
        booking,
        'status_updated',
        metadata={
            'previous_status': previous_status,
            'new_status': new_status,
        },
    )
    return jsonify({'request': _serialize_waste_request(booking)})



@bp.route('/api/v1/waste-requests/<int:request_id>/location', methods=['POST'])
@jwt_required(roles={'driver', 'admin'})
def api_create_vehicle_location(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_driver_mutation_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403

    payload = request.get_json(silent=True) or {}
    latitude = _to_float_or_none(payload.get('latitude'))
    longitude = _to_float_or_none(payload.get('longitude'))
    if latitude is None or longitude is None:
        return jsonify({'error': 'latitude and longitude are required numeric values'}), 400

    recorded_raw = payload.get('recorded_at')
    if recorded_raw:
        try:
            recorded_at = _parse_datetime_or_error(recorded_raw, 'recorded_at')
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
    else:
        recorded_at = utcnow()

    location_row = WasteRemovalVehicleLocation(
        waste_removal_request_id=booking.id,
        driver_id=(str(_current_jwt_user_id() or '').strip()[:120] or None),
        vehicle_id=(str(payload.get('vehicle_id') or '').strip()[:120] or None),
        latitude=latitude,
        longitude=longitude,
        recorded_at=recorded_at,
        source=(str(payload.get('source') or 'mobile').strip()[:32] or 'mobile'),
    )
    db.session.add(location_row)
    db.session.commit()
    _publish_waste_request_event(
        booking.id,
        'location_updated',
        payload=_serialize_waste_request_snapshot(booking),
        metadata={
            'location_id': location_row.id,
            'latitude': location_row.latitude,
            'longitude': location_row.longitude,
        },
    )
    return jsonify({'location': _serialize_vehicle_location(location_row)}), 201



@bp.route('/api/v1/waste-requests/<int:request_id>/location/latest', methods=['GET'])
@jwt_required(roles={'customer', 'driver', 'admin'})
def api_get_latest_vehicle_location(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_access_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403

    location_row = (
        WasteRemovalVehicleLocation.query.filter_by(waste_removal_request_id=booking.id)
        .order_by(WasteRemovalVehicleLocation.recorded_at.desc(), WasteRemovalVehicleLocation.id.desc())
        .first()
    )
    if not location_row:
        return jsonify({'error': 'No location updates for this request yet'}), 404

    return jsonify(
        {
            'request_id': booking.id,
            'request_status': booking.status,
            'latest_location': _serialize_vehicle_location(location_row),
        }
    )


def _claimable_requests(query):
    """Narrow a request query to jobs a driver could actually pick up.

    Two conditions, and both were missing. The status filter said 'pending',
    which no request has ever been created with -- the initial status is
    'pending_match', so the available list was unconditionally empty. And a
    request with no open offer cannot be claimed at all, so listing one only
    produces a button that fails.
    """
    return query.filter(
        WasteRemovalRequest.status == INITIAL_STATUS,
        WasteRemovalRequest.assigned_driver_user_id.is_(None),
        WasteRemovalRequest.id.in_(
            select(WasteRemovalDispatchOffer.waste_removal_request_id)
            .where(WasteRemovalDispatchOffer.status == 'offered')
        ),
    )


#: How the list endpoint scopes rows, per role. A customer can only ever see
#: their own requests regardless of what they ask for.
_LIST_SCOPES = ('mine', 'assigned', 'available', 'all')


@bp.route('/api/v1/waste-requests', methods=['GET'])
@jwt_required(roles={'customer', 'driver', 'admin'})
def api_list_waste_requests():
    """List waste requests visible to the caller.

    One endpoint rather than three, scoped by role so the caller cannot widen
    its own view:

      customer  always their own requests, whatever scope is asked for
      driver    'assigned' (default) or 'available' open jobs to claim
      admin     any scope, 'all' by default
    """
    role = _current_jwt_role()
    email = (_current_jwt_email() or '').lower()
    user_id = _current_jwt_user_id()

    scope = (request.args.get('scope') or '').strip().lower()
    if scope and scope not in _LIST_SCOPES:
        return jsonify({'error': 'Invalid scope', 'allowed_scopes': sorted(_LIST_SCOPES)}), 400

    query = WasteRemovalRequest.query
    if role == 'customer':
        if not email:
            return jsonify({'error': 'Token missing email claim'}), 403
        query = query.filter(WasteRemovalRequest.requester_email == email)
        scope = 'mine'
    elif role == 'driver':
        scope = scope if scope in ('assigned', 'available') else 'assigned'
        if scope == 'assigned':
            query = query.filter(WasteRemovalRequest.assigned_driver_user_id == user_id)
        else:
            query = _claimable_requests(query)
    else:
        scope = scope or 'all'
        if scope == 'mine':
            query = query.filter(WasteRemovalRequest.requester_email == email)
        elif scope == 'assigned':
            query = query.filter(WasteRemovalRequest.assigned_driver_user_id == user_id)
        elif scope == 'available':
            query = _claimable_requests(query)

    status = (request.args.get('status') or '').strip()
    if status:
        query = query.filter(WasteRemovalRequest.status == status)

    try:
        limit = max(1, min(int(request.args.get('limit') or 50), 200))
        offset = max(0, int(request.args.get('offset') or 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'limit and offset must be integers'}), 400

    total = query.count()
    rows = (
        query.order_by(WasteRemovalRequest.scheduled_pickup_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return jsonify({
        'scope': scope,
        'count': len(rows),
        'total': total,
        'limit': limit,
        'offset': offset,
        'requests': [_serialize_waste_request(row) for row in rows],
    })
