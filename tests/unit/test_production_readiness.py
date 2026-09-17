"""Tests for the production-hardening fixes.

Each test here pins one behaviour that was wrong or absent before: the
double-booking race on dispatch acceptance, escalation webhooks firing from
read-only endpoints, cross-process event fan-out, CSRF enforcement on the
cookie-authenticated routes, and the boot guard on the placeholder secret key.
"""

from datetime import datetime, timedelta

import pytest
from fakeredis import FakeStrictRedis

import projectdivert
from projectdivert.services import dispatch, events


# --- Double-booking (#1) ---------------------------------------------------


def _seed_request_with_two_offers(app_context):
    """A waste request with two open offers, as fan-out would leave it."""
    with app_context.app.app_context():
        booking = app_context.WasteRemovalRequest(
            requester_name='Race Customer',
            requester_email='race@example.com',
            material_type='Glass',
            waste_amount=1.0,
            waste_unit='Tonnes',
            pickup_address='1 Example Road',
            pickup_postcode='SW1A1AA',
            scheduled_pickup_at=datetime.utcnow() + timedelta(days=1),
            status='pending_match',
        )
        app_context.db.session.add(booking)
        app_context.db.session.flush()

        offers = []
        for rank, name in enumerate(['Provider Alpha', 'Provider Beta'], start=1):
            offer = app_context.WasteRemovalDispatchOffer(
                waste_removal_request_id=booking.id,
                provider_name=name,
                provider_type='Waste Carrier',
                provider_city='London',
                provider_postcode='SW1A1AA',
                provider_latitude=51.5074,
                provider_longitude=-0.1278,
                distance_miles=1.0,
                match_radius_miles=25.0,
                offer_rank=rank,
                offer_token='token-{}'.format(rank),
                status='offered',
            )
            app_context.db.session.add(offer)
            offers.append(offer)
        app_context.db.session.commit()
        return booking.id, [offer.id for offer in offers]


def test_second_acceptance_of_the_same_request_is_rejected(app_context):
    request_id, offer_ids = _seed_request_with_two_offers(app_context)

    with app_context.app.app_context():
        booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
        first_offer = app_context.db.session.get(app_context.WasteRemovalDispatchOffer, offer_ids[0])
        match, outcome = dispatch._accept_dispatch_offer(booking, first_offer)
        assert outcome == 'accepted'
        assert match is not None

    with app_context.app.app_context():
        booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
        second_offer = app_context.db.session.get(app_context.WasteRemovalDispatchOffer, offer_ids[1])
        match, outcome = dispatch._accept_dispatch_offer(booking, second_offer)
        # The winning acceptance expires its siblings, so a sequential second
        # driver is turned away on the offer before the match check is reached.
        assert outcome == 'offer_unavailable'

    with app_context.app.app_context():
        matches = app_context.WasteRemovalMatch.query.filter_by(
            waste_removal_request_id=request_id,
        ).all()
        assert len(matches) == 1
        assert matches[0].provider_name == 'Provider Alpha'


def test_a_second_match_row_cannot_be_inserted_for_one_request(app_context):
    """The constraint holds even when the service checks are bypassed entirely."""
    from sqlalchemy.exc import IntegrityError

    request_id, _ = _seed_request_with_two_offers(app_context)

    with app_context.app.app_context():
        for provider_name in ('Provider Alpha', 'Provider Beta'):
            app_context.db.session.add(
                app_context.WasteRemovalMatch(
                    waste_removal_request_id=request_id,
                    provider_name=provider_name,
                    provider_latitude=51.5074,
                    provider_longitude=-0.1278,
                    distance_miles=1.0,
                    match_radius_miles=25.0,
                )
            )
        with pytest.raises(IntegrityError):
            app_context.db.session.commit()
        app_context.db.session.rollback()


def test_acceptance_survives_a_concurrent_insert_that_beat_the_lock(app_context):
    """A match inserted between the pre-flight check and the commit is caught."""
    request_id, offer_ids = _seed_request_with_two_offers(app_context)
    original_get_latest = dispatch._get_latest_match_for_request
    calls = {'count': 0}

    def _get_latest_pretending_none_first(rid):
        calls['count'] += 1
        if calls['count'] == 1:
            # Simulate the window the lock closes: another worker commits a
            # match while this one still believes there is none.
            app_context.db.session.add(
                app_context.WasteRemovalMatch(
                    waste_removal_request_id=rid,
                    provider_name='Provider Concurrent',
                    provider_latitude=51.5074,
                    provider_longitude=-0.1278,
                    distance_miles=1.0,
                    match_radius_miles=25.0,
                )
            )
            app_context.db.session.commit()
            return None
        return original_get_latest(rid)

    with app_context.app.app_context():
        booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
        offer = app_context.db.session.get(app_context.WasteRemovalDispatchOffer, offer_ids[0])
        dispatch._get_latest_match_for_request = _get_latest_pretending_none_first
        try:
            match, outcome = dispatch._accept_dispatch_offer(booking, offer)
        finally:
            dispatch._get_latest_match_for_request = original_get_latest

        assert outcome == 'already_matched'
        assert match is not None
        assert match.provider_name == 'Provider Concurrent'

    with app_context.app.app_context():
        assert app_context.WasteRemovalMatch.query.filter_by(
            waste_removal_request_id=request_id,
        ).count() == 1


