"""Tests for Stripe charges, refunds and driver payouts."""

from datetime import datetime, timedelta
from datetime import datetime, timedelta

from tests.helpers import _auth_header, _create_user, _fake_postcode_lookup, _provider_frame


def test_waste_request_financials_report_offline_billing_launch_mode(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())

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
