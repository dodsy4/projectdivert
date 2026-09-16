"""Unit tests for service-layer logic that needs no HTTP request."""

import pandas as pd
import pytest


def test_provider_dispatch_prefers_closest_candidate(app_context, monkeypatch):
    monkeypatch.setattr(
        app_context.reference_data,
        'suppliers',
        pd.DataFrame(
            [
                {
                    'name': 'Provider Near',
                    'sup_type': 'Waste Carrier',
                    'city': 'London',
                    'postcode': 'SW1A1AA',
                    'lat': 51.5073,
                    'long': -0.1277,
                },
                {
                    'name': 'Provider Mid',
                    'sup_type': 'Waste Carrier',
                    'city': 'London',
                    'postcode': 'E11AA',
                    'lat': 51.5350,
                    'long': -0.0900,
                },
            ]
        ),
    )

    best = app_context._select_best_provider_within_radius(51.5072, -0.1276, 25)

    assert best is not None
    assert best['provider_name'] == 'Provider Near'


def test_provider_dispatch_uses_quality_tiebreakers(app_context, monkeypatch):
    monkeypatch.setattr(
        app_context.reference_data,
        'suppliers',
        pd.DataFrame(
            [
                {
                    'name': 'Provider Base',
                    'sup_type': 'Waste Carrier',
                    'city': 'London',
                    'postcode': 'SW1A1AA',
                    'lat': 51.5072,
                    'long': -0.1276,
                    'percent_recyclablenum': 45,
                    'percent_efwnum': 35,
                    'supplier_auditislist_yes_no_na': 'no',
                    'provides_a_rebateyn': '0',
                },
                {
                    'name': 'Provider Quality',
                    'sup_type': 'Waste Carrier',
                    'city': 'London',
                    'postcode': 'SW1A1AA',
                    'lat': 51.5072,
                    'long': -0.1276,
                    'percent_recyclablenum': 92,
                    'percent_efwnum': 4,
                    'supplier_auditislist_yes_no_na': 'yes',
                    'provides_a_rebateyn': '1',
                },
            ]
        ),
    )

    best = app_context._select_best_provider_within_radius(51.5072, -0.1276, 25)

    assert best is not None
    assert best['provider_name'] == 'Provider Quality'


def test_provider_dispatch_parses_numeric_flags(app_context, monkeypatch):
    monkeypatch.setattr(
        app_context.reference_data,
        'suppliers',
        pd.DataFrame(
            [
                {
                    'name': 'Provider No Rebate',
                    'sup_type': 'Waste Carrier',
                    'city': 'London',
                    'postcode': 'SW1A1AA',
                    'lat': 51.5072,
                    'long': -0.1276,
                    'percent_recyclablenum': 90,
                    'percent_efwnum': 5,
                    'supplier_auditislist_yes_no_na': '1.0',
                    'provides_a_rebateyn': '0.0',
                },
                {
                    'name': 'Provider Rebate',
                    'sup_type': 'Waste Carrier',
                    'city': 'London',
                    'postcode': 'SW1A1AA',
                    'lat': 51.5072,
                    'long': -0.1276,
                    'percent_recyclablenum': 90,
                    'percent_efwnum': 5,
                    'supplier_auditislist_yes_no_na': '1.0',
                    'provides_a_rebateyn': '1.0',
                },
            ]
        ),
    )

    best = app_context._select_best_provider_within_radius(51.5072, -0.1276, 25)

    assert best is not None
    assert best['provider_name'] == 'Provider Rebate'


def test_provider_dispatch_uses_stable_name_tiebreaker(app_context, monkeypatch):
    monkeypatch.setattr(
        app_context.reference_data,
        'suppliers',
        pd.DataFrame(
            [
                {
                    'name': 'Provider Zulu',
                    'sup_type': 'Waste Carrier',
                    'city': 'London',
                    'postcode': 'E11AA',
                    'lat': 51.5072,
                    'long': -0.1276,
                    'percent_recyclablenum': 80,
                    'percent_efwnum': 10,
                    'supplier_auditislist_yes_no_na': 'yes',
                    'provides_a_rebateyn': '1',
                },
                {
                    'name': 'Provider Alpha',
                    'sup_type': 'Waste Carrier',
                    'city': 'London',
                    'postcode': 'E11AA',
                    'lat': 51.5072,
                    'long': -0.1276,
                    'percent_recyclablenum': 80,
                    'percent_efwnum': 10,
                    'supplier_auditislist_yes_no_na': 'yes',
                    'provides_a_rebateyn': '1',
                },
            ]
        ),
    )

    candidates = app_context._select_provider_candidates_within_radius(51.5072, -0.1276, 25)

    assert len(candidates) == 2
    assert candidates[0]['provider_name'] == 'Provider Alpha'
    assert candidates[1]['provider_name'] == 'Provider Zulu'


