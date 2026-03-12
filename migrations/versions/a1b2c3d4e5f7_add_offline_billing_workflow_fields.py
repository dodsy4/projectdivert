"""Add offline billing workflow fields to waste removal requests.

Revision ID: a1b2c3d4e5f7
Revises: f7a8b9c0d1e2
Create Date: 2026-03-12 21:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f7'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def _has_column(inspector, table_name, column_name):
    return any(column.get('name') == column_name for column in inspector.get_columns(table_name))


def _has_index(inspector, table_name, index_name):
    return any(index.get('name') == index_name for index in inspector.get_indexes(table_name))


def _has_fk_name(inspector, table_name, fk_name):
    return any((fk.get('name') or '') == fk_name for fk in inspector.get_foreign_keys(table_name))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'waste_removal_requests'

    columns = {
        'billing_state': sa.Column('billing_state', sa.String(length=32), nullable=True),
        'billing_reference': sa.Column('billing_reference', sa.String(length=120), nullable=True),
        'billing_notes': sa.Column('billing_notes', sa.Text(), nullable=True),
        'billing_updated_at': sa.Column('billing_updated_at', sa.DateTime(), nullable=True),
        'billing_updated_by_user_id': sa.Column('billing_updated_by_user_id', sa.Integer(), nullable=True),
    }

    for column_name, column in columns.items():
        if not _has_column(inspector, table_name, column_name):
            op.add_column(table_name, column)

    inspector = sa.inspect(bind)
    if not _has_fk_name(inspector, table_name, 'fk_waste_removal_requests_billing_updated_by_user_id_users'):
        op.create_foreign_key(
            'fk_waste_removal_requests_billing_updated_by_user_id_users',
            table_name,
            'users',
            ['billing_updated_by_user_id'],
            ['id'],
        )

    inspector = sa.inspect(bind)
    for index_name, column_name in [
        ('ix_waste_removal_requests_billing_state', 'billing_state'),
        ('ix_waste_removal_requests_billing_updated_at', 'billing_updated_at'),
        ('ix_waste_removal_requests_billing_updated_by_user_id', 'billing_updated_by_user_id'),
    ]:
        if not _has_index(inspector, table_name, index_name):
            op.create_index(index_name, table_name, [column_name], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'waste_removal_requests'

    for index_name in [
        'ix_waste_removal_requests_billing_updated_by_user_id',
        'ix_waste_removal_requests_billing_updated_at',
        'ix_waste_removal_requests_billing_state',
    ]:
        if _has_index(inspector, table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
            inspector = sa.inspect(bind)

    if _has_fk_name(inspector, table_name, 'fk_waste_removal_requests_billing_updated_by_user_id_users'):
        op.drop_constraint(
            'fk_waste_removal_requests_billing_updated_by_user_id_users',
            table_name,
            type_='foreignkey',
        )
        inspector = sa.inspect(bind)

    for column_name in [
        'billing_updated_by_user_id',
        'billing_updated_at',
        'billing_notes',
        'billing_reference',
        'billing_state',
    ]:
        if _has_column(inspector, table_name, column_name):
            op.drop_column(table_name, column_name)
            inspector = sa.inspect(bind)
