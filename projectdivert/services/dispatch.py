"""Driver dispatch, offers, incidents and request timelines."""

import uuid
from datetime import timedelta
import requests
from flask import current_app
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from projectdivert.extensions import db
from projectdivert.models.audit import AuthAuditEvent
from projectdivert.models.user import User
from projectdivert.models.waste import DispatchIncidentEvent, WasteRemovalDispatchOffer, WasteRemovalMatch, WasteRemovalRequest, WasteRemovalVehicleLocation
from projectdivert.services.audit import _normalize_auth_audit_details, record_audit_event
from projectdivert.services.billing_core import _billing_summary, _communication_logs_for_request, _serialize_request_billing_followup_workflow, _serialize_request_communication_log, _serialize_request_communication_summary
from projectdivert.services.compliance import _compliance_documents_for_request, _compliance_documents_for_requests, _compliance_summary_for_documents, _driver_dispatch_compliance_status, _serialize_compliance_document
from projectdivert.services.events import _publish_waste_request_event
from projectdivert.services.geo import _haversine_miles
from projectdivert.services.notifications import _notify_mobile_push_for_waste_event
from projectdivert.services.payments import _financial_summary_for_request
from projectdivert.services.reference_data import _ensure_reference_data_loaded
from projectdivert.services.utils import _current_jwt_role, _is_truthy, _minutes_since, _normalize_email, _parse_yes_no_flag, _to_float_or_none, _to_int_or_none, _to_percent_or_none, utcnow
from projectdivert.services import reference_data
import logging

logger = logging.getLogger(__name__)


def _dispatch_quality_score(candidate):
    """Compute a deterministic quality score for provider ranking tie-breaks."""
    recyclable = candidate.get('percent_recyclable')
    efw = candidate.get('percent_efw')
    audited = candidate.get('is_audited')
    rebate = candidate.get('provides_rebate')

    score = 0.0
    if recyclable is not None:
        score += recyclable
    if efw is not None:
        score += (100.0 - efw) * 0.65
    if audited is True:
        score += 10.0
    if rebate is True:
        score += 5.0
    return round(score, 4)


def _dispatch_sort_key(candidate):
    # Distance is primary. If equal, prefer higher quality score, then explicit deterministic fields.
    recyclable = candidate.get('percent_recyclable')
    efw = candidate.get('percent_efw')
    audited = candidate.get('is_audited')
    rebate = candidate.get('provides_rebate')
    quality_score = candidate.get('dispatch_quality_score')
    if quality_score is None:
        quality_score = _dispatch_quality_score(candidate)
    return (
        round(candidate.get('distance_miles_raw', candidate['distance_miles']), 6),
        -quality_score,
        -(recyclable if recyclable is not None else -1.0),
        efw if efw is not None else 101.0,
        0 if audited is True else 1,
        0 if rebate is True else 1,
        candidate['provider_name'].strip().lower(),
        str(candidate.get('provider_postcode') or '').strip().lower(),
        round(candidate.get('provider_latitude') or 0.0, 6),
        round(candidate.get('provider_longitude') or 0.0, 6),
    )


def _dispatch_offer_fanout():
    value = current_app.config.get('DISPATCH_OFFER_FANOUT', 10)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 10


def _dispatch_pending_match_sla_minutes():
    value = current_app.config.get('DISPATCH_PENDING_MATCH_SLA_MINUTES', 30)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 30


def _dispatch_unassigned_match_sla_minutes():
    value = current_app.config.get('DISPATCH_UNASSIGNED_MATCH_SLA_MINUTES', 20)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 20


def _dispatch_location_stale_minutes():
    value = current_app.config.get('DISPATCH_LOCATION_STALE_MINUTES', 20)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 20


def _dispatch_escalation_ack_sla_minutes(severity):
    severity = str(severity or '').strip().lower()
    config_map = {
        'critical': 'DISPATCH_ESCALATION_ACK_SLA_CRITICAL_MINUTES',
        'high': 'DISPATCH_ESCALATION_ACK_SLA_HIGH_MINUTES',
        'medium': 'DISPATCH_ESCALATION_ACK_SLA_MEDIUM_MINUTES',
        'low': 'DISPATCH_ESCALATION_ACK_SLA_LOW_MINUTES',
    }
    value = current_app.config.get(config_map.get(severity, 'DISPATCH_ESCALATION_ACK_SLA_LOW_MINUTES'), 90)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 90


def _dispatch_escalation_resolve_sla_minutes(severity):
    severity = str(severity or '').strip().lower()
    config_map = {
        'critical': 'DISPATCH_ESCALATION_RESOLVE_SLA_CRITICAL_MINUTES',
        'high': 'DISPATCH_ESCALATION_RESOLVE_SLA_HIGH_MINUTES',
        'medium': 'DISPATCH_ESCALATION_RESOLVE_SLA_MEDIUM_MINUTES',
        'low': 'DISPATCH_ESCALATION_RESOLVE_SLA_LOW_MINUTES',
    }
    value = current_app.config.get(config_map.get(severity, 'DISPATCH_ESCALATION_RESOLVE_SLA_LOW_MINUTES'), 720)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 720


def _dispatch_escalation_webhook_url():
    return (str(current_app.config.get('DISPATCH_ESCALATION_WEBHOOK_URL') or '').strip() or '')


def _dispatch_escalation_webhook_timeout_seconds():
    value = current_app.config.get('DISPATCH_ESCALATION_WEBHOOK_TIMEOUT_SECONDS', 8)
    try:
        return max(2, int(value))
    except (TypeError, ValueError):
        return 8


def _dispatch_escalation_cooldown_minutes():
    value = current_app.config.get('DISPATCH_ESCALATION_COOLDOWN_MINUTES', 30)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 30


def _dispatch_incident_maintenance_limit(value=None):
    if value is None:
        value = current_app.config.get('DISPATCH_INCIDENT_MAINTENANCE_LIMIT', 500)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 500


def _dispatch_incident_auto_assign_enabled(value=None):
    if value is None:
        value = current_app.config.get('DISPATCH_INCIDENT_AUTO_ASSIGN_ENABLED', False)
    return _is_truthy(value)


def _dispatch_incident_auto_assign_admin_email(value=None):
    if value is None:
        value = current_app.config.get('DISPATCH_INCIDENT_AUTO_ASSIGN_ADMIN_EMAIL', '')
    return (_normalize_email(value) or '')


