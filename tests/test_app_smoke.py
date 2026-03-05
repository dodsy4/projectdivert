import json
from datetime import datetime, timedelta

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
