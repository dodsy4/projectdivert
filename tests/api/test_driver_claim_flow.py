"""The driver job board: seeing open work, and claiming it.

Both halves of this journey were broken, independently, and neither had a test.
The available list filtered on a status no request is ever created with, and
claiming required an offer token that the board has no way to know.
"""

from datetime import timedelta

import pytest

from projectdivert.models.waste import WasteRemovalDispatchOffer
from projectdivert.services.utils import utcnow
from projectdivert.services.waste_requests import INITIAL_STATUS
from tests.helpers import _auth_header, _create_user, _seed_driver_dispatch_compliance


def _booking(app_context, status=INITIAL_STATUS, assigned_to=None, offers=('offered',)):
    """A request, optionally assigned, with dispatch offers in given states."""
    with app_context.app.app_context():
        booking = app_context.WasteRemovalRequest(
            requester_name='Site', requester_email='site@example.com',
            material_type='Timber', waste_amount=2.0, waste_unit='Tonnes',
            pickup_address='1 Example Road', pickup_postcode='SW1A1AA',
            scheduled_pickup_at=utcnow() + timedelta(days=1),
            status=status, assigned_driver_user_id=assigned_to,
        )
        app_context.db.session.add(booking)
        app_context.db.session.flush()
        for rank, offer_status in enumerate(offers, start=1):
            app_context.db.session.add(WasteRemovalDispatchOffer(
                waste_removal_request_id=booking.id,
                provider_name='Provider {}'.format(rank),
                provider_latitude=51.5, provider_longitude=-0.1,
                distance_miles=3.0, match_radius_miles=25.0,
                offer_rank=rank,
                offer_token='token-{}-{}'.format(booking.id, rank),
                status=offer_status,
            ))
        app_context.db.session.commit()
        return booking.id


@pytest.fixture
def driver_headers(client, app_context):
    _create_user(app_context, 'claimdriver@example.com', 'Password123!', role='driver', name='D')
    _create_user(app_context, 'claimadmin@example.com', 'Password123!', role='admin', name='A')
    _seed_driver_dispatch_compliance(app_context, 'claimdriver@example.com', 'claimadmin@example.com')
    return _auth_header(client, 'claimdriver@example.com', 'Password123!')


def _available(client, headers):
    response = client.get('/api/v1/waste-requests?scope=available&limit=100', headers=headers)
    assert response.status_code == 200
    body = response.get_json()
    return body.get('requests', body.get('items', []))


# --- The job board actually lists jobs --------------------------------------


def test_an_open_job_appears_on_the_board(client, app_context, driver_headers):
    """The bug: this filtered on status 'pending', which nothing is created with."""
    request_id = _booking(app_context)
    listed = _available(client, driver_headers)

    assert [r['id'] for r in listed] == [request_id]
    assert listed[0]['status'] == INITIAL_STATUS


def test_a_job_already_taken_does_not_appear(client, app_context, driver_headers):
    with app_context.app.app_context():
        other = app_context.User.query.filter_by(email='claimadmin@example.com').first().id
    _booking(app_context, assigned_to=other)

    assert _available(client, driver_headers) == []


def test_a_job_with_no_open_offer_does_not_appear(client, app_context, driver_headers):
    """Listing one would only produce a claim button that fails."""
    _booking(app_context, offers=('expired', 'accepted'))

    assert _available(client, driver_headers) == []


@pytest.mark.parametrize('status', ['matched', 'en_route', 'completed', 'cancelled'])
def test_jobs_past_the_open_stage_do_not_appear(client, app_context, driver_headers, status):
    _booking(app_context, status=status)

    assert _available(client, driver_headers) == []


# --- Claiming works the way the board calls it ------------------------------


def test_a_driver_can_claim_without_quoting_an_offer_token(client, app_context, driver_headers):
    """The board lists the request, not the offer, so it has no token to send."""
    request_id = _booking(app_context)

    response = client.post(
        f'/api/v1/waste-requests/{request_id}/dispatch/accept',
        json={}, headers=driver_headers,
    )
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body['request']['status'] == 'matched'
    assert body['request']['assigned_driver_user_id'] is not None
    assert body['match'] is not None


def test_claiming_takes_the_best_ranked_open_offer(client, app_context, driver_headers):
    request_id = _booking(app_context, offers=('expired', 'offered', 'offered'))

    response = client.post(
        f'/api/v1/waste-requests/{request_id}/dispatch/accept',
        json={}, headers=driver_headers,
    )
    assert response.status_code == 200
    # Rank 1 was expired, so rank 2 is the best one still open.
    assert response.get_json()['accepted_offer']['offer_rank'] == 2


def test_the_emailed_token_route_still_works(client, app_context, driver_headers):
    """A provider following a link from their notification quotes the offer."""
    request_id = _booking(app_context, offers=('offered', 'offered'))

    response = client.post(
        f'/api/v1/waste-requests/{request_id}/dispatch/accept',
        json={'offer_token': f'token-{request_id}-2'}, headers=driver_headers,
    )
    assert response.status_code == 200
    assert response.get_json()['accepted_offer']['offer_rank'] == 2


def test_an_unknown_token_is_still_rejected(client, app_context, driver_headers):
    request_id = _booking(app_context)

    response = client.post(
        f'/api/v1/waste-requests/{request_id}/dispatch/accept',
        json={'offer_token': 'not-a-real-token'}, headers=driver_headers,
    )
    assert response.status_code == 404


def test_claiming_a_request_with_nothing_open_is_refused(client, app_context, driver_headers):
    request_id = _booking(app_context, offers=('expired',))

    response = client.post(
        f'/api/v1/waste-requests/{request_id}/dispatch/accept',
        json={}, headers=driver_headers,
    )
    assert response.status_code == 409
    assert 'no open dispatch offer' in response.get_json()['error'].lower()


def test_an_ineligible_driver_still_cannot_claim(client, app_context):
    """Dropping the token requirement must not drop the compliance gate."""
    _create_user(app_context, 'nocompliance@example.com', 'Password123!', role='driver', name='D')
    headers = _auth_header(client, 'nocompliance@example.com', 'Password123!')
    request_id = _booking(app_context)

    response = client.post(
        f'/api/v1/waste-requests/{request_id}/dispatch/accept',
        json={}, headers=headers,
    )
    assert response.status_code == 409
    assert response.get_json()['missing_document_types']


def test_a_customer_cannot_reach_the_job_board(client, app_context):
    """Scope is decided by role, not by what the caller asks for."""
    _create_user(app_context, 'nosy@example.com', 'Password123!', role='customer', name='C')
    headers = _auth_header(client, 'nosy@example.com', 'Password123!')
    _booking(app_context)

    response = client.get('/api/v1/waste-requests?scope=available', headers=headers)
    assert response.status_code == 200
    # Scoped to their own requests regardless of the scope they asked for.
    assert response.get_json().get('requests', []) == []