def _dispatch_incident_auto_resolve_test_enabled(value=None):
    if value is None:
        value = current_app.config.get('DISPATCH_INCIDENT_AUTO_RESOLVE_TEST_ENABLED', False)
    return _is_truthy(value)


def _dispatch_incident_auto_resolve_test_minutes(value=None):
    if value is None:
        value = current_app.config.get('DISPATCH_INCIDENT_AUTO_RESOLVE_TEST_MINUTES', 720)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 720


def _select_provider_candidates_within_radius(
    pickup_latitude,
    pickup_longitude,
    radius_miles,
    limit=None,
):
    _ensure_reference_data_loaded()

    if radius_miles <= 0:
        raise ValueError('Provider match radius must be greater than zero.')

    if reference_data.suppliers is None or getattr(reference_data.suppliers, 'empty', True):
        return []

    candidates = []
    for _, row in reference_data.suppliers.iterrows():
        provider_name = str(row.get('name') or '').strip()
        provider_latitude = _to_float_or_none(row.get('lat'))
        provider_longitude = _to_float_or_none(row.get('long'))
        if not provider_name or provider_latitude is None or provider_longitude is None:
            continue

        distance_miles = _haversine_miles(
            pickup_latitude,
            pickup_longitude,
            provider_latitude,
            provider_longitude,
        )
        if distance_miles <= radius_miles:
            percent_recyclable = _to_percent_or_none(row.get('percent_recyclablenum'))
            percent_efw = _to_percent_or_none(row.get('percent_efwnum'))
            candidate = {
                'provider_name': provider_name[:255],
                'provider_type': str(row.get('sup_type') or '').strip()[:120] or None,
                'provider_city': str(row.get('city') or '').strip()[:120] or None,
                'provider_postcode': str(row.get('postcode') or '').strip()[:32] or None,
                'provider_latitude': provider_latitude,
                'provider_longitude': provider_longitude,
                'provider_email': (
                    str(row.get('supplier_contact_email') or row.get('email') or '').strip()[:255] or None
                ),
                'provider_phone': (
                    str(row.get('supplier_contact_telephone') or row.get('telephone') or '').strip()[:120] or None
                ),
                'distance_miles_raw': distance_miles,
                'distance_miles': round(distance_miles, 2),
                'percent_recyclable': percent_recyclable,
                'percent_efw': percent_efw,
                'is_audited': _parse_yes_no_flag(row.get('supplier_auditislist_yes_no_na')),
                'provides_rebate': _parse_yes_no_flag(row.get('provides_a_rebateyn')),
            }
            candidate['dispatch_quality_score'] = _dispatch_quality_score(candidate)
            candidates.append(candidate)

    if not candidates:
        return []
    candidates.sort(key=_dispatch_sort_key)
    if limit is not None:
        return candidates[: max(1, int(limit))]
    return candidates


def _select_best_provider_within_radius(pickup_latitude, pickup_longitude, radius_miles):
    candidates = _select_provider_candidates_within_radius(
        pickup_latitude,
        pickup_longitude,
        radius_miles,
        limit=1,
    )
    if not candidates:
        return None
    return candidates[0]


def _create_dispatch_offers_for_request(
    booking,
    pickup_latitude,
    pickup_longitude,
    match_radius_miles,
):
    candidates = _select_provider_candidates_within_radius(
        pickup_latitude,
        pickup_longitude,
        match_radius_miles,
        limit=_dispatch_offer_fanout(),
    )
    offer_rows = []
    for rank, candidate in enumerate(candidates, start=1):
        offer_rows.append(
            WasteRemovalDispatchOffer(
                waste_removal_request_id=booking.id,
                provider_name=candidate['provider_name'],
                provider_type=candidate['provider_type'],
                provider_city=candidate['provider_city'],
                provider_postcode=candidate['provider_postcode'],
                provider_latitude=candidate['provider_latitude'],
                provider_longitude=candidate['provider_longitude'],
                provider_email=candidate['provider_email'],
                provider_phone=candidate['provider_phone'],
                distance_miles=candidate['distance_miles'],
                match_radius_miles=match_radius_miles,
                offer_rank=rank,
                offer_token=uuid.uuid4().hex,
                status='offered',
            )
        )
    return candidates, offer_rows


def _get_latest_match_for_request(request_id):
    return (
        WasteRemovalMatch.query.filter_by(waste_removal_request_id=request_id)
        .order_by(WasteRemovalMatch.created_at.desc(), WasteRemovalMatch.id.desc())
        .first()
    )


def _dispatch_summary_for_request(request_id):
    offers = WasteRemovalDispatchOffer.query.filter_by(waste_removal_request_id=request_id)
    offers_sent = offers.count()
    offers_open = offers.filter_by(status='offered').count()
    accepted_offer = (
        offers.filter_by(status='accepted')
        .order_by(WasteRemovalDispatchOffer.responded_at.desc(), WasteRemovalDispatchOffer.id.desc())
        .first()
    )
    return {
        'offers_sent': offers_sent,
        'offers_open': offers_open,
        'accepted_offer': _serialize_dispatch_offer(accepted_offer),
    }


