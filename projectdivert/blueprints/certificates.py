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

from projectdivert.extensions import db
from projectdivert.models.waste import WasteRemovalRequest
from projectdivert.services.carbon import assess_collection_carbon

logger = logging.getLogger(__name__)

bp = Blueprint('certificates', __name__)

@bp.route('/certificate/<int:request_id>', methods=['GET'])
def certificate_page(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking or booking.status != 'completed':
        abort(404)

    result, context = assess_collection_carbon(booking)
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
