"""Add assigned driver ownership to waste removal requests.

Revision ID: d3a7c1e0b1f2
Revises: 9f0d5d71d7b3
Create Date: 2026-02-27 13:40:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd3a7c1e0b1f2'
down_revision = '9f0d5d71d7b3'
branch_labels = None
depends_on = None


def _has_column(inspector, table_name, column_name):
    return any(column.get('name') == column_name for column in inspector.get_columns(table_name))


def _has_index(inspector, table_name, index_name):
    return any(index.get('name') == index_name for index in inspector.get_indexes(table_name))


def _has_fk(inspector, table_name, constrained_column):
    for foreign_key in inspector.get_foreign_keys(table_name):
        columns = foreign_key.get('constrained_columns') or []
        if constrained_column in columns:
            return True
    return False


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'waste_removal_requests'
    column_name = 'assigned_driver_user_id'
    index_name = 'ix_waste_removal_requests_assigned_driver_user_id'
    fk_name = 'fk_waste_removal_requests_assigned_driver_user_id_users'

    if not _has_column(inspector, table_name, column_name):
        op.add_column(
            table_name,
            sa.Column(column_name, sa.Integer(), nullable=True),
        )

    inspector = sa.inspect(bind)
    if not _has_fk(inspector, table_name, column_name):
        op.create_foreign_key(
            fk_name,
            table_name,
            'users',
            [column_name],
            ['id'],
        )

    inspector = sa.inspect(bind)
    if not _has_index(inspector, table_name, index_name):
        op.create_index(index_name, table_name, [column_name], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'waste_removal_requests'
    column_name = 'assigned_driver_user_id'
    index_name = 'ix_waste_removal_requests_assigned_driver_user_id'
    fk_name = 'fk_waste_removal_requests_assigned_driver_user_id_users'

    if _has_index(inspector, table_name, index_name):
        op.drop_index(index_name, table_name=table_name)

    inspector = sa.inspect(bind)
    if _has_fk(inspector, table_name, column_name):
        op.drop_constraint(fk_name, table_name, type_='foreignkey')

    inspector = sa.inspect(bind)
    if _has_column(inspector, table_name, column_name):
        op.drop_column(table_name, column_name)
