"""Tests for the dispatch queue's query count and for schema ownership.

The queue used to issue three queries per row plus a driver-compliance lookup,
against a page of up to 500 requests. And the schema had two owners: Alembic,
and a before_request hook calling db.create_all().
"""

from datetime import timedelta

import sqlalchemy as sa

from projectdivert.models.waste import WasteRemovalVehicleLocation
from projectdivert.services.dispatch import (
    DispatchQueueContext,
    _latest_vehicle_locations_for_requests,
)
from projectdivert.services.utils import utcnow
from tests.helpers import _auth_header, _create_user


def _seed_requests(app_context, count, driver_user_id=None, locations_each=2):
    """A page of active requests, each with a few vehicle locations."""
    ids = []
    with app_context.app.app_context():
        for _ in range(count):
            booking = app_context.WasteRemovalRequest(
                requester_name='R', requester_email='r@example.com',
                material_type='Glass', waste_amount=1.0, waste_unit='Tonnes',
                pickup_address='1 Example Road', pickup_postcode='SW1A1AA',
                scheduled_pickup_at=utcnow() + timedelta(days=1),
                status='pending_match', assigned_driver_user_id=driver_user_id,
            )
            app_context.db.session.add(booking)
            app_context.db.session.flush()
            ids.append(booking.id)
            for minute in range(locations_each):
                app_context.db.session.add(
                    WasteRemovalVehicleLocation(
                        waste_removal_request_id=booking.id,
                        latitude=51.5, longitude=-0.1,
                        recorded_at=utcnow() - timedelta(minutes=minute),
                    )
                )
        app_context.db.session.commit()
    return ids


class _StatementCounter:
    """Counts SELECTs issued while it is active."""

    def __init__(self, engine):
        self.engine = engine
        self.statements = []

    def __enter__(self):
        sa.event.listen(self.engine, 'before_cursor_execute', self._record)
        return self

    def __exit__(self, *exc):
        sa.event.remove(self.engine, 'before_cursor_execute', self._record)

    def _record(self, conn, cursor, statement, params, context, executemany):
        self.statements.append(statement)

    @property
    def selects(self):
        return [s for s in self.statements if s.lstrip().upper().startswith('SELECT')]


# --- The queue's query count no longer grows with the page ------------------


def test_the_dispatch_queue_query_count_does_not_grow_with_the_page(client, app_context):
    _create_user(app_context, 'admin@example.com', 'Password123!', role='admin', name='A')
    _create_user(app_context, 'driver@example.com', 'Password123!', role='driver', name='D')
    with app_context.app.app_context():
        driver_id = app_context.User.query.filter_by(email='driver@example.com').first().id
    headers = _auth_header(client, 'admin@example.com', 'Password123!')

    with app_context.app.app_context():
        engine = app_context.db.engine

    counts = {}
    for size in (3, 24):
        with app_context.app.app_context():
            WasteRemovalVehicleLocation.query.delete()
            app_context.WasteRemovalRequest.query.delete()
            app_context.db.session.commit()
        _seed_requests(app_context, size, driver_user_id=driver_id)

        with _StatementCounter(engine) as counter:
            response = client.get('/api/v1/admin/dispatch/queue?limit=500', headers=headers)
        assert response.status_code == 200
        assert len(response.get_json()['items']) == size
        counts[size] = len(counter.selects)

    assert counts[3] == counts[24], (
        'query count grew with the page size: {}'.format(counts)
    )


def test_the_queue_still_reports_driver_and_location(client, app_context):
    """Batching must not change what a queue item says."""
    _create_user(app_context, 'admin2@example.com', 'Password123!', role='admin', name='A')
    _create_user(app_context, 'driver2@example.com', 'Password123!', role='driver', name='D')
    with app_context.app.app_context():
        driver_id = app_context.User.query.filter_by(email='driver2@example.com').first().id
    _seed_requests(app_context, 2, driver_user_id=driver_id)

    headers = _auth_header(client, 'admin2@example.com', 'Password123!')
    items = client.get('/api/v1/admin/dispatch/queue', headers=headers).get_json()['items']

    assert items
    for item in items:
        assert item['driver']['id'] == driver_id
        assert item['driver']['email'] == 'driver2@example.com'
        assert 'dispatch_eligible' in item['driver']
        assert item['latest_location'] is not None
        assert 'compliance' in item


