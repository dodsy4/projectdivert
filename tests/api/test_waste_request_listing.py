"""Tests for GET /api/v1/auth/me and GET /api/v1/waste-requests.

Both were added for the React dashboard, which needs to re-hydrate a session
after a page reload and to list requests without knowing their ids.

The listing endpoint is scoped by role on the server. The point of these tests
is that a caller cannot widen its own view: a customer asking for
``scope=all`` must still see only their own rows.
"""

from datetime import datetime, timedelta

from tests.helpers import _auth_header, _create_user

LIST = '/api/v1/waste-requests'
ME = '/api/v1/auth/me'
PASSWORD = 'Sup3rSecret!pass'


def _make_request(app_context, email, status='pending', driver_id=None, material='Timber'):
    with app_context.app.app_context():
        booking = app_context.WasteRemovalRequest(
            requester_name='Requester', requester_email=email,
            material_type=material, waste_amount=1.5, waste_unit='tonnes',
            pickup_address='1 Site Road', pickup_postcode='SW1A1AA',
            scheduled_pickup_at=datetime.utcnow() + timedelta(days=1),
            status=status, assigned_driver_user_id=driver_id,
        )
        app_context.db.session.add(booking)
        app_context.db.session.commit()
        return booking.id


# ---------------------------------------------------------------------------
# /auth/me
# ---------------------------------------------------------------------------

def test_me_requires_a_token(client):
    assert client.get(ME).status_code == 401


def test_me_returns_the_token_holder(client, app_context):
    _create_user(app_context, 'me@example.com', PASSWORD, name='Ada')
    headers = _auth_header(client, 'me@example.com', PASSWORD)
    response = client.get(ME, headers=headers)
    assert response.status_code == 200
    user = response.get_json()['user']
    assert user['email'] == 'me@example.com'
    assert user['name'] == 'Ada'
    assert user['role'] == 'customer'
    assert 'password_hash' not in user


# ---------------------------------------------------------------------------
# Listing: scoping
# ---------------------------------------------------------------------------

def test_listing_requires_a_token(client):
    assert client.get(LIST).status_code == 401


def test_a_customer_sees_only_their_own_requests(client, app_context):
    _create_user(app_context, 'a@example.com', PASSWORD)
    _create_user(app_context, 'b@example.com', PASSWORD)
    mine = _make_request(app_context, 'a@example.com')
    _make_request(app_context, 'b@example.com')

    headers = _auth_header(client, 'a@example.com', PASSWORD)
    body = client.get(LIST, headers=headers).get_json()
    assert [r['id'] for r in body['requests']] == [mine]
    assert body['scope'] == 'mine'


def test_a_customer_cannot_widen_its_own_scope(client, app_context):
    """Asking for every request must not return anyone else's."""
    _create_user(app_context, 'a@example.com', PASSWORD)
    _create_user(app_context, 'b@example.com', PASSWORD)
    mine = _make_request(app_context, 'a@example.com')
    theirs = _make_request(app_context, 'b@example.com')

    headers = _auth_header(client, 'a@example.com', PASSWORD)
    body = client.get(LIST + '?scope=all', headers=headers).get_json()
    ids = [r['id'] for r in body['requests']]
    assert ids == [mine]
    assert theirs not in ids
    assert body['scope'] == 'mine'


def test_a_driver_sees_assigned_jobs_by_default(client, app_context):
    driver = _create_user(app_context, 'driver@example.com', PASSWORD, role='driver')
    _create_user(app_context, 'cust@example.com', PASSWORD)
    with app_context.app.app_context():
        driver_id = app_context.User.query.filter_by(email='driver@example.com').first().id
    assigned = _make_request(app_context, 'cust@example.com', status='accepted', driver_id=driver_id)
    _make_request(app_context, 'cust@example.com')  # unassigned

    headers = _auth_header(client, 'driver@example.com', PASSWORD)
    body = client.get(LIST, headers=headers).get_json()
    assert [r['id'] for r in body['requests']] == [assigned]
    assert body['scope'] == 'assigned'


def test_a_driver_can_ask_for_available_jobs(client, app_context):
    _create_user(app_context, 'driver@example.com', PASSWORD, role='driver')
    _create_user(app_context, 'cust@example.com', PASSWORD)
    with app_context.app.app_context():
        driver_id = app_context.User.query.filter_by(email='driver@example.com').first().id
    _make_request(app_context, 'cust@example.com', status='accepted', driver_id=driver_id)
    open_job = _make_request(app_context, 'cust@example.com')

    headers = _auth_header(client, 'driver@example.com', PASSWORD)
    body = client.get(LIST + '?scope=available', headers=headers).get_json()
    assert [r['id'] for r in body['requests']] == [open_job]


def test_an_admin_sees_everything(client, app_context):
    _create_user(app_context, 'admin@example.com', PASSWORD, role='admin')
    _create_user(app_context, 'a@example.com', PASSWORD)
    _create_user(app_context, 'b@example.com', PASSWORD)
    first = _make_request(app_context, 'a@example.com')
    second = _make_request(app_context, 'b@example.com')

    headers = _auth_header(client, 'admin@example.com', PASSWORD)
    body = client.get(LIST, headers=headers).get_json()
    assert {first, second} <= {r['id'] for r in body['requests']}
    assert body['scope'] == 'all'


# ---------------------------------------------------------------------------
# Listing: filtering and paging
# ---------------------------------------------------------------------------

def test_status_filter(client, app_context):
    _create_user(app_context, 'a@example.com', PASSWORD)
    _make_request(app_context, 'a@example.com', status='pending')
    done = _make_request(app_context, 'a@example.com', status='completed')

    headers = _auth_header(client, 'a@example.com', PASSWORD)
    body = client.get(LIST + '?status=completed', headers=headers).get_json()
    assert [r['id'] for r in body['requests']] == [done]


def test_paging_reports_the_total(client, app_context):
    _create_user(app_context, 'a@example.com', PASSWORD)
    for _ in range(3):
        _make_request(app_context, 'a@example.com')

    headers = _auth_header(client, 'a@example.com', PASSWORD)
    body = client.get(LIST + '?limit=2', headers=headers).get_json()
    assert body['count'] == 2
    assert body['total'] == 3
    assert body['limit'] == 2

    page_two = client.get(LIST + '?limit=2&offset=2', headers=headers).get_json()
    assert page_two['count'] == 1


def test_an_unknown_scope_is_rejected(client, app_context):
    _create_user(app_context, 'admin@example.com', PASSWORD, role='admin')
    headers = _auth_header(client, 'admin@example.com', PASSWORD)
    response = client.get(LIST + '?scope=everything', headers=headers)
    assert response.status_code == 400
    assert 'allowed_scopes' in response.get_json()


def test_non_integer_paging_is_rejected(client, app_context):
    _create_user(app_context, 'a@example.com', PASSWORD)
    headers = _auth_header(client, 'a@example.com', PASSWORD)
    assert client.get(LIST + '?limit=lots', headers=headers).status_code == 400
