"""Tests for the single clock, the postcode lookup, and the response headers.

Each of these pins behaviour that was wrong before: timestamps taken from two
different clocks, a postcode lookup that could not tell an outage from a typo,
and a complete absence of the headers a browser uses to constrain a page.
"""

from datetime import datetime, timedelta, timezone

import pytest
import requests

from projectdivert.hooks import DEFAULT_CONTENT_SECURITY_POLICY
from projectdivert.services import geo
from projectdivert.services.geo import PostcodeLookupUnavailable
from projectdivert.services.utils import _parse_datetime_or_error, to_utc_naive, utcnow


# --- One clock (#2) --------------------------------------------------------


def test_utcnow_is_naive_utc_and_agrees_with_the_aware_clock():
    now = utcnow()
    assert now.tzinfo is None, 'stored timestamps are naive, so the clock must be too'

    aware = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((aware - now).total_seconds()) < 5


def test_utcnow_does_not_follow_the_servers_local_zone():
    """The bug this replaces: datetime.now() drifts by the server's UTC offset."""
    local_offset = datetime.now().astimezone().utcoffset() or timedelta(0)
    drift = abs((datetime.now() - utcnow()).total_seconds())
    # Whatever the host's zone, utcnow() tracks UTC rather than local time.
    assert abs(drift - abs(local_offset.total_seconds())) < 5


@pytest.mark.parametrize(
    'raw, expected',
    [
        # An explicit offset is converted, not discarded: 14:00+01:00 is 13:00Z.
        ('2027-03-01T14:00:00+01:00', datetime(2027, 3, 1, 13, 0)),
        ('2027-03-01T14:00:00-05:00', datetime(2027, 3, 1, 19, 0)),
        ('2027-03-01T14:00:00Z', datetime(2027, 3, 1, 14, 0)),
        # A bare local-looking string is taken as UTC, matching storage.
        ('2027-03-01T14:00', datetime(2027, 3, 1, 14, 0)),
    ],
)
def test_parse_datetime_normalises_offsets_to_utc(raw, expected):
    assert _parse_datetime_or_error(raw, 'scheduled_pickup_at') == expected


def test_to_utc_naive_converts_rather_than_truncating():
    aware = datetime(2027, 3, 1, 14, 0, tzinfo=timezone(timedelta(hours=1)))
    assert to_utc_naive(aware) == datetime(2027, 3, 1, 13, 0)
    assert to_utc_naive(None) is None
    naive = datetime(2027, 3, 1, 14, 0)
    assert to_utc_naive(naive) == naive


def test_the_package_uses_no_other_clock():
    """A regression guard: one clock means one source of 'now'.

    Parsed rather than grepped, so prose in a docstring that names the
    discouraged call is not mistaken for a use of it.
    """
    import ast
    import pathlib

    offenders = []
    for path in sorted(pathlib.Path('projectdivert').rglob('*.py')):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == 'datetime'
                and node.attr == 'utcnow'
            ):
                offenders.append('{}:{} datetime.utcnow'.format(path, node.lineno))
            # datetime.now(timezone.utc) is fine; a bare datetime.now() is the
            # server's local clock and disagrees with everything stored.
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'now'
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == 'datetime'
                and not node.args
                and not node.keywords
            ):
                offenders.append('{}:{} bare datetime.now()'.format(path, node.lineno))

    assert offenders == [], 'these use a clock other than utcnow(): {}'.format(offenders)


def test_whatsapp_pickup_times_honour_an_offset(app_context, monkeypatch):
    """The chatbot used to drop the offset, booking an hour late."""
    from projectdivert.services import chatbot

    captured = {}

    def _capture(postcode):
        captured['postcode'] = postcode
        return 51.5072, -0.1276

    monkeypatch.setattr(chatbot, '_postcode_coordinates', _capture)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', None)

    user = app_context.User(email='wa@example.com', name='WA', role='customer',
                            password_hash='x')
    with app_context.app.app_context():
        app_context.db.session.add(user)
        app_context.db.session.commit()

        far_future = (utcnow() + timedelta(days=3)).replace(microsecond=0)
        # Expressed as 14:00+01:00 relative to that instant, so the stored
        # value must come back an hour earlier than the wall-clock reading.
        aware = far_future.replace(hour=14, minute=0, second=0)
        result = chatbot._tool_create_request(
            app_context.User.query.filter_by(email='wa@example.com').first(),
            waste_amount='2',
            waste_unit='tonnes',
            material_type='Glass',
            pickup_address='1 Example Road',
            pickup_postcode='SW1A1AA',
            scheduled_pickup_at=aware.strftime('%Y-%m-%dT%H:%M:%S') + '+01:00',
        )
        assert 'error' not in result, result

        booking = app_context.WasteRemovalRequest.query.filter_by(
            requester_email='wa@example.com',
        ).first()
        assert booking is not None
        assert booking.scheduled_pickup_at == aware.replace(hour=13)


