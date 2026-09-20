"""Tests for dispatch offers, incidents, telemetry and admin override."""

from datetime import datetime, timedelta
import pandas as pd

from tests.helpers import _auth_header, _create_user, _fake_postcode_lookup, _provider_frame, _seed_driver_dispatch_compliance
from projectdivert.services.utils import utcnow


def test_api_status_and_location_flow(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context.geo,
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
        app_context.reference_data,
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


def test_admin_dispatch_incident_ack_resolve_flow(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context.geo,
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
            booking.created_at = utcnow() - timedelta(minutes=2)
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
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context.geo,
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
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context.geo,
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
            booking.created_at = utcnow() - timedelta(minutes=3)
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
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context.geo,
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
            booking.created_at = utcnow() - timedelta(minutes=90)
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


def test_admin_dispatch_request_timeline_includes_dispatch_and_auth_events(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context.geo,
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
            booking.created_at = utcnow() - timedelta(minutes=3)
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


def test_driver_compliance_documents_control_dispatch_eligibility_and_admin_override(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())

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
                # A real-shaped Environment Agency number: a carrier licence is
                # validated on the way in, so a placeholder is refused.
                'document_reference': (
                    'CBDU123456' if document_type == 'carrier_license'
                    else f'{document_type.upper()}-123'
                ),
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
                # A real-shaped Environment Agency number: a carrier licence is
                # validated on the way in, so a placeholder is refused.
                'document_reference': (
                    'CBDU123456' if document_type == 'carrier_license'
                    else f'{document_type.upper()}-123'
                ),
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
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())

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
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())

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


def test_accepting_an_offer_locks_the_request_row(app_context):
    """Concurrent acceptances must serialise on the request row.

    SQLite ignores ``FOR UPDATE``, so a behavioural test cannot catch the lock
    going missing -- the statement itself is inspected instead.
    """
    from sqlalchemy import event

    from projectdivert.services.dispatch import _accept_dispatch_offer

    db = app_context.db
    with app_context.app.app_context():
        booking = app_context.WasteRemovalRequest(
            requester_name='Sam', requester_email='sam@example.com',
            material_type='Timber', waste_amount=2.0, waste_unit='tonnes',
            pickup_address='1 Site Road', pickup_postcode='SW1A1AA',
            scheduled_pickup_at=utcnow() + timedelta(days=2),
            status='pending',
        )
        db.session.add(booking)
        db.session.commit()
        offer = app_context.WasteRemovalDispatchOffer(
            waste_removal_request_id=booking.id,
            provider_name='Acme Recycling', provider_latitude=51.5,
            provider_longitude=-0.12, distance_miles=4.2, match_radius_miles=25.0,
            offer_rank=1, offer_token='lock-test-token', status='offered',
        )
        db.session.add(offer)
        db.session.commit()

        locked_statements = []

        @event.listens_for(db.engine, 'before_execute')
        def _record_locking_selects(conn, clauseelement, multiparams, params, execution_options):
            if getattr(clauseelement, '_for_update_arg', None) is not None:
                locked_statements.append(str(clauseelement))

        try:
            _match, outcome = _accept_dispatch_offer(booking, offer)
        finally:
            event.remove(db.engine, 'before_execute', _record_locking_selects)

        assert outcome == 'accepted'
        assert any('FROM waste_removal_requests' in statement for statement in locked_statements), (
            'the request row should be selected FOR UPDATE before the match is created'
        )
