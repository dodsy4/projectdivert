import json
from datetime import datetime, timedelta

import pytest


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


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
        lambda *args, **kwargs: FakeResponse({'result': {'longitude': -0.1276, 'latitude': 51.5072}}),
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


def test_waste_removal_request_valid_creates_record(client, app_context):
    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    payload = {
        'requester_name': 'Test User',
        'requester_email': 'test@example.com',
        'material_type': 'Glass',
        'waste_amount': '2.5',
        'waste_unit': 'Tonnes',
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

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/waste-removal/request')
    assert count_after == count_before + 1
    assert latest.material_type == 'Glass'
    assert latest.waste_amount == pytest.approx(2.5)


def test_waste_removal_request_past_time_is_rejected(client, app_context):
    past_time = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M')
    payload = {
        'requester_name': 'Test User',
        'requester_email': 'test@example.com',
        'material_type': 'Glass',
        'waste_amount': '1',
        'waste_unit': 'Tonnes',
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


def test_waste_removal_request_sends_notification_email(client, app_context, monkeypatch):
    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    payload = {
        'requester_name': 'Test User',
        'requester_email': 'test@example.com',
        'material_type': 'Glass',
        'waste_amount': '2.5',
        'waste_unit': 'Tonnes',
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
