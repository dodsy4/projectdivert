"""The carbon figure behind a completed collection.

Lifted out of the certificate blueprint so the reports endpoint can total the
same numbers the certificate shows. Two implementations of "how much carbon did
this collection avoid" would disagree eventually, and the one people would
notice is the one on the certificate.
"""

import logging

from flask import current_app

import project_divert_lca
from projectdivert.services.dispatch import _get_latest_match_for_request
from projectdivert.services.lca_glue import _diversion_mass_tonnes
from projectdivert.services.utils import _to_float_or_none

logger = logging.getLogger(__name__)


DEFAULT_LANDFILL_DISTANCE_KM = 25.0


def landfill_distance_km():
    return _to_float_or_none(
        current_app.config.get('CERTIFICATE_LANDFILL_DISTANCE_KM')
    ) or DEFAULT_LANDFILL_DISTANCE_KM


def assess_collection_carbon(booking):
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

    landfill_km = landfill_distance_km()
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