# --- The batched lookup matches the per-row one it replaced -----------------


def test_the_batched_latest_location_matches_the_per_row_lookup(app_context):
    ids = _seed_requests(app_context, 5, locations_each=4)

    with app_context.app.app_context():
        batched = _latest_vehicle_locations_for_requests(ids)
        for request_id in ids:
            per_row = (
                WasteRemovalVehicleLocation.query
                .filter_by(waste_removal_request_id=request_id)
                .order_by(
                    WasteRemovalVehicleLocation.recorded_at.desc(),
                    WasteRemovalVehicleLocation.id.desc(),
                )
                .first()
            )
            assert batched[request_id].id == per_row.id


def test_a_backdated_location_does_not_win_on_id(app_context):
    """Why this is ranked rather than MAX(id): the newest row is not the last."""
    ids = _seed_requests(app_context, 1, locations_each=0)
    request_id = ids[0]

    with app_context.app.app_context():
        newest = WasteRemovalVehicleLocation(
            waste_removal_request_id=request_id, latitude=51.6, longitude=-0.2,
            recorded_at=utcnow(),
        )
        app_context.db.session.add(newest)
        app_context.db.session.flush()
        newest_id = newest.id

        # Inserted afterwards, so it has the higher id, but it is older.
        app_context.db.session.add(
            WasteRemovalVehicleLocation(
                waste_removal_request_id=request_id, latitude=51.7, longitude=-0.3,
                recorded_at=utcnow() - timedelta(hours=6),
            )
        )
        app_context.db.session.commit()

        batched = _latest_vehicle_locations_for_requests([request_id])
        assert batched[request_id].id == newest_id


def test_the_context_handles_a_page_with_no_drivers_or_locations(app_context):
    ids = _seed_requests(app_context, 2, driver_user_id=None, locations_each=0)
    with app_context.app.app_context():
        bookings = app_context.WasteRemovalRequest.query.filter(
            app_context.WasteRemovalRequest.id.in_(ids),
        ).all()
        context = DispatchQueueContext(bookings)
        for booking in bookings:
            item = context.serialize(booking, now=utcnow())
            assert item['driver'] is None
            assert item['latest_location'] is None

    assert DispatchQueueContext([]).drivers == {}


# --- Alembic owns the schema -------------------------------------------------


def test_no_request_hook_creates_tables(app_context):
    """The before_request hook that called db.create_all() is gone."""
    hooks = [
        func.__name__
        for funcs in app_context.app.before_request_funcs.values()
        for func in funcs
    ]
    assert 'ensure_core_tables' not in hooks

    import projectdivert.hooks as hooks_module
    assert not hasattr(hooks_module, 'ensure_core_tables')


def test_a_request_does_not_recreate_a_dropped_table(client, app_context):
    """An un-migrated database must fail, not be silently patched up.

    Two workers doing this concurrently on a cold start is the race; one worker
    doing it at all is two sources of truth for the schema.
    """
    with app_context.app.app_context():
        app_context.Material.__table__.drop(app_context.db.engine)
        assert not sa.inspect(app_context.db.engine).has_table('materials')

    try:
        try:
            client.get('/materials')
        except Exception:
            # An un-migrated database is supposed to fail. Under TESTING Flask
            # re-raises rather than rendering the 500 page; either way what
            # matters is what it did *not* do.
            pass

        with app_context.app.app_context():
            assert not sa.inspect(app_context.db.engine).has_table('materials'), (
                'the application recreated a table it does not own'
            )
    finally:
        # Put it back whatever happened, so the fixture teardown still works.
        with app_context.app.app_context():
            if not sa.inspect(app_context.db.engine).has_table('materials'):
                app_context.Material.__table__.create(app_context.db.engine)


def test_seed_materials_is_available_as_a_command_and_is_idempotent(app_context):
    runner = app_context.app.test_cli_runner()

    first = runner.invoke(args=['seed-materials'])
    assert first.exit_code == 0, first.output
    assert 'seeded' in first.output

    second = runner.invoke(args=['seed-materials'])
    assert second.exit_code == 0, second.output
    assert '(0 seeded)' in second.output
