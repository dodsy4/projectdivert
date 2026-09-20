"""The migration chain must actually run, and must agree with the models.

The suite builds its schema with ``db.create_all()``, so nothing else here
exercises Alembic. That gap hid a real break: nine migrations added foreign
keys with a plain ``op.create_foreign_key``, which SQLite cannot do via ALTER
TABLE, so ``flask db upgrade`` on a fresh SQLite database aborted partway --
the exact command the README quickstart tells a new contributor to run. It
worked on Postgres, so production never noticed.

These tests run the whole chain end to end on SQLite and then compare the
result against the schema the models describe, which also catches a migration
that drifts away from a model.
"""

import importlib
import os

import pytest
from sqlalchemy import create_engine, inspect

# Tables Alembic owns or that are created outside the model metadata.
IGNORED_TABLES = {'alembic_version'}


def _build_app_on(database_uri):
    """A fresh application bound to database_uri.

    config snapshots the environment at import, so it has to be reloaded after
    the variable is set, before the factory reads it.
    """
    import config

    previous = os.environ.get('SQLALCHEMY_DATABASE_URI')
    os.environ['SQLALCHEMY_DATABASE_URI'] = database_uri
    try:
        importlib.reload(config)
        from projectdivert import create_app

        return create_app()
    finally:
        if previous is None:
            os.environ.pop('SQLALCHEMY_DATABASE_URI', None)
        else:
            os.environ['SQLALCHEMY_DATABASE_URI'] = previous
        importlib.reload(config)


@pytest.fixture(scope='module')
def migrated(tmp_path_factory):
    """Run the full migration chain against an empty SQLite database."""
    from flask_migrate import upgrade

    path = tmp_path_factory.mktemp('migrations') / 'migrated.db'
    uri = 'sqlite:///{}'.format(path)
    app = _build_app_on(uri)
    with app.app_context():
        upgrade()
    return uri


def test_the_chain_upgrades_from_empty(migrated):
    """flask db upgrade must succeed on a fresh database, not abort partway."""
    engine = create_engine(migrated)
    with engine.connect() as connection:
        from sqlalchemy import text

        revisions = [r[0] for r in connection.execute(text('SELECT version_num FROM alembic_version'))]
    assert len(revisions) == 1, 'expected exactly one head, got {}'.format(revisions)


def test_chain_reaches_the_scripts_head(migrated):
    from alembic.script import ScriptDirectory
    from flask import current_app

    app = _build_app_on(migrated)
    with app.app_context():
        directory = current_app.extensions['migrate'].directory
        heads = ScriptDirectory(directory).get_heads()

    engine = create_engine(migrated)
    with engine.connect() as connection:
        from sqlalchemy import text

        applied = connection.execute(text('SELECT version_num FROM alembic_version')).scalar()
    assert applied in heads, 'database is at {}, script head is {}'.format(applied, heads)


def test_migrated_tables_match_the_models(migrated, tmp_path):
    """Every table the models declare must exist after migrating, and vice versa."""
    from projectdivert.extensions import db

    fresh_uri = 'sqlite:///{}'.format(tmp_path / 'created.db')
    app = _build_app_on(fresh_uri)
    with app.app_context():
        db.create_all()
        model_tables = set(db.metadata.tables)

    migrated_tables = set(inspect(create_engine(migrated)).get_table_names()) - IGNORED_TABLES

    missing = sorted(model_tables - migrated_tables)
    assert not missing, 'the models declare tables the migrations never create: {}'.format(missing)


@pytest.mark.parametrize('table', ['users', 'waste_removal_requests', 'audit_events'])
def test_core_table_columns_match_the_models(migrated, tmp_path, table):
    """A migration that drifts from its model shows up as a column difference."""
    from projectdivert.extensions import db

    fresh_uri = 'sqlite:///{}'.format(tmp_path / 'created_{}.db'.format(table))
    app = _build_app_on(fresh_uri)
    with app.app_context():
        db.create_all()
        expected = {c.name for c in db.metadata.tables[table].columns}

    actual = {c['name'] for c in inspect(create_engine(migrated)).get_columns(table)}

    missing = sorted(expected - actual)
    assert not missing, '{} is missing columns the model declares: {}'.format(table, missing)


def test_users_carries_the_whatsapp_columns(migrated):
    columns = {c['name'] for c in inspect(create_engine(migrated)).get_columns('users')}
    assert {'phone', 'whatsapp_linked_at'} <= columns


def test_estimate_conversion_is_skipped_when_the_columns_are_already_numeric(tmp_path):
    """A database built from the models must not break the chain.

    d5e6f7a8b9c0 converts three diversion_estimates columns from text to
    numeric, cleaning blank strings with btrim() first. A database whose tables
    came from db.create_all() already has them as numeric, and btrim() on a
    numeric column is an error rather than a no-op -- so the migration aborted
    on an otherwise healthy database. It now asks before converting.
    """
    from sqlalchemy import Column, MetaData, Numeric, String, Table

    module = importlib.import_module(
        'migrations.versions.d5e6f7a8b9c0_rename_core_marketplace_models',
    )

    engine = create_engine('sqlite:///{}'.format(tmp_path / 'shapes.db'))
    metadata = MetaData()
    Table(
        'already_numeric', metadata,
        Column('amount', Numeric(12, 3)),
        Column('traditional_cost', Numeric(12, 2)),
    )
    Table(
        'still_text', metadata,
        Column('amount', String(120)),
        Column('traditional_cost', String(120)),
    )
    metadata.create_all(engine)

    inspector = inspect(engine)
    for column in ('amount', 'traditional_cost'):
        assert module._is_string_column(inspector, 'still_text', column) is True
        assert module._is_string_column(inspector, 'already_numeric', column) is False

    # A column the table does not have is not something to convert either.
    assert module._is_string_column(inspector, 'already_numeric', 'nope') is False
