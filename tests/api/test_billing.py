"""Tests for the offline billing workflow and customer communications."""

from datetime import datetime, timedelta

from tests.helpers import _auth_header, _create_user, _fake_postcode_lookup, _provider_frame
from projectdivert.services.utils import utcnow


def test_admin_can_update_offline_billing_workflow_for_request(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())

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


def test_admin_billing_requests_list_filters_and_export(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())

    _create_user(app_context, 'billingadmin3@example.com', 'Password123!', role='admin', name='Billing Admin 3')
    _create_user(app_context, 'billingcustomer3@example.com', 'Password123!', role='customer', name='Billing Customer 3')

    admin_headers = _auth_header(client, 'billingadmin3@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'billingcustomer3@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')

    created_ids = []
    for index, material in enumerate(['Glass', 'Metal'], start=1):
        create_response = client.post(
            '/api/v1/waste-requests',
            json={
                'requester_name': 'Billing Customer 3',
                'requester_email': 'billingcustomer3@example.com',
                'material_type': material,
                'waste_amount': 1.0 + index,
                'waste_unit': 'Tonnes',
                'match_radius_miles': 25,
                'pickup_address': f'{index} Example Road',
                'pickup_postcode': 'SW1A1AA',
                'scheduled_pickup_at': scheduled_time,
            },
            headers=customer_headers,
        )
        assert create_response.status_code == 201
        created_ids.append(create_response.get_json()['request']['id'])

    first_id, second_id = created_ids
    first_update = client.post(
        f'/api/v1/admin/waste-requests/{first_id}/billing',
        json={
            'state': 'invoice_sent',
            'reference': 'INV-2001',
            'notes': 'First invoice sent',
        },
        headers=admin_headers,
    )
    assert first_update.status_code == 200

    second_update = client.post(
        f'/api/v1/admin/waste-requests/{second_id}/billing',
        json={
            'state': 'paid_offline',
            'reference': 'INV-2002',
            'notes': 'Paid by bank transfer',
        },
        headers=admin_headers,
    )
    assert second_update.status_code == 200

    list_response = client.get(
        '/api/v1/admin/billing/requests?state=paid_offline&reference=INV-2002&limit=10',
        headers=admin_headers,
    )
    assert list_response.status_code == 200
    list_payload = list_response.get_json()
    assert list_payload['pagination']['total'] == 1
    assert len(list_payload['items']) == 1
    assert list_payload['items'][0]['request']['id'] == second_id
    assert list_payload['items'][0]['request']['billing_workflow']['state'] == 'paid_offline'
    assert list_payload['items'][0]['request']['billing_workflow']['reference'] == 'INV-2002'
    assert list_payload['summary']['state_counts']['paid_offline'] == 1

    export_response = client.get(
        '/api/v1/admin/billing/requests/export?search=INV-2002&limit=10',
        headers=admin_headers,
    )
    assert export_response.status_code == 200
    assert export_response.mimetype == 'text/csv'
    export_text = export_response.get_data(as_text=True)
    assert 'request_id,request_status,billing_state,billing_reference' in export_text
    assert 'INV-2002' in export_text
    assert 'paid_offline' in export_text


def test_admin_can_log_request_communications_and_customer_sees_visible_entries_only(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())

    _create_user(app_context, 'billingadmin4@example.com', 'Password123!', role='admin', name='Billing Admin 4')
    _create_user(app_context, 'billingcustomer4@example.com', 'Password123!', role='customer', name='Billing Customer 4')

    admin_headers = _auth_header(client, 'billingadmin4@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'billingcustomer4@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'Billing Customer 4',
            'requester_email': 'billingcustomer4@example.com',
            'material_type': 'Cardboard',
            'waste_amount': 2.0,
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

    visible_response = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/communications',
        json={
            'direction': 'outbound',
            'channel': 'email',
            'subject': 'Invoice issued',
            'message': 'Sent offline invoice INV-3001 to the customer.',
            'outcome': 'email_sent',
            'contact_email': 'billingcustomer4@example.com',
            'customer_visible': True,
        },
        headers=admin_headers,
    )
    assert visible_response.status_code == 201

    internal_response = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/communications',
        json={
            'direction': 'internal',
            'channel': 'manual',
            'message': 'Customer requested 7-day payment terms.',
            'outcome': 'awaiting_settlement',
            'customer_visible': False,
        },
        headers=admin_headers,
    )
    assert internal_response.status_code == 201

    admin_list_response = client.get(
        f'/api/v1/waste-requests/{request_id}/communications',
        headers=admin_headers,
    )
    assert admin_list_response.status_code == 200
    admin_payload = admin_list_response.get_json()
    assert admin_payload['summary']['total'] == 2
    assert admin_payload['summary']['customer_visible_count'] == 1

    customer_list_response = client.get(
        f'/api/v1/waste-requests/{request_id}/communications',
        headers=customer_headers,
    )
    assert customer_list_response.status_code == 200
    customer_payload = customer_list_response.get_json()
    assert customer_payload['summary']['total'] == 1
    assert len(customer_payload['communications']) == 1
    assert customer_payload['communications'][0]['subject'] == 'Invoice issued'

    request_response = client.get(
        f'/api/v1/waste-requests/{request_id}',
        headers=customer_headers,
    )
    assert request_response.status_code == 200
    request_payload = request_response.get_json()
    assert len(request_payload['communications']) == 1
    assert request_payload['communication_summary']['customer_visible_count'] == 1


