import io
import json
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import pandas as pd
import pytest


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def _fake_postcode_lookup(*args, **kwargs):
    return FakeResponse({'result': {'longitude': -0.1276, 'latitude': 51.5072}})


def _provider_frame():
    return pd.DataFrame(
        [
            {
                'name': 'Provider Alpha',
                'sup_type': 'Waste Carrier',
                'city': 'London',
                'postcode': 'SW1A1AA',
                'lat': 51.5074,
                'long': -0.1278,
            },
            {
                'name': 'Provider Far',
                'sup_type': 'Waste Carrier',
                'city': 'Leeds',
                'postcode': 'LS11AA',
                'lat': 53.8008,
                'long': -1.5491,
            },
        ]
    )


def test_provider_dispatch_prefers_closest_candidate(app_context, monkeypatch):
    monkeypatch.setattr(
        app_context,
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
        app_context,
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
        app_context,
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
        app_context,
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
        app_context,
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


def _create_user(app_context, email, password, role='customer', name='Test User'):
    with app_context.app.app_context():
        user = app_context.User(
            email=email,
            name=name,
            role=role,
            password_hash=app_context.generate_password_hash(password, method='pbkdf2:sha256'),
        )
        app_context.db.session.add(user)
        app_context.db.session.commit()
        return user


def _auth_header(client, email, password):
    response = client.post(
        '/api/v1/auth/login',
        json={
            'email': email,
            'password': password,
        },
    )
    assert response.status_code == 200
    token = response.get_json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def _seed_driver_dispatch_compliance(app_context, driver_email, verifier_email=None):
    with app_context.app.app_context():
        driver = app_context.User.query.filter_by(email=driver_email).first()
        assert driver is not None
        verifier = app_context.User.query.filter_by(email=verifier_email).first() if verifier_email else None
        company_name = f'Seeded Carrier {driver.id}'
        company = app_context.CarrierCompany.query.filter_by(name=company_name).first()
        if not company:
            company = app_context.CarrierCompany(
                name=company_name,
                contact_email=f'carrier{driver.id}@example.com',
                is_active=True,
            )
            app_context.db.session.add(company)
            app_context.db.session.flush()
        driver.carrier_company_id = company.id
        app_context.DriverComplianceDocument.query.filter_by(driver_user_id=driver.id).delete()
        app_context.CompanyComplianceDocument.query.filter_by(carrier_company_id=company.id).delete()
        now = datetime.utcnow()
        expires_at = now + timedelta(days=365)
        for document_type in ['carrier_license', 'insurance_certificate']:
            app_context.db.session.add(
                app_context.DriverComplianceDocument(
                    driver_user_id=driver.id,
                    uploaded_by_user_id=driver.id,
                    verified_by_user_id=verifier.id if verifier else driver.id,
                    document_type=document_type,
                    status='verified',
                    file_url=f'https://example.com/driver-compliance/{driver.id}/{document_type}.pdf',
                    document_reference=f'{document_type.upper()}-{driver.id}',
                    verified_at=now,
                    expires_at=expires_at,
                    metadata_json={'seeded': True},
                )
            )
        for document_type in ['operator_license', 'insurance_certificate']:
            app_context.db.session.add(
                app_context.CompanyComplianceDocument(
                    carrier_company_id=company.id,
                    uploaded_by_user_id=verifier.id if verifier else driver.id,
                    verified_by_user_id=verifier.id if verifier else driver.id,
                    document_type=document_type,
                    status='verified',
                    file_url=f'https://example.com/company-compliance/{company.id}/{document_type}.pdf',
                    document_reference=f'{document_type.upper()}-{company.id}',
                    verified_at=now,
                    expires_at=expires_at,
                    metadata_json={'seeded': True},
                )
            )
        app_context.db.session.commit()


def test_core_get_routes(client):
    expected = {
        '/': 302,
        '/home': 200,
        '/login': 200,
        '/register': 200,
        '/materials': 200,
        '/first': 200,
        '/output': 200,
        '/map': 200,
        '/waste-removal/request': 200,
    }

    for route, status_code in expected.items():
        response = client.get(route)
        assert response.status_code == status_code


def test_output_post_missing_required_fields_does_not_create_record(client, app_context):
    with app_context.app.app_context():
        count_before = app_context.output.query.count()

    response = client.post('/output', data={})

    with app_context.app.app_context():
        count_after = app_context.output.query.count()

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/result')
    assert count_after == count_before


def test_output_post_valid_creates_record(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context, 'numeric_distance', lambda origin, destination: 10.0)

    payload = {
        'material': 'Paper and card',
        'amount': '1',
        'unit': 'Tonnes',
        'site_address': 'London',
        'traditional_address': 'Birmingham',
        'divert_address': 'Manchester',
        'traditional_cost': '100',
        'divert_cost': '80',
    }

    with app_context.app.app_context():
        count_before = app_context.output.query.count()

    response = client.post('/output', data=payload)

    with app_context.app.app_context():
        count_after = app_context.output.query.count()

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/result')
    assert count_after == count_before + 1


def test_material_post_missing_required_fields_does_not_create_record(client, app_context):
    with app_context.app.app_context():
        count_before = app_context.m.query.count()

    response = client.post('/material_input', data={})

    with app_context.app.app_context():
        count_after = app_context.m.query.count()

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/materials')
    assert count_after == count_before


def test_material_post_valid_creates_record(client, app_context, monkeypatch):
    monkeypatch.setattr(
        app_context.requests,
        'get',
        _fake_postcode_lookup,
    )

    payload = {
        'waste_stream': 'Desk',
        'amount': '3',
        'address': '1 Test Street',
        'city': 'London',
        'county': 'Greater London',
        'postcode': 'SW1A1AA',
        'dimensions': '120x60x75',
        'condition': 'Good',
    }

    with app_context.app.app_context():
        count_before = app_context.m.query.count()

    response = client.post('/material_input', data=payload)

    with app_context.app.app_context():
        count_after = app_context.m.query.count()

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/materials')
    assert count_after == count_before + 1


def test_fun_uses_specific_recycle_factor_for_glass(app_context, monkeypatch):
    monkeypatch.setattr(app_context, 'numeric_distance', lambda *args, **kwargs: 10.0)

    result = app_context.fun('Glass', 1.0, 'Tonnes', 'London', 'Birmingham', 'Manchester', 100.0)

    assert result[7] == pytest.approx(670.0)


def test_fun_carpet_tiles_square_meters_conversion_is_case_insensitive(app_context, monkeypatch):
    monkeypatch.setattr(app_context, 'numeric_distance', lambda *args, **kwargs: 0.0)

    reuse_key = app_context._material_factor_key(app_context.reuse_offset, 'Carpet Tiles')
    reuse_factor = app_context._factor_value(
        app_context.reuse_offset,
        reuse_key,
        'Emission Factor (kg CO2 equivalents/ tonne)',
    )
    expected_reuse = (1000.0 * 4.3 / 1000.0) * reuse_factor

    result = app_context.fun('Carpet Tiles', 1000.0, 'Square Meters', 'A', 'B', 'C', 100.0)

    assert result[6] == pytest.approx(expected_reuse)


def test_fun_distance_api_failure_raises_error(app_context, monkeypatch):
    monkeypatch.setattr(app_context, 'numeric_distance', lambda *args, **kwargs: None)

    with pytest.raises(ValueError, match='Google Maps API'):
        app_context.fun('Paper and card', 1.0, 'Tonnes', 'A', 'B', 'C', 100.0)


def test_result_redirects_to_output_when_distance_api_fails(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context, 'numeric_distance', lambda *args, **kwargs: None)

    payload = {
        'material': 'Paper and card',
        'amount': '1',
        'unit': 'Tonnes',
        'site_address': 'London',
        'traditional_address': 'Birmingham',
        'divert_address': 'Manchester',
        'traditional_cost': '100',
        'divert_cost': '80',
    }
    client.post('/output', data=payload)

    response = client.get('/result', follow_redirects=False)

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/output')


def test_waste_removal_request_missing_required_fields_does_not_create_record(client, app_context):
    with app_context.app.app_context():
        count_before = app_context.WasteRemovalRequest.query.count()

    response = client.post('/waste-removal/request', data={})

    with app_context.app.app_context():
        count_after = app_context.WasteRemovalRequest.query.count()

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/waste-removal/request')
    assert count_after == count_before


def test_waste_removal_request_valid_creates_record(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    payload = {
        'requester_name': 'Test User',
        'requester_email': 'test@example.com',
        'material_type': 'Glass',
        'waste_amount': '2.5',
        'waste_unit': 'Tonnes',
        'match_radius_miles': '25',
        'pickup_address': '1 Example Road',
        'pickup_city': 'London',
        'pickup_county': 'Greater London',
        'pickup_postcode': 'SW1A1AA',
        'scheduled_pickup_at': scheduled_time,
        'notes': 'Gate code 1234',
    }

    with app_context.app.app_context():
        count_before = app_context.WasteRemovalRequest.query.count()

    response = client.post('/waste-removal/request', data=payload)

    with app_context.app.app_context():
        count_after = app_context.WasteRemovalRequest.query.count()
        latest = app_context.WasteRemovalRequest.query.order_by(app_context.WasteRemovalRequest.id.desc()).first()
        match_count = app_context.WasteRemovalMatch.query.filter_by(waste_removal_request_id=latest.id).count()
        offer_rows = (
            app_context.WasteRemovalDispatchOffer.query.filter_by(waste_removal_request_id=latest.id)
            .order_by(app_context.WasteRemovalDispatchOffer.offer_rank.asc())
            .all()
        )

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/waste-removal/request')
    assert count_after == count_before + 1
    assert latest.material_type == 'Glass'
    assert latest.waste_amount == pytest.approx(2.5)
    assert latest.status == 'pending_match'
    assert match_count == 0
    assert len(offer_rows) == 1
    assert offer_rows[0].provider_name == 'Provider Alpha'


def test_waste_removal_request_past_time_is_rejected(client, app_context):
    past_time = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M')
    payload = {
        'requester_name': 'Test User',
        'requester_email': 'test@example.com',
        'material_type': 'Glass',
        'waste_amount': '1',
        'waste_unit': 'Tonnes',
        'match_radius_miles': '25',
        'pickup_address': '1 Example Road',
        'pickup_postcode': 'SW1A1AA',
        'scheduled_pickup_at': past_time,
    }

    with app_context.app.app_context():
        count_before = app_context.WasteRemovalRequest.query.count()

    response = client.post('/waste-removal/request', data=payload)

    with app_context.app.app_context():
        count_after = app_context.WasteRemovalRequest.query.count()

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/waste-removal/request')
    assert count_after == count_before


def test_waste_removal_request_no_provider_in_radius_sets_pending(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(
        app_context,
        'suppliers',
        pd.DataFrame(
            [
                {
                    'name': 'Provider Far',
                    'sup_type': 'Waste Carrier',
                    'city': 'Leeds',
                    'postcode': 'LS11AA',
                    'lat': 53.8008,
                    'long': -1.5491,
                }
            ]
        ),
    )

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    payload = {
        'requester_name': 'Test User',
        'requester_email': 'test@example.com',
        'material_type': 'Glass',
        'waste_amount': '2.5',
        'waste_unit': 'Tonnes',
        'match_radius_miles': '1',
        'pickup_address': '1 Example Road',
        'pickup_postcode': 'SW1A1AA',
        'scheduled_pickup_at': scheduled_time,
    }

    response = client.post('/waste-removal/request', data=payload)

    with app_context.app.app_context():
        latest = app_context.WasteRemovalRequest.query.order_by(app_context.WasteRemovalRequest.id.desc()).first()
        match_count = app_context.WasteRemovalMatch.query.filter_by(waste_removal_request_id=latest.id).count()

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/waste-removal/request')
    assert latest.status == 'pending_match'
    assert match_count == 0


def test_waste_removal_request_sends_notification_email(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context,
        '_drive_time_between_points',
        lambda *args, **kwargs: {'minutes': 32.0, 'text': '32 mins'},
    )

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    payload = {
        'requester_name': 'Test User',
        'requester_email': 'test@example.com',
        'material_type': 'Glass',
        'waste_amount': '2.5',
        'waste_unit': 'Tonnes',
        'match_radius_miles': '25',
        'pickup_address': '1 Example Road',
        'pickup_city': 'London',
        'pickup_county': 'Greater London',
        'pickup_postcode': 'SW1A1AA',
        'scheduled_pickup_at': scheduled_time,
    }

    app_context.app.config['WASTE_REMOVAL_NOTIFICATION_EMAIL'] = 'ops@example.com'
    captured = {}

    def _fake_send(to_email, subject, text_body, html_body=None):
        captured['to_email'] = to_email
        captured['subject'] = subject
        captured['text_body'] = text_body
        return True

    monkeypatch.setattr(app_context, '_send_material_request_email', _fake_send)

    response = client.post('/waste-removal/request', data=payload)

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/waste-removal/request')
    assert captured['to_email'] == 'ops@example.com'
    assert 'New waste removal request' in captured['subject']
    assert 'Waste Amount: 2.5 Tonnes' in captured['text_body']
    assert 'Dispatch Offers Created: 1' in captured['text_body']
    assert 'Closest Provider Candidate: Provider Alpha' in captured['text_body']
    assert 'Estimated Drive Time: 32 mins' in captured['text_body']


def test_api_requires_bearer_token(client):
    response = client.post('/api/v1/waste-requests', json={})
    assert response.status_code == 401
    assert response.get_json()['error'] == 'Missing Bearer token'


def test_api_create_waste_request_returns_match_and_drive_time(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context,
        '_drive_time_between_points',
        lambda *args, **kwargs: {'minutes': 18.0, 'text': '18 mins'},
    )
    _create_user(app_context, 'mobile@example.com', 'Password123!', role='customer', name='Mobile User')
    headers = _auth_header(client, 'mobile@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    payload = {
        'requester_name': 'Mobile User',
        'requester_email': 'spoofed@example.com',
        'material_type': 'Glass',
        'waste_amount': 2.0,
        'waste_unit': 'Tonnes',
        'match_radius_miles': 25,
        'pickup_address': '1 Example Road',
        'pickup_city': 'London',
        'pickup_county': 'Greater London',
        'pickup_postcode': 'SW1A1AA',
        'scheduled_pickup_at': scheduled_time,
        'notes': 'Ring bell',
    }

    response = client.post('/api/v1/waste-requests', json=payload, headers=headers)
    body = response.get_json()

    assert response.status_code == 201
    assert body['request']['status'] == 'pending_match'
    assert body['request']['requester_email'] == 'mobile@example.com'
    assert body['match'] is None
    assert body['drive_time']['text'] == '18 mins'
    assert body['dispatch']['offers_created'] == 1


def test_api_status_and_location_flow(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context,
        '_drive_time_between_points',
        lambda *args, **kwargs: {'minutes': 12.0, 'text': '12 mins'},
    )
    _create_user(app_context, 'customer@example.com', 'Password123!', role='customer', name='Customer')
    _create_user(app_context, 'driver@example.com', 'Password123!', role='driver', name='Driver')
    _seed_driver_dispatch_compliance(app_context, 'driver@example.com')
    customer_headers = _auth_header(client, 'customer@example.com', 'Password123!')
    driver_headers = _auth_header(client, 'driver@example.com', 'Password123!')
    with app_context.app.app_context():
        driver_user = app_context.User.query.filter_by(email='driver@example.com').first()
        driver_user_id = driver_user.id

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_payload = {
        'requester_name': 'Driver Test',
        'requester_email': 'customer@example.com',
        'material_type': 'Glass',
        'waste_amount': 1.0,
        'waste_unit': 'Tonnes',
        'match_radius_miles': 25,
        'pickup_address': '1 Example Road',
        'pickup_postcode': 'SW1A1AA',
        'scheduled_pickup_at': scheduled_time,
    }

    create_response = client.post('/api/v1/waste-requests', json=create_payload, headers=customer_headers)
    request_id = create_response.get_json()['request']['id']

    with app_context.app.app_context():
        offer = app_context.WasteRemovalDispatchOffer.query.filter_by(waste_removal_request_id=request_id).first()
        offer_token = offer.offer_token

    accept_response = client.post(
        f'/api/v1/waste-requests/{request_id}/dispatch/accept',
        json={'offer_token': offer_token},
        headers=driver_headers,
    )
    assert accept_response.status_code == 200
    assert accept_response.get_json()['match']['provider_name'] == 'Provider Alpha'
    assert accept_response.get_json()['request']['assigned_driver_user_id'] == driver_user_id

    status_response = client.post(
        f'/api/v1/waste-requests/{request_id}/status',
        json={'status': 'en_route'},
        headers=driver_headers,
    )
    assert status_response.status_code == 200
    assert status_response.get_json()['request']['status'] == 'en_route'

    location_response = client.post(
        f'/api/v1/waste-requests/{request_id}/location',
        json={
            'latitude': 51.509,
            'longitude': -0.128,
            'driver_id': 'driver-1',
            'vehicle_id': 'van-42',
        },
        headers=driver_headers,
    )
    assert location_response.status_code == 201

    latest_response = client.get(
        f'/api/v1/waste-requests/{request_id}/location/latest',
        headers=customer_headers,
    )
    latest_body = latest_response.get_json()

    assert latest_response.status_code == 200
    assert latest_body['request_status'] == 'en_route'
    assert latest_body['latest_location']['driver_id'] == str(driver_user_id)
    assert latest_body['latest_location']['vehicle_id'] == 'van-42'


def test_api_dispatch_first_accept_wins(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(
        app_context,
        'suppliers',
        pd.DataFrame(
            [
                {
                    'name': 'Provider One',
                    'sup_type': 'Waste Carrier',
                    'city': 'London',
                    'postcode': 'SW1A1AA',
                    'lat': 51.5072,
                    'long': -0.1276,
                },
                {
                    'name': 'Provider Two',
                    'sup_type': 'Waste Carrier',
                    'city': 'London',
                    'postcode': 'SW1A1AA',
                    'lat': 51.5073,
                    'long': -0.1277,
                },
            ]
        ),
    )
    _create_user(app_context, 'customer@example.com', 'Password123!', role='customer', name='Customer')
    _create_user(app_context, 'driver1@example.com', 'Password123!', role='driver', name='Driver One')
    _create_user(app_context, 'driver2@example.com', 'Password123!', role='driver', name='Driver Two')
    _seed_driver_dispatch_compliance(app_context, 'driver1@example.com')
    _seed_driver_dispatch_compliance(app_context, 'driver2@example.com')
    customer_headers = _auth_header(client, 'customer@example.com', 'Password123!')
    driver_one_headers = _auth_header(client, 'driver1@example.com', 'Password123!')
    driver_two_headers = _auth_header(client, 'driver2@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_payload = {
        'requester_name': 'Customer',
        'requester_email': 'customer@example.com',
        'material_type': 'Glass',
        'waste_amount': 1.0,
        'waste_unit': 'Tonnes',
        'match_radius_miles': 25,
        'pickup_address': '1 Example Road',
        'pickup_postcode': 'SW1A1AA',
        'scheduled_pickup_at': scheduled_time,
    }
    create_response = client.post('/api/v1/waste-requests', json=create_payload, headers=customer_headers)
    request_id = create_response.get_json()['request']['id']

    with app_context.app.app_context():
        offers = (
            app_context.WasteRemovalDispatchOffer.query.filter_by(waste_removal_request_id=request_id)
            .order_by(app_context.WasteRemovalDispatchOffer.offer_rank.asc())
            .all()
        )
        first_token = offers[0].offer_token
        second_token = offers[1].offer_token

    first_accept = client.post(
        f'/api/v1/waste-requests/{request_id}/dispatch/accept',
        json={'offer_token': first_token},
        headers=driver_one_headers,
    )
    assert first_accept.status_code == 200
    assert first_accept.get_json()['request']['status'] == 'matched'

    second_accept = client.post(
        f'/api/v1/waste-requests/{request_id}/dispatch/accept',
        json={'offer_token': second_token},
        headers=driver_two_headers,
    )
    assert second_accept.status_code == 409
    assert second_accept.get_json()['error'] == 'Request is assigned to a different driver'

    unauthorized_status = client.post(
        f'/api/v1/waste-requests/{request_id}/status',
        json={'status': 'en_route'},
        headers=driver_two_headers,
    )
    assert unauthorized_status.status_code == 403

    unauthorized_location = client.post(
        f'/api/v1/waste-requests/{request_id}/location',
        json={
            'latitude': 51.509,
            'longitude': -0.128,
            'vehicle_id': 'van-2',
        },
        headers=driver_two_headers,
    )
    assert unauthorized_location.status_code == 403


def test_api_customer_cannot_update_status(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context,
        '_drive_time_between_points',
        lambda *args, **kwargs: {'minutes': 10.0, 'text': '10 mins'},
    )
    _create_user(app_context, 'customer@example.com', 'Password123!', role='customer', name='Customer')
    headers = _auth_header(client, 'customer@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_payload = {
        'requester_name': 'Customer',
        'requester_email': 'customer@example.com',
        'material_type': 'Glass',
        'waste_amount': 1.0,
        'waste_unit': 'Tonnes',
        'match_radius_miles': 25,
        'pickup_address': '1 Example Road',
        'pickup_postcode': 'SW1A1AA',
        'scheduled_pickup_at': scheduled_time,
    }
    create_response = client.post('/api/v1/waste-requests', json=create_payload, headers=headers)
    request_id = create_response.get_json()['request']['id']

    status_response = client.post(
        f'/api/v1/waste-requests/{request_id}/status',
        json={'status': 'en_route'},
        headers=headers,
    )
    assert status_response.status_code == 403


def test_api_customer_cannot_read_other_customer_request(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context,
        '_drive_time_between_points',
        lambda *args, **kwargs: {'minutes': 10.0, 'text': '10 mins'},
    )
    _create_user(app_context, 'customer1@example.com', 'Password123!', role='customer', name='Customer 1')
    _create_user(app_context, 'customer2@example.com', 'Password123!', role='customer', name='Customer 2')
    owner_headers = _auth_header(client, 'customer1@example.com', 'Password123!')
    other_headers = _auth_header(client, 'customer2@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_payload = {
        'requester_name': 'Customer 1',
        'requester_email': 'customer1@example.com',
        'material_type': 'Glass',
        'waste_amount': 1.0,
        'waste_unit': 'Tonnes',
        'match_radius_miles': 25,
        'pickup_address': '1 Example Road',
        'pickup_postcode': 'SW1A1AA',
        'scheduled_pickup_at': scheduled_time,
    }
    create_response = client.post('/api/v1/waste-requests', json=create_payload, headers=owner_headers)
    request_id = create_response.get_json()['request']['id']

    forbidden_response = client.get(f'/api/v1/waste-requests/{request_id}', headers=other_headers)
    assert forbidden_response.status_code == 403


def _reset_auth_security_runtime_state(app_context):
    with app_context._auth_rate_limit_lock:
        app_context._auth_rate_limit_events.clear()
    with app_context._auth_login_lockout_lock:
        app_context._auth_login_lockouts.clear()
    app_context._auth_rate_limit_redis_client = None
    app_context._auth_rate_limit_redis_disabled = False


def test_auth_login_lockout_triggers_and_blocks_until_expiry(client, app_context):
    _create_user(app_context, 'lockout@example.com', 'Password123!', role='customer', name='Lockout User')

    overrides = {
        'AUTH_RATE_LIMIT_ENABLED': False,
        'AUTH_LOGIN_LOCKOUT_ENABLED': True,
        'AUTH_LOGIN_LOCKOUT_MAX_ATTEMPTS': 3,
        'AUTH_LOGIN_LOCKOUT_WINDOW_SECONDS': 300,
        'AUTH_LOGIN_LOCKOUT_DURATION_SECONDS': 120,
        'AUTH_REQUIRE_EMAIL_VERIFICATION': False,
    }
    original = {key: app_context.app.config.get(key) for key in overrides}
    app_context.app.config.update(overrides)
    _reset_auth_security_runtime_state(app_context)

    try:
        for _ in range(2):
            response = client.post(
                '/api/v1/auth/login',
                json={'email': 'lockout@example.com', 'password': 'WrongPass123'},
            )
            assert response.status_code == 401

        trigger = client.post(
            '/api/v1/auth/login',
            json={'email': 'lockout@example.com', 'password': 'WrongPass123'},
        )
        assert trigger.status_code == 429
        assert 'Retry-After' in trigger.headers
        assert trigger.get_json()['error'] == 'Too many failed login attempts. Please try again later.'

        blocked = client.post(
            '/api/v1/auth/login',
            json={'email': 'lockout@example.com', 'password': 'Password123!'},
        )
        assert blocked.status_code == 429
        assert blocked.get_json()['error'] == 'Too many failed login attempts. Please try again later.'

        with app_context.app.app_context():
            rows = (
                app_context.AuthAuditEvent.query.filter_by(event='login', email='lockout@example.com')
                .order_by(app_context.AuthAuditEvent.id.asc())
                .all()
            )
            reasons = [str((row.details_json or {}).get('reason') or '') for row in rows]

        assert 'lockout_triggered' in reasons
        assert 'lockout_active' in reasons
    finally:
        app_context.app.config.update(original)
        _reset_auth_security_runtime_state(app_context)


def test_auth_login_rate_limit_applies_before_credentials_check(client, app_context):
    overrides = {
        'AUTH_RATE_LIMIT_ENABLED': True,
        'AUTH_RATE_LIMIT_WINDOW_SECONDS': 120,
        'AUTH_RATE_LIMIT_LOGIN_MAX_ATTEMPTS': 2,
        'AUTH_LOGIN_LOCKOUT_ENABLED': False,
        'AUTH_REQUIRE_EMAIL_VERIFICATION': False,
    }
    original = {key: app_context.app.config.get(key) for key in overrides}
    app_context.app.config.update(overrides)
    _reset_auth_security_runtime_state(app_context)

    try:
        first = client.post(
            '/api/v1/auth/login',
            json={'email': 'missing@example.com', 'password': 'WrongPass123'},
        )
        second = client.post(
            '/api/v1/auth/login',
            json={'email': 'missing@example.com', 'password': 'WrongPass123'},
        )
        third = client.post(
            '/api/v1/auth/login',
            json={'email': 'missing@example.com', 'password': 'WrongPass123'},
        )

        assert first.status_code == 401
        assert second.status_code == 401
        assert third.status_code == 429
        assert third.get_json()['error'] == 'Too many attempts. Please try again later.'
        assert 'Retry-After' in third.headers

        with app_context.app.app_context():
            rows = (
                app_context.AuthAuditEvent.query.filter_by(event='login', email='missing@example.com')
                .order_by(app_context.AuthAuditEvent.id.asc())
                .all()
            )
            reasons = [str((row.details_json or {}).get('reason') or '') for row in rows]

        assert reasons[-1] == 'rate_limited'
    finally:
        app_context.app.config.update(original)
        _reset_auth_security_runtime_state(app_context)


def test_auth_login_lockout_escalates_duration_on_repeated_lockouts(client, app_context):
    _create_user(app_context, 'escalate@example.com', 'Password123!', role='customer', name='Escalate User')

    overrides = {
        'AUTH_RATE_LIMIT_ENABLED': False,
        'AUTH_LOGIN_LOCKOUT_ENABLED': True,
        'AUTH_LOGIN_LOCKOUT_MAX_ATTEMPTS': 2,
        'AUTH_LOGIN_LOCKOUT_WINDOW_SECONDS': 300,
        'AUTH_LOGIN_LOCKOUT_DURATION_SECONDS': 60,
        'AUTH_LOGIN_LOCKOUT_ESCALATION_ENABLED': True,
        'AUTH_LOGIN_LOCKOUT_ESCALATION_FACTOR': 2,
        'AUTH_LOGIN_LOCKOUT_ESCALATION_RESET_SECONDS': 3600,
        'AUTH_LOGIN_LOCKOUT_MAX_DURATION_SECONDS': 300,
        'AUTH_REQUIRE_EMAIL_VERIFICATION': False,
    }
    original = {key: app_context.app.config.get(key) for key in overrides}
    app_context.app.config.update(overrides)
    _reset_auth_security_runtime_state(app_context)

    try:
        first_attempt = client.post(
            '/api/v1/auth/login',
            json={'email': 'escalate@example.com', 'password': 'WrongPass123'},
        )
        first_lock = client.post(
            '/api/v1/auth/login',
            json={'email': 'escalate@example.com', 'password': 'WrongPass123'},
        )
        assert first_attempt.status_code == 401
        assert first_lock.status_code == 429
        first_retry_after = int(first_lock.headers['Retry-After'])

        # Simulate lockout expiry without waiting so we can trigger a second lockout cycle.
        with app_context._auth_login_lockout_lock:
            for key, state in list(app_context._auth_login_lockouts.items()):
                if not key.startswith('ip:') and not key.endswith('escalate@example.com'):
                    continue
                state['locked_until'] = datetime.utcnow() - timedelta(seconds=1)
                state['count'] = 0
                state['first_failed_at'] = None
                app_context._auth_login_lockouts[key] = state

        second_attempt = client.post(
            '/api/v1/auth/login',
            json={'email': 'escalate@example.com', 'password': 'WrongPass123'},
        )
        second_lock = client.post(
            '/api/v1/auth/login',
            json={'email': 'escalate@example.com', 'password': 'WrongPass123'},
        )
        assert second_attempt.status_code == 401
        assert second_lock.status_code == 429
        second_retry_after = int(second_lock.headers['Retry-After'])
        assert second_retry_after > first_retry_after

        with app_context.app.app_context():
            latest = (
                app_context.AuthAuditEvent.query.filter_by(event='login', email='escalate@example.com')
                .order_by(app_context.AuthAuditEvent.id.desc())
                .first()
            )
            details = latest.details_json or {}

        assert details.get('reason') == 'lockout_triggered'
        assert int(details.get('lockout_level') or 0) >= 2
    finally:
        app_context.app.config.update(original)
        _reset_auth_security_runtime_state(app_context)


def test_auth_lockout_revokes_sessions_when_suspicious_activity_enabled(client, app_context):
    _create_user(app_context, 'suspicious@example.com', 'Password123!', role='customer', name='Suspicious User')
    login = client.post(
        '/api/v1/auth/login',
        json={'email': 'suspicious@example.com', 'password': 'Password123!'},
    )
    assert login.status_code == 200

    overrides = {
        'AUTH_RATE_LIMIT_ENABLED': False,
        'AUTH_LOGIN_LOCKOUT_ENABLED': True,
        'AUTH_LOGIN_LOCKOUT_MAX_ATTEMPTS': 2,
        'AUTH_LOGIN_LOCKOUT_WINDOW_SECONDS': 300,
        'AUTH_LOGIN_LOCKOUT_DURATION_SECONDS': 120,
        'AUTH_LOGIN_LOCKOUT_ESCALATION_ENABLED': False,
        'AUTH_SUSPICIOUS_ACTIVITY_REVOKE_SESSIONS': True,
        'AUTH_SUSPICIOUS_ACTIVITY_REVOKE_MIN_LOCKOUT_LEVEL': 1,
        'AUTH_REQUIRE_EMAIL_VERIFICATION': False,
    }
    original = {key: app_context.app.config.get(key) for key in overrides}
    app_context.app.config.update(overrides)
    _reset_auth_security_runtime_state(app_context)

    try:
        first = client.post(
            '/api/v1/auth/login',
            json={'email': 'suspicious@example.com', 'password': 'WrongPass123'},
        )
        lockout = client.post(
            '/api/v1/auth/login',
            json={'email': 'suspicious@example.com', 'password': 'WrongPass123'},
        )
        assert first.status_code == 401
        assert lockout.status_code == 429

        with app_context.app.app_context():
            user = app_context.User.query.filter_by(email='suspicious@example.com').first()
            assert user is not None
            assert user.access_token_revoked_at is not None

            active_refresh = (
                app_context.AuthLifecycleToken.query.filter_by(
                    user_id=user.id,
                    token_type='refresh',
                )
                .filter(app_context.AuthLifecycleToken.revoked_at.is_(None))
                .count()
            )
            assert active_refresh == 0

            latest = (
                app_context.AuthAuditEvent.query.filter_by(event='login', email='suspicious@example.com')
                .order_by(app_context.AuthAuditEvent.id.desc())
                .first()
            )
            details = latest.details_json or {}

        assert details.get('reason') == 'lockout_triggered'
        assert details.get('sessions_revoked') is True
    finally:
        app_context.app.config.update(original)
        _reset_auth_security_runtime_state(app_context)


def test_admin_api_rate_limit_applies_per_ip_and_user(client, app_context):
    _create_user(app_context, 'adminratelimit@example.com', 'Password123!', role='admin', name='Admin Limit')
    admin_headers = _auth_header(client, 'adminratelimit@example.com', 'Password123!')

    overrides = {
        'AUTH_RATE_LIMIT_ENABLED': True,
        'AUTH_RATE_LIMIT_ADMIN_ENABLED': True,
        'AUTH_RATE_LIMIT_WINDOW_SECONDS': 120,
        'AUTH_RATE_LIMIT_ADMIN_MAX_ATTEMPTS': 2,
        'AUTH_REQUIRE_EMAIL_VERIFICATION': False,
    }
    original = {key: app_context.app.config.get(key) for key in overrides}
    app_context.app.config.update(overrides)
    _reset_auth_security_runtime_state(app_context)

    try:
        first = client.get('/api/v1/admin/auth-audit?limit=1', headers=admin_headers)
        second = client.get('/api/v1/admin/auth-audit?limit=1', headers=admin_headers)
        third = client.get('/api/v1/admin/auth-audit?limit=1', headers=admin_headers)

        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 429
        assert third.get_json()['error'] == 'Too many admin API requests. Please try again later.'
        assert 'Retry-After' in third.headers
    finally:
        app_context.app.config.update(original)
        _reset_auth_security_runtime_state(app_context)


def test_admin_auth_blocklist_can_block_and_unblock_login(client, app_context):
    _create_user(app_context, 'adminsec@example.com', 'Password123!', role='admin', name='Security Admin')
    _create_user(app_context, 'blocked@example.com', 'Password123!', role='customer', name='Blocked User')
    admin_headers = _auth_header(client, 'adminsec@example.com', 'Password123!')

    _reset_auth_security_runtime_state(app_context)

    create_block = client.post(
        '/api/v1/admin/auth-security/blocks',
        headers=admin_headers,
        json={
            'identifier_type': 'email',
            'identifier_value': 'blocked@example.com',
            'reason': 'test_block',
            'expires_in_seconds': 600,
        },
    )
    assert create_block.status_code == 201
    block_id = create_block.get_json()['block']['id']

    blocked_login = client.post(
        '/api/v1/auth/login',
        json={'email': 'blocked@example.com', 'password': 'Password123!'},
    )
    assert blocked_login.status_code == 403
    blocked_payload = blocked_login.get_json()
    assert blocked_payload['error'] == 'Access temporarily blocked'
    assert blocked_payload['reason'] == 'test_block'

    list_blocks = client.get(
        '/api/v1/admin/auth-security/blocks?active=true&identifier_type=email&identifier_value=blocked@example.com',
        headers=admin_headers,
    )
    assert list_blocks.status_code == 200
    listed_ids = [row['id'] for row in list_blocks.get_json()['items']]
    assert block_id in listed_ids

    unblock = client.post(
        f'/api/v1/admin/auth-security/blocks/{block_id}/unblock',
        headers=admin_headers,
        json={'reason': 'manual release'},
    )
    assert unblock.status_code == 200
    assert unblock.get_json()['revoked'] is True

    login_after_unblock = client.post(
        '/api/v1/auth/login',
        json={'email': 'blocked@example.com', 'password': 'Password123!'},
    )
    assert login_after_unblock.status_code == 200
    assert login_after_unblock.get_json()['user']['email'] == 'blocked@example.com'


def test_admin_auth_security_telemetry_reports_failed_login_activity(client, app_context):
    _create_user(app_context, 'admintelemetry@example.com', 'Password123!', role='admin', name='Telemetry Admin')
    _create_user(app_context, 'telemetryuser@example.com', 'Password123!', role='customer', name='Telemetry User')
    admin_headers = _auth_header(client, 'admintelemetry@example.com', 'Password123!')

    _reset_auth_security_runtime_state(app_context)

    failed = client.post(
        '/api/v1/auth/login',
        json={'email': 'telemetryuser@example.com', 'password': 'WrongPass123'},
        headers={'User-Agent': 'pytest-agent/telemetry'},
    )
    assert failed.status_code == 401

    telemetry = client.get(
        '/api/v1/admin/auth-security/telemetry?minutes=120&limit=20',
        headers=admin_headers,
    )
    assert telemetry.status_code == 200
    payload = telemetry.get_json()

    assert payload['considered_events'] >= 1
    assert isinstance(payload['top_failed_emails'], list)
    assert any(row['email'] == 'telemetryuser@example.com' for row in payload['top_failed_emails'])


def test_admin_ops_health_endpoint_returns_summary(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context,
        '_drive_time_between_points',
        lambda *args, **kwargs: {'minutes': 10.0, 'text': '10 mins'},
    )
    _create_user(app_context, 'opshealthadmin@example.com', 'Password123!', role='admin', name='Ops Health Admin')
    _create_user(app_context, 'opshealthcustomer@example.com', 'Password123!', role='customer', name='Ops Customer')
    admin_headers = _auth_header(client, 'opshealthadmin@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'opshealthcustomer@example.com', 'Password123!')

    original_pending = app_context.app.config.get('DISPATCH_PENDING_MATCH_SLA_MINUTES')
    app_context.app.config['DISPATCH_PENDING_MATCH_SLA_MINUTES'] = 0

    try:
        client.post(
            '/api/v1/auth/login',
            json={'email': 'opshealthcustomer@example.com', 'password': 'WrongPass123'},
        )

        scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
        create_response = client.post(
            '/api/v1/waste-requests',
            json={
                'requester_name': 'Ops Customer',
                'requester_email': 'opshealthcustomer@example.com',
                'material_type': 'Glass',
                'waste_amount': 1.0,
                'waste_unit': 'Tonnes',
                'match_radius_miles': 25,
                'pickup_address': '1 Example Road',
                'pickup_postcode': 'SW1A1AA',
                'scheduled_pickup_at': scheduled_time,
            },
            headers=customer_headers,
        )
        assert create_response.status_code == 201
        request_id = create_response.get_json()['request']['id']
        with app_context.app.app_context():
            booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
            booking.created_at = datetime.utcnow() - timedelta(minutes=4)
            app_context.db.session.commit()

        response = client.get(
            '/api/v1/admin/ops/health?auth_window_minutes=120&dispatch_limit=200',
            headers=admin_headers,
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload['status'] in {'ok', 'warning', 'critical'}
        assert 'metrics' in payload
        assert 'auth' in payload['metrics']
        assert 'dispatch' in payload['metrics']
        assert isinstance(payload.get('alerts'), list)
        assert payload['metrics']['auth']['failed_login_events'] >= 1
    finally:
        app_context.app.config['DISPATCH_PENDING_MATCH_SLA_MINUTES'] = original_pending


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


def test_admin_dispatch_incident_ack_resolve_flow(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context,
        '_drive_time_between_points',
        lambda *args, **kwargs: {'minutes': 15.0, 'text': '15 mins'},
    )
    _create_user(app_context, 'opsadmin@example.com', 'Password123!', role='admin', name='Ops Admin')
    _create_user(app_context, 'incustomer@example.com', 'Password123!', role='customer', name='Incident Customer')
    admin_headers = _auth_header(client, 'opsadmin@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'incustomer@example.com', 'Password123!')

    original_pending = app_context.app.config.get('DISPATCH_PENDING_MATCH_SLA_MINUTES')
    app_context.app.config['DISPATCH_PENDING_MATCH_SLA_MINUTES'] = 0

    try:
        scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
        create_response = client.post(
            '/api/v1/waste-requests',
            json={
                'requester_name': 'Incident Customer',
                'requester_email': 'incustomer@example.com',
                'material_type': 'Glass',
                'waste_amount': 1.0,
                'waste_unit': 'Tonnes',
                'match_radius_miles': 25,
                'pickup_address': '1 Example Road',
                'pickup_postcode': 'SW1A1AA',
                'scheduled_pickup_at': scheduled_time,
            },
            headers=customer_headers,
        )
        assert create_response.status_code == 201
        request_id = create_response.get_json()['request']['id']
        with app_context.app.app_context():
            booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
            booking.created_at = datetime.utcnow() - timedelta(minutes=2)
            app_context.db.session.commit()

        incidents = client.get('/api/v1/admin/dispatch/incidents?active_only=false&limit=50', headers=admin_headers)
        assert incidents.status_code == 200
        assert 'items' in incidents.get_json()

        ack = client.post(
            f'/api/v1/admin/dispatch/incidents/{request_id}/ack',
            json={'notes': 'triage acknowledged'},
            headers=admin_headers,
        )
        assert ack.status_code == 200
        assert ack.get_json()['incident']['state'] == 'acknowledged'

        resolve = client.post(
            f'/api/v1/admin/dispatch/incidents/{request_id}/resolve',
            json={'notes': 'resolved for now'},
            headers=admin_headers,
        )
        assert resolve.status_code == 200
        assert resolve.get_json()['incident']['state'] == 'resolved'

        queue = client.get(
            '/api/v1/admin/dispatch/queue?incident_state=resolved&incidents_only=true&limit=50',
            headers=admin_headers,
        )
        assert queue.status_code == 200
        queue_ids = [item['request']['id'] for item in queue.get_json()['items']]
        assert request_id in queue_ids

        telemetry = client.get('/api/v1/admin/dispatch/telemetry?limit=50', headers=admin_headers)
        assert telemetry.status_code == 200
        summary = telemetry.get_json()['summary']
        assert 'incident_state_counts' in summary
        assert 'incident_severity_counts' in summary
    finally:
        app_context.app.config['DISPATCH_PENDING_MATCH_SLA_MINUTES'] = original_pending


def test_admin_dispatch_incident_ack_requires_active_incident(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context,
        '_drive_time_between_points',
        lambda *args, **kwargs: {'minutes': 10.0, 'text': '10 mins'},
    )
    _create_user(app_context, 'opsadmin2@example.com', 'Password123!', role='admin', name='Ops Admin 2')
    _create_user(app_context, 'quietcustomer@example.com', 'Password123!', role='customer', name='Quiet Customer')
    admin_headers = _auth_header(client, 'opsadmin2@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'quietcustomer@example.com', 'Password123!')

    original_pending = app_context.app.config.get('DISPATCH_PENDING_MATCH_SLA_MINUTES')
    app_context.app.config['DISPATCH_PENDING_MATCH_SLA_MINUTES'] = 9999

    try:
        scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
        create_response = client.post(
            '/api/v1/waste-requests',
            json={
                'requester_name': 'Quiet Customer',
                'requester_email': 'quietcustomer@example.com',
                'material_type': 'Glass',
                'waste_amount': 1.0,
                'waste_unit': 'Tonnes',
                'match_radius_miles': 25,
                'pickup_address': '1 Example Road',
                'pickup_postcode': 'SW1A1AA',
                'scheduled_pickup_at': scheduled_time,
            },
            headers=customer_headers,
        )
        assert create_response.status_code == 201
        request_id = create_response.get_json()['request']['id']

        ack = client.post(
            f'/api/v1/admin/dispatch/incidents/{request_id}/ack',
            json={'notes': 'should fail'},
            headers=admin_headers,
        )
        assert ack.status_code == 409
        assert ack.get_json()['error'] == 'No active incident to acknowledge'
    finally:
        app_context.app.config['DISPATCH_PENDING_MATCH_SLA_MINUTES'] = original_pending


def test_admin_dispatch_incident_owner_reassignment_flow(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context,
        '_drive_time_between_points',
        lambda *args, **kwargs: {'minutes': 12.0, 'text': '12 mins'},
    )
    _create_user(app_context, 'opsowner1@example.com', 'Password123!', role='admin', name='Ops Owner 1')
    _create_user(app_context, 'opsowner2@example.com', 'Password123!', role='admin', name='Ops Owner 2')
    _create_user(app_context, 'ownercustomer@example.com', 'Password123!', role='customer', name='Owner Customer')
    _create_user(app_context, 'notadminowner@example.com', 'Password123!', role='customer', name='Not Admin')
    admin_headers = _auth_header(client, 'opsowner1@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'ownercustomer@example.com', 'Password123!')

    original_pending = app_context.app.config.get('DISPATCH_PENDING_MATCH_SLA_MINUTES')
    app_context.app.config['DISPATCH_PENDING_MATCH_SLA_MINUTES'] = 0

    try:
        scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
        create_response = client.post(
            '/api/v1/waste-requests',
            json={
                'requester_name': 'Owner Customer',
                'requester_email': 'ownercustomer@example.com',
                'material_type': 'Glass',
                'waste_amount': 1.0,
                'waste_unit': 'Tonnes',
                'match_radius_miles': 25,
                'pickup_address': '1 Example Road',
                'pickup_postcode': 'SW1A1AA',
                'scheduled_pickup_at': scheduled_time,
            },
            headers=customer_headers,
        )
        assert create_response.status_code == 201
        request_id = create_response.get_json()['request']['id']
        with app_context.app.app_context():
            booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
            booking.created_at = datetime.utcnow() - timedelta(minutes=3)
            app_context.db.session.commit()
            owner_two_id = app_context.User.query.filter_by(email='opsowner2@example.com').first().id
            customer_id = app_context.User.query.filter_by(email='notadminowner@example.com').first().id

        ack = client.post(
            f'/api/v1/admin/dispatch/incidents/{request_id}/ack',
            json={'notes': 'set initial owner'},
            headers=admin_headers,
        )
        assert ack.status_code == 200
        assert ack.get_json()['incident']['state'] == 'acknowledged'

        reassign = client.post(
            f'/api/v1/admin/dispatch/incidents/{request_id}/owner',
            json={'owner_admin_user_id': owner_two_id, 'notes': 'handoff to on-call admin'},
            headers=admin_headers,
        )
        assert reassign.status_code == 200
        reassign_payload = reassign.get_json()
        assert reassign_payload['updated'] is True
        assert reassign_payload['owner_admin_user_id'] == owner_two_id
        assert reassign_payload['request']['request']['incident_owner_admin_user_id'] == owner_two_id

        noop = client.post(
            f'/api/v1/admin/dispatch/incidents/{request_id}/owner',
            json={'owner_admin_user_id': owner_two_id},
            headers=admin_headers,
        )
        assert noop.status_code == 200
        assert noop.get_json()['updated'] is False

        unassign = client.post(
            f'/api/v1/admin/dispatch/incidents/{request_id}/owner',
            json={'owner_admin_user_id': None, 'notes': 'clear owner'},
            headers=admin_headers,
        )
        assert unassign.status_code == 200
        assert unassign.get_json()['updated'] is True
        assert unassign.get_json()['owner_admin_user_id'] is None

        invalid_owner = client.post(
            f'/api/v1/admin/dispatch/incidents/{request_id}/owner',
            json={'owner_admin_user_id': customer_id},
            headers=admin_headers,
        )
        assert invalid_owner.status_code == 400
        assert invalid_owner.get_json()['error'] == 'Selected user is not an admin'
    finally:
        app_context.app.config['DISPATCH_PENDING_MATCH_SLA_MINUTES'] = original_pending


def test_admin_dispatch_incident_maintenance_dry_run_and_apply(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context,
        '_drive_time_between_points',
        lambda *args, **kwargs: {'minutes': 9.0, 'text': '9 mins'},
    )
    _create_user(app_context, 'opsmaint@example.com', 'Password123!', role='admin', name='Ops Maint Admin')
    _create_user(app_context, 'smokecustomer@example.com', 'Password123!', role='customer', name='Smoke Customer')
    admin_headers = _auth_header(client, 'opsmaint@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'smokecustomer@example.com', 'Password123!')

    original_pending = app_context.app.config.get('DISPATCH_PENDING_MATCH_SLA_MINUTES')
    app_context.app.config['DISPATCH_PENDING_MATCH_SLA_MINUTES'] = 0

    try:
        scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
        create_response = client.post(
            '/api/v1/waste-requests',
            json={
                'requester_name': 'Smoke Customer',
                'requester_email': 'smokecustomer@example.com',
                'material_type': 'Glass',
                'waste_amount': 1.0,
                'waste_unit': 'Tonnes',
                'match_radius_miles': 25,
                'pickup_address': '1 Example Road',
                'pickup_postcode': 'SW1A1AA',
                'scheduled_pickup_at': scheduled_time,
            },
            headers=customer_headers,
        )
        assert create_response.status_code == 201
        request_id = create_response.get_json()['request']['id']

        with app_context.app.app_context():
            booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
            booking.created_at = datetime.utcnow() - timedelta(minutes=90)
            app_context.db.session.commit()

        dry_run = client.post(
            '/api/v1/admin/dispatch/incidents/maintenance',
            json={
                'dry_run': True,
                'auto_assign': True,
                'auto_resolve_test': True,
                'resolve_test_minutes': 30,
                'limit': 100,
            },
            headers=admin_headers,
        )
        assert dry_run.status_code == 200
        dry_payload = dry_run.get_json()
        assert dry_payload['dry_run'] is True
        assert dry_payload['summary']['actions_planned'] >= 1
        assert dry_payload['summary']['actions_applied'] == 0

        apply_run = client.post(
            '/api/v1/admin/dispatch/incidents/maintenance',
            json={
                'dry_run': False,
                'auto_assign': True,
                'auto_resolve_test': True,
                'resolve_test_minutes': 30,
                'limit': 100,
            },
            headers=admin_headers,
        )
        assert apply_run.status_code == 200
        apply_payload = apply_run.get_json()
        assert apply_payload['dry_run'] is False
        assert apply_payload['summary']['actions_applied'] >= 1
        assert apply_payload['summary']['auto_resolved_test'] >= 1

        with app_context.app.app_context():
            booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
            assert booking.incident_state == 'resolved'
            assert booking.incident_owner_admin_user_id is not None
            event_types = {
                row.event_type
                for row in (
                    app_context.DispatchIncidentEvent.query.filter_by(
                        waste_removal_request_id=request_id
                    )
                    .order_by(app_context.DispatchIncidentEvent.id.asc())
                    .all()
                )
            }
            assert 'incident_auto_resolve_test' in event_types
    finally:
        app_context.app.config['DISPATCH_PENDING_MATCH_SLA_MINUTES'] = original_pending


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


def test_admin_dispatch_request_timeline_includes_dispatch_and_auth_events(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context,
        '_drive_time_between_points',
        lambda *args, **kwargs: {'minutes': 11.0, 'text': '11 mins'},
    )
    _create_user(app_context, 'opsadmintimeline@example.com', 'Password123!', role='admin', name='Ops Timeline')
    _create_user(app_context, 'opsadmintimeline2@example.com', 'Password123!', role='admin', name='Ops Timeline 2')
    _create_user(app_context, 'timelinedriver@example.com', 'Password123!', role='driver', name='Timeline Driver')
    _create_user(app_context, 'timelinecustomer@example.com', 'Password123!', role='customer', name='Timeline Customer')
    _seed_driver_dispatch_compliance(
        app_context,
        'timelinedriver@example.com',
        verifier_email='opsadmintimeline@example.com',
    )
    admin_headers = _auth_header(client, 'opsadmintimeline@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'timelinecustomer@example.com', 'Password123!')

    original_pending = app_context.app.config.get('DISPATCH_PENDING_MATCH_SLA_MINUTES')
    app_context.app.config['DISPATCH_PENDING_MATCH_SLA_MINUTES'] = 0

    try:
        scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
        create_response = client.post(
            '/api/v1/waste-requests',
            json={
                'requester_name': 'Timeline Customer',
                'requester_email': 'timelinecustomer@example.com',
                'material_type': 'Glass',
                'waste_amount': 1.0,
                'waste_unit': 'Tonnes',
                'match_radius_miles': 25,
                'pickup_address': '1 Example Road',
                'pickup_postcode': 'SW1A1AA',
                'scheduled_pickup_at': scheduled_time,
            },
            headers=customer_headers,
        )
        assert create_response.status_code == 201
        request_id = create_response.get_json()['request']['id']
        with app_context.app.app_context():
            booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
            booking.created_at = datetime.utcnow() - timedelta(minutes=3)
            app_context.db.session.commit()
            owner_two_id = app_context.User.query.filter_by(email='opsadmintimeline2@example.com').first().id
            driver_id = app_context.User.query.filter_by(email='timelinedriver@example.com').first().id
            admin_user_id = app_context.User.query.filter_by(email='opsadmintimeline@example.com').first().id

        ack = client.post(
            f'/api/v1/admin/dispatch/incidents/{request_id}/ack',
            json={'notes': 'timeline ack'},
            headers=admin_headers,
        )
        assert ack.status_code == 200

        owner = client.post(
            f'/api/v1/admin/dispatch/incidents/{request_id}/owner',
            json={'owner_admin_user_id': owner_two_id, 'notes': 'timeline owner change'},
            headers=admin_headers,
        )
        assert owner.status_code == 200

        override = client.post(
            f'/api/v1/admin/waste-requests/{request_id}/dispatch/override',
            json={'driver_user_id': driver_id, 'reason': 'timeline assign'},
            headers=admin_headers,
        )
        assert override.status_code == 200

        timeline_response = client.get(
            f'/api/v1/admin/waste-requests/{request_id}/timeline?include_actor_auth=true&auth_window_hours=168&limit=200',
            headers=admin_headers,
        )
        assert timeline_response.status_code == 200
        payload = timeline_response.get_json()
        timeline = payload.get('timeline') or []
        event_types = {row.get('event_type') for row in timeline}

        assert 'incident_ack' in event_types
        assert 'incident_owner_reassign' in event_types
        assert 'dispatch_override' in event_types
        assert payload.get('summary', {}).get('category_counts', {}).get('dispatch', 0) >= 3
        assert any(
            row.get('category') == 'auth' and row.get('actor_user_id') == admin_user_id
            for row in timeline
        )
    finally:
        app_context.app.config['DISPATCH_PENDING_MATCH_SLA_MINUTES'] = original_pending


def test_waste_request_compliance_document_flow_and_permissions(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())

    _create_user(app_context, 'complianceadmin@example.com', 'Password123!', role='admin', name='Compliance Admin')
    _create_user(app_context, 'compliancecustomer@example.com', 'Password123!', role='customer', name='Compliance Customer')
    _create_user(app_context, 'compliancedriver1@example.com', 'Password123!', role='driver', name='Compliance Driver 1')
    _create_user(app_context, 'compliancedriver2@example.com', 'Password123!', role='driver', name='Compliance Driver 2')

    admin_headers = _auth_header(client, 'complianceadmin@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'compliancecustomer@example.com', 'Password123!')
    driver_one_headers = _auth_header(client, 'compliancedriver1@example.com', 'Password123!')
    driver_two_headers = _auth_header(client, 'compliancedriver2@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'Compliance Customer',
            'requester_email': 'compliancecustomer@example.com',
            'material_type': 'Glass',
            'waste_amount': 1.0,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '1 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': scheduled_time,
        },
        headers=customer_headers,
    )
    assert create_response.status_code == 201
    request_id = create_response.get_json()['request']['id']

    with app_context.app.app_context():
        booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
        assigned_driver = app_context.User.query.filter_by(email='compliancedriver1@example.com').first()
        booking.assigned_driver_user_id = assigned_driver.id
        app_context.db.session.commit()

    forbidden_create = client.post(
        f'/api/v1/waste-requests/{request_id}/compliance/documents',
        json={
            'document_type': 'waste_transfer_note',
            'file_url': 'https://example.com/docs/wtn-unauthorized.pdf',
        },
        headers=driver_two_headers,
    )
    assert forbidden_create.status_code == 403

    create_doc = client.post(
        f'/api/v1/waste-requests/{request_id}/compliance/documents',
        json={
            'document_type': 'waste_transfer_note',
            'file_url': 'https://example.com/docs/wtn-123.pdf',
            'document_reference': 'WTN-123',
            'notes': 'Captured at pickup',
            'metadata': {'vehicle_registration': 'AB12CDE'},
        },
        headers=driver_one_headers,
    )
    assert create_doc.status_code == 201
    create_payload = create_doc.get_json()
    document_id = create_payload['document']['id']
    assert create_payload['document']['status'] == 'submitted'
    assert create_payload['summary']['by_type']['waste_transfer_note']['present'] is True

    customer_list = client.get(
        f'/api/v1/waste-requests/{request_id}/compliance',
        headers=customer_headers,
    )
    assert customer_list.status_code == 200
    list_payload = customer_list.get_json()
    assert len(list_payload['documents']) == 1
    assert list_payload['documents'][0]['document_type'] == 'waste_transfer_note'

    verify = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/compliance/documents/{document_id}/verify',
        json={
            'status': 'verified',
            'notes': 'Validated against carrier paperwork',
            'metadata': {'validated_by': 'ops'},
        },
        headers=admin_headers,
    )
    assert verify.status_code == 200
    verify_payload = verify.get_json()
    assert verify_payload['updated'] is True
    assert verify_payload['previous_status'] == 'submitted'
    assert verify_payload['document']['status'] == 'verified'
    assert verify_payload['summary']['by_type']['waste_transfer_note']['verified'] is True

    customer_verify = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/compliance/documents/{document_id}/verify',
        json={'status': 'verified'},
        headers=customer_headers,
    )
    assert customer_verify.status_code == 403

    driver_license_upload = client.post(
        f'/api/v1/waste-requests/{request_id}/compliance/documents',
        json={
            'document_type': 'carrier_license',
            'file_url': 'https://example.com/docs/carrier-license.pdf',
        },
        headers=driver_one_headers,
    )
    assert driver_license_upload.status_code == 403


def test_admin_compliance_review_queue_lists_pending_documents(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())

    _create_user(app_context, 'reviewadmin@example.com', 'Password123!', role='admin', name='Review Admin')
    _create_user(app_context, 'reviewcustomer@example.com', 'Password123!', role='customer', name='Review Customer')
    _create_user(app_context, 'reviewdriver@example.com', 'Password123!', role='driver', name='Review Driver')

    admin_headers = _auth_header(client, 'reviewadmin@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'reviewcustomer@example.com', 'Password123!')
    driver_headers = _auth_header(client, 'reviewdriver@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'Review Customer',
            'requester_email': 'reviewcustomer@example.com',
            'material_type': 'Glass',
            'waste_amount': 1.0,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '1 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': scheduled_time,
        },
        headers=customer_headers,
    )
    assert create_response.status_code == 201
    request_id = create_response.get_json()['request']['id']

    with app_context.app.app_context():
        booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
        driver_user = app_context.User.query.filter_by(email='reviewdriver@example.com').first()
        booking.assigned_driver_user_id = driver_user.id
        app_context.db.session.commit()

    create_doc = client.post(
        f'/api/v1/waste-requests/{request_id}/compliance/documents',
        json={
            'document_type': 'proof_of_collection_photo',
            'file_url': 'https://example.com/docs/proof-photo.jpg',
        },
        headers=driver_headers,
    )
    assert create_doc.status_code == 201
    document_id = create_doc.get_json()['document']['id']

    pending_queue = client.get(
        '/api/v1/admin/compliance/review-queue?status=submitted&limit=50',
        headers=admin_headers,
    )
    assert pending_queue.status_code == 200
    pending_payload = pending_queue.get_json()
    document_ids = [item['document']['id'] for item in pending_payload['items']]
    assert document_id in document_ids

    verify = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/compliance/documents/{document_id}/verify',
        json={'status': 'verified'},
        headers=admin_headers,
    )
    assert verify.status_code == 200

    pending_queue_after = client.get(
        '/api/v1/admin/compliance/review-queue?status=submitted&limit=50',
        headers=admin_headers,
    )
    assert pending_queue_after.status_code == 200
    pending_after_ids = [item['document']['id'] for item in pending_queue_after.get_json()['items']]
    assert document_id not in pending_after_ids


def test_driver_can_upload_compliance_file_and_receive_served_url(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())

    _create_user(app_context, 'uploadadmin@example.com', 'Password123!', role='admin', name='Upload Admin')
    _create_user(app_context, 'uploadcustomer@example.com', 'Password123!', role='customer', name='Upload Customer')
    _create_user(app_context, 'uploaddriver@example.com', 'Password123!', role='driver', name='Upload Driver')

    customer_headers = _auth_header(client, 'uploadcustomer@example.com', 'Password123!')
    driver_headers = _auth_header(client, 'uploaddriver@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'Upload Customer',
            'requester_email': 'uploadcustomer@example.com',
            'material_type': 'Glass',
            'waste_amount': 1.0,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '1 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': scheduled_time,
        },
        headers=customer_headers,
    )
    assert create_response.status_code == 201
    request_id = create_response.get_json()['request']['id']

    with app_context.app.app_context():
        booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
        driver_user = app_context.User.query.filter_by(email='uploaddriver@example.com').first()
        booking.assigned_driver_user_id = driver_user.id
        app_context.db.session.commit()

    upload_response = client.post(
        f'/api/v1/waste-requests/{request_id}/compliance/uploads',
        data={
            'document_type': 'proof_of_collection_photo',
            'file': (io.BytesIO(b'fake-image-binary'), 'proof-photo.jpg'),
        },
        content_type='multipart/form-data',
        headers=driver_headers,
    )
    assert upload_response.status_code == 201
    upload_payload = upload_response.get_json()
    file_url = upload_payload['upload']['file_url']
    assert '/static/uploads/compliance/request-{}'.format(request_id) in file_url
    assert upload_payload['upload']['original_filename'] == 'proof-photo.jpg'

    served_asset = client.get(urlsplit(file_url).path)
    assert served_asset.status_code == 200
    assert served_asset.data == b'fake-image-binary'


def test_driver_compliance_upload_can_use_s3_storage_backend(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())

    _create_user(app_context, 's3customer@example.com', 'Password123!', role='customer', name='S3 Customer')
    _create_user(app_context, 's3driver@example.com', 'Password123!', role='driver', name='S3 Driver')

    customer_headers = _auth_header(client, 's3customer@example.com', 'Password123!')
    driver_headers = _auth_header(client, 's3driver@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'S3 Customer',
            'requester_email': 's3customer@example.com',
            'material_type': 'Glass',
            'waste_amount': 1.0,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '1 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': scheduled_time,
        },
        headers=customer_headers,
    )
    assert create_response.status_code == 201
    request_id = create_response.get_json()['request']['id']

    with app_context.app.app_context():
        booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
        driver_user = app_context.User.query.filter_by(email='s3driver@example.com').first()
        booking.assigned_driver_user_id = driver_user.id
        app_context.db.session.commit()

    class FakeS3Client:
        def __init__(self):
            self.calls = []

        def put_object(self, **kwargs):
            self.calls.append(kwargs)

    fake_s3 = FakeS3Client()
    monkeypatch.setattr(app_context, '_compliance_s3_client', lambda: fake_s3)

    monkeypatch.setitem(app_context.app.config, 'COMPLIANCE_STORAGE_BACKEND', 's3')
    monkeypatch.setitem(app_context.app.config, 'COMPLIANCE_S3_BUCKET', 'projectdivert-compliance')
    monkeypatch.setitem(
        app_context.app.config,
        'COMPLIANCE_S3_PUBLIC_BASE_URL',
        'https://cdn.example.com/projectdivert',
    )

    upload_response = client.post(
        f'/api/v1/waste-requests/{request_id}/compliance/uploads',
        data={
            'document_type': 'waste_transfer_note',
            'file': (io.BytesIO(b'fake-pdf-binary'), 'wtn.pdf'),
        },
        content_type='multipart/form-data',
        headers=driver_headers,
    )
    assert upload_response.status_code == 201
    upload_payload = upload_response.get_json()
    assert upload_payload['upload']['backend'] == 's3'
    assert upload_payload['upload']['file_url'].startswith(
        'https://cdn.example.com/projectdivert/compliance/request-{}'.format(request_id)
    )
    assert upload_payload['upload']['storage_key'].endswith('.pdf')

    assert len(fake_s3.calls) == 1
    put_call = fake_s3.calls[0]
    assert put_call['Bucket'] == 'projectdivert-compliance'
    assert put_call['ContentType'] == 'application/pdf'
    assert put_call['Metadata']['request-id'] == str(request_id)
    assert put_call['Metadata']['document-type'] == 'waste_transfer_note'


def test_driver_can_request_signed_compliance_upload(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())

    _create_user(app_context, 'signcustomer@example.com', 'Password123!', role='customer', name='Sign Customer')
    _create_user(app_context, 'signdriver@example.com', 'Password123!', role='driver', name='Sign Driver')

    customer_headers = _auth_header(client, 'signcustomer@example.com', 'Password123!')
    driver_headers = _auth_header(client, 'signdriver@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'Sign Customer',
            'requester_email': 'signcustomer@example.com',
            'material_type': 'Glass',
            'waste_amount': 1.0,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '1 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': scheduled_time,
        },
        headers=customer_headers,
    )
    assert create_response.status_code == 201
    request_id = create_response.get_json()['request']['id']

    with app_context.app.app_context():
        booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
        driver_user = app_context.User.query.filter_by(email='signdriver@example.com').first()
        booking.assigned_driver_user_id = driver_user.id
        app_context.db.session.commit()

    class FakeS3Client:
        def __init__(self):
            self.calls = []

        def generate_presigned_url(self, operation_name, Params=None, ExpiresIn=None, HttpMethod=None):
            self.calls.append(
                {
                    'operation_name': operation_name,
                    'params': Params,
                    'expires_in': ExpiresIn,
                    'http_method': HttpMethod,
                }
            )
            return 'https://signed-upload.example.com/put-object'

    fake_s3 = FakeS3Client()
    monkeypatch.setattr(app_context, '_compliance_s3_client', lambda: fake_s3)
    monkeypatch.setitem(app_context.app.config, 'COMPLIANCE_STORAGE_BACKEND', 's3')
    monkeypatch.setitem(app_context.app.config, 'COMPLIANCE_S3_BUCKET', 'projectdivert-compliance')
    monkeypatch.setitem(
        app_context.app.config,
        'COMPLIANCE_S3_PUBLIC_BASE_URL',
        'https://cdn.example.com/projectdivert',
    )
    monkeypatch.setitem(app_context.app.config, 'COMPLIANCE_S3_PRESIGN_EXP_SECONDS', 600)

    sign_response = client.post(
        f'/api/v1/waste-requests/{request_id}/compliance/uploads/sign',
        json={
            'document_type': 'proof_of_collection_photo',
            'file_name': 'proof-photo.jpg',
            'mime_type': 'image/jpeg',
        },
        headers=driver_headers,
    )
    assert sign_response.status_code == 200
    sign_payload = sign_response.get_json()
    assert sign_payload['method'] == 'PUT'
    assert sign_payload['upload_url'] == 'https://signed-upload.example.com/put-object'
    assert sign_payload['upload']['file_url'].startswith(
        'https://cdn.example.com/projectdivert/compliance/request-{}'.format(request_id)
    )
    assert sign_payload['headers']['Content-Type'] == 'image/jpeg'

    assert len(fake_s3.calls) == 1
    call = fake_s3.calls[0]
    assert call['operation_name'] == 'put_object'
    assert call['http_method'] == 'PUT'
    assert call['expires_in'] == 600
    assert call['params']['Bucket'] == 'projectdivert-compliance'
    assert call['params']['ContentType'] == 'image/jpeg'


def test_driver_compliance_documents_control_dispatch_eligibility_and_admin_override(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())

    _create_user(app_context, 'drivercompadmin@example.com', 'Password123!', role='admin', name='Driver Comp Admin')
    _create_user(app_context, 'drivercompcustomer@example.com', 'Password123!', role='customer', name='Driver Comp Customer')
    _create_user(app_context, 'drivercompdriver@example.com', 'Password123!', role='driver', name='Driver Comp Driver')

    admin_headers = _auth_header(client, 'drivercompadmin@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'drivercompcustomer@example.com', 'Password123!')
    driver_headers = _auth_header(client, 'drivercompdriver@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'Driver Comp Customer',
            'requester_email': 'drivercompcustomer@example.com',
            'material_type': 'Glass',
            'waste_amount': 1.0,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '1 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': scheduled_time,
        },
        headers=customer_headers,
    )
    assert create_response.status_code == 201
    request_id = create_response.get_json()['request']['id']

    with app_context.app.app_context():
        driver_id = app_context.User.query.filter_by(email='drivercompdriver@example.com').first().id

    drivers_before = client.get('/api/v1/admin/drivers?active=true&limit=20', headers=admin_headers)
    assert drivers_before.status_code == 200
    driver_before = next(
        item for item in drivers_before.get_json()['items']
        if item['email'] == 'drivercompdriver@example.com'
    )
    assert driver_before['dispatch_eligible'] is False
    assert set(driver_before['dispatch_missing_document_types']) == {
        'driver:carrier_license',
        'driver:insurance_certificate',
        'company:assignment',
    }

    blocked_override = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/dispatch/override',
        json={'driver_user_id': driver_id, 'reason': 'should fail until compliant'},
        headers=admin_headers,
    )
    assert blocked_override.status_code == 409
    assert set(blocked_override.get_json()['missing_document_types']) == {
        'driver:carrier_license',
        'driver:insurance_certificate',
        'company:assignment',
    }

    create_company = client.post(
        '/api/v1/admin/carrier-companies',
        json={
            'name': 'Driver Comp Carrier',
            'contact_email': 'ops@driver-comp-carrier.example.com',
        },
        headers=admin_headers,
    )
    assert create_company.status_code == 201
    carrier_company_id = create_company.get_json()['company']['id']

    assign_company = client.post(
        f'/api/v1/admin/drivers/{driver_id}/carrier-company',
        json={'carrier_company_id': carrier_company_id},
        headers=admin_headers,
    )
    assert assign_company.status_code == 200

    still_blocked_override = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/dispatch/override',
        json={'driver_user_id': driver_id, 'reason': 'should fail until company docs exist'},
        headers=admin_headers,
    )
    assert still_blocked_override.status_code == 409
    assert set(still_blocked_override.get_json()['missing_document_types']) == {
        'driver:carrier_license',
        'driver:insurance_certificate',
        'company:insurance_certificate',
        'company:operator_license',
    }

    created_document_ids = []
    for document_type in ['carrier_license', 'insurance_certificate']:
        create_doc = client.post(
            '/api/v1/drivers/me/compliance/documents',
            json={
                'document_type': document_type,
                'file_url': f'https://example.com/driver-docs/{document_type}.pdf',
                'document_reference': f'{document_type.upper()}-123',
            },
            headers=driver_headers,
        )
        assert create_doc.status_code == 201
        created_document_ids.append(create_doc.get_json()['document']['id'])
        assert create_doc.get_json()['summary']['dispatch_eligible'] is False

    created_company_document_ids = []
    for document_type in ['operator_license', 'insurance_certificate']:
        create_doc = client.post(
            f'/api/v1/admin/carrier-companies/{carrier_company_id}/compliance/documents',
            json={
                'document_type': document_type,
                'file_url': f'https://example.com/company-docs/{document_type}.pdf',
                'document_reference': f'{document_type.upper()}-123',
            },
            headers=admin_headers,
        )
        assert create_doc.status_code == 201
        created_company_document_ids.append(create_doc.get_json()['document']['id'])

    driver_compliance = client.get(
        f'/api/v1/admin/drivers/{driver_id}/compliance',
        headers=admin_headers,
    )
    assert driver_compliance.status_code == 200
    compliance_payload = driver_compliance.get_json()
    assert len(compliance_payload['documents']) == 2
    assert compliance_payload['summary']['dispatch_eligible'] is False

    for document_id in created_document_ids:
        verify = client.post(
            f'/api/v1/admin/drivers/{driver_id}/compliance/documents/{document_id}/verify',
            json={'status': 'verified', 'notes': 'reviewed'},
            headers=admin_headers,
        )
        assert verify.status_code == 200

    company_compliance = client.get(
        f'/api/v1/admin/carrier-companies/{carrier_company_id}/compliance',
        headers=admin_headers,
    )
    assert company_compliance.status_code == 200
    company_payload = company_compliance.get_json()
    assert len(company_payload['documents']) == 2
    assert company_payload['summary']['dispatch_eligible'] is False

    for document_id in created_company_document_ids:
        verify = client.post(
            f'/api/v1/admin/carrier-companies/{carrier_company_id}/compliance/documents/{document_id}/verify',
            json={'status': 'verified', 'notes': 'company reviewed'},
            headers=admin_headers,
        )
        assert verify.status_code == 200

    drivers_after = client.get('/api/v1/admin/drivers?active=true&limit=20', headers=admin_headers)
    assert drivers_after.status_code == 200
    driver_after = next(
        item for item in drivers_after.get_json()['items']
        if item['email'] == 'drivercompdriver@example.com'
    )
    assert driver_after['dispatch_eligible'] is True
    assert driver_after['dispatch_missing_document_types'] == []
    assert driver_after['carrier_company']['id'] == carrier_company_id

    allowed_override = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/dispatch/override',
        json={'driver_user_id': driver_id, 'reason': 'driver now compliant'},
        headers=admin_headers,
    )
    assert allowed_override.status_code == 200
    assert allowed_override.get_json()['assigned_driver_user_id'] == driver_id


def test_driver_dispatch_accept_requires_verified_driver_compliance_documents(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())

    _create_user(app_context, 'eligibilityadmin@example.com', 'Password123!', role='admin', name='Eligibility Admin')
    _create_user(app_context, 'eligibilitycustomer@example.com', 'Password123!', role='customer', name='Eligibility Customer')
    _create_user(app_context, 'eligibilitydriver@example.com', 'Password123!', role='driver', name='Eligibility Driver')

    customer_headers = _auth_header(client, 'eligibilitycustomer@example.com', 'Password123!')
    driver_headers = _auth_header(client, 'eligibilitydriver@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'Eligibility Customer',
            'requester_email': 'eligibilitycustomer@example.com',
            'material_type': 'Glass',
            'waste_amount': 1.0,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '1 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': scheduled_time,
        },
        headers=customer_headers,
    )
    assert create_response.status_code == 201
    request_id = create_response.get_json()['request']['id']

    with app_context.app.app_context():
        offer = app_context.WasteRemovalDispatchOffer.query.filter_by(waste_removal_request_id=request_id).first()
        offer_token = offer.offer_token

    blocked_accept = client.post(
        f'/api/v1/waste-requests/{request_id}/dispatch/accept',
        json={'offer_token': offer_token},
        headers=driver_headers,
    )
    assert blocked_accept.status_code == 409
    assert set(blocked_accept.get_json()['missing_document_types']) == {
        'driver:carrier_license',
        'driver:insurance_certificate',
        'company:assignment',
    }

    _seed_driver_dispatch_compliance(
        app_context,
        'eligibilitydriver@example.com',
        verifier_email='eligibilityadmin@example.com',
    )

    accepted = client.post(
        f'/api/v1/waste-requests/{request_id}/dispatch/accept',
        json={'offer_token': offer_token},
        headers=driver_headers,
    )
    assert accepted.status_code == 200
    assert accepted.get_json()['request']['assigned_driver_user_id'] is not None


def test_waste_request_completion_requires_verified_collection_documents(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())

    _create_user(app_context, 'completeadmin@example.com', 'Password123!', role='admin', name='Complete Admin')
    _create_user(app_context, 'completecustomer@example.com', 'Password123!', role='customer', name='Complete Customer')
    _create_user(app_context, 'completedriver@example.com', 'Password123!', role='driver', name='Complete Driver')
    _seed_driver_dispatch_compliance(
        app_context,
        'completedriver@example.com',
        verifier_email='completeadmin@example.com',
    )

    admin_headers = _auth_header(client, 'completeadmin@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'completecustomer@example.com', 'Password123!')
    driver_headers = _auth_header(client, 'completedriver@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'Complete Customer',
            'requester_email': 'completecustomer@example.com',
            'material_type': 'Glass',
            'waste_amount': 1.0,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '1 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': scheduled_time,
        },
        headers=customer_headers,
    )
    assert create_response.status_code == 201
    request_id = create_response.get_json()['request']['id']

    with app_context.app.app_context():
        offer = app_context.WasteRemovalDispatchOffer.query.filter_by(waste_removal_request_id=request_id).first()
        offer_token = offer.offer_token

    accept_response = client.post(
        f'/api/v1/waste-requests/{request_id}/dispatch/accept',
        json={'offer_token': offer_token},
        headers=driver_headers,
    )
    assert accept_response.status_code == 200

    blocked_complete = client.post(
        f'/api/v1/waste-requests/{request_id}/status',
        json={'status': 'completed'},
        headers=driver_headers,
    )
    assert blocked_complete.status_code == 409
    blocked_payload = blocked_complete.get_json()
    assert blocked_payload['error'] == 'Compliance review incomplete for request completion'
    assert set(blocked_payload['missing_document_types']) == {
        'waste_transfer_note',
        'proof_of_collection_photo',
    }

    uploaded_ids = []
    for document_type in ['waste_transfer_note', 'proof_of_collection_photo']:
        create_doc = client.post(
            f'/api/v1/waste-requests/{request_id}/compliance/documents',
            json={
                'document_type': document_type,
                'file_url': f'https://example.com/docs/{document_type}-{request_id}.pdf',
            },
            headers=driver_headers,
        )
        assert create_doc.status_code == 201
        uploaded_ids.append(create_doc.get_json()['document']['id'])

    partially_blocked = client.post(
        f'/api/v1/waste-requests/{request_id}/status',
        json={'status': 'completed'},
        headers=driver_headers,
    )
    assert partially_blocked.status_code == 409

    for document_id in uploaded_ids:
        verify = client.post(
            f'/api/v1/admin/waste-requests/{request_id}/compliance/documents/{document_id}/verify',
            json={'status': 'verified'},
            headers=admin_headers,
        )
        assert verify.status_code == 200

    completed = client.post(
        f'/api/v1/waste-requests/{request_id}/status',
        json={'status': 'completed'},
        headers=driver_headers,
    )
    assert completed.status_code == 200
    assert completed.get_json()['request']['status'] == 'completed'


def test_waste_request_financials_report_offline_billing_launch_mode(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())

    _create_user(app_context, 'billingcustomer@example.com', 'Password123!', role='customer', name='Billing Customer')
    customer_headers = _auth_header(client, 'billingcustomer@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'Billing Customer',
            'requester_email': 'billingcustomer@example.com',
            'material_type': 'Glass',
            'waste_amount': 1.0,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '1 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': scheduled_time,
        },
        headers=customer_headers,
    )
    assert create_response.status_code == 201
    request_id = create_response.get_json()['request']['id']

    with app_context.app.app_context():
        app_context.app.config['PAYMENTS_ENABLED'] = False
        app_context.app.config['STRIPE_SECRET_KEY'] = ''

    financials_response = client.get(
        f'/api/v1/waste-requests/{request_id}/payments',
        headers=customer_headers,
    )
    assert financials_response.status_code == 200
    payload = financials_response.get_json()
    assert payload['payments_enabled'] is False
    assert payload['billing']['mode'] == 'offline'
    assert payload['billing']['launch_scope'] == 'offline_billing'
    assert payload['billing']['offline_reason'] == 'feature_flag_disabled'
    assert payload['billing']['actions_disabled'] == ['charge', 'refund', 'payout']
    assert 'Billing is arranged offline' in payload['billing']['customer_message']


