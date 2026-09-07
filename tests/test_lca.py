"""Tests for the ISO 14040/14044-aligned LCA engine (project_divert_lca)."""

import math

import pytest

import project_divert_lca as lca


def test_factor_dataset_loads_and_has_core_materials():
    materials = lca.available_materials()
    assert 'Ferrous metals' in materials
    assert 'Plasterboard' in materials
    factors = lca.load_factors()
    # Every listed material needs the two required stages.
    for material in materials:
        for stage in lca.REQUIRED_STAGES:
            assert lca._lookup(factors, material, stage) is not None, (material, stage)


def test_net_avoided_is_baseline_minus_diversion():
    r = lca.assess_diversion(
        'Ferrous metals', 2.0,
        collection_distance_km=40.0, landfill_distance_km=15.0,
        pathway='recycle',
    )
    assert r.net_avoided_kg == pytest.approx(r.baseline_kg - r.diversion_kg)
    # Steel: huge avoided-virgin credit dominates -> large positive benefit.
    assert r.net_avoided_kg > 3000
    assert r.functional_unit == lca.FUNCTIONAL_UNIT


def test_stage_breakdown_signs_and_provenance():
    r = lca.assess_diversion(
        'Glass', 1.0,
        collection_distance_km=10.0, landfill_distance_km=10.0,
        pathway='recycle',
    )
    by_stage = {s['stage']: s['kg_co2e'] for s in r.stages}
    assert by_stage['virgin_production_avoided'] < 0  # a credit
    assert by_stage['landfill_disposal'] > 0          # a burden
    assert by_stage['collection_transport'] > 0
    assert r.factor_provenance and all('source_url' in p for p in r.factor_provenance)


def test_transport_scales_linearly_with_distance_and_mass():
    near = lca.assess_diversion('Timber', 1.0, collection_distance_km=10.0, landfill_distance_km=0.0)
    far = lca.assess_diversion('Timber', 1.0, collection_distance_km=110.0, landfill_distance_km=0.0)
    near_t = {s['stage']: s['kg_co2e'] for s in near.stages}['collection_transport']
    far_t = {s['stage']: s['kg_co2e'] for s in far.stages}['collection_transport']
    assert far_t == pytest.approx(near_t * 11.0)


def test_unknown_material_raises_lca_data_error():
    with pytest.raises(lca.LcaDataError):
        lca.assess_diversion('Unobtanium', 1.0, collection_distance_km=1.0, landfill_distance_km=1.0)


def test_bad_pathway_and_mass_rejected():
    with pytest.raises(lca.LcaDataError):
        lca.assess_diversion('Glass', 1.0, collection_distance_km=1.0, landfill_distance_km=1.0, pathway='burn')
    with pytest.raises(lca.LcaDataError):
        lca.assess_diversion('Glass', 0.0, collection_distance_km=1.0, landfill_distance_km=1.0)


def test_assess_pathways_returns_reuse_and_recycle():
    both = lca.assess_pathways('Pallets', 3.0, collection_distance_km=25.0, landfill_distance_km=12.0)
    assert set(both) == {'reuse', 'recycle'}
    # Pallets landfill (wood -> methane) makes diversion clearly beneficial.
    assert both['reuse'].net_avoided_kg > 0
    assert both['recycle'].net_avoided_kg > 0


def test_paper_diversion_beats_landfill_methane():
    r = lca.assess_diversion('Paper and card', 1.0, collection_distance_km=30.0, landfill_distance_km=20.0)
    # Landfill of 1 t paper ~ 1041 kg CO2e disposal; diversion must beat that.
    assert r.baseline_kg > 1000
    assert r.net_avoided_kg > 0
