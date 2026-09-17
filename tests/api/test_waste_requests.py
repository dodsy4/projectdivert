"""Tests for the waste-request lifecycle, status and live location."""

from datetime import datetime, timedelta

from tests.helpers import _auth_header, _create_user, _fake_postcode_lookup, _provider_frame


def test_api_requires_bearer_token(client):
    response = client.post('/api/v1/waste-requests', json={})
    assert response.status_code == 401
    assert response.get_json()['error'] == 'Missing Bearer token'


def test_api_create_waste_request_returns_match_and_drive_time(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context.geo,
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


def test_api_customer_cannot_update_status(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context.geo,
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
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context.geo,
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
