"""Creating a waste removal request.

One implementation, called by every transport that can raise one: the web form,
the JSON API and the WhatsApp assistant. Previously each had its own copy, and
they had drifted -- the assistant stored a status the dispatch board does not
consider active, and never persisted the dispatch offers it built, so a request
raised over WhatsApp was invisible to operations and could not be claimed by
anyone.

A transport is responsible for reading its own input format, for deciding who
the requester is, and for rendering the outcome. Everything between those two
points lives here.
"""

import logging

from flask import current_app, has_request_context, request

from projectdivert.extensions import db
from projectdivert.models.waste import WasteRemovalRequest
from projectdivert.services import geo
from projectdivert.services.dispatch import (
    _create_dispatch_offers_for_request,
    _serialize_waste_request_snapshot,
)
from projectdivert.services.events import _publish_waste_request_event
from projectdivert.services.geo import _postcode_coordinates
from projectdivert.services.notifications import (
    _notify_dispatch_offers,
    _notify_mobile_push_for_waste_event,
)
from projectdivert.services.utils import _parse_datetime_or_error, _to_float_or_none, utcnow

logger = logging.getLogger(__name__)

#: Every field a request cannot be created without.
REQUIRED_FIELDS = (
    'requester_name',
    'requester_email',
    'material_type',
    'waste_amount',
    'waste_unit',
    'match_radius_miles',
    'pickup_address',
    'pickup_postcode',
    'scheduled_pickup_at',
)

#: The status a new request starts in. Must be one the dispatch board and the
#: incident sweep treat as active, or the request is created and then never
#: looked at again -- which is what happened to WhatsApp bookings.
INITIAL_STATUS = 'pending_match'


class WasteRequestError(ValueError):
    """The submitted request is not valid.

    Subclasses ValueError because the transports already map that to a 400 for
    the caller. ``fields`` names the offending fields when the problem is
    missing input, so the API can report them individually.
    """

    def __init__(self, message, fields=None):
        super().__init__(message)
        self.fields = list(fields or ())


class CreatedWasteRequest:
    """What a successful creation produced, for the transport to render."""

    def __init__(self, booking, provider_candidates, dispatch_offers,
                 drive_time, provider_notifications_sent, match_radius_miles):
        self.booking = booking
        self.provider_candidates = provider_candidates
        self.dispatch_offers = dispatch_offers
        self.drive_time = drive_time
        self.provider_notifications_sent = provider_notifications_sent
        self.match_radius_miles = match_radius_miles

    @property
    def closest_candidate(self):
        return self.provider_candidates[0] if self.provider_candidates else None

    @property
    def offers_created(self):
        return len(self.dispatch_offers)


def _cleaned_required_fields(payload):
    """Trim every required field, and report all the missing ones at once."""
    cleaned = {}
    missing = []
    for field in REQUIRED_FIELDS:
        value = str(payload.get(field) or '').strip()
        cleaned[field] = value
        if not value:
            missing.append(field)
    if missing:
        raise WasteRequestError('Missing required field(s)', fields=missing)
    return cleaned


def _resolve_material_type(material_type, custom_material_type):
    """'Other' means the real type is in the free-text field beside it."""
    if material_type != 'Other':
        return material_type[:120]
    if not custom_material_type:
        raise WasteRequestError(
            'custom_material_type is required when material_type is Other',
            fields=['custom_material_type'],
        )
    return custom_material_type[:120]


def _resolve_base_url(base_url=None):
    """Absolute URL used in provider notification links."""
    if base_url:
        return str(base_url).rstrip('/')
    configured = (current_app.config.get('APP_BASE_URL') or '').strip()
    if configured:
        return configured.rstrip('/')
    if has_request_context():
        return request.url_root.rstrip('/')
    return ''


