"""Tests for /api/v1/auth: login, signup, refresh, verification, password reset."""

from datetime import datetime, timedelta
from datetime import datetime, timedelta

from tests.helpers import _auth_header, _create_user, _fake_postcode_lookup, _provider_frame, _reset_auth_security_runtime_state


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


def test_auth_login_lockout_escalates_duration_on_repeated_lockouts(client, app_context):
    _create_user(app_context, 'escalate@example.com', 'Password123!', role='customer', name='Escalate User')

    overrides = {
        'AUTH_RATE_LIMIT_ENABLED': False,
        'AUTH_LOGIN_LOCKOUT_ENABLED': True,
        'AUTH_LOGIN_LOCKOUT_MAX_ATTEMPTS': 2,
        'AUTH_LOGIN_LOCKOUT_WINDOW_SECONDS': 300,
        'AUTH_LOGIN_LOCKOUT_DURATION_SECONDS': 60,
        'AUTH_LOGIN_LOCKOUT_ESCALATION_ENABLED': True,
        'AUTH_LOGIN_LOCKOUT_ESCALATION_FACTOR': 2,
        'AUTH_LOGIN_LOCKOUT_ESCALATION_RESET_SECONDS': 3600,
        'AUTH_LOGIN_LOCKOUT_MAX_DURATION_SECONDS': 300,
        'AUTH_REQUIRE_EMAIL_VERIFICATION': False,
    }
    original = {key: app_context.app.config.get(key) for key in overrides}
    app_context.app.config.update(overrides)
    _reset_auth_security_runtime_state(app_context)

    try:
        first_attempt = client.post(
            '/api/v1/auth/login',
            json={'email': 'escalate@example.com', 'password': 'WrongPass123'},
        )
        first_lock = client.post(
            '/api/v1/auth/login',
            json={'email': 'escalate@example.com', 'password': 'WrongPass123'},
        )
        assert first_attempt.status_code == 401
        assert first_lock.status_code == 429
        first_retry_after = int(first_lock.headers['Retry-After'])

        # Simulate lockout expiry without waiting so we can trigger a second lockout cycle.
        with app_context._auth_login_lockout_lock:
            for key, state in list(app_context._auth_login_lockouts.items()):
                if not key.startswith('ip:') and not key.endswith('escalate@example.com'):
                    continue
                state['locked_until'] = datetime.utcnow() - timedelta(seconds=1)
                state['count'] = 0
                state['first_failed_at'] = None
                app_context._auth_login_lockouts[key] = state

        second_attempt = client.post(
            '/api/v1/auth/login',
            json={'email': 'escalate@example.com', 'password': 'WrongPass123'},
        )
        second_lock = client.post(
            '/api/v1/auth/login',
            json={'email': 'escalate@example.com', 'password': 'WrongPass123'},
        )
        assert second_attempt.status_code == 401
        assert second_lock.status_code == 429
        second_retry_after = int(second_lock.headers['Retry-After'])
        assert second_retry_after > first_retry_after

        with app_context.app.app_context():
            latest = (
                app_context.AuthAuditEvent.query.filter_by(event='login', email='escalate@example.com')
                .order_by(app_context.AuthAuditEvent.id.desc())
                .first()
            )
            details = latest.details_json or {}

        assert details.get('reason') == 'lockout_triggered'
        assert int(details.get('lockout_level') or 0) >= 2
    finally:
        app_context.app.config.update(original)
        _reset_auth_security_runtime_state(app_context)


