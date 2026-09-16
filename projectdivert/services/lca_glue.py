"""Adapters between request data and the ISO 14040/44 LCA engine."""

import project_divert_lca
from projectdivert.services.geo import _distance_km_or_error


def _normalize_material_name(value):
    if value is None:
        return ''
    cleaned = str(value).replace('\xa0', ' ').strip().lower()
    return ' '.join(cleaned.split())


def _material_factor_key(frame, material_name):
    target = _normalize_material_name(material_name)
    if not target:
        return None
    for key in frame.index.to_list():
        if _normalize_material_name(key) == target:
            return key
    return None


def _factor_value(frame, row_key, column_name):
    value = frame.loc[row_key, column_name]
    if hasattr(value, 'iloc'):
        value = value.iloc[0]
    return float(value)


# Approximate unit masses (tonnes) for materials quoted per item or per m2.
_MATERIAL_ITEM_TONNES = {
    'pallets': 0.025,
    'task chair': 0.015,
    'carpet tiles': 0.0043,
}


_CARPET_TILE_KG_PER_SQM = 4.3


def _diversion_mass_tonnes(material, amount, unit):
    """Convert a user-entered quantity to tonnes for the LCA model."""
    amount = float(amount)
    material_key = _normalize_material_name(material)
    unit_norm = str(unit or '').strip().lower()

    if unit_norm in ('tonnes', 'tonne', 't', 'metric tonnes'):
        return amount
    if unit_norm in ('kg', 'kilograms', 'kilogrammes'):
        return amount / 1000.0
    if unit_norm in ('square meters', 'square metres', 'sq m', 'm2', 'm^2'):
        if material_key == 'carpet tiles':
            return (amount * _CARPET_TILE_KG_PER_SQM) / 1000.0
        raise ValueError(
            'Area units are only supported for carpet tiles. Enter {} in tonnes or kg.'.format(material)
        )
    if unit_norm in ('per item', 'item', 'items', 'each', 'unit', 'units'):
        per_item = _MATERIAL_ITEM_TONNES.get(material_key)
        if per_item is None:
            raise ValueError(
                'No per-item weight is configured for {}. Enter the quantity in tonnes.'.format(material)
            )
        return amount * per_item
    # Fall back to treating the number as tonnes.
    return amount


def assess_diversion_estimate(estimate):
    """Run the ISO 14040/44 LCA model for a stored DiversionEstimate row.

    Returns a template-ready dict comparing the landfill baseline with the reuse
    and recycle diversion pathways, plus the user-supplied cost comparison.
    """
    mass_tonnes = _diversion_mass_tonnes(estimate.material, estimate.amount, estimate.unit)

    # The "traditional" address routes the landfill counterfactual haul; the
    # "divert" address is the reprocessor / reuse destination.
    landfill_distance_km = _distance_km_or_error(
        estimate.traditional_address, estimate.site_address, 'landfill'
    )
    collection_distance_km = _distance_km_or_error(
        estimate.divert_address, estimate.site_address, 'diversion'
    )

    pathways = project_divert_lca.assess_pathways(
        estimate.material,
        mass_tonnes,
        collection_distance_km=collection_distance_km,
        landfill_distance_km=landfill_distance_km,
    )

    traditional_cost = float(estimate.traditional_cost or 0)
    divert_cost = float(estimate.divert_cost or 0)

    return {
        'material': estimate.material,
        'mass_tonnes': mass_tonnes,
        'unit': estimate.unit,
        'functional_unit': project_divert_lca.FUNCTIONAL_UNIT,
        'collection_distance_km': collection_distance_km,
        'landfill_distance_km': landfill_distance_km,
        'baseline_kg': pathways['recycle'].baseline_kg,
        'reuse': pathways['reuse'].as_dict(),
        'recycle': pathways['recycle'].as_dict(),
        'best_net_avoided_kg': max(
            pathways['reuse'].net_avoided_kg, pathways['recycle'].net_avoided_kg
        ),
        'cost': {
            'traditional': traditional_cost,
            'divert': divert_cost,
            'saving': traditional_cost - divert_cost,
        },
        'warnings': sorted(set(pathways['reuse'].warnings) | set(pathways['recycle'].warnings)),
    }