# --- Postcode lookup (#3) --------------------------------------------------


class _RecordingGet:
    def __init__(self, payload=None, status_code=200, raises=None, body=None):
        self.calls = []
        self._payload = payload if payload is not None else {
            'result': {'latitude': 51.5072, 'longitude': -0.1276},
        }
        self._status_code = status_code
        self._raises = raises
        self._body = body

    def __call__(self, url, **kwargs):
        self.calls.append(url)
        if self._raises:
            raise self._raises
        payload, body = self._payload, self._body
        status_code = self._status_code

        class _Response:
            status_code = None

            def json(self):
                if body is not None:
                    raise ValueError('not json')
                return payload

        response = _Response()
        response.status_code = status_code
        return response


def test_postcode_lookup_uses_https(app_context, monkeypatch):
    getter = _RecordingGet()
    monkeypatch.setattr(requests, 'get', getter)
    geo.clear_postcode_cache()

    with app_context.app.app_context():
        geo._postcode_coordinates('SW1A 1AA')

    assert getter.calls[0].startswith('https://'), getter.calls[0]


def test_postcode_lookup_is_cached_and_normalised(app_context, monkeypatch):
    getter = _RecordingGet()
    monkeypatch.setattr(requests, 'get', getter)
    geo.clear_postcode_cache()

    with app_context.app.app_context():
        first = geo._postcode_coordinates('SW1A 1AA')
        second = geo._postcode_coordinates('sw1a1aa')
        third = geo._postcode_coordinates('  SW1A1AA  ')

    assert first == second == third == (51.5072, -0.1276)
    # Three spellings of one postcode, one upstream request.
    assert len(getter.calls) == 1


def test_clearing_the_cache_makes_the_lookup_happen_again(app_context, monkeypatch):
    getter = _RecordingGet()
    monkeypatch.setattr(requests, 'get', getter)
    geo.clear_postcode_cache()

    with app_context.app.app_context():
        geo._postcode_coordinates('SW1A1AA')
        geo.clear_postcode_cache()
        geo._postcode_coordinates('SW1A1AA')

    assert len(getter.calls) == 2


def test_a_network_failure_is_not_reported_as_a_bad_postcode(app_context, monkeypatch):
    monkeypatch.setattr(
        requests, 'get',
        _RecordingGet(raises=requests.ConnectionError('boom')),
    )
    geo.clear_postcode_cache()

    with app_context.app.app_context():
        with pytest.raises(PostcodeLookupUnavailable):
            geo._postcode_coordinates('SW1A1AA')


def test_a_server_error_upstream_is_not_reported_as_a_bad_postcode(app_context, monkeypatch):
    monkeypatch.setattr(requests, 'get', _RecordingGet(status_code=503))
    geo.clear_postcode_cache()

    with app_context.app.app_context():
        with pytest.raises(PostcodeLookupUnavailable):
            geo._postcode_coordinates('SW1A1AA')


def test_unparseable_json_is_not_reported_as_a_bad_postcode(app_context, monkeypatch):
    """json() raises a ValueError subclass, which used to look like a typo."""
    monkeypatch.setattr(requests, 'get', _RecordingGet(body='<html>502</html>'))
    geo.clear_postcode_cache()

    with app_context.app.app_context():
        with pytest.raises(PostcodeLookupUnavailable):
            geo._postcode_coordinates('SW1A1AA')


def test_an_unknown_postcode_is_still_the_callers_problem(app_context, monkeypatch):
    monkeypatch.setattr(requests, 'get', _RecordingGet(status_code=404))
    geo.clear_postcode_cache()

    with app_context.app.app_context():
        with pytest.raises(ValueError) as excinfo:
            geo._postcode_coordinates('ZZ1 1ZZ')
    assert not isinstance(excinfo.value, PostcodeLookupUnavailable)