def _accept_dispatch_offer(booking, offer, assigned_driver_user_id=None):
    """Accept one dispatch offer, returning ``(match_row, outcome)``.

    ``outcome`` is ``'accepted'`` only when this call created the match. Every
    other value -- ``'already_matched'``, ``'driver_mismatch'``,
    ``'offer_unavailable'``, ``'invalid_offer'`` -- means no match was made, so
    callers must compare against ``'accepted'`` rather than treating the second
    value as an error flag (it is truthy on success).

    Two drivers can accept two different offers for the same request at the
    same instant. Both would read an ``offered`` offer and no existing match,
    and both would create one, double-booking the job. So the request row is
    locked first and the offer re-read underneath it: every acceptance for a
    given request serialises on that row, and the loser sees the winner's
    committed match and gets ``already_matched``. SQLite ignores ``FOR UPDATE``,
    which is why the test inspects the statement rather than racing.

    A unique constraint on ``waste_removal_matches.waste_removal_request_id``
    backs the lock up, so the invariant also holds where the lock does not
    apply; the commit below turns that into ``already_matched`` too.
    """
    if not booking or not offer:
        return None, 'invalid_offer'

    if offer.waste_removal_request_id != booking.id:
        return None, 'invalid_offer'

    booking = (
        db.session.query(WasteRemovalRequest)
        .filter(WasteRemovalRequest.id == booking.id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if not booking:
        return None, 'invalid_offer'
    # The offer was read before the lock, so its status may be stale by now.
    db.session.refresh(offer)

    # The early returns below leave the lock held until the transaction ends
    # with the request; rolling back here would expire `existing_match` while
    # the caller is still serialising it.
    if assigned_driver_user_id is not None:
        if booking.assigned_driver_user_id and booking.assigned_driver_user_id != assigned_driver_user_id:
            return None, 'driver_mismatch'

    if (offer.status or '').strip().lower() != 'offered':
        return None, 'offer_unavailable'

    existing_match = _get_latest_match_for_request(booking.id)
    if existing_match:
        return existing_match, 'already_matched'

    now = utcnow()
    offer.status = 'accepted'
    offer.responded_at = now

    (
        WasteRemovalDispatchOffer.query.filter(
            WasteRemovalDispatchOffer.waste_removal_request_id == booking.id,
            WasteRemovalDispatchOffer.id != offer.id,
            WasteRemovalDispatchOffer.status == 'offered',
        ).update(
            {
                WasteRemovalDispatchOffer.status: 'expired',
                WasteRemovalDispatchOffer.responded_at: now,
            },
            synchronize_session=False,
        )
    )

    match_row = WasteRemovalMatch(
        waste_removal_request_id=booking.id,
        provider_name=offer.provider_name,
        provider_type=offer.provider_type,
        provider_city=offer.provider_city,
        provider_postcode=offer.provider_postcode,
        provider_latitude=offer.provider_latitude,
        provider_longitude=offer.provider_longitude,
        distance_miles=offer.distance_miles,
        match_radius_miles=offer.match_radius_miles,
    )
    db.session.add(match_row)
    previous_status = booking.status
    if assigned_driver_user_id is not None:
        booking.assigned_driver_user_id = assigned_driver_user_id
    booking.status = 'matched'
    try:
        db.session.commit()
    except IntegrityError:
        # The unique constraint on waste_removal_matches caught a concurrent
        # acceptance that the row lock could not (no row locking on SQLite, or
        # a lock taken in a separate transaction). Report it the same way the
        # pre-flight check would have.
        db.session.rollback()
        logger.warning(
            'Concurrent dispatch acceptance rejected for request_id=%s offer_id=%s',
            booking.id,
            offer.id,
        )
        return _get_latest_match_for_request(booking.id), 'already_matched'

    record_audit_event(
        action='dispatch_offer.accept',
        entity_type='waste_request',
        entity_id=booking.id,
        summary='Dispatch offer #{} accepted; provider {}'.format(offer.id, offer.provider_name),
        changes={
            'status': [previous_status, booking.status],
            'assigned_driver_user_id': [None, assigned_driver_user_id],
            'dispatch_offer_id': [None, offer.id],
        },
    )
    return match_row, 'accepted'


def _serialize_request_billing_workflow(booking):
    if not booking:
        return None
    state = (booking.billing_state or '').strip().lower() or 'pending_offline_invoice'
    return {
        'state': state,
        'reference': booking.billing_reference,
        'notes': booking.billing_notes,
        'updated_at': booking.billing_updated_at.isoformat() if booking.billing_updated_at else None,
        'updated_by_user_id': booking.billing_updated_by_user_id,
    }


def _serialize_waste_request(booking):
    return {
        'id': booking.id,
        'requester_name': booking.requester_name,
        'requester_email': booking.requester_email,
        'material_type': booking.material_type,
        'waste_amount': booking.waste_amount,
        'waste_unit': booking.waste_unit,
        'pickup_address': booking.pickup_address,
        'pickup_city': booking.pickup_city,
        'pickup_county': booking.pickup_county,
        'pickup_postcode': booking.pickup_postcode,
        'scheduled_pickup_at': booking.scheduled_pickup_at.isoformat() if booking.scheduled_pickup_at else None,
        'notes': booking.notes,
        'status': booking.status,
        'assigned_driver_user_id': booking.assigned_driver_user_id,
        'incident_state': booking.incident_state,
        'incident_severity': booking.incident_severity,
        'incident_owner_admin_user_id': booking.incident_owner_admin_user_id,
        'incident_acknowledged_at': (
            booking.incident_acknowledged_at.isoformat() if booking.incident_acknowledged_at else None
        ),
        'incident_resolved_at': booking.incident_resolved_at.isoformat() if booking.incident_resolved_at else None,
        'incident_notes': booking.incident_notes,
        'incident_updated_at': booking.incident_updated_at.isoformat() if booking.incident_updated_at else None,
        'incident_last_escalation_key': booking.incident_last_escalation_key,
        'incident_last_escalated_at': (
            booking.incident_last_escalated_at.isoformat() if booking.incident_last_escalated_at else None
        ),
        'billing_workflow': _serialize_request_billing_workflow(booking),
        'billing_followup_workflow': _serialize_request_billing_followup_workflow(booking),
        'created_at': booking.created_at.isoformat() if booking.created_at else None,
    }


def _serialize_admin_billing_queue_item(booking):
    return {
        'request': _serialize_waste_request(booking),
        'billing': _billing_summary(),
        'financials': _financial_summary_for_request(booking.id),
    }


def _serialize_waste_match(match):
    if not match:
        return None
    return {
        'id': match.id,
        'waste_removal_request_id': match.waste_removal_request_id,
        'provider_name': match.provider_name,
        'provider_type': match.provider_type,
        'provider_city': match.provider_city,
        'provider_postcode': match.provider_postcode,
        'provider_latitude': match.provider_latitude,
        'provider_longitude': match.provider_longitude,
        'distance_miles': match.distance_miles,
        'match_radius_miles': match.match_radius_miles,
        'created_at': match.created_at.isoformat() if match.created_at else None,
    }


def _serialize_dispatch_offer(offer, include_token=False):
    if not offer:
        return None
    data = {
        'id': offer.id,
        'waste_removal_request_id': offer.waste_removal_request_id,
        'provider_name': offer.provider_name,
        'provider_type': offer.provider_type,
        'provider_city': offer.provider_city,
        'provider_postcode': offer.provider_postcode,
        'provider_latitude': offer.provider_latitude,
        'provider_longitude': offer.provider_longitude,
        'provider_email': offer.provider_email,
        'provider_phone': offer.provider_phone,
        'distance_miles': offer.distance_miles,
        'match_radius_miles': offer.match_radius_miles,
        'offer_rank': offer.offer_rank,
        'status': offer.status,
        'notified_at': offer.notified_at.isoformat() if offer.notified_at else None,
        'responded_at': offer.responded_at.isoformat() if offer.responded_at else None,
        'created_at': offer.created_at.isoformat() if offer.created_at else None,
    }
    if include_token:
        data['offer_token'] = offer.offer_token
    return data


def _serialize_vehicle_location(location):
    if not location:
        return None
    return {
        'id': location.id,
        'waste_removal_request_id': location.waste_removal_request_id,
        'driver_id': location.driver_id,
        'vehicle_id': location.vehicle_id,
        'latitude': location.latitude,
        'longitude': location.longitude,
        'recorded_at': location.recorded_at.isoformat() if location.recorded_at else None,
        'source': location.source,
        'created_at': location.created_at.isoformat() if location.created_at else None,
    }


def _serialize_dispatch_driver(user, compliance=None):
    if not user:
        return None
    if compliance is None:
        compliance = _driver_dispatch_compliance_status(user.id)
    return {
        'id': user.id,
        'email': user.email,
        'name': user.name,
        'role': user.role,
        'is_active': bool(user.is_active_user),
        'carrier_company_id': user.carrier_company_id,
        'carrier_company': compliance['summary'].get('carrier_company'),
        'dispatch_eligible': compliance['eligible'],
        'dispatch_missing_document_types': compliance['missing_document_types'],
        'compliance': compliance['summary'],
    }


def _dispatch_incident_flags(booking, latest_location=None, now=None):
    if not booking:
        return []

    now = now or utcnow()
    status = (booking.status or '').strip().lower()
    age_minutes = _minutes_since(booking.created_at, now=now) or 0
    pickup_due_minutes = None
    if booking.scheduled_pickup_at:
        pickup_due_minutes = int((now - booking.scheduled_pickup_at).total_seconds() // 60)

    flags = []
    if status == 'pending_match' and age_minutes >= _dispatch_pending_match_sla_minutes():
        flags.append('stale_pending_match')

    if status in {'matched', 'accepted'} and not booking.assigned_driver_user_id:
        if age_minutes >= _dispatch_unassigned_match_sla_minutes():
            flags.append('matched_without_driver')

    if status in {'en_route', 'arrived', 'collected'}:
        location_age = _minutes_since(getattr(latest_location, 'recorded_at', None), now=now)
        if location_age is None:
            flags.append('missing_driver_location')
        elif location_age >= _dispatch_location_stale_minutes():
            flags.append('stale_driver_location')

    if pickup_due_minutes is not None and pickup_due_minutes > 0 and status not in {'completed', 'cancelled'}:
        flags.append('pickup_overdue')

    return flags


def _dispatch_incident_severity(flags):
    flags = list(flags or [])
    if not flags:
        return None
    if 'pickup_overdue' in flags:
        return 'critical'
    if 'stale_pending_match' in flags or 'matched_without_driver' in flags:
        return 'high'
    if 'stale_driver_location' in flags:
        return 'medium'
    return 'low'


def _dispatch_effective_incident_state(booking, flags):
    flags = list(flags or [])
    stored_state = str(getattr(booking, 'incident_state', '') or '').strip().lower()
    if flags:
        if stored_state in {'acknowledged', 'resolved'}:
            return stored_state
        return 'open'
    if stored_state in {'open', 'acknowledged', 'resolved'}:
        return 'resolved'
    return None


def _dispatch_incident_summary(booking, flags, now=None):
    now = now or utcnow()
    flags = list(flags or [])
    state = _dispatch_effective_incident_state(booking, flags)
    severity = _dispatch_incident_severity(flags)
    ack_minutes = _minutes_since(getattr(booking, 'incident_acknowledged_at', None), now=now)
    resolve_minutes = _minutes_since(getattr(booking, 'incident_resolved_at', None), now=now)
    created_age_minutes = _minutes_since(getattr(booking, 'created_at', None), now=now) or 0
    ack_sla_minutes = _dispatch_escalation_ack_sla_minutes(severity) if severity else None
    resolve_sla_minutes = _dispatch_escalation_resolve_sla_minutes(severity) if severity else None

    breach_type = None
    breach_minutes = 0
    if state == 'open' and ack_sla_minutes is not None and created_age_minutes > ack_sla_minutes:
        breach_type = 'ack_sla'
        breach_minutes = created_age_minutes - ack_sla_minutes
    elif state == 'acknowledged' and resolve_sla_minutes is not None:
        resolve_window_age = ack_minutes if ack_minutes is not None else created_age_minutes
        if resolve_window_age > resolve_sla_minutes:
            breach_type = 'resolve_sla'
            breach_minutes = resolve_window_age - resolve_sla_minutes

    return {
        'state': state,
        'severity': severity,
        'owner_admin_user_id': booking.incident_owner_admin_user_id,
        'acknowledged_at': (
            booking.incident_acknowledged_at.isoformat() if booking.incident_acknowledged_at else None
        ),
        'resolved_at': booking.incident_resolved_at.isoformat() if booking.incident_resolved_at else None,
        'notes': booking.incident_notes,
        'updated_at': booking.incident_updated_at.isoformat() if booking.incident_updated_at else None,
        'ack_age_minutes': ack_minutes,
        'resolve_age_minutes': resolve_minutes,
        'ack_sla_minutes': ack_sla_minutes,
        'resolve_sla_minutes': resolve_sla_minutes,
        'breach_type': breach_type,
        'breach_minutes': breach_minutes if breach_type else 0,
    }


def _dispatch_escalation_key_for_item(queue_item):
    incident = queue_item.get('incident') or {}
    breach_type = str(incident.get('breach_type') or '').strip().lower()
    severity = str(incident.get('severity') or '').strip().lower()
    request_id = (queue_item.get('request') or {}).get('id')
    if not breach_type or not severity or request_id is None:
        return ''
    return '{}:{}:{}'.format(breach_type, severity, request_id)


def _dispatch_send_escalation_webhook(booking, queue_item, now=None, source=''):
    webhook_url = _dispatch_escalation_webhook_url()
    if not webhook_url:
        return False

    incident = queue_item.get('incident') or {}
    breach_type = str(incident.get('breach_type') or '').strip().lower()
    severity = str(incident.get('severity') or '').strip().lower()
    if not breach_type or not severity:
        return False

    now = now or utcnow()
    escalation_key = _dispatch_escalation_key_for_item(queue_item)
    if not escalation_key:
        return False

    cooldown_minutes = _dispatch_escalation_cooldown_minutes()
    if (
        booking.incident_last_escalation_key == escalation_key
        and booking.incident_last_escalated_at
        and (now - booking.incident_last_escalated_at).total_seconds() < (cooldown_minutes * 60)
    ):
        return False

    request_data = queue_item.get('request') or {}
    payload = {
        'text': (
            '[Project Divert] Dispatch incident escalation: request #{request_id} '
            '{severity} {breach_type} breach (+{breach_minutes}m)'
        ).format(
            request_id=request_data.get('id'),
            severity=severity.upper(),
            breach_type=breach_type,
            breach_minutes=int(incident.get('breach_minutes') or 0),
        ),
        'request_id': request_data.get('id'),
        'request_status': request_data.get('status'),
        'severity': severity,
        'incident_state': incident.get('state'),
        'breach_type': breach_type,
        'breach_minutes': int(incident.get('breach_minutes') or 0),
        'incident_flags': queue_item.get('incident_flags') or [],
        'assigned_driver_user_id': request_data.get('assigned_driver_user_id'),
        'pickup_postcode': request_data.get('pickup_postcode'),
        'owner_admin_user_id': incident.get('owner_admin_user_id'),
        'source': str(source or ''),
        'occurred_at': now.isoformat() + 'Z',
    }

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=_dispatch_escalation_webhook_timeout_seconds(),
        )
        if response.status_code >= 400:
            logger.warning(
                'Dispatch escalation webhook failed status=%s request_id=%s',
                response.status_code,
                request_data.get('id'),
            )
            return False
    except Exception:
        logger.exception(
            'Dispatch escalation webhook request failed for request_id=%s',
            request_data.get('id'),
        )
        return False

    booking.incident_last_escalation_key = escalation_key
    booking.incident_last_escalated_at = now
    booking.incident_updated_at = now
    return True


def _drivers_by_id(user_ids):
    """Assigned drivers for a page of requests, in one query."""
    user_ids = [uid for uid in set(user_ids or ()) if uid is not None]
    if not user_ids:
        return {}
    return {row.id: row for row in User.query.filter(User.id.in_(user_ids)).all()}


def _latest_vehicle_locations_for_requests(request_ids):
    """The newest vehicle location per request, in one query.

    Ranked with a window function rather than MAX(id) so the ordering matches
    the per-row lookup exactly: newest recorded_at wins, and the higher id
    breaks a tie. A backdated row inserted later must not win.
    """
    request_ids = [rid for rid in set(request_ids or ()) if rid is not None]
    if not request_ids:
        return {}

    ranked = (
        select(
            WasteRemovalVehicleLocation.id.label('id'),
            func.row_number().over(
                partition_by=WasteRemovalVehicleLocation.waste_removal_request_id,
                order_by=(
                    WasteRemovalVehicleLocation.recorded_at.desc(),
                    WasteRemovalVehicleLocation.id.desc(),
                ),
            ).label('rank'),
        )
        .where(WasteRemovalVehicleLocation.waste_removal_request_id.in_(request_ids))
        .subquery()
    )
    newest_ids = select(ranked.c.id).where(ranked.c.rank == 1)
    rows = (
        WasteRemovalVehicleLocation.query
        .filter(WasteRemovalVehicleLocation.id.in_(newest_ids))
        .all()
    )
    return {row.waste_removal_request_id: row for row in rows}


class DispatchQueueContext:
    """Everything a page of queue items needs, loaded up front.

    Serialising one item looks up the assigned driver, the latest vehicle
    location, the request's compliance documents and the driver's compliance
    standing. Done per row against a page of up to 500 requests that is over a
    thousand queries for a single dashboard load, so a caller builds this once
    and serialises through it.
    """

    def __init__(self, bookings):
        bookings = list(bookings or ())
        request_ids = [booking.id for booking in bookings]
        driver_ids = [booking.assigned_driver_user_id for booking in bookings]

        self.drivers = _drivers_by_id(driver_ids)
        self.locations = _latest_vehicle_locations_for_requests(request_ids)
        self.compliance_documents = _compliance_documents_for_requests(request_ids)
        # Keyed by driver rather than by request: a page is usually many
        # requests across a handful of drivers, and the standing is the same
        # for every request a driver holds.
        self.driver_compliance = {
            driver_id: _driver_dispatch_compliance_status(driver_id)
            for driver_id in {d for d in driver_ids if d is not None}
        }

    def serialize(self, booking, now=None):
        """One queue item, with nothing left to look up."""
        driver_id = booking.assigned_driver_user_id
        return _serialize_dispatch_queue_item(
            booking,
            driver=self.drivers.get(driver_id),
            latest_location=self.locations.get(booking.id),
            now=now,
            compliance_documents=self.compliance_documents.get(booking.id, []),
            driver_compliance=self.driver_compliance.get(driver_id),
        )


def _serialize_dispatch_queue_item(booking, driver=None, latest_location=None, now=None,
                                   compliance_documents=None, driver_compliance=None):
    now = now or utcnow()
    pickup_due_minutes = None
    if booking.scheduled_pickup_at:
        pickup_due_minutes = int((now - booking.scheduled_pickup_at).total_seconds() // 60)

    incident_flags = _dispatch_incident_flags(booking, latest_location=latest_location, now=now)
    incident = _dispatch_incident_summary(booking, incident_flags, now=now)
    if compliance_documents is None:
        compliance_documents = _compliance_documents_for_request(booking.id)
    compliance_summary = _compliance_summary_for_documents(compliance_documents)

    return {
        'request': _serialize_waste_request(booking),
        'driver': _serialize_dispatch_driver(driver, compliance=driver_compliance),
        'latest_location': _serialize_vehicle_location(latest_location),
        'age_minutes': _minutes_since(booking.created_at, now=now),
        'pickup_due_minutes': pickup_due_minutes,
        'incident_flags': incident_flags,
        'incident': incident,
        'compliance': compliance_summary,
    }


def _serialize_waste_request_snapshot(booking):
    if not booking:
        return None

    match_row = _get_latest_match_for_request(booking.id)
    latest_location = (
        WasteRemovalVehicleLocation.query.filter_by(waste_removal_request_id=booking.id)
        .order_by(WasteRemovalVehicleLocation.recorded_at.desc(), WasteRemovalVehicleLocation.id.desc())
        .first()
    )
    compliance_documents = _compliance_documents_for_request(booking.id)
    customer_visible_only = _current_jwt_role() in {'customer', 'driver'}
    communication_logs = _communication_logs_for_request(
        booking.id,
        customer_visible_only=customer_visible_only,
    )
    return {
        'request': _serialize_waste_request(booking),
        'match': _serialize_waste_match(match_row),
        'latest_location': _serialize_vehicle_location(latest_location),
        'dispatch': _dispatch_summary_for_request(booking.id),
        'financials': _financial_summary_for_request(booking.id),
        'billing': _billing_summary(),
        'compliance': {
            'documents': [_serialize_compliance_document(row) for row in compliance_documents],
            'summary': _compliance_summary_for_documents(compliance_documents),
        },
        'communications': [_serialize_request_communication_log(row) for row in communication_logs],
        'communication_summary': _serialize_request_communication_summary(communication_logs),
    }


def _record_dispatch_incident_event(
    waste_removal_request_id,
    event_type,
    actor_user_id=None,
    actor_email=None,
    source='system',
    details=None,
    occurred_at=None,
):
    request_id = _to_int_or_none(waste_removal_request_id)
    if request_id is None:
        return None
    normalized_type = (str(event_type or '').strip().lower() or 'unknown')[:64]
    normalized_source = (str(source or '').strip().lower() or 'system')[:64]
    row = DispatchIncidentEvent(
        waste_removal_request_id=request_id,
        event_type=normalized_type,
        actor_user_id=_to_int_or_none(actor_user_id),
        actor_email=(_normalize_email(actor_email) or None),
        source=normalized_source,
        details_json=_normalize_auth_audit_details(details),
        created_at=occurred_at or utcnow(),
    )
    db.session.add(row)
    return row


def _build_dispatch_request_timeline(
    booking,
    include_actor_auth=True,
    auth_window_hours=168,
    limit=200,
):
    if not booking:
        return [], {'total_events': 0, 'category_counts': {}}

    try:
        limit = max(1, min(500, int(limit)))
    except (TypeError, ValueError):
        limit = 200
    try:
        auth_window_hours = max(1, min(24 * 30, int(auth_window_hours)))
    except (TypeError, ValueError):
        auth_window_hours = 168

    rows = []
    actor_user_ids = set()

    def _append_event(
        category,
        event_type,
        occurred_at,
        source='system',
        event_id='',
        actor_user_id=None,
        actor_email=None,
        details=None,
    ):
        if not occurred_at:
            return
        normalized_actor_user_id = _to_int_or_none(actor_user_id)
        if normalized_actor_user_id is not None:
            actor_user_ids.add(normalized_actor_user_id)

        rows.append(
            {
                '_occurred_at': occurred_at,
                '_sort_id': str(event_id or ''),
                'id': str(event_id or ''),
                'category': str(category or 'system'),
                'event_type': str(event_type or 'unknown'),
                'source': str(source or 'system'),
                'occurred_at': occurred_at.isoformat() + 'Z',
                'actor_user_id': normalized_actor_user_id,
                'actor_email': _normalize_email(actor_email) or None,
                'actor_name': None,
                'details': _normalize_auth_audit_details(details),
            }
        )

    _append_event(
        'system',
        'request_created',
        booking.created_at,
        source='waste_request',
        event_id='request_created:{}'.format(booking.id),
        actor_email=booking.requester_email,
        details={
            'status': booking.status,
            'material_type': booking.material_type,
            'scheduled_pickup_at': booking.scheduled_pickup_at.isoformat() if booking.scheduled_pickup_at else None,
        },
    )

    match_rows = (
        WasteRemovalMatch.query.filter_by(waste_removal_request_id=booking.id)
        .order_by(WasteRemovalMatch.created_at.asc(), WasteRemovalMatch.id.asc())
        .all()
    )
    for match_row in match_rows:
        _append_event(
            'system',
            'dispatch_match_created',
            match_row.created_at,
            source='matching',
            event_id='match:{}'.format(match_row.id),
            details={
                'provider_name': match_row.provider_name,
                'provider_type': match_row.provider_type,
                'distance_miles': match_row.distance_miles,
                'match_radius_miles': match_row.match_radius_miles,
            },
        )

    accepted_offer_rows = (
        WasteRemovalDispatchOffer.query.filter_by(
            waste_removal_request_id=booking.id,
            status='accepted',
        )
        .order_by(WasteRemovalDispatchOffer.responded_at.asc(), WasteRemovalDispatchOffer.id.asc())
        .all()
    )
    for offer_row in accepted_offer_rows:
        _append_event(
            'system',
            'dispatch_offer_accepted',
            offer_row.responded_at or offer_row.created_at,
            source='dispatch_offer',
            event_id='offer:{}'.format(offer_row.id),
            details={
                'provider_name': offer_row.provider_name,
                'distance_miles': offer_row.distance_miles,
                'offer_rank': offer_row.offer_rank,
            },
        )

    if booking.incident_acknowledged_at:
        _append_event(
            'system',
            'incident_acknowledged_state',
            booking.incident_acknowledged_at,
            source='incident_state',
            event_id='incident_ack_state:{}'.format(booking.id),
            actor_user_id=booking.incident_owner_admin_user_id,
            details={'incident_state': booking.incident_state, 'incident_severity': booking.incident_severity},
        )
    if booking.incident_resolved_at:
        _append_event(
            'system',
            'incident_resolved_state',
            booking.incident_resolved_at,
            source='incident_state',
            event_id='incident_resolved_state:{}'.format(booking.id),
            actor_user_id=booking.incident_owner_admin_user_id,
            details={'incident_state': booking.incident_state, 'incident_severity': booking.incident_severity},
        )

    incident_event_rows = (
        DispatchIncidentEvent.query.filter_by(waste_removal_request_id=booking.id)
        .order_by(DispatchIncidentEvent.created_at.asc(), DispatchIncidentEvent.id.asc())
        .all()
    )
    for incident_row in incident_event_rows:
        _append_event(
            'dispatch',
            incident_row.event_type,
            incident_row.created_at,
            source=incident_row.source,
            event_id='dispatch_event:{}'.format(incident_row.id),
            actor_user_id=incident_row.actor_user_id,
            actor_email=incident_row.actor_email,
            details=incident_row.details_json or {},
        )

    if include_actor_auth and actor_user_ids:
        auth_since = utcnow() - timedelta(hours=auth_window_hours)
        auth_rows = (
            AuthAuditEvent.query.filter(
                AuthAuditEvent.user_id.in_(sorted(actor_user_ids)),
                AuthAuditEvent.occurred_at >= auth_since,
            )
            .order_by(AuthAuditEvent.occurred_at.asc(), AuthAuditEvent.id.asc())
            .all()
        )
        for auth_row in auth_rows:
            _append_event(
                'auth',
                'auth_{}'.format(auth_row.event),
                auth_row.occurred_at,
                source='auth_audit',
                event_id='auth_audit:{}'.format(auth_row.id),
                actor_user_id=auth_row.user_id,
                actor_email=auth_row.email,
                details={
                    'success': bool(auth_row.success),
                    'status_code': auth_row.status_code,
                    'ip': auth_row.ip,
                    'user_agent': auth_row.user_agent,
                    'auth_details': auth_row.details_json or {},
                },
            )

    user_map = {}
    if actor_user_ids:
        user_rows = User.query.filter(User.id.in_(sorted(actor_user_ids))).all()
        user_map = {row.id: row for row in user_rows}

    for row in rows:
        actor_user_id = row.get('actor_user_id')
        actor_user = user_map.get(actor_user_id) if actor_user_id is not None else None
        if actor_user:
            row['actor_name'] = (actor_user.name or actor_user.email or '').strip() or None
            if not row.get('actor_email'):
                row['actor_email'] = _normalize_email(actor_user.email) or None

    rows.sort(key=lambda item: (item['_occurred_at'], item['_sort_id']), reverse=True)
    rows = rows[:limit]
    category_counts = {}
    for row in rows:
        category_key = row.get('category') or 'unknown'
        category_counts[category_key] = category_counts.get(category_key, 0) + 1
        row.pop('_occurred_at', None)
        row.pop('_sort_id', None)

    return rows, {
        'total_events': len(rows),
        'category_counts': category_counts,
    }


def _get_dispatch_incident_context(booking, now=None):
    now = now or utcnow()
    latest_location = (
        WasteRemovalVehicleLocation.query.filter_by(waste_removal_request_id=booking.id)
        .order_by(WasteRemovalVehicleLocation.recorded_at.desc(), WasteRemovalVehicleLocation.id.desc())
        .first()
    )
    flags = _dispatch_incident_flags(booking, latest_location=latest_location, now=now)
    incident = _dispatch_incident_summary(booking, flags, now=now)
    driver = db.session.get(User, booking.assigned_driver_user_id) if booking.assigned_driver_user_id else None
    item = _serialize_dispatch_queue_item(
        booking,
        driver=driver,
        latest_location=latest_location,
        now=now,
    )
    return item


def _dispatch_incident_active_statuses():
    return ['pending_match', 'matched', 'accepted', 'en_route', 'arrived', 'collected']


def _resolve_dispatch_incident_owner_candidate(owner_admin_user_id=None, owner_admin_email=None):
    candidate_id = _to_int_or_none(owner_admin_user_id)
    if candidate_id is not None:
        candidate = db.session.get(User, candidate_id)
        if candidate and (candidate.role or '').strip().lower() == 'admin' and candidate.is_active_user:
            return candidate
        return None

    normalized_email = _normalize_email(owner_admin_email or _dispatch_incident_auto_assign_admin_email())
    if normalized_email:
        candidate = User.query.filter(func.lower(User.email) == normalized_email).first()
        if candidate and (candidate.role or '').strip().lower() == 'admin' and candidate.is_active_user:
            return candidate
        return None

    return (
        User.query.filter(
            func.lower(User.role) == 'admin',
            User.is_active_user.is_(True),
        )
        .order_by(User.id.asc())
        .first()
    )


def _dispatch_incident_is_test_candidate(booking):
    email = _normalize_email(getattr(booking, 'requester_email', None))
    if email:
        if email.endswith('@example.com'):
            return True
        domain = email.split('@')[-1] if '@' in email else ''
        if domain in {'localhost', 'projectdivert.local'} or domain.endswith('.test'):
            return True

    requester_name = (str(getattr(booking, 'requester_name', '') or '').strip().lower())
    if requester_name.startswith(('smoke', 'test', 'qa')):
        return True

    notes = (str(getattr(booking, 'incident_notes', '') or '').strip().lower())
    if 'smoke' in notes or 'test incident' in notes:
        return True

    return False


def _run_dispatch_incident_maintenance(
    *,
    auto_assign=False,
    auto_resolve_test=False,
    resolve_test_minutes=None,
    owner_admin_user_id=None,
    owner_admin_email=None,
    limit=None,
    dry_run=False,
    actor_user_id=None,
    actor_email=None,
    source='system_dispatch_incident_maintenance',
    now=None,
):
    now = now or utcnow()
    limit = _dispatch_incident_maintenance_limit(limit)
    resolve_test_minutes = _dispatch_incident_auto_resolve_test_minutes(resolve_test_minutes)
    auto_assign = bool(auto_assign)
    auto_resolve_test = bool(auto_resolve_test)

    owner_user = None
    if auto_assign or auto_resolve_test:
        owner_user = _resolve_dispatch_incident_owner_candidate(
            owner_admin_user_id=owner_admin_user_id,
            owner_admin_email=owner_admin_email,
        )

    query = WasteRemovalRequest.query.filter(
        WasteRemovalRequest.status.in_(_dispatch_incident_active_statuses())
    )
    rows = (
        query.order_by(WasteRemovalRequest.created_at.asc(), WasteRemovalRequest.id.asc())
        .limit(limit)
        .all()
    )

    scanned = 0
    incident_rows = 0
    actions_planned = 0
    actions_applied = 0
    auto_assigned = 0
    auto_resolved = 0
    skipped_owner_unavailable = 0
    changed_request_ids = []
    escalated_request_ids = []
    items = []
    publish_jobs = []

    for booking in rows:
        scanned += 1
        queue_item = _get_dispatch_incident_context(booking, now=now)
        incident_flags = list(queue_item.get('incident_flags') or [])
        if not incident_flags:
            continue

        incident_rows += 1
        incident_info = queue_item.get('incident') or {}
        incident_state = str(incident_info.get('state') or '').strip().lower()
        created_age_minutes = _minutes_since(getattr(booking, 'created_at', None), now=now) or 0
        is_test_candidate = _dispatch_incident_is_test_candidate(booking)

        # Escalation delivery lives here rather than on the admin read paths:
        # it is an outbound HTTP call, so firing it from a GET made dashboard
        # latency depend on the webhook and made delivery depend on somebody
        # happening to load the page.
        if not dry_run and _dispatch_send_escalation_webhook(
            booking,
            queue_item,
            now=now,
            source=source,
        ):
            escalated_request_ids.append(booking.id)

        can_assign_owner = (
            auto_assign
            and booking.incident_owner_admin_user_id is None
            and incident_state != 'resolved'
            and owner_user is not None
        )
        can_resolve_test = (
            auto_resolve_test
            and incident_state != 'resolved'
            and is_test_candidate
            and created_age_minutes >= resolve_test_minutes
        )

        if auto_assign and booking.incident_owner_admin_user_id is None and owner_user is None:
            skipped_owner_unavailable += 1

        planned_actions = []
        if can_assign_owner:
            planned_actions.append('auto_assign_owner')
        if can_resolve_test:
            planned_actions.append('auto_resolve_test')
        if not planned_actions:
            continue

        actions_planned += len(planned_actions)
        item_summary = {
            'request_id': booking.id,
            'status': booking.status,
            'incident_state': incident_state,
            'incident_flags': incident_flags,
            'created_age_minutes': created_age_minutes,
            'test_candidate': is_test_candidate,
            'planned_actions': planned_actions,
            'applied_actions': [],
        }
        items.append(item_summary)

        if dry_run:
            continue

        if can_assign_owner:
            previous_owner_user_id = booking.incident_owner_admin_user_id
            booking.incident_owner_admin_user_id = owner_user.id
            booking.incident_updated_at = now
            _record_dispatch_incident_event(
                booking.id,
                event_type='incident_owner_auto_assign',
                actor_user_id=actor_user_id,
                actor_email=actor_email,
                source=source,
                details={
                    'previous_owner_admin_user_id': previous_owner_user_id,
                    'owner_admin_user_id': owner_user.id,
                    'automation': True,
                },
                occurred_at=now,
            )
            publish_jobs.append(
                {
                    'request_id': booking.id,
                    'event_name': 'admin_dispatch_incident_owner_reassign',
                    'metadata': {
                        'action': 'owner_reassign',
                        'previous_owner_admin_user_id': previous_owner_user_id,
                        'owner_admin_user_id': owner_user.id,
                        'admin_user_id': actor_user_id,
                        'automation': True,
                    },
                }
            )
            item_summary['applied_actions'].append('auto_assign_owner')
            auto_assigned += 1
            actions_applied += 1

        if can_resolve_test:
            if booking.incident_owner_admin_user_id is None and owner_user is not None:
                previous_owner_user_id = booking.incident_owner_admin_user_id
                booking.incident_owner_admin_user_id = owner_user.id
                _record_dispatch_incident_event(
                    booking.id,
                    event_type='incident_owner_auto_assign',
                    actor_user_id=actor_user_id,
                    actor_email=actor_email,
                    source=source,
                    details={
                        'previous_owner_admin_user_id': previous_owner_user_id,
                        'owner_admin_user_id': owner_user.id,
                        'automation': True,
                        'reason': 'auto_resolve_test',
                    },
                    occurred_at=now,
                )
                publish_jobs.append(
                    {
                        'request_id': booking.id,
                        'event_name': 'admin_dispatch_incident_owner_reassign',
                        'metadata': {
                            'action': 'owner_reassign',
                            'previous_owner_admin_user_id': previous_owner_user_id,
                            'owner_admin_user_id': owner_user.id,
                            'admin_user_id': actor_user_id,
                            'automation': True,
                            'reason': 'auto_resolve_test',
                        },
                    }
                )
                auto_assigned += 1
                actions_applied += 1
                item_summary['applied_actions'].append('auto_assign_owner')

            booking.incident_state = 'resolved'
            booking.incident_updated_at = now
            booking.incident_resolved_at = now
            if not booking.incident_acknowledged_at:
                booking.incident_acknowledged_at = now

            existing_notes = (booking.incident_notes or '').strip()
            note_prefix = '[{} AUTO-RESOLVE] '.format(now.isoformat())
            auto_note = (
                'Resolved stale test incident automatically '
                '(age_minutes={}, threshold_minutes={}).'
            ).format(created_age_minutes, resolve_test_minutes)
            booking.incident_notes = (existing_notes + '\n' if existing_notes else '') + note_prefix + auto_note

            _record_dispatch_incident_event(
                booking.id,
                event_type='incident_auto_resolve_test',
                actor_user_id=actor_user_id,
                actor_email=actor_email,
                source=source,
                details={
                    'incident_state': booking.incident_state,
                    'incident_severity': booking.incident_severity,
                    'incident_flags': incident_flags,
                    'age_minutes': created_age_minutes,
                    'threshold_minutes': resolve_test_minutes,
                    'automation': True,
                },
                occurred_at=now,
            )
            publish_jobs.append(
                {
                    'request_id': booking.id,
                    'event_name': 'admin_dispatch_incident_resolve',
                    'metadata': {
                        'action': 'resolve',
                        'admin_user_id': actor_user_id,
                        'incident_state': booking.incident_state,
                        'incident_severity': booking.incident_severity,
                        'automation': True,
                        'reason': 'stale_test_incident',
                    },
                }
            )
            item_summary['applied_actions'].append('auto_resolve_test')
            auto_resolved += 1
            actions_applied += 1

        if item_summary['applied_actions']:
            changed_request_ids.append(booking.id)

    if not dry_run and (changed_request_ids or escalated_request_ids):
        db.session.commit()
    if not dry_run and changed_request_ids:
        for job in publish_jobs:
            booking = db.session.get(WasteRemovalRequest, job['request_id'])
            if not booking:
                continue
            _publish_waste_request_event(
                booking.id,
                job['event_name'],
                payload=_serialize_waste_request_snapshot(booking),
                metadata=job['metadata'],
            )
            _notify_mobile_push_for_waste_event(
                booking,
                job['event_name'],
                metadata=job['metadata'],
            )

    return {
        'executed_at': now.isoformat() + 'Z',
        'dry_run': bool(dry_run),
        'options': {
            'auto_assign': auto_assign,
            'auto_resolve_test': auto_resolve_test,
            'resolve_test_minutes': resolve_test_minutes,
            'limit': limit,
            'owner_admin_user_id': owner_user.id if owner_user else None,
            'owner_admin_email': _normalize_email(getattr(owner_user, 'email', None)) if owner_user else None,
        },
        'summary': {
            'scanned': scanned,
            'incident_rows': incident_rows,
            'actions_planned': actions_planned,
            'actions_applied': actions_applied if not dry_run else 0,
            'auto_assigned': auto_assigned if not dry_run else 0,
            'auto_resolved_test': auto_resolved if not dry_run else 0,
            'skipped_owner_unavailable': skipped_owner_unavailable,
            'escalations_sent': len(escalated_request_ids) if not dry_run else 0,
            'changed_request_count': len(set(changed_request_ids)) if not dry_run else 0,
        },
        'items': items,
    }
