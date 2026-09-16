"""Tests for the admin auth-audit, token and blocklist endpoints."""


from tests.helpers import _auth_header, _create_user, _reset_auth_security_runtime_state


def test_admin_api_rate_limit_applies_per_ip_and_user(client, app_context):
    _create_user(app_context, 'adminratelimit@example.com', 'Password123!', role='admin', name='Admin Limit')
    admin_headers = _auth_header(client, 'adminratelimit@example.com', 'Password123!')

    overrides = {
        'AUTH_RATE_LIMIT_ENABLED': True,
        'AUTH_RATE_LIMIT_ADMIN_ENABLED': True,
        'AUTH_RATE_LIMIT_WINDOW_SECONDS': 120,
        'AUTH_RATE_LIMIT_ADMIN_MAX_ATTEMPTS': 2,
        'AUTH_REQUIRE_EMAIL_VERIFICATION': False,
    }
    original = {key: app_context.app.config.get(key) for key in overrides}
    app_context.app.config.update(overrides)
    _reset_auth_security_runtime_state(app_context)

    try:
        first = client.get('/api/v1/admin/auth-audit?limit=1', headers=admin_headers)
        second = client.get('/api/v1/admin/auth-audit?limit=1', headers=admin_headers)
        third = client.get('/api/v1/admin/auth-audit?limit=1', headers=admin_headers)

        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 429
        assert third.get_json()['error'] == 'Too many admin API requests. Please try again later.'
        assert 'Retry-After' in third.headers
    finally:
        app_context.app.config.update(original)
        _reset_auth_security_runtime_state(app_context)