def test_a_failed_lookup_is_not_cached(app_context, monkeypatch):
    getter = _RecordingGet(raises=requests.ConnectionError('boom'))
    monkeypatch.setattr(requests, 'get', getter)
    geo.clear_postcode_cache()

    with app_context.app.app_context():
        for _ in range(2):
            with pytest.raises(PostcodeLookupUnavailable):
                geo._postcode_coordinates('SW1A1AA')

    # A transient failure must not poison the cache for the next caller.
    assert len(getter.calls) == 2


def test_the_api_reports_a_lookup_outage_as_503(client, app_context, monkeypatch):
    from tests.helpers import _auth_header, _create_user

    monkeypatch.setattr(
        requests, 'get',
        _RecordingGet(raises=requests.ConnectionError('boom')),
    )
    geo.clear_postcode_cache()
    _create_user(app_context, 'c@example.com', 'Password123!', role='customer', name='C')
    headers = _auth_header(client, 'c@example.com', 'Password123!')

    response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'C',
            'requester_email': 'c@example.com',
            'material_type': 'Glass',
            'waste_amount': 1.0,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '1 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': (utcnow() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),
        },
        headers=headers,
    )
    # Not a 400: the customer's postcode was fine, the service was not.
    assert response.status_code == 503
    assert 'unavailable' in response.get_json()['error'].lower()


# --- Security headers (#4) -------------------------------------------------


def test_security_headers_are_present_on_a_page(client, app_context):
    response = client.get('/login')
    assert response.status_code == 200

    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['X-Frame-Options'] == 'DENY'
    # Not 'no-referrer': Flask-WTF's CSRF check needs the Referer over HTTPS.
    assert response.headers['Referrer-Policy'] == 'same-origin'
    assert 'Content-Security-Policy' in response.headers


def test_security_headers_are_present_on_an_api_response(client, app_context):
    response = client.post('/api/v1/auth/login', json={'email': 'x@y.z', 'password': 'n'})
    assert response.headers['X-Content-Type-Options'] == 'nosniff'


def test_the_csp_allows_what_the_templates_actually_load(client, app_context):
    policy = client.get('/login').headers['Content-Security-Policy']

    for directive in ("default-src 'self'", "frame-ancestors 'none'",
                      "form-action 'self'", "object-src 'none'",
                      "base-uri 'self'"):
        assert directive in policy, directive

    # The hosts the live templates still reference. jQuery is served from
    # /static, so no CDN needs to be allowed for it.
    for host in ('https://kit.fontawesome.com', 'https://maps.googleapis.com'):
        assert host in policy, host
    assert 'ajax.googleapis.com' not in policy


def test_templates_load_no_scripts_the_csp_would_block(client, app_context):
    """A protocol-relative //host src resolves to http: and is blocked.

    This is what the CSP work actually caught: every layout loaded jQuery from
    //ajax.googleapis.com, which became http:// on a plain-HTTP page.
    """
    import pathlib
    import re

    offenders = []
    for path in sorted(pathlib.Path('templates').rglob('*.html')):
        for match in re.finditer(r'src="(//[^"]+)"', path.read_text()):
            offenders.append('{}: {}'.format(path, match.group(1)))
    assert offenders == [], 'protocol-relative script sources: {}'.format(offenders)


def test_the_csp_can_be_overridden_or_switched_off(app_context, client):
    app = app_context.app
    app.config['CONTENT_SECURITY_POLICY'] = "default-src 'none'"
    try:
        assert client.get('/login').headers['Content-Security-Policy'] == "default-src 'none'"
    finally:
        app.config['CONTENT_SECURITY_POLICY'] = None

    app.config['CONTENT_SECURITY_POLICY'] = ''
    try:
        assert 'Content-Security-Policy' not in client.get('/login').headers
    finally:
        app.config['CONTENT_SECURITY_POLICY'] = None

    # Unset falls back to the default rather than sending nothing.
    assert client.get('/login').headers['Content-Security-Policy'] == DEFAULT_CONTENT_SECURITY_POLICY


def test_hsts_is_off_by_default_and_only_sent_over_https(app_context, client):
    app = app_context.app
    assert 'Strict-Transport-Security' not in client.get('/login').headers

    app.config['HSTS_MAX_AGE_SECONDS'] = 63072000
    try:
        # The test client speaks https because PREFERRED_URL_SCHEME says so.
        secure = client.get('/login')
        assert 'max-age=63072000' in secure.headers['Strict-Transport-Security']

        plain = client.get('http://localhost/login')
        assert 'Strict-Transport-Security' not in plain.headers
    finally:
        app.config['HSTS_MAX_AGE_SECONDS'] = 0
