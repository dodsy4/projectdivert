"""Add application-wide audit_events table.

Revision ID: e7f8a9b0c1d2
Revises: d5e6f7a8b9c0
Create Date: 2026-09-07 22:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7f8a9b0c1d2'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_index(inspector, table_name, index_name):
    return any(index.get('name') == index_name for index in inspector.get_indexes(table_name))


INDEXES = [
    ('ix_audit_events_occurred_at', 'occurred_at'),
    ('ix_audit_events_action', 'action'),
    ('ix_audit_events_entity_type', 'entity_type'),
    ('ix_audit_events_entity_id', 'entity_id'),
    ('ix_audit_events_actor_user_id', 'actor_user_id'),
    ('ix_audit_events_actor_role', 'actor_role'),
    ('ix_audit_events_actor_email', 'actor_email'),
    ('ix_audit_events_source', 'source'),
    ('ix_audit_events_status_code', 'status_code'),
    ('ix_audit_events_request_id', 'request_id'),
]


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'audit_events'

    if not _has_table(inspector, table_name):
        op.create_table(
            table_name,
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('occurred_at', sa.DateTime(), nullable=False),
            sa.Column('action', sa.String(length=80), nullable=False),
            sa.Column('entity_type', sa.String(length=64), nullable=True),
            sa.Column('entity_id', sa.String(length=64), nullable=True),
            sa.Column('actor_user_id', sa.Integer(), nullable=True),
            sa.Column('actor_role', sa.String(length=32), nullable=True),
            sa.Column('actor_email', sa.String(length=255), nullable=True),
            sa.Column('actor_ip', sa.String(length=64), nullable=True),
            sa.Column('user_agent', sa.String(length=255), nullable=True),
            sa.Column('source', sa.String(length=16), nullable=False, server_default='web'),
            sa.Column('http_method', sa.String(length=8), nullable=True),
            sa.Column('path', sa.String(length=255), nullable=True),
            sa.Column('status_code', sa.Integer(), nullable=True),
            sa.Column('request_id', sa.String(length=32), nullable=True),
            sa.Column('summary', sa.String(length=255), nullable=True),
            sa.Column('changes', sa.JSON(), nullable=False),
            sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name='fk_audit_events_actor_user_id_users'),
        )

    inspector = sa.inspect(bind)
    for index_name, column_name in INDEXES:
        if not _has_index(inspector, table_name, index_name):
            op.create_index(index_name, table_name, [column_name], unique=False)

    if not _has_index(inspector, table_name, 'ix_audit_events_entity'):
        op.create_index('ix_audit_events_entity', table_name, ['entity_type', 'entity_id'], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'audit_events'

    if not _has_table(inspector, table_name):
        return

    if _has_index(inspector, table_name, 'ix_audit_events_entity'):
        op.drop_index('ix_audit_events_entity', table_name=table_name)

    for index_name, _column_name in INDEXES:
        if _has_index(inspector, table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
            inspector = sa.inspect(bind)

    op.drop_table(table_name)
