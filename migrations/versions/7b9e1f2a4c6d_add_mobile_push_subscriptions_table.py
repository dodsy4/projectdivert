"""Add mobile push subscriptions table.

Revision ID: 7b9e1f2a4c6d
Revises: d3a7c1e0b1f2
Create Date: 2026-02-27 17:20:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7b9e1f2a4c6d'
down_revision = 'd3a7c1e0b1f2'
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


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
    table_name = 'mobile_push_subscriptions'

    if not _has_table(inspector, table_name):
        op.create_table(
            table_name,
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('provider', sa.String(length=32), nullable=False, server_default='expo'),
            sa.Column('token', sa.String(length=255), nullable=False),
            sa.Column('platform', sa.String(length=32), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('last_seen_at', sa.DateTime(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    inspector = sa.inspect(bind)
    if _has_table(inspector, table_name):
        if not _has_index(inspector, table_name, 'ix_mobile_push_subscriptions_user_id'):
            op.create_index('ix_mobile_push_subscriptions_user_id', table_name, ['user_id'], unique=False)
        if not _has_index(inspector, table_name, 'ix_mobile_push_subscriptions_token'):
            op.create_index('ix_mobile_push_subscriptions_token', table_name, ['token'], unique=True)
        if not _has_index(inspector, table_name, 'ix_mobile_push_subscriptions_is_active'):
            op.create_index('ix_mobile_push_subscriptions_is_active', table_name, ['is_active'], unique=False)

        if not _has_fk(inspector, table_name, 'user_id'):
            op.create_foreign_key(
                'fk_mobile_push_subscriptions_user_id_users',
                table_name,
                'users',
                ['user_id'],
                ['id'],
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'mobile_push_subscriptions'

    if not _has_table(inspector, table_name):
        return

    if _has_index(inspector, table_name, 'ix_mobile_push_subscriptions_is_active'):
        op.drop_index('ix_mobile_push_subscriptions_is_active', table_name=table_name)
    if _has_index(inspector, table_name, 'ix_mobile_push_subscriptions_token'):
        op.drop_index('ix_mobile_push_subscriptions_token', table_name=table_name)
    if _has_index(inspector, table_name, 'ix_mobile_push_subscriptions_user_id'):
        op.drop_index('ix_mobile_push_subscriptions_user_id', table_name=table_name)

    if _has_fk(inspector, table_name, 'user_id'):
        op.drop_constraint('fk_mobile_push_subscriptions_user_id_users', table_name, type_='foreignkey')

    op.drop_table(table_name)
