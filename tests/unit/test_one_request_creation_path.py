"""Tests for the single waste-request creation service.

The point of collapsing the three copies is that they cannot drift again, so
the central test drives all three transports and compares what each persisted.
The rest pin the two bugs the drift had already produced on the WhatsApp path:
a status the dispatch board does not consider active, and dispatch offers that
were built and then thrown away.
"""

from datetime import timedelta

import pandas as pd
import pytest

from projectdivert.services import chatbot, waste_requests
from projectdivert.services.dispatch import _dispatch_incident_active_statuses
from projectdivert.services.utils import utcnow
from projectdivert.services.waste_requests import (
    INITIAL_STATUS,
    WasteRequestError,
    create_waste_request,
)
from tests.helpers import _auth_header, _create_user


def _stub_geocoding_and_providers(app_context, monkeypatch):
    """One provider in range, and a postcode lookup that never leaves the process."""
    monkeypatch.setattr(
        waste_requests, '_postcode_coordinates', lambda postcode: (51.5072, -0.1276),
    )
    monkeypatch.setattr(
        app_context.reference_data,
        'suppliers',
        pd.DataFrame([{
            'name': 'Provider Alpha', 'sup_type': 'Waste Carrier', 'city': 'London',
            'postcode': 'SW1A1AA', 'lat': 51.5074, 'long': -0.1278,
        }]),
    )
    monkeypatch.setattr(
        app_context.geo, '_drive_time_between_points',
        lambda *args, **kwargs: {'minutes': 12.0, 'text': '12 mins'},
    )


def _future_pickup():
    return (utcnow() + timedelta(days=2)).replace(microsecond=0)


def _payload(**overrides):
    payload = {
        'requester_name': 'Test Requester',
        'requester_email': 'requester@example.com',
        'material_type': 'Glass',
        'waste_amount': '2.5',
        'waste_unit': 'Tonnes',
        'match_radius_miles': '25',
        'pickup_address': '1 Example Road',
        'pickup_postcode': 'SW1A1AA',
        'scheduled_pickup_at': _future_pickup().strftime('%Y-%m-%dT%H:%M'),
    }
    payload.update(overrides)
    return payload


def _persisted_shape(app_context, booking):
    """The parts of a request that every transport should agree on."""
    offers = app_context.WasteRemovalDispatchOffer.query.filter_by(
        waste_removal_request_id=booking.id,
    ).all()
    return {
        'status': booking.status,
        'material_type': booking.material_type,
        'waste_amount': booking.waste_amount,
        'waste_unit': booking.waste_unit,
        'pickup_postcode': booking.pickup_postcode,
        'offers': len(offers),
        'offer_providers': sorted(o.provider_name for o in offers),
        'offer_statuses': sorted({o.status for o in offers}),
    }


# --- The three transports agree ---------------------------------------------


def test_all_three_transports_persist_the_same_shape(client, app_context, monkeypatch):
    """The regression this refactor exists to prevent."""
    _stub_geocoding_and_providers(app_context, monkeypatch)
    _create_user(app_context, 'customer@example.com', 'Password123!', role='customer', name='C')
    headers = _auth_header(client, 'customer@example.com', 'Password123!')

    shapes = {}

    # 1. JSON API.
    response = client.post('/api/v1/waste-requests', json=_payload(), headers=headers)
    assert response.status_code == 201, response.get_json()
    with app_context.app.app_context():
        booking = app_context.db.session.get(
            app_context.WasteRemovalRequest, response.get_json()['request']['id'],
        )
        shapes['api'] = _persisted_shape(app_context, booking)

    # 2. Server-rendered form.
    form_response = client.post('/waste-removal/request', data=_payload())
    assert form_response.status_code == 302
    with app_context.app.app_context():
        booking = (
            app_context.WasteRemovalRequest.query
            .order_by(app_context.WasteRemovalRequest.id.desc()).first()
        )
        shapes['web'] = _persisted_shape(app_context, booking)

    # 3. WhatsApp assistant.
    with app_context.app.app_context():
        user = app_context.User.query.filter_by(email='customer@example.com').first()
        result = chatbot._tool_create_request(
            user,
            material_type='Glass',
            waste_amount='2.5',
            waste_unit='Tonnes',
            pickup_address='1 Example Road',
            pickup_postcode='SW1A1AA',
            scheduled_pickup_at=_future_pickup().isoformat(),
        )
        assert result.get('created') is True, result
        booking = (
            app_context.WasteRemovalRequest.query
            .order_by(app_context.WasteRemovalRequest.id.desc()).first()
        )
        shapes['whatsapp'] = _persisted_shape(app_context, booking)

    assert shapes['api'] == shapes['web'] == shapes['whatsapp'], shapes