def test_admin_can_update_offline_billing_workflow_for_request(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context, 'suppliers', _provider_frame())

    _create_user(app_context, 'billingadmin2@example.com', 'Password123!', role='admin', name='Billing Admin 2')
    _create_user(app_context, 'billingcustomer2@example.com', 'Password123!', role='customer', name='Billing Customer 2')

    admin_headers = _auth_header(client, 'billingadmin2@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'billingcustomer2@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'Billing Customer 2',
            'requester_email': 'billingcustomer2@example.com',
            'material_type': 'Glass',
            'waste_amount': 1.0,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '1 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': scheduled_time,
        },
        headers=customer_headers,
    )
    assert create_response.status_code == 201
    request_id = create_response.get_json()['request']['id']

    update_response = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/billing',
        json={
            'state': 'invoice_sent',
            'reference': 'INV-1001',
            'notes': 'Invoice emailed to customer',
        },
        headers=admin_headers,
    )
    assert update_response.status_code == 200
    update_payload = update_response.get_json()
    assert update_payload['updated'] is True
    assert update_payload['request']['billing_workflow']['state'] == 'invoice_sent'
    assert update_payload['request']['billing_workflow']['reference'] == 'INV-1001'
    assert update_payload['request']['billing_workflow']['notes'] == 'Invoice emailed to customer'

    request_response = client.get(
        f'/api/v1/waste-requests/{request_id}',
        headers=customer_headers,
    )
    assert request_response.status_code == 200
    request_payload = request_response.get_json()
    assert request_payload['request']['billing_workflow']['state'] == 'invoice_sent'
    assert request_payload['request']['billing_workflow']['reference'] == 'INV-1001'