def test_admin_communication_templates_and_report_export(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())

    _create_user(app_context, 'billingadmin5@example.com', 'Password123!', role='admin', name='Billing Admin 5')
    _create_user(app_context, 'billingcustomer5@example.com', 'Password123!', role='customer', name='Billing Customer 5')

    admin_headers = _auth_header(client, 'billingadmin5@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'billingcustomer5@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'Billing Customer 5',
            'requester_email': 'billingcustomer5@example.com',
            'material_type': 'Wood',
            'waste_amount': 1.2,
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

    billing_response = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/billing',
        json={'state': 'invoice_sent', 'reference': 'INV-3005'},
        headers=admin_headers,
    )
    assert billing_response.status_code == 200

    template_response = client.get(
        f'/api/v1/admin/waste-requests/{request_id}/communications/templates',
        headers=admin_headers,
    )
    assert template_response.status_code == 200
    templates = template_response.get_json()['templates']
    invoice_template = next(item for item in templates if item['key'] == 'invoice_sent')
    assert invoice_template['customer_visible'] is True
    assert 'INV-3005' in invoice_template['message']

    create_comm_response = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/communications',
        json={
            'direction': invoice_template['direction'],
            'channel': invoice_template['channel'],
            'subject': invoice_template['subject'],
            'message': invoice_template['message'],
            'outcome': invoice_template['outcome'],
            'customer_visible': invoice_template['customer_visible'],
        },
        headers=admin_headers,
    )
    assert create_comm_response.status_code == 201

    report_response = client.get(
        '/api/v1/admin/communications/report?direction=outbound&channel=email&search=INV-3005&limit=10',
        headers=admin_headers,
    )
    assert report_response.status_code == 200
    report_payload = report_response.get_json()
    assert report_payload['pagination']['total'] == 1
    assert report_payload['items'][0]['request']['id'] == request_id
    assert report_payload['summary']['direction_counts']['outbound'] == 1

    export_response = client.get(
        '/api/v1/admin/communications/export?search=INV-3005&limit=10',
        headers=admin_headers,
    )
    assert export_response.status_code == 200
    assert export_response.mimetype == 'text/csv'
    export_text = export_response.get_data(as_text=True)
    assert 'communication_id,request_id,request_status,billing_state,billing_reference' in export_text
    assert 'INV-3005' in export_text


