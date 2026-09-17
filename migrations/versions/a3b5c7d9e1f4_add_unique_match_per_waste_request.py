"""Add a unique constraint so a waste request can only be matched once.

Before this, _accept_dispatch_offer decided whether a request was already
matched with a read-then-write check and no row lock, so two drivers accepting
different offers on the same request concurrently could both create a match and
double-book the job. The service now takes a row lock; this constraint is what
makes the invariant hold even without one.

Any duplicate matches already in the table are the result of that race. The
earliest row per request is kept, which is the outcome the row lock produces
going forward (first acceptance wins), and the rest are deleted.

Revision ID: a3b5c7d9e1f4
Revises: f2a4b6c8d0e1
Create Date: 2026-09-17 21:10:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3b5c7d9e1f4'
down_revision = 'f2a4b6c8d0e1'
branch_labels = None
depends_on = None

TABLE_NAME = 'waste_removal_matches'
CONSTRAINT_NAME = 'uq_waste_removal_matches_request_id'


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_unique_constraint(inspector, table_name, constraint_name):
    existing = inspector.get_unique_constraints(table_name)
    return any(constraint.get('name') == constraint_name for constraint in existing)


def _delete_duplicate_matches(bind):
    """Keep the earliest match per request, delete the rest."""
    duplicates = bind.execute(
        sa.text(
            'SELECT id FROM {table} WHERE id NOT IN ('
            '  SELECT MIN(id) FROM {table} GROUP BY waste_removal_request_id'
            ')'.format(table=TABLE_NAME)
        )
    ).fetchall()
    if not duplicates:
        return 0

    duplicate_ids = [row[0] for row in duplicates]
    bind.execute(
        sa.text(
            'DELETE FROM {table} WHERE id IN :ids'.format(table=TABLE_NAME)
        ).bindparams(sa.bindparam('ids', value=duplicate_ids, expanding=True))
    )
    return len(duplicate_ids)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, TABLE_NAME):
        return
    if _has_unique_constraint(inspector, TABLE_NAME, CONSTRAINT_NAME):
        return

    removed = _delete_duplicate_matches(bind)
    if removed:
        print(
            'Removed {} duplicate waste_removal_matches row(s) before adding '
            '{}.'.format(removed, CONSTRAINT_NAME)
        )

    # batch_alter_table so this also applies on SQLite, which cannot ALTER a
    # table to add a constraint in place.
    with op.batch_alter_table(TABLE_NAME) as batch_op:
        batch_op.create_unique_constraint(
            CONSTRAINT_NAME,
            ['waste_removal_request_id'],
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, TABLE_NAME):
        return
    if not _has_unique_constraint(inspector, TABLE_NAME, CONSTRAINT_NAME):
        return

    with op.batch_alter_table(TABLE_NAME) as batch_op:
        batch_op.drop_constraint(CONSTRAINT_NAME, type_='unique')
