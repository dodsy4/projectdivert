"""Totals across collections, and who is allowed to see which.

Every carbon figure comes from the same assessment the certificate uses, so a
total and the certificates behind it cannot disagree. Collections the model
cannot assess are reported rather than dropped -- a total that silently omits
them looks identical to one that includes them.
"""

from datetime import timedelta

from projectdivert.models.waste import WasteRemovalMatch, WasteRemovalRequest
from projectdivert.services.reports import collection_report
from projectdivert.services.utils import utcnow
from tests.helpers import _auth_header, _create_user


def _collection(app_context, email, status, material='Aggregate', amount=10.0):
    with app_context.app.app_context():
        booking = WasteRemovalRequest(
            requester_name='Requester', requester_email=email,
            material_type=material, waste_amount=amount, waste_unit='Tonnes',
            pickup_address='1 Site Road', pickup_postcode='BS1 4ST',
            pickup_latitude=51.4488, pickup_longitude=-2.5972,
            scheduled_pickup_at=utcnow() - timedelta(days=1), status=status,
        )
        app_context.db.session.add(booking)
        app_context.db.session.flush()
        app_context.db.session.add(WasteRemovalMatch(
            waste_removal_request_id=booking.id, provider_name='Provider',
            provider_latitude=51.45, provider_longitude=-2.58,
            distance_miles=4.0, match_radius_miles=25.0,
        ))
        app_context.db.session.commit()
        return booking.id


def test_only_completed_collections_count_towards_carbon(app_context):
    """A booked collection has avoided nothing yet."""
    _collection(app_context, 'a@example.com', 'completed')
    _collection(app_context, 'a@example.com', 'pending_match')
    _collection(app_context, 'a@example.com', 'en_route')

    with app_context.app.app_context():
        report = collection_report(WasteRemovalRequest.query)

    assert report['collections'] == 3
    assert report['diverted']['collections'] == 1
    assert report['diverted']['tonnes'] == 10.0
    assert report['diverted']['net_avoided_kg_co2e'] > 0


def test_the_total_matches_the_certificate_for_the_same_collection(app_context):
    """One assessment, so the report and the certificate cannot drift apart."""
    from projectdivert.services.carbon import assess_collection_carbon

    request_id = _collection(app_context, 'a@example.com', 'completed')

    with app_context.app.app_context():
        booking = app_context.db.session.get(WasteRemovalRequest, request_id)
        result, _context = assess_collection_carbon(booking)
        report = collection_report(WasteRemovalRequest.query)

    assert report['diverted']['net_avoided_kg_co2e'] == round(result.net_avoided_kg, 1)


def test_material_breakdown_totals_separately(app_context):
    _collection(app_context, 'a@example.com', 'completed', material='Aggregate', amount=10)
    _collection(app_context, 'a@example.com', 'completed', material='Timber', amount=2)

    with app_context.app.app_context():
        report = collection_report(WasteRemovalRequest.query)

    materials = {row['material']: row for row in report['by_material']}
    assert set(materials) == {'Aggregate', 'Timber'}
    assert materials['Aggregate']['tonnes'] == 10.0
    assert materials['Timber']['tonnes'] == 2.0
    total = sum(row['avoided_kg'] for row in report['by_material'])
    assert abs(total - report['diverted']['net_avoided_kg_co2e']) < 0.5


def test_a_collection_the_model_cannot_assess_is_named_not_dropped(app_context):
    """Excluding it silently would make the total look complete when it is not."""
    _collection(app_context, 'a@example.com', 'completed', material='Unobtainium')

    with app_context.app.app_context():
        report = collection_report(WasteRemovalRequest.query)

    unavailable = report['diverted']['carbon_unavailable']
    assert len(unavailable) == 1
    assert unavailable[0]['reason']
    assert report['diverted']['carbon_assessed_collections'] == 0


def test_truncation_is_reported(app_context):
    for _ in range(3):
        _collection(app_context, 'a@example.com', 'completed')

    with app_context.app.app_context():
        report = collection_report(WasteRemovalRequest.query, limit=2)

    assert report['collections'] == 2
    assert report['truncated'] is True


# --- The endpoint shows only what the caller may see ------------------------


def test_a_customer_only_totals_their_own_collections(client, app_context):
    _create_user(app_context, 'mine@example.com', 'Password123!', role='customer', name='C')
    _collection(app_context, 'mine@example.com', 'completed')
    _collection(app_context, 'someone.else@example.com', 'completed')

    headers = _auth_header(client, 'mine@example.com', 'Password123!')
    body = client.get('/api/v1/reports/collections', headers=headers).get_json()

    assert body['collections'] == 1
    assert body['diverted']['collections'] == 1


def test_an_admin_totals_everything(client, app_context):
    _create_user(app_context, 'boss@example.com', 'Password123!', role='admin', name='A')
    _collection(app_context, 'one@example.com', 'completed')
    _collection(app_context, 'two@example.com', 'completed')

    headers = _auth_header(client, 'boss@example.com', 'Password123!')
    body = client.get('/api/v1/reports/collections', headers=headers).get_json()

    assert body['collections'] == 2


def test_a_driver_totals_the_jobs_assigned_to_them(client, app_context):
    _create_user(app_context, 'rep-driver@example.com', 'Password123!', role='driver', name='D')
    with app_context.app.app_context():
        driver_id = app_context.User.query.filter_by(email='rep-driver@example.com').first().id

    mine = _collection(app_context, 'cust@example.com', 'completed')
    _collection(app_context, 'cust@example.com', 'completed')
    with app_context.app.app_context():
        booking = app_context.db.session.get(WasteRemovalRequest, mine)
        booking.assigned_driver_user_id = driver_id
        app_context.db.session.commit()

    headers = _auth_header(client, 'rep-driver@example.com', 'Password123!')
    body = client.get('/api/v1/reports/collections', headers=headers).get_json()

    assert body['collections'] == 1


def test_the_report_needs_a_token(client, app_context):
    assert client.get('/api/v1/reports/collections').status_code == 401
