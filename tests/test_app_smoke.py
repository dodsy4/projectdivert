import json


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