def test_auth_lockout_revokes_sessions_when_suspicious_activity_enabled(client, app_context):
    _create_user(app_context, 'suspicious@example.com', 'Password123!', role='customer', name='Suspicious User')
    login = client.post(
        '/api/v1/auth/login',
        json={'email': 'suspicious@example.com', 'password': 'Password123!'},
    )
    assert login.status_code == 200

    overrides = {
        'AUTH_RATE_LIMIT_ENABLED': False,
        'AUTH_LOGIN_LOCKOUT_ENABLED': True,
        'AUTH_LOGIN_LOCKOUT_MAX_ATTEMPTS': 2,
        'AUTH_LOGIN_LOCKOUT_WINDOW_SECONDS': 300,
        'AUTH_LOGIN_LOCKOUT_DURATION_SECONDS': 120,
        'AUTH_LOGIN_LOCKOUT_ESCALATION_ENABLED': False,
        'AUTH_SUSPICIOUS_ACTIVITY_REVOKE_SESSIONS': True,
        'AUTH_SUSPICIOUS_ACTIVITY_REVOKE_MIN_LOCKOUT_LEVEL': 1,
        'AUTH_REQUIRE_EMAIL_VERIFICATION': False,
    }
    original = {key: app_context.app.config.get(key) for key in overrides}
    app_context.app.config.update(overrides)
    _reset_auth_security_runtime_state(app_context)

    try:
        first = client.post(
            '/api/v1/auth/login',
            json={'email': 'suspicious@example.com', 'password': 'WrongPass123'},
        )
        lockout = client.post(
            '/api/v1/auth/login',
            json={'email': 'suspicious@example.com', 'password': 'WrongPass123'},
        )
        assert first.status_code == 401
        assert lockout.status_code == 429

        with app_context.app.app_context():
            user = app_context.User.query.filter_by(email='suspicious@example.com').first()
            assert user is not None
            assert user.access_token_revoked_at is not None

            active_refresh = (
                app_context.AuthLifecycleToken.query.filter_by(
                    user_id=user.id,
                    token_type='refresh',
                )
                .filter(app_context.AuthLifecycleToken.revoked_at.is_(None))
                .count()
            )
            assert active_refresh == 0

            latest = (
                app_context.AuthAuditEvent.query.filter_by(event='login', email='suspicious@example.com')
                .order_by(app_context.AuthAuditEvent.id.desc())
                .first()
            )
            details = latest.details_json or {}

        assert details.get('reason') == 'lockout_triggered'
        assert details.get('sessions_revoked') is True
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


def test_admin_ops_health_endpoint_returns_summary(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())
    monkeypatch.setattr(
        app_context.geo,
        '_drive_time_between_points',
        lambda *args, **kwargs: {'minutes': 10.0, 'text': '10 mins'},
    )
    _create_user(app_context, 'opshealthadmin@example.com', 'Password123!', role='admin', name='Ops Health Admin')
    _create_user(app_context, 'opshealthcustomer@example.com', 'Password123!', role='customer', name='Ops Customer')
    admin_headers = _auth_header(client, 'opshealthadmin@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'opshealthcustomer@example.com', 'Password123!')

    original_pending = app_context.app.config.get('DISPATCH_PENDING_MATCH_SLA_MINUTES')
    app_context.app.config['DISPATCH_PENDING_MATCH_SLA_MINUTES'] = 0

    try:
        client.post(
            '/api/v1/auth/login',
            json={'email': 'opshealthcustomer@example.com', 'password': 'WrongPass123'},
        )

        scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
        create_response = client.post(
            '/api/v1/waste-requests',
            json={
                'requester_name': 'Ops Customer',
                'requester_email': 'opshealthcustomer@example.com',
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
            booking.created_at = datetime.utcnow() - timedelta(minutes=4)
            app_context.db.session.commit()

        response = client.get(
            '/api/v1/admin/ops/health?auth_window_minutes=120&dispatch_limit=200',
            headers=admin_headers,
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload['status'] in {'ok', 'warning', 'critical'}
        assert 'metrics' in payload
        assert 'auth' in payload['metrics']
        assert 'dispatch' in payload['metrics']
        assert isinstance(payload.get('alerts'), list)
        assert payload['metrics']['auth']['failed_login_events'] >= 1
    finally:
        app_context.app.config['DISPATCH_PENDING_MATCH_SLA_MINUTES'] = original_pending
