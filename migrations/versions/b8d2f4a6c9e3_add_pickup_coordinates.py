"""Store the pickup coordinates on a waste request.

The postcode was geocoded when a request was created, used to choose providers
and then thrown away. So nothing recorded where a collection actually is, and a
map of collections had nothing to plot.

Existing rows keep NULL coordinates. Backfilling would mean geocoding every
historical postcode through an external service during a migration, which is
the wrong place for a network call that can fail halfway; `flask backfill-
pickup-coordinates` does it afterwards, and can be re-run.

Revision ID: b8d2f4a6c9e3
Revises: a3b5c7d9e1f4
Create Date: 2026-09-20 14:05:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8d2f4a6c9e3'
down_revision = 'a3b5c7d9e1f4'
branch_labels = None
depends_on = None

TABLE_NAME = 'waste_removal_requests'
COLUMNS = ('pickup_latitude', 'pickup_longitude')


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name, column_name):
    return any(column.get('name') == column_name
               for column in inspector.get_columns(table_name))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, TABLE_NAME):
        return

    with op.batch_alter_table(TABLE_NAME) as batch_op:
        for column_name in COLUMNS:
            if not _has_column(inspector, TABLE_NAME, column_name):
                batch_op.add_column(sa.Column(column_name, sa.Float(), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, TABLE_NAME):
        return

    with op.batch_alter_table(TABLE_NAME) as batch_op:
        for column_name in COLUMNS:
            if _has_column(inspector, TABLE_NAME, column_name):
                batch_op.drop_column(column_name)