def test_provider_dispatch_exposes_quality_score_and_prefers_higher_score(app_context, monkeypatch):
    monkeypatch.setattr(
        app_context.reference_data,
        'suppliers',
        pd.DataFrame(
            [
                {
                    'name': 'Provider Mid Quality',
                    'sup_type': 'Waste Carrier',
                    'city': 'London',
                    'postcode': 'E11AA',
                    'lat': 51.5072,
                    'long': -0.1276,
                    'percent_recyclablenum': 60,
                    'percent_efwnum': 30,
                    'supplier_auditislist_yes_no_na': 'no',
                    'provides_a_rebateyn': '0',
                },
                {
                    'name': 'Provider High Quality',
                    'sup_type': 'Waste Carrier',
                    'city': 'London',
                    'postcode': 'E11AA',
                    'lat': 51.5072,
                    'long': -0.1276,
                    'percent_recyclablenum': 90,
                    'percent_efwnum': 5,
                    'supplier_auditislist_yes_no_na': 'yes',
                    'provides_a_rebateyn': '1',
                },
            ]
        ),
    )

    candidates = app_context._select_provider_candidates_within_radius(51.5072, -0.1276, 25)

    assert len(candidates) == 2
    assert candidates[0]['provider_name'] == 'Provider High Quality'
    assert candidates[0]['dispatch_quality_score'] > candidates[1]['dispatch_quality_score']


def test_reference_data_can_be_loaded_from_supplier_reference_table(app_context):
    with app_context.app.app_context():
        app_context.db.session.query(app_context.SupplierReference).delete()
        app_context.db.session.add(
            app_context.SupplierReference(
                source_row_index=0,
                sup_type='Waste Carrier',
                name='DB Provider',
                city='London',
                postcode='SW1A1AA',
                lat=51.5072,
                long=-0.1276,
                row_data={
                    'sup_type': 'Waste Carrier',
                    'name': 'DB Provider',
                    'city': 'London',
                    'postcode': 'SW1A1AA',
                    'lat': 51.5072,
                    'long': -0.1276,
                },
            )
        )
        app_context.db.session.commit()

        loaded = app_context._refresh_reference_dataframes_from_db()

    assert loaded is True
    best = app_context._select_best_provider_within_radius(51.5072, -0.1276, 25)
    assert best is not None
    assert best['provider_name'] == 'DB Provider'


def test_assess_estimate_carpet_tiles_area_conversion(app_context, monkeypatch):
    monkeypatch.setattr(app_context.geo, 'numeric_distance', lambda *args, **kwargs: 5.0)

    estimate = app_context.DiversionEstimate(
        material='Carpet Tiles', amount=1000.0, unit='Square Meters',
        site_address='A', traditional_address='B', divert_address='C',
        traditional_cost=100.0, divert_cost=80.0,
    )
    result = app_context.assess_diversion_estimate(estimate)

    # 1000 m2 x 4.3 kg/m2 / 1000 -> 4.3 tonnes
    assert result['mass_tonnes'] == pytest.approx(4.3)
    assert result['recycle']['functional_unit']


def test_assess_estimate_distance_api_failure_raises_error(app_context, monkeypatch):
    monkeypatch.setattr(app_context.geo, 'numeric_distance', lambda *args, **kwargs: None)

    estimate = app_context.DiversionEstimate(
        material='Paper and card', amount=1.0, unit='Tonnes',
        site_address='A', traditional_address='B', divert_address='C',
        traditional_cost=100.0, divert_cost=80.0,
    )
    with pytest.raises(ValueError, match='Distance Matrix API'):
        app_context.assess_diversion_estimate(estimate)


def test_ops_health_digest_cli_dry_run_outputs_snapshot(app_context):
    runner = app_context.app.test_cli_runner()
    result = runner.invoke(
        args=['ops-health-digest', '--dry-run', '--include-ok', '--auth-window-minutes', '60', '--dispatch-limit', '100'],
    )
    assert result.exit_code == 0
    assert '"status"' in result.output
    assert 'Dry run: notifications not sent.' in result.output


def test_waste_request_event_replay_respects_last_event_id(app_context):
    request_id = 991001

    with app_context._waste_request_event_lock:
        app_context._waste_request_event_history.pop(request_id, None)
        app_context._waste_request_event_subscribers.pop(request_id, None)

    app_context._publish_waste_request_event(
        request_id,
        'status_updated',
        payload={'request': {'id': request_id, 'status': 'pending_match'}},
        metadata={'previous_status': 'pending_match', 'new_status': 'matched'},
    )
    app_context._publish_waste_request_event(
        request_id,
        'status_updated',
        payload={'request': {'id': request_id, 'status': 'matched'}},
        metadata={'previous_status': 'pending_match', 'new_status': 'matched'},
    )

    replay_all = app_context._waste_request_replay_events_since(request_id, 0)
    assert len(replay_all) == 2
    first_event_id = int(replay_all[0]['event_id'])
    second_event_id = int(replay_all[1]['event_id'])
    assert second_event_id > first_event_id

    replay_after_first = app_context._waste_request_replay_events_since(request_id, first_event_id)
    assert len(replay_after_first) == 1
    assert int(replay_after_first[0]['event_id']) == second_event_id

    replay_after_second = app_context._waste_request_replay_events_since(request_id, second_event_id)
    assert replay_after_second == []


def test_dispatch_incident_maintenance_cli_dry_run_outputs_summary(app_context):
    runner = app_context.app.test_cli_runner()
    result = runner.invoke(
        args=[
            'dispatch-incident-maintenance',
            '--dry-run',
            '--auto-assign',
            '--auto-resolve-test',
            '--resolve-test-minutes',
            '30',
            '--limit',
            '100',
        ],
    )
    assert result.exit_code == 0
    assert '"summary"' in result.output