def test_admin_billing_followups_report_and_maintenance(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())

    _create_user(app_context, 'billingadmin6@example.com', 'Password123!', role='admin', name='Billing Admin 6')
    _create_user(app_context, 'billingcustomer6@example.com', 'Password123!', role='customer', name='Billing Customer 6')

    admin_headers = _auth_header(client, 'billingadmin6@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'billingcustomer6@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'Billing Customer 6',
            'requester_email': 'billingcustomer6@example.com',
            'material_type': 'Metal',
            'waste_amount': 2.0,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '2 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': scheduled_time,
        },
        headers=customer_headers,
    )
    assert create_response.status_code == 201
    request_id = create_response.get_json()['request']['id']

    billing_response = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/billing',
        json={'state': 'invoice_sent', 'reference': 'INV-4006'},
        headers=admin_headers,
    )
    assert billing_response.status_code == 200

    with app_context.app.app_context():
        booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
        booking.billing_updated_at = utcnow() - timedelta(hours=96)
        app_context.db.session.commit()

    followup_response = client.get(
        '/api/v1/admin/billing/followups?reminder_after_hours=24&repeat_hours=48&limit=10',
        headers=admin_headers,
    )
    assert followup_response.status_code == 200
    followup_payload = followup_response.get_json()
    assert followup_payload['summary']['due_now_count'] == 1
    assert followup_payload['items'][0]['request']['id'] == request_id
    assert followup_payload['items'][0]['followup']['due_reason'] == 'invoice_age_exceeded'

    maintenance_response = client.post(
        '/api/v1/admin/billing/followups/maintenance',
        json={
            'reminder_after_hours': 24,
            'repeat_hours': 48,
            'limit': 10,
            'dry_run': False,
            'log_reminders': True,
        },
        headers=admin_headers,
    )
    assert maintenance_response.status_code == 200
    maintenance_payload = maintenance_response.get_json()
    assert maintenance_payload['summary']['reminders_logged'] == 1
    assert maintenance_payload['items'][0]['request_id'] == request_id

    communications_response = client.get(
        f'/api/v1/waste-requests/{request_id}/communications?limit=20',
        headers=admin_headers,
    )
    assert communications_response.status_code == 200
    communications_payload = communications_response.get_json()
    assert any(
        row['outcome'] == 'payment_reminder_sent'
        for row in communications_payload['communications']
    )


def test_admin_ops_health_reports_billing_followups_due(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())
    monkeypatch.setitem(app_context.app.config, 'OPS_HEALTH_BILLING_FOLLOWUPS_WARN', 1)
    monkeypatch.setitem(app_context.app.config, 'OPS_HEALTH_BILLING_FOLLOWUPS_CRITICAL', 5)
    monkeypatch.setitem(app_context.app.config, 'OFFLINE_BILLING_FOLLOWUP_AFTER_HOURS', 24)
    monkeypatch.setitem(app_context.app.config, 'OFFLINE_BILLING_FOLLOWUP_REPEAT_HOURS', 48)

    _create_user(app_context, 'billingadmin7@example.com', 'Password123!', role='admin', name='Billing Admin 7')
    _create_user(app_context, 'billingcustomer7@example.com', 'Password123!', role='customer', name='Billing Customer 7')

    admin_headers = _auth_header(client, 'billingadmin7@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'billingcustomer7@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'Billing Customer 7',
            'requester_email': 'billingcustomer7@example.com',
            'material_type': 'Glass',
            'waste_amount': 0.8,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '3 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': scheduled_time,
        },
        headers=customer_headers,
    )
    assert create_response.status_code == 201
    request_id = create_response.get_json()['request']['id']

    billing_response = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/billing',
        json={'state': 'invoice_sent', 'reference': 'INV-5007'},
        headers=admin_headers,
    )
    assert billing_response.status_code == 200

    with app_context.app.app_context():
        booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
        booking.billing_updated_at = utcnow() - timedelta(hours=120)
        app_context.db.session.commit()

    ops_response = client.get(
        '/api/v1/admin/ops/health?auth_window_minutes=60&dispatch_limit=100',
        headers=admin_headers,
    )
    assert ops_response.status_code == 200
    ops_payload = ops_response.get_json()
    assert ops_payload['metrics']['billing']['followups_due'] >= 1
    alert_codes = {row['code'] for row in ops_payload['alerts']}
    assert 'billing_followups_warn' in alert_codes or 'billing_followups_critical' in alert_codes


