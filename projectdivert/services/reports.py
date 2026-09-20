"""Aggregate figures across collections.

The certificate answers "what did this one collection avoid". This answers the
same question across a set of them, through the same assessment, so the total
and the certificates that make it up cannot disagree.
"""

import logging

from projectdivert.models.waste import WasteRemovalRequest
from projectdivert.services.carbon import assess_collection_carbon
from projectdivert.services.lca_glue import _diversion_mass_tonnes

logger = logging.getLogger(__name__)

#: Statuses that mean the material actually left the site. Carbon is only
#: claimed for these: a booked collection has avoided nothing yet.
DIVERTED_STATUSES = ('completed',)

#: Assessing carbon runs the model per collection, so a report over an
#: unbounded history would get slow. Callers can ask for less.
DEFAULT_REPORT_LIMIT = 500


def _tonnes_or_none(booking):
    try:
        return _diversion_mass_tonnes(
            booking.material_type, booking.waste_amount, booking.waste_unit,
        )
    except (ValueError, TypeError):
        return None


def collection_report(query, limit=DEFAULT_REPORT_LIMIT):
    """Summarise the collections a query selects.

    ``query`` is already scoped to what the caller may see, so this never
    decides visibility itself.

    Carbon is reported alongside the number of collections it could not be
    calculated for, rather than quietly averaging over them -- a total that
    silently omits collections reads the same as one that includes them.
    """
    rows = (
        query.order_by(WasteRemovalRequest.scheduled_pickup_at.desc())
        .limit(limit)
        .all()
    )

    status_counts = {}
    by_material = {}
    total_tonnes = 0.0
    total_avoided_kg = 0.0
    assessed = 0
    unassessable = []

    for booking in rows:
        status = (booking.status or '').strip().lower() or 'unknown'
        status_counts[status] = status_counts.get(status, 0) + 1

        if status not in DIVERTED_STATUSES:
            continue

        material = booking.material_type or 'Unknown'
        entry = by_material.setdefault(
            material, {'material': material, 'collections': 0,
                       'tonnes': 0.0, 'avoided_kg': 0.0},
        )
        entry['collections'] += 1

        tonnes = _tonnes_or_none(booking)
        if tonnes:
            total_tonnes += tonnes
            entry['tonnes'] += tonnes

        result, context = assess_collection_carbon(booking)
        if result is None:
            unassessable.append({'id': booking.id, 'reason': context})
            continue
        assessed += 1
        total_avoided_kg += result.net_avoided_kg
        entry['avoided_kg'] += result.net_avoided_kg

    materials = sorted(
        by_material.values(), key=lambda row: row['avoided_kg'], reverse=True,
    )
    for row in materials:
        row['tonnes'] = round(row['tonnes'], 3)
        row['avoided_kg'] = round(row['avoided_kg'], 1)

    diverted = sum(status_counts.get(s, 0) for s in DIVERTED_STATUSES)
    return {
        'collections': len(rows),
        'status_counts': status_counts,
        'diverted': {
            'collections': diverted,
            'tonnes': round(total_tonnes, 3),
            'net_avoided_kg_co2e': round(total_avoided_kg, 1),
            'carbon_assessed_collections': assessed,
            # Named rather than counted, so a gap in the emission factors can
            # be chased rather than just noted.
            'carbon_unavailable': unassessable,
        },
        'by_material': materials,
        'limit': limit,
        'truncated': len(rows) >= limit,
    }
