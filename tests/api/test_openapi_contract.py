"""The OpenAPI document must describe the API that actually exists.

These tests fail if a route is added, removed or renamed without regenerating
``docs/openapi.json`` (``python scripts/generate_openapi.py``), so the published
spec cannot quietly drift away from the code.
"""

import importlib.util
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC_PATH = ROOT / 'docs' / 'openapi.json'


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        'generate_openapi', ROOT / 'scripts' / 'generate_openapi.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _committed_spec():
    if not SPEC_PATH.exists():
        pytest.fail('docs/openapi.json is missing; run scripts/generate_openapi.py')
    return json.loads(SPEC_PATH.read_text())


def _live_operations(app):
    """(path template, method) for every /api/v1 route on the application."""
    out = set()
    for rule in app.url_map.iter_rules():
        path = str(rule.rule)
        if not path.startswith('/api/v1'):
            continue
        template = re.sub(r'<(?:[^:<>]+:)?([^<>]+)>', r'{\1}', path)
        for method in rule.methods:
            if method not in ('HEAD', 'OPTIONS'):
                out.add((template, method.lower()))
    return out


def _spec_operations(spec):
    return {(path, method)
            for path, item in spec['paths'].items()
            for method in item
            if method in ('get', 'post', 'put', 'patch', 'delete')}


def test_spec_covers_every_api_route(app_context):
    spec = _committed_spec()
    missing = _live_operations(app_context.app) - _spec_operations(spec)
    assert not missing, (
        'these API routes are not in docs/openapi.json; '
        'run scripts/generate_openapi.py: %s' % sorted(missing))


def test_spec_documents_no_phantom_routes(app_context):
    spec = _committed_spec()
    extra = _spec_operations(spec) - _live_operations(app_context.app)
    assert not extra, (
        'docs/openapi.json documents routes that no longer exist: %s' % sorted(extra))


def test_committed_spec_is_not_stale():
    generator = _load_generator()
    regenerated = json.dumps(generator.build_spec(), indent=2, sort_keys=True) + '\n'
    assert regenerated == SPEC_PATH.read_text(), (
        'docs/openapi.json is out of date; run: python scripts/generate_openapi.py')


def test_protected_endpoints_declare_bearer_auth():
    spec = _committed_spec()
    public = {
        ('/api/v1/auth/login', 'post'),
        ('/api/v1/auth/signup', 'post'),
        ('/api/v1/auth/refresh', 'post'),
        # Logout takes a refresh token in the body and revokes it; it is
        # rate limited rather than bearer-protected, which is deliberate.
        ('/api/v1/auth/logout', 'post'),
        ('/api/v1/auth/verify/request', 'post'),
        ('/api/v1/auth/verify/confirm', 'post'),
        ('/api/v1/auth/password-reset/request', 'post'),
        ('/api/v1/auth/password-reset/confirm', 'post'),
        ('/api/v1/payments/stripe/webhook', 'post'),
        ('/api/v1/openapi.json', 'get'),
    }
    undeclared = [
        (path, method)
        for path, item in spec['paths'].items()
        for method, op in item.items()
        if (path, method) not in public and not op.get('security')
    ]
    assert not undeclared, (
        'these endpoints claim to need no bearer token: %s' % sorted(undeclared))


def test_spec_is_served_by_the_app(client):
    response = client.get('/api/v1/openapi.json')
    assert response.status_code == 200
    assert response.get_json()['info']['title'] == 'Project Divert API'


def test_reference_page_renders(client):
    response = client.get('/api/docs')
    assert response.status_code == 200
    assert '/api/v1/openapi.json' in response.get_data(as_text=True)