# --- The two bugs the WhatsApp copy had -------------------------------------


def test_a_whatsapp_request_is_visible_to_dispatch(client, app_context, monkeypatch):
    """It used to be stored as 'pending', which the dispatch board ignores."""
    _stub_geocoding_and_providers(app_context, monkeypatch)
    _create_user(app_context, 'wa@example.com', 'Password123!', role='customer', name='WA')
    _create_user(app_context, 'admin@example.com', 'Password123!', role='admin', name='A')

    with app_context.app.app_context():
        user = app_context.User.query.filter_by(email='wa@example.com').first()
        result = chatbot._tool_create_request(
            user,
            material_type='Glass', waste_amount='2', waste_unit='Tonnes',
            pickup_address='1 Example Road', pickup_postcode='SW1A1AA',
            scheduled_pickup_at=_future_pickup().isoformat(),
        )
        assert result.get('created') is True, result
        booking = (
            app_context.WasteRemovalRequest.query
            .order_by(app_context.WasteRemovalRequest.id.desc()).first()
        )
        assert booking.status == INITIAL_STATUS
        assert booking.status in _dispatch_incident_active_statuses()

    # And it actually shows up on the admin dispatch queue.
    headers = _auth_header(client, 'admin@example.com', 'Password123!')
    queue = client.get('/api/v1/admin/dispatch/queue', headers=headers)
    assert queue.status_code == 200
    ids = [item['request']['id'] for item in queue.get_json()['items']]
    assert ids, 'the WhatsApp request did not reach the dispatch queue'


def test_a_whatsapp_request_persists_its_dispatch_offers(app_context, monkeypatch):
    """The rows were built and then never added to the session."""
    _stub_geocoding_and_providers(app_context, monkeypatch)
    _create_user(app_context, 'wa2@example.com', 'Password123!', role='customer', name='WA')

    with app_context.app.app_context():
        user = app_context.User.query.filter_by(email='wa2@example.com').first()
        result = chatbot._tool_create_request(
            user,
            material_type='Glass', waste_amount='2', waste_unit='Tonnes',
            pickup_address='1 Example Road', pickup_postcode='SW1A1AA',
            scheduled_pickup_at=_future_pickup().isoformat(),
        )
        assert result.get('created') is True, result
        booking = (
            app_context.WasteRemovalRequest.query
            .order_by(app_context.WasteRemovalRequest.id.desc()).first()
        )
        offers = app_context.WasteRemovalDispatchOffer.query.filter_by(
            waste_removal_request_id=booking.id,
        ).all()

    assert len(offers) == 1, 'no offer means no driver is ever notified'
    assert offers[0].status == 'offered'
    assert offers[0].offer_token


def test_a_whatsapp_request_can_then_be_claimed(app_context, monkeypatch):
    """Without persisted offers there was nothing for a driver to claim."""
    _stub_geocoding_and_providers(app_context, monkeypatch)
    _create_user(app_context, 'wa3@example.com', 'Password123!', role='customer', name='WA')
    _create_user(app_context, 'driver3@example.com', 'Password123!', role='driver', name='D')

    with app_context.app.app_context():
        user = app_context.User.query.filter_by(email='wa3@example.com').first()
        assert chatbot._tool_create_request(
            user,
            material_type='Glass', waste_amount='2', waste_unit='Tonnes',
            pickup_address='1 Example Road', pickup_postcode='SW1A1AA',
            scheduled_pickup_at=_future_pickup().isoformat(),
        ).get('created') is True

        booking = (
            app_context.WasteRemovalRequest.query
            .order_by(app_context.WasteRemovalRequest.id.desc()).first()
        )
        driver = app_context.User.query.filter_by(email='driver3@example.com').first()
        claim = chatbot._tool_claim_job(driver, booking.id)

    assert claim.get('claimed') is True, claim


# --- Shared validation -------------------------------------------------------


def test_the_service_rejects_missing_fields_and_names_them(app_context, monkeypatch):
    _stub_geocoding_and_providers(app_context, monkeypatch)
    with app_context.app.app_context():
        with pytest.raises(WasteRequestError) as excinfo:
            create_waste_request({'requester_name': 'Only a name'})
    assert 'Missing required field(s)' in str(excinfo.value)
    assert 'pickup_postcode' in excinfo.value.fields
    assert 'requester_name' not in excinfo.value.fields


