"""Public diversion certificate.

A shareable page for a completed collection, showing what was diverted and the
carbon avoided by diverting it rather than sending it to landfill.

The figure is computed by the ISO 14040/44 engine at render time from the
request's own material, mass and the real collection distance recorded on the
accepted match -- not read from a stored number -- so the certificate and the
methodology cannot disagree. Where an input is assumed rather than measured,
the page says so.

The upstream implementation this was ported from minted a reference in the
shape of a DEFRA Digital Waste Tracking number. That is not reproduced here: a
reference formatted like a statutory record but issued by us could be mistaken
for one. The reference below is plainly an internal one, and the page says what
it is and is not.
"""

import logging

from flask import Blueprint, abort, render_template

import project_divert_lca
from projectdivert.extensions import db
from projectdivert.models.waste import WasteRemovalRequest
from projectdivert.services.dispatch import _get_latest_match_for_request
from projectdivert.services.lca_glue import _diversion_mass_tonnes
from projectdivert.services.utils import _to_float_or_none

logger = logging.getLogger(__name__)

bp = Blueprint('certificates', __name__)

DEFAULT_LANDFILL_DISTANCE_KM = 25.0


def _landfill_distance_km():
    from flask import current_app

    return _to_float_or_none(
        current_app.config.get('CERTIFICATE_LANDFILL_DISTANCE_KM')
    ) or DEFAULT_LANDFILL_DISTANCE_KM


def _assess(booking):
    """Return (result, context) for the certificate, or (None, reason)."""
    try:
        tonnes = _diversion_mass_tonnes(
            booking.material_type, booking.waste_amount, booking.waste_unit)
    except ValueError as exc:
        return None, str(exc)
    if not tonnes or tonnes <= 0:
        return None, 'The diverted mass is not recorded for this collection.'

    match = _get_latest_match_for_request(booking.id)
    collection_km = None
    if match and match.distance_miles is not None:
        collection_km = float(match.distance_miles) * project_divert_lca.MILES_TO_KM

    landfill_km = _landfill_distance_km()
    measured_collection = collection_km is not None
    if collection_km is None:
        collection_km = landfill_km

    for pathway in ('recycle', 'reuse'):
        try:
            result = project_divert_lca.assess_diversion(
                booking.material_type,
                tonnes,
                collection_distance_km=collection_km,
                landfill_distance_km=landfill_km,
                pathway=pathway,
            )
        except project_divert_lca.LcaDataError:
            continue
        # A pathway with no processing factor for this material reports a
        # warning; prefer one that models the route properly.
        if not any('treated as 0' in w for w in result.warnings):
            return result, {
                'pathway': pathway,
                'tonnes': tonnes,
                'collection_km': collection_km,
                'landfill_km': landfill_km,
                'measured_collection': measured_collection,
                'provider': match.provider_name if match else None,
            }
    return None, 'No emission factors are configured for {}.'.format(booking.material_type)


@bp.route('/certificate/<int:request_id>', methods=['GET'])
def certificate_page(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking or booking.status != 'completed':
        abort(404)

    result, context = _assess(booking)
    if result is None:
        logger.info('Certificate for request %s has no carbon figure: %s', request_id, context)
        return render_template(
            'pages/certificate.html',
            booking=booking,
            reference='PD-{:%Y}-{:05d}'.format(booking.created_at or booking.scheduled_pickup_at, booking.id),
            result=None,
            unavailable_reason=context,
            context=None,
        ), 200

    return render_template(
        'pages/certificate.html',
        booking=booking,
        reference='PD-{:%Y}-{:05d}'.format(booking.created_at or booking.scheduled_pickup_at, booking.id),
        result=result,
        unavailable_reason=None,
        context=context,
    )
