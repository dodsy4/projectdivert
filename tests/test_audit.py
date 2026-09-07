"""Tests for the application-wide audit log (AuditEvent + capture hooks)."""

from datetime import datetime

import pytest

from tests.test_app_smoke import _auth_header, _create_user


def _audit_rows(app_context, **filters):
    with app_context.app.app_context():
        query = app_context.AuditEvent.query
        for key, value in filters.items():
            query = query.filter(getattr(app_context.AuditEvent, key) == value)
        return query.order_by(app_context.AuditEvent.id.desc()).all()


def test_get_requests_are_not_audited(client, app_context):
    before = len(_audit_rows(app_context))
    assert client.get('/materials').status_code == 200
    assert client.get('/output').status_code == 200
    assert len(_audit_rows(app_context)) == before


def test_web_mutation_creates_audit_event(client, app_context):
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
    response = client.post('/output', data=payload)
    assert response.status_code == 302

    rows = _audit_rows(app_context, action='diversion_estimate.create')
    assert len(rows) == 1
    row = rows[0]
    assert row.entity_type == 'diversion_estimate'
    assert row.http_method == 'POST'
    assert row.path == '/output'
    assert row.source in {'web', 'system'}
    assert row.request_id


def test_api_mutation_records_actor_and_source(client, app_context):
    _create_user(app_context, 'pushuser@example.com', 'Password123!', role='customer')
    headers = _auth_header(client, 'pushuser@example.com', 'Password123!')

    with app_context.app.app_context():
        user = app_context.User.query.filter_by(email='pushuser@example.com').first()
        user_id = user.id

    response = client.post(
        '/api/v1/push-subscriptions',
        json={'token': 'ExponentPushToken[audit-test]', 'platform': 'ios'},
        headers=headers,
    )
    assert response.status_code == 200

    rows = _audit_rows(app_context, action='push_subscription.register')
    assert len(rows) == 1
    assert rows[0].actor_user_id == user_id
    assert rows[0].actor_email == 'pushuser@example.com'
    assert rows[0].source == 'api'


def test_failed_request_is_not_audited(client, app_context):
    before = len(_audit_rows(app_context))
    # No bearer token -> 401 before the handler runs.
    response = client.post('/api/v1/push-subscriptions', json={'token': 'x'})
    assert response.status_code == 401
    assert len(_audit_rows(app_context)) == before


def test_record_audit_event_records_diff_and_survives_bad_payload(app_context):
    with app_context.app.test_request_context('/x', method='POST'):
        app_context.record_audit_event(
            action='unit.test',
            entity_type='thing',
            entity_id=7,
            summary='changed a thing',
            changes=app_context._audit_diff({'status': 'a'}, {'status': 'b'}),
        )
        # Non-serialisable change payload must not raise.
        app_context.record_audit_event(
            action='unit.test.badpayload',
            changes={'obj': object()},
        )

    rows = _audit_rows(app_context, action='unit.test')
    assert rows and rows[0].changes == {'status': ['a', 'b']}
    bad = _audit_rows(app_context, action='unit.test.badpayload')
    assert bad and 'obj' in bad[0].changes  # object() coerced to a string


def test_admin_audit_events_api_lists_and_filters(client, app_context):
    _create_user(app_context, 'auditadmin@example.com', 'Password123!', role='admin')
    headers = _auth_header(client, 'auditadmin@example.com', 'Password123!')

    client.post('/output', data={
        'material': 'Glass', 'amount': '2', 'unit': 'Tonnes',
        'site_address': 'London', 'traditional_address': 'Leeds',
        'divert_address': 'York', 'traditional_cost': '50', 'divert_cost': '40',
    })

    response = client.get('/api/v1/admin/audit-events?action=diversion_estimate', headers=headers)
    assert response.status_code == 200
    body = response.get_json()
    assert body['pagination']['total'] >= 1
    assert all('diversion_estimate' in item['action'] for item in body['items'])


def test_admin_audit_page_requires_admin(client, app_context):
    assert client.get('/admin/audit').status_code == 302  # redirected to login