# --- Escalation webhooks off the read paths (#2) ----------------------------


class _RecordingPost:
    """Stands in for requests.post so an escalation attempt is observable."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, json=None, timeout=None, **kwargs):
        self.calls.append({'url': url, 'payload': json})

        class _Response:
            status_code = 200

        return _Response()


def _seed_breaching_request(app_context, age_minutes=90):
    """A request old enough to breach the pending-match SLA."""
    request_id, offer_ids = _seed_request_with_two_offers(app_context)
    with app_context.app.app_context():
        booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
        booking.created_at = datetime.utcnow() - timedelta(minutes=age_minutes)
        app_context.db.session.commit()
    return request_id, offer_ids


def test_escalation_fires_from_the_maintenance_job_and_not_from_reads(
    client, app_context, monkeypatch,
):
    """The same breaching request: silent on GET, escalated by the job.

    Asserting on requests.post rather than on the service function matters,
    because the blueprints used to hold their own bound reference to it.
    """
    from tests.helpers import _auth_header, _create_user

    recorder = _RecordingPost()
    monkeypatch.setattr('requests.post', recorder)
    app_context.app.config.update(
        DISPATCH_ESCALATION_WEBHOOK_URL='https://hooks.example.com/dispatch',
    )

    _create_user(app_context, 'admin@example.com', 'Password123!', role='admin', name='Admin')
    headers = _auth_header(client, 'admin@example.com', 'Password123!')
    request_id, _ = _seed_breaching_request(app_context)

    try:
        for path in (
            '/api/v1/admin/dispatch/queue',
            '/api/v1/admin/dispatch/incidents',
            '/api/v1/admin/dispatch/telemetry',
        ):
            response = client.get(path, headers=headers)
            assert response.status_code == 200, path

        board = client.get('/admin/dispatch')
        assert board.status_code in {200, 302, 401, 403}

        assert recorder.calls == [], 'a read endpoint sent an escalation webhook'

        # The same request, through the job that owns escalation now.
        with app_context.app.app_context():
            result = dispatch._run_dispatch_incident_maintenance()

        assert len(recorder.calls) == 1, 'the maintenance job did not escalate'
        assert recorder.calls[0]['url'] == 'https://hooks.example.com/dispatch'
        assert recorder.calls[0]['payload']['request_id'] == request_id
        assert result['summary']['escalations_sent'] == 1
    finally:
        app_context.app.config.update(DISPATCH_ESCALATION_WEBHOOK_URL='')


def test_escalation_respects_the_cooldown_on_a_second_run(app_context, monkeypatch):
    recorder = _RecordingPost()
    monkeypatch.setattr('requests.post', recorder)
    app_context.app.config.update(
        DISPATCH_ESCALATION_WEBHOOK_URL='https://hooks.example.com/dispatch',
    )
    _seed_breaching_request(app_context)

    try:
        with app_context.app.app_context():
            first = dispatch._run_dispatch_incident_maintenance()
            second = dispatch._run_dispatch_incident_maintenance()

        assert first['summary']['escalations_sent'] == 1
        assert second['summary']['escalations_sent'] == 0
        assert len(recorder.calls) == 1
    finally:
        app_context.app.config.update(DISPATCH_ESCALATION_WEBHOOK_URL='')


def test_incident_maintenance_dry_run_sends_nothing(app_context, monkeypatch):
    recorder = _RecordingPost()
    monkeypatch.setattr('requests.post', recorder)
    app_context.app.config.update(
        DISPATCH_ESCALATION_WEBHOOK_URL='https://hooks.example.com/dispatch',
    )
    _seed_breaching_request(app_context)

    try:
        with app_context.app.app_context():
            result = dispatch._run_dispatch_incident_maintenance(dry_run=True)

        assert recorder.calls == []
        assert result['summary']['escalations_sent'] == 0
    finally:
        app_context.app.config.update(DISPATCH_ESCALATION_WEBHOOK_URL='')


# --- Cross-process event fan-out (#4) --------------------------------------


@pytest.fixture
def redis_events(app_context):
    """Point the event bus at a fake Redis, and reset it afterwards."""
    client = FakeStrictRedis(decode_responses=True)
    events._waste_request_event_redis_client = client
    events._waste_request_event_redis_disabled = False
    events._waste_request_event_relay_thread = None
    yield client
    events._waste_request_event_redis_client = None
    events._waste_request_event_redis_disabled = False
    events._waste_request_event_relay_thread = None
    events._waste_request_event_history.clear()


def test_publishing_with_redis_writes_history_and_publishes(app_context, redis_events):
    request_id = 992001

    with app_context.app.app_context():
        events._publish_waste_request_event(
            request_id,
            'status_updated',
            payload={'request': {'id': request_id}},
        )

        history_key = events._waste_request_event_history_key(request_id)
        assert redis_events.llen(history_key) == 1
        # Expiry is set so a finished job's history does not accumulate.
        assert redis_events.ttl(history_key) > 0

        # Nothing was written to the in-process history: the relay thread is
        # what feeds local subscribers when Redis is in use.
        assert request_id not in events._waste_request_event_history


def test_replay_after_a_reconnect_reads_redis_history(app_context, redis_events):
    request_id = 992002

    with app_context.app.app_context():
        events._publish_waste_request_event(request_id, 'first')
        events._publish_waste_request_event(request_id, 'second')

        replay_all = events._waste_request_replay_events_since(request_id, 0)
        assert [row['event'] for row in replay_all] == ['first', 'second']

        first_id = int(replay_all[0]['event_id'])
        replay_after_first = events._waste_request_replay_events_since(request_id, first_id)
        assert [row['event'] for row in replay_after_first] == ['second']


def test_event_ids_come_from_redis_so_they_are_shared_across_workers(
    app_context, redis_events,
):
    with app_context.app.app_context():
        events._publish_waste_request_event(992003, 'one')
        events._publish_waste_request_event(992004, 'two')

    # A single counter, not a per-process one, so ids never collide between
    # workers streaming the same request.
    assert int(redis_events.get(events._waste_request_event_sequence_key())) == 2


def test_a_relayed_event_reaches_a_local_subscriber(app_context, redis_events):
    request_id = 992005

    with app_context.app.app_context():
        channel = events._subscribe_waste_request_events(request_id)
        try:
            events._publish_waste_request_event(request_id, 'status_updated')
            # Stand in for the relay thread, which is what consumes the Redis
            # channel in a real process.
            raw = redis_events.lrange(events._waste_request_event_history_key(request_id), 0, -1)[0]
            import json
            events._deliver_to_local_subscribers(request_id, json.loads(raw))
            delivered = channel.get(timeout=2)
        finally:
            events._unsubscribe_waste_request_events(request_id, channel)

    assert delivered['event'] == 'status_updated'
    assert delivered['request_id'] == request_id


def test_in_memory_history_is_bounded_by_request_count(app_context):
    """Without Redis the history must not grow one entry per request forever."""
    events._waste_request_event_history.clear()
    cap = events._waste_request_event_history_request_cap

    with app_context.app.app_context():
        for request_id in range(cap + 25):
            events._publish_waste_request_event(request_id, 'status_updated')

    try:
        assert len(events._waste_request_event_history) == cap
        # The oldest ids were evicted, the newest retained.
        assert 0 not in events._waste_request_event_history
        assert (cap + 24) in events._waste_request_event_history
    finally:
        events._waste_request_event_history.clear()


# --- CSRF (#5) -------------------------------------------------------------


def test_csrf_is_registered_and_the_api_is_exempt(app_context):
    app = app_context.app
    assert 'csrf' in app.extensions

    exempt = {
        getattr(item, 'name', item)
        for item in app.extensions['csrf']._exempt_blueprints
    }
    assert 'api_waste_requests' in exempt
    assert 'api_payments' in exempt
    assert 'api_whatsapp' in exempt
    # The cookie-authenticated blueprints must stay protected.
    assert 'web' not in exempt
    assert 'admin' not in exempt


def test_admin_post_without_a_csrf_token_is_rejected(app_context):
    """The admin dispatch forms are session-authenticated, so they need a token."""
    from tests.helpers import _create_user

    app = app_context.app
    _create_user(app_context, 'csrfadmin@example.com', 'Password123!', role='admin', name='Admin')

    app.config.update(WTF_CSRF_ENABLED=True)
    try:
        client = app.test_client()
        login = client.post(
            '/login',
            data={'email': 'csrfadmin@example.com', 'password': 'Password123!'},
        )
        # The login form itself is protected, so even reaching the board
        # requires a token; what matters here is that the POST is refused.
        assert login.status_code == 400

        response = client.post('/admin/dispatch/override', data={'request_id': '1'})
        assert response.status_code == 400
    finally:
        app.config.update(WTF_CSRF_ENABLED=False)


def test_api_post_without_a_csrf_token_still_works(client, app_context):
    """Exempting the API is what keeps the mobile app and webhooks working."""
    app_context.app.config.update(WTF_CSRF_ENABLED=True)
    try:
        response = client.post('/api/v1/auth/login', json={'email': 'x@example.com', 'password': 'y'})
        # Rejected on credentials, not on a missing CSRF token.
        assert response.status_code == 401
    finally:
        app_context.app.config.update(WTF_CSRF_ENABLED=False)


# --- Secret key boot guard (#6) --------------------------------------------


@pytest.mark.parametrize('secret', [projectdivert.DEV_SECRET_KEY, '', '   '])
def test_verify_secrets_refuses_the_placeholder_secret(app_context, secret):
    app = app_context.app
    original = {
        'SECRET_KEY': app.config.get('SECRET_KEY'),
        'JWT_SECRET_KEY': app.config.get('JWT_SECRET_KEY'),
        'TESTING': app.config.get('TESTING'),
    }
    app.config.update(SECRET_KEY=secret, JWT_SECRET_KEY=secret, TESTING=False)
    try:
        with pytest.raises(RuntimeError, match='strong random value'):
            projectdivert._verify_secrets(app)
    finally:
        app.config.update(**original)


def test_verify_secrets_allows_the_placeholder_while_testing(app_context):
    app = app_context.app
    original = app.config.get('SECRET_KEY')
    app.config.update(SECRET_KEY=projectdivert.DEV_SECRET_KEY, TESTING=True)
    try:
        projectdivert._verify_secrets(app)  # must not raise
    finally:
        app.config.update(SECRET_KEY=original)


def test_verify_secrets_accepts_a_real_secret(app_context):
    app = app_context.app
    original = {
        'SECRET_KEY': app.config.get('SECRET_KEY'),
        'JWT_SECRET_KEY': app.config.get('JWT_SECRET_KEY'),
        'TESTING': app.config.get('TESTING'),
    }
    app.config.update(
        SECRET_KEY='a-real-and-sufficiently-random-secret',
        JWT_SECRET_KEY='a-different-real-secret',
        TESTING=False,
    )
    try:
        projectdivert._verify_secrets(app)  # must not raise
    finally:
        app.config.update(**original)


def test_a_real_login_still_works_with_its_csrf_token(app_context):
    """The protection must not break the flow it protects.

    Flask-WTF also requires a same-origin Referer on secure requests, and the
    test client speaks https because PREFERRED_URL_SCHEME says so, so the
    request has to carry the header a browser would send.
    """
    import re

    from tests.helpers import _create_user

    app = app_context.app
    _create_user(app_context, 'csrfuser@example.com', 'Password123!', role='customer', name='User')

    app.config.update(WTF_CSRF_ENABLED=True)
    try:
        client = app.test_client()
        page = client.get('/login')
        assert page.status_code == 200

        match = re.search(r'name="csrf_token" value="([^"]+)"', page.get_data(as_text=True))
        assert match, 'the login form did not render a CSRF token'

        response = client.post(
            '/login',
            data={
                'email': 'csrfuser@example.com',
                'password': 'Password123!',
                'csrf_token': match.group(1),
            },
            headers={'Referer': 'https://localhost/login'},
        )
        assert response.status_code != 400, 'a tokened login was rejected as a CSRF failure'
        assert response.status_code in {200, 302}
    finally:
        app.config.update(WTF_CSRF_ENABLED=False)


def test_a_token_from_another_origin_is_rejected(app_context):
    """A valid token replayed from an attacker's page still fails the origin check."""
    import re

    from tests.helpers import _create_user

    app = app_context.app
    _create_user(app_context, 'csrforigin@example.com', 'Password123!', role='customer', name='User')

    app.config.update(WTF_CSRF_ENABLED=True)
    try:
        client = app.test_client()
        match = re.search(
            r'name="csrf_token" value="([^"]+)"',
            client.get('/login').get_data(as_text=True),
        )
        assert match

        response = client.post(
            '/login',
            data={
                'email': 'csrforigin@example.com',
                'password': 'Password123!',
                'csrf_token': match.group(1),
            },
            headers={'Referer': 'https://attacker.example.com/pay'},
        )
        assert response.status_code == 400
    finally:
        app.config.update(WTF_CSRF_ENABLED=False)
