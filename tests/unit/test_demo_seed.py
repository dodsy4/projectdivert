"""The demo seeder builds a scenario that is already part-way through.

Demonstrating from an empty database means clicking through every stage before
anything is worth showing, and a carbon certificate cannot be shown at all
without a collection that has already completed.
"""

import pytest

from projectdivert.models.auth import AuthLifecycleToken
from projectdivert.services import demo_seed
from projectdivert.services.demo_seed import (
    DEMO_CUSTOMER_EMAIL,
    DEMO_DRIVER_EMAIL,
    clear_demo_data,
    seed_demo,
)


def test_it_seeds_accounts_and_a_scenario(app_context):
    with app_context.app.app_context():
        summary = seed_demo(password='DemoPassword123!')

        assert {a['role'] for a in summary['accounts']} == {'customer', 'driver', 'admin'}
        statuses = {c['status'] for c in summary['collections']}
        # A demo needs something to claim, something in flight, and something
        # finished enough to have a certificate.
        assert 'pending_match' in statuses
        assert 'completed' in statuses


def test_the_completed_collection_can_produce_a_certificate(client, app_context):
    """Its material must be one the carbon engine has factors for."""
    with app_context.app.app_context():
        seed_demo(password='DemoPassword123!')
        completed = app_context.WasteRemovalRequest.query.filter_by(
            requester_email=DEMO_CUSTOMER_EMAIL, status='completed',
        ).first()
        assert completed is not None
        request_id = completed.id

    page = client.get(f'/certificate/{request_id}')
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert 'CO' in body and 'avoided' in body.lower()


def test_the_demo_driver_is_dispatch_eligible(app_context):
    """Otherwise the demo stops at the first claim."""
    from projectdivert.services.compliance import _driver_dispatch_compliance_status

    with app_context.app.app_context():
        seed_demo(password='DemoPassword123!')
        driver = app_context.User.query.filter_by(email=DEMO_DRIVER_EMAIL).first()
        status = _driver_dispatch_compliance_status(driver.id)

    assert status['eligible'] is True, status['missing_document_types']


def test_the_seeded_carrier_licence_is_a_real_shaped_number(app_context):
    """Seeded data should model valid data, not placeholder junk.

    Asserted against the Environment Agency shape directly rather than through
    the validator, so this does not depend on that landing first.
    """
    import re

    with app_context.app.app_context():
        seed_demo(password='DemoPassword123!')
        driver = app_context.User.query.filter_by(email=DEMO_DRIVER_EMAIL).first()
        licence = app_context.DriverComplianceDocument.query.filter_by(
            driver_user_id=driver.id, document_type='carrier_license',
        ).first()

    assert re.match(r'^(CBD|CBT|ABW|ABT)[UL]?\d{4,10}$', licence.document_reference), (
        'seeded licence {!r} is not a plausible registration number'.format(
            licence.document_reference)
    )


def test_the_accounts_can_actually_sign_in(client, app_context):
    with app_context.app.app_context():
        seed_demo(password='DemoPassword123!')

    for email in (DEMO_CUSTOMER_EMAIL, DEMO_DRIVER_EMAIL):
        response = client.post(
            '/api/v1/auth/login',
            json={'email': email, 'password': 'DemoPassword123!'},
        )
        assert response.status_code == 200, (email, response.get_json())


def test_running_it_twice_does_not_duplicate_the_scenario(app_context):
    with app_context.app.app_context():
        seed_demo(password='DemoPassword123!')
        first = app_context.WasteRemovalRequest.query.filter_by(
            requester_email=DEMO_CUSTOMER_EMAIL).count()

        second_summary = seed_demo(password='DemoPassword123!')
        second = app_context.WasteRemovalRequest.query.filter_by(
            requester_email=DEMO_CUSTOMER_EMAIL).count()

    assert first == second
    assert second_summary['collections'] == []
    assert second_summary['existing_collections'] == first


def test_reset_rebuilds_the_scenario(app_context):
    with app_context.app.app_context():
        seed_demo(password='DemoPassword123!')
        before = app_context.WasteRemovalRequest.query.filter_by(
            requester_email=DEMO_CUSTOMER_EMAIL).count()

        summary = seed_demo(password='DemoPassword123!', reset=True)
        after = app_context.WasteRemovalRequest.query.filter_by(
            requester_email=DEMO_CUSTOMER_EMAIL).count()

    assert before == after
    assert len(summary['collections']) == after