@pytest.mark.parametrize(
    'overrides, expected',
    [
        ({'waste_amount': '0'}, 'waste_amount must be a positive number'),
        ({'waste_amount': 'lots'}, 'waste_amount must be a positive number'),
        ({'match_radius_miles': '-3'}, 'match_radius_miles must be a positive number'),
        ({'material_type': 'Other'}, 'custom_material_type is required'),
    ],
)
def test_the_service_rejects_bad_values(app_context, monkeypatch, overrides, expected):
    _stub_geocoding_and_providers(app_context, monkeypatch)
    with app_context.app.app_context():
        with pytest.raises(WasteRequestError) as excinfo:
            create_waste_request(_payload(**overrides))
    assert expected in str(excinfo.value)


def test_a_past_pickup_is_rejected(app_context, monkeypatch):
    _stub_geocoding_and_providers(app_context, monkeypatch)
    past = (utcnow() - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    with app_context.app.app_context():
        with pytest.raises(WasteRequestError) as excinfo:
            create_waste_request(_payload(scheduled_pickup_at=past))
    assert 'must be in the future' in str(excinfo.value)


def test_other_material_type_uses_the_free_text_value(app_context, monkeypatch):
    _stub_geocoding_and_providers(app_context, monkeypatch)
    with app_context.app.app_context():
        created = create_waste_request(
            _payload(material_type='Other', custom_material_type='Reclaimed oak'),
        )
        assert created.booking.material_type == 'Reclaimed oak'


def test_requester_email_is_stored_lowercased(app_context, monkeypatch):
    _stub_geocoding_and_providers(app_context, monkeypatch)
    with app_context.app.app_context():
        created = create_waste_request(_payload(requester_email='MiXeD@Example.COM'))
        assert created.booking.requester_email == 'mixed@example.com'


def test_notify_false_persists_without_telling_anyone(app_context, monkeypatch):
    _stub_geocoding_and_providers(app_context, monkeypatch)
    sent = []
    monkeypatch.setattr(
        waste_requests, '_notify_dispatch_offers',
        lambda *args, **kwargs: sent.append(args) or 1,
    )
    with app_context.app.app_context():
        created = create_waste_request(_payload(), notify=False)
        assert created.booking.id is not None
        assert created.offers_created == 1
    assert sent == []


# --- Transport-specific behaviour is still transport-specific ----------------


def test_a_customer_cannot_raise_a_request_as_somebody_else(client, app_context, monkeypatch):
    """The JWT identity override is the API's own rule, and must survive."""
    _stub_geocoding_and_providers(app_context, monkeypatch)
    _create_user(app_context, 'me@example.com', 'Password123!', role='customer', name='Me')
    headers = _auth_header(client, 'me@example.com', 'Password123!')

    response = client.post(
        '/api/v1/waste-requests',
        json=_payload(requester_email='someone.else@example.com'),
        headers=headers,
    )
    assert response.status_code == 201
    assert response.get_json()['request']['requester_email'] == 'me@example.com'


def test_an_admin_may_raise_a_request_for_someone_else(client, app_context, monkeypatch):
    _stub_geocoding_and_providers(app_context, monkeypatch)
    _create_user(app_context, 'admin2@example.com', 'Password123!', role='admin', name='A')
    headers = _auth_header(client, 'admin2@example.com', 'Password123!')

    response = client.post(
        '/api/v1/waste-requests',
        json=_payload(requester_email='client@example.com'),
        headers=headers,
    )
    assert response.status_code == 201
    assert response.get_json()['request']['requester_email'] == 'client@example.com'


def test_the_api_reports_missing_fields_individually(client, app_context, monkeypatch):
    _stub_geocoding_and_providers(app_context, monkeypatch)
    _create_user(app_context, 'c2@example.com', 'Password123!', role='customer', name='C')
    headers = _auth_header(client, 'c2@example.com', 'Password123!')

    response = client.post('/api/v1/waste-requests', json={}, headers=headers)
    assert response.status_code == 400
    body = response.get_json()
    assert body['error'] == 'Missing required field(s)'
    assert 'pickup_postcode' in body['fields']


def test_the_form_names_missing_fields_in_prose(client, app_context, monkeypatch):
    """The form has always spoken sentences; the service speaks field names."""
    _stub_geocoding_and_providers(app_context, monkeypatch)
    with client.session_transaction() as session:
        session.clear()

    response = client.post('/waste-removal/request', data={}, follow_redirects=True)
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'Missing required field(s):' in body
    assert 'pickup_postcode' in body