def create_waste_request(payload, *, base_url=None, notify=True):
    """Validate, persist and dispatch one waste removal request.

    ``payload`` is a flat mapping using the field names in
    :data:`REQUIRED_FIELDS`, plus the optional ``pickup_city``,
    ``pickup_county``, ``notes`` and ``custom_material_type``. Transports build
    it from whatever they received.

    Raises :class:`WasteRequestError` for invalid input and
    :class:`~projectdivert.services.geo.PostcodeLookupUnavailable` when the
    postcode service cannot be reached. The caller owns the rollback, because
    it also owns how the failure is reported.

    ``notify=False`` persists the request and its offers without telling
    anybody, which is what a caller replaying or backfilling wants.
    """
    cleaned = _cleaned_required_fields(payload)

    material_type = _resolve_material_type(
        cleaned['material_type'],
        str(payload.get('custom_material_type') or '').strip(),
    )
    waste_amount = _to_float_or_none(cleaned['waste_amount'])
    if waste_amount is None or waste_amount <= 0:
        raise WasteRequestError(
            'waste_amount must be a positive number', fields=['waste_amount'],
        )

    match_radius_miles = _to_float_or_none(cleaned['match_radius_miles'])
    if match_radius_miles is None or match_radius_miles <= 0:
        raise WasteRequestError(
            'match_radius_miles must be a positive number',
            fields=['match_radius_miles'],
        )

    scheduled_pickup_at = _parse_datetime_or_error(
        cleaned['scheduled_pickup_at'], 'scheduled_pickup_at',
    )
    if scheduled_pickup_at <= utcnow():
        raise WasteRequestError(
            'scheduled_pickup_at must be in the future',
            fields=['scheduled_pickup_at'],
        )

    # Geocoding is the one step that can fail because of something outside the
    # request, so it happens before anything is written.
    pickup_latitude, pickup_longitude = _postcode_coordinates(cleaned['pickup_postcode'])

    booking = WasteRemovalRequest(
        requester_name=cleaned['requester_name'][:120],
        requester_email=cleaned['requester_email'].lower()[:255],
        material_type=material_type,
        waste_amount=waste_amount,
        waste_unit=cleaned['waste_unit'][:32],
        pickup_address=cleaned['pickup_address'][:255],
        pickup_city=(str(payload.get('pickup_city') or '').strip()[:120] or None),
        pickup_county=(str(payload.get('pickup_county') or '').strip()[:120] or None),
        pickup_postcode=cleaned['pickup_postcode'][:32],
        scheduled_pickup_at=scheduled_pickup_at,
        notes=(str(payload.get('notes') or '').strip() or None),
        status=INITIAL_STATUS,
    )
    db.session.add(booking)
    db.session.flush()

    provider_candidates, dispatch_offer_rows = _create_dispatch_offers_for_request(
        booking,
        pickup_latitude,
        pickup_longitude,
        match_radius_miles,
    )
    # _create_dispatch_offers_for_request builds the rows but does not add them;
    # forgetting this is what left WhatsApp bookings with no offers at all.
    if dispatch_offer_rows:
        db.session.add_all(dispatch_offer_rows)

    closest_candidate = provider_candidates[0] if provider_candidates else None
    drive_time = None
    if closest_candidate:
        drive_time = geo._drive_time_between_points(
            pickup_latitude,
            pickup_longitude,
            closest_candidate['provider_latitude'],
            closest_candidate['provider_longitude'],
        )

    db.session.commit()

    provider_notifications_sent = 0
    if notify:
        provider_notifications_sent = _notify_dispatch_offers(
            booking, dispatch_offer_rows, _resolve_base_url(base_url),
        )
        _publish_waste_request_event(
            booking.id,
            'request_created',
            payload=_serialize_waste_request_snapshot(booking),
            metadata={
                'offers_created': len(dispatch_offer_rows),
                'provider_notifications_sent': provider_notifications_sent,
            },
        )
        _notify_mobile_push_for_waste_event(
            booking,
            'request_created',
            metadata={'offers_created': len(dispatch_offer_rows)},
        )

    return CreatedWasteRequest(
        booking=booking,
        provider_candidates=provider_candidates,
        dispatch_offers=dispatch_offer_rows,
        drive_time=drive_time,
        provider_notifications_sent=provider_notifications_sent,
        match_radius_miles=match_radius_miles,
    )