def test_clearing_leaves_other_data_alone(app_context):
    """It must not be able to reach a real customer's collections."""
    from datetime import timedelta

    from projectdivert.services.utils import utcnow

    with app_context.app.app_context():
        seed_demo(password='DemoPassword123!')
        real = app_context.WasteRemovalRequest(
            requester_name='A Real Customer', requester_email='real@example.com',
            material_type='Glass', waste_amount=1.0, waste_unit='Tonnes',
            pickup_address='1 Real Road', pickup_postcode='SW1A1AA',
            scheduled_pickup_at=utcnow() + timedelta(days=1), status='pending_match',
        )
        app_context.db.session.add(real)
        app_context.db.session.commit()

        clear_demo_data()

        assert app_context.WasteRemovalRequest.query.filter_by(
            requester_email=DEMO_CUSTOMER_EMAIL).count() == 0
        assert app_context.WasteRemovalRequest.query.filter_by(
            requester_email='real@example.com').count() == 1


def test_it_refuses_to_create_known_passwords_where_that_is_not_wanted(app_context, monkeypatch):
    """A demo account on a real deployment is a published username and password."""
    app = app_context.app
    original = {'TESTING': app.config.get('TESTING'),
                'ALLOW_DEMO_SEED': app.config.get('ALLOW_DEMO_SEED')}
    app.config.update(TESTING=False, ALLOW_DEMO_SEED=False)
    monkeypatch.setattr(app, 'debug', False, raising=False)
    try:
        with app.app_context():
            with pytest.raises(PermissionError, match='ALLOW_DEMO_SEED'):
                seed_demo(password='DemoPassword123!')
    finally:
        app.config.update(**original)


def test_the_cli_reports_what_it_made(app_context):
    runner = app_context.app.test_cli_runner()
    result = runner.invoke(args=['seed-demo'])

    assert result.exit_code == 0, result.output
    assert DEMO_DRIVER_EMAIL in result.output
    assert 'completed' in result.output


def test_reset_works_after_the_accounts_have_been_used(client, app_context):
    """The reason to reset is that a demo has been run, so that must work.

    Signing in writes session and audit rows that carry a foreign key to the
    account. Clearing the accounts without clearing those first fails on the
    constraint -- so this reset is only ever exercised in the state the earlier
    version of it could not handle.
    """
    with app_context.app.app_context():
        seed_demo(password='DemoPassword123!')

    for email in (DEMO_CUSTOMER_EMAIL, DEMO_DRIVER_EMAIL):
        assert client.post(
            '/api/v1/auth/login',
            json={'email': email, 'password': 'DemoPassword123!'},
        ).status_code == 200

    with app_context.app.app_context():
        summary = seed_demo(password='DemoPassword123!', reset=True)

        assert len(summary['collections']) > 0
        assert app_context.User.query.filter_by(
            email=DEMO_DRIVER_EMAIL).count() == 1
        # Nothing may be left pointing at an account that no longer exists.
        assert AuthLifecycleToken.query.count() == 0


def test_clearing_keeps_real_rows_that_merely_name_a_demo_user(app_context):
    """A real collection the demo driver touched is data, not demo data.

    Those columns only record who acted. Deleting the row would destroy real
    work, so the reference is cleared and the row kept.
    """
    from datetime import timedelta

    from projectdivert.services.utils import utcnow

    with app_context.app.app_context():
        seed_demo(password='DemoPassword123!')
        driver = app_context.User.query.filter_by(email=DEMO_DRIVER_EMAIL).first()

        real = app_context.WasteRemovalRequest(
            requester_name='A Real Customer', requester_email='real@example.com',
            material_type='Glass', waste_amount=1.0, waste_unit='Tonnes',
            pickup_address='1 Real Road', pickup_postcode='SW1A1AA',
            scheduled_pickup_at=utcnow() + timedelta(days=1), status='matched',
            assigned_driver_user_id=driver.id,
        )
        app_context.db.session.add(real)
        app_context.db.session.commit()
        real_id = real.id

        clear_demo_data()

        kept = app_context.db.session.get(
            app_context.WasteRemovalRequest, real_id)
        assert kept is not None
        assert kept.assigned_driver_user_id is None
