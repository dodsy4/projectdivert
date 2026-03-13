"""Add billing follow-up workflow fields to waste removal requests.

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a8
Create Date: 2026-03-13 16:55:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4d5e6f7a8b9'
down_revision = 'b2c3d4e5f6a8'
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
        'billing_followup_state': sa.Column('billing_followup_state', sa.String(length=32), nullable=True),
        'billing_followup_notes': sa.Column('billing_followup_notes', sa.Text(), nullable=True),
        'billing_followup_updated_at': sa.Column('billing_followup_updated_at', sa.DateTime(), nullable=True),
        'billing_followup_updated_by_user_id': sa.Column(
            'billing_followup_updated_by_user_id',
            sa.Integer(),
            nullable=True,
        ),
    }

    for column_name, column in columns.items():
        if not _has_column(inspector, table_name, column_name):
            op.add_column(table_name, column)

    inspector = sa.inspect(bind)
    fk_name = 'fk_wrr_billing_followup_updated_by_uid_users'
    if not _has_fk_name(inspector, table_name, fk_name):
        op.create_foreign_key(
            fk_name,
            table_name,
            'users',
            ['billing_followup_updated_by_user_id'],
            ['id'],
        )

    inspector = sa.inspect(bind)
    for index_name, column_name in [
        ('ix_wrr_billing_followup_state', 'billing_followup_state'),
        ('ix_wrr_billing_followup_updated_at', 'billing_followup_updated_at'),
        (
            'ix_wrr_billing_followup_updated_by_uid',
            'billing_followup_updated_by_user_id',
        ),
    ]:
        if not _has_index(inspector, table_name, index_name):
            op.create_index(index_name, table_name, [column_name], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'waste_removal_requests'

    for index_name in [
        'ix_wrr_billing_followup_updated_by_uid',
        'ix_wrr_billing_followup_updated_at',
        'ix_wrr_billing_followup_state',
    ]:
        if _has_index(inspector, table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
            inspector = sa.inspect(bind)

    fk_name = 'fk_wrr_billing_followup_updated_by_uid_users'
    if _has_fk_name(inspector, table_name, fk_name):
        op.drop_constraint(
            fk_name,
            table_name,
            type_='foreignkey',
        )
        inspector = sa.inspect(bind)

    for column_name in [
        'billing_followup_updated_by_user_id',
        'billing_followup_updated_at',
        'billing_followup_notes',
        'billing_followup_state',
    ]:
        if _has_column(inspector, table_name, column_name):
            op.drop_column(table_name, column_name)
            inspector = sa.inspect(bind)