def test_admin_billing_followup_maintenance_accepts_zero_hour_threshold(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())

    _create_user(app_context, 'billingadmin8@example.com', 'Password123!', role='admin', name='Billing Admin 8')
    _create_user(app_context, 'billingcustomer8@example.com', 'Password123!', role='customer', name='Billing Customer 8')

    admin_headers = _auth_header(client, 'billingadmin8@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'billingcustomer8@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'Billing Customer 8',
            'requester_email': 'billingcustomer8@example.com',
            'material_type': 'Cardboard',
            'waste_amount': 1.0,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '4 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': scheduled_time,
        },
        headers=customer_headers,
    )
    assert create_response.status_code == 201
    request_id = create_response.get_json()['request']['id']

    billing_response = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/billing',
        json={'state': 'invoice_sent', 'reference': 'INV-6008'},
        headers=admin_headers,
    )
    assert billing_response.status_code == 200

    maintenance_response = client.post(
        '/api/v1/admin/billing/followups/maintenance',
        json={
            'reminder_after_hours': 0,
            'repeat_hours': 48,
            'limit': 10,
            'dry_run': False,
            'log_reminders': True,
        },
        headers=admin_headers,
    )
    assert maintenance_response.status_code == 200
    maintenance_payload = maintenance_response.get_json()
    assert maintenance_payload['summary']['reminders_logged'] >= 1
    assert request_id in [item['request_id'] for item in maintenance_payload['items']]


def test_admin_can_acknowledge_and_close_billing_followups(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())

    _create_user(app_context, 'billingadmin9@example.com', 'Password123!', role='admin', name='Billing Admin 9')
    _create_user(app_context, 'billingcustomer9@example.com', 'Password123!', role='customer', name='Billing Customer 9')

    admin_headers = _auth_header(client, 'billingadmin9@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'billingcustomer9@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'Billing Customer 9',
            'requester_email': 'billingcustomer9@example.com',
            'material_type': 'Wood',
            'waste_amount': 1.2,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '5 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': scheduled_time,
        },
        headers=customer_headers,
    )
    assert create_response.status_code == 201
    request_id = create_response.get_json()['request']['id']

    billing_response = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/billing',
        json={'state': 'invoice_sent', 'reference': 'INV-7009'},
        headers=admin_headers,
    )
    assert billing_response.status_code == 200
    assert billing_response.get_json()['request']['billing_followup_workflow']['state'] == 'open'

    with app_context.app.app_context():
        booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
        booking.billing_updated_at = utcnow() - timedelta(hours=96)
        app_context.db.session.commit()

    acknowledge_response = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/billing-followup',
        json={'state': 'acknowledged', 'notes': 'Called customer, waiting for remittance advice.'},
        headers=admin_headers,
    )
    assert acknowledge_response.status_code == 200
    acknowledge_payload = acknowledge_response.get_json()
    assert acknowledge_payload['updated'] is True
    assert acknowledge_payload['followup']['state'] == 'acknowledged'

    followup_response = client.get(
        '/api/v1/admin/billing/followups?reminder_after_hours=24&repeat_hours=48&limit=10',
        headers=admin_headers,
    )
    assert followup_response.status_code == 200
    followup_payload = followup_response.get_json()
    assert followup_payload['summary']['due_now_count'] == 0
    assert followup_payload['summary']['state_counts']['acknowledged'] >= 1

    maintenance_response = client.post(
        '/api/v1/admin/billing/followups/maintenance',
        json={
            'reminder_after_hours': 24,
            'repeat_hours': 48,
            'limit': 10,
            'dry_run': False,
            'log_reminders': True,
        },
        headers=admin_headers,
    )
    assert maintenance_response.status_code == 200
    assert maintenance_response.get_json()['summary']['reminders_logged'] == 0

    close_response = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/billing-followup',
        json={'state': 'closed', 'notes': 'Customer confirmed bank transfer outside the app.'},
        headers=admin_headers,
    )
    assert close_response.status_code == 200
    close_payload = close_response.get_json()
    assert close_payload['followup']['state'] == 'closed'

    admin_comm_response = client.get(
        f'/api/v1/waste-requests/{request_id}/communications?limit=20',
        headers=admin_headers,
    )
    assert admin_comm_response.status_code == 200
    admin_outcomes = [row['outcome'] for row in admin_comm_response.get_json()['communications']]
    assert 'billing_followup_acknowledged' in admin_outcomes
    assert 'billing_followup_closed' in admin_outcomes

    customer_comm_response = client.get(
        f'/api/v1/waste-requests/{request_id}/communications?limit=20',
        headers=customer_headers,
    )
    assert customer_comm_response.status_code == 200
    customer_outcomes = [row['outcome'] for row in customer_comm_response.get_json()['communications']]
    assert 'billing_followup_acknowledged' not in customer_outcomes
    assert 'billing_followup_closed' not in customer_outcomes
