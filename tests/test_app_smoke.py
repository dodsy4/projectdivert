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
        latest_match = app_context.WasteRemovalMatch.query.order_by(app_context.WasteRemovalMatch.id.desc()).first()

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/waste-removal/request')
    assert count_after == count_before + 1
    assert latest.material_type == 'Glass'
    assert latest.waste_amount == pytest.approx(2.5)
    assert latest.status == 'matched'
    assert latest_match.waste_removal_request_id == latest.id
    assert latest_match.provider_name == 'Provider Alpha'


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
    assert 'Matched Provider: Provider Alpha' in captured['text_body']
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
    assert body['request']['status'] == 'matched'
    assert body['request']['requester_email'] == 'mobile@example.com'
    assert body['match']['provider_name'] == 'Provider Alpha'
    assert body['drive_time']['text'] == '18 mins'


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
    assert latest_body['latest_location']['driver_id'] == 'driver-1'
    assert latest_body['latest_location']['vehicle_id'] == 'van-42'


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
