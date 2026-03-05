"""Add auth audit events table.

Revision ID: c9d5e2a1f4b7
Revises: b4c1d9e7f2a3
Create Date: 2026-02-28 15:35:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9d5e2a1f4b7'
down_revision = 'b4c1d9e7f2a3'
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


def _has_fk_name(inspector, table_name, constraint_name):
    for foreign_key in inspector.get_foreign_keys(table_name):
        if foreign_key.get('name') == constraint_name:
            return True
    return False


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'auth_audit_events'

    if not _has_table(inspector, table_name):
        op.create_table(
            table_name,
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('event', sa.String(length=64), nullable=False),
            sa.Column('success', sa.Boolean(), nullable=False),
            sa.Column('status_code', sa.Integer(), nullable=False),
            sa.Column('email', sa.String(length=255), nullable=True),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('ip', sa.String(length=64), nullable=True),
            sa.Column('user_agent', sa.String(length=255), nullable=True),
            sa.Column('details_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column('occurred_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(
                ['user_id'],
                ['users.id'],
                name='fk_auth_audit_events_user_id_users',
            ),
            sa.PrimaryKeyConstraint('id'),
        )

    inspector = sa.inspect(bind)
    if _has_table(inspector, table_name):
        if not _has_index(inspector, table_name, 'ix_auth_audit_events_event'):
            op.create_index('ix_auth_audit_events_event', table_name, ['event'], unique=False)
        if not _has_index(inspector, table_name, 'ix_auth_audit_events_success'):
            op.create_index('ix_auth_audit_events_success', table_name, ['success'], unique=False)
        if not _has_index(inspector, table_name, 'ix_auth_audit_events_status_code'):
            op.create_index('ix_auth_audit_events_status_code', table_name, ['status_code'], unique=False)
        if not _has_index(inspector, table_name, 'ix_auth_audit_events_email'):
            op.create_index('ix_auth_audit_events_email', table_name, ['email'], unique=False)
        if not _has_index(inspector, table_name, 'ix_auth_audit_events_user_id'):
            op.create_index('ix_auth_audit_events_user_id', table_name, ['user_id'], unique=False)
        if not _has_index(inspector, table_name, 'ix_auth_audit_events_ip'):
            op.create_index('ix_auth_audit_events_ip', table_name, ['ip'], unique=False)
        if not _has_index(inspector, table_name, 'ix_auth_audit_events_occurred_at'):
            op.create_index('ix_auth_audit_events_occurred_at', table_name, ['occurred_at'], unique=False)
        if not _has_fk(inspector, table_name, 'user_id'):
            op.create_foreign_key(
                'fk_auth_audit_events_user_id_users',
                table_name,
                'users',
                ['user_id'],
                ['id'],
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'auth_audit_events'
    if not _has_table(inspector, table_name):
        return

    if _has_index(inspector, table_name, 'ix_auth_audit_events_occurred_at'):
        op.drop_index('ix_auth_audit_events_occurred_at', table_name=table_name)
    if _has_index(inspector, table_name, 'ix_auth_audit_events_ip'):
        op.drop_index('ix_auth_audit_events_ip', table_name=table_name)
    if _has_index(inspector, table_name, 'ix_auth_audit_events_user_id'):
        op.drop_index('ix_auth_audit_events_user_id', table_name=table_name)
    if _has_index(inspector, table_name, 'ix_auth_audit_events_email'):
        op.drop_index('ix_auth_audit_events_email', table_name=table_name)
    if _has_index(inspector, table_name, 'ix_auth_audit_events_status_code'):
        op.drop_index('ix_auth_audit_events_status_code', table_name=table_name)
    if _has_index(inspector, table_name, 'ix_auth_audit_events_success'):
        op.drop_index('ix_auth_audit_events_success', table_name=table_name)
    if _has_index(inspector, table_name, 'ix_auth_audit_events_event'):
        op.drop_index('ix_auth_audit_events_event', table_name=table_name)
    if _has_fk_name(inspector, table_name, 'fk_auth_audit_events_user_id_users'):
        op.drop_constraint('fk_auth_audit_events_user_id_users', table_name, type_='foreignkey')

    op.drop_table(table_name)
