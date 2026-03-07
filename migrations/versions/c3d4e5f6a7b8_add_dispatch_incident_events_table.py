"""Add dispatch incident events table.

Revision ID: c3d4e5f6a7b8
Revises: b7c8d9e0f1a2
Create Date: 2026-03-07 14:45:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_index(inspector, table_name, index_name):
    return any(index.get('name') == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'dispatch_incident_events'

    if not _has_table(inspector, table_name):
        op.create_table(
            table_name,
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('waste_removal_request_id', sa.Integer(), nullable=False),
            sa.Column('event_type', sa.String(length=64), nullable=False),
            sa.Column('actor_user_id', sa.Integer(), nullable=True),
            sa.Column('actor_email', sa.String(length=255), nullable=True),
            sa.Column('source', sa.String(length=64), nullable=False, server_default='system'),
            sa.Column('details_json', sa.JSON(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['waste_removal_request_id'], ['waste_removal_requests.id']),
            sa.ForeignKeyConstraint(['actor_user_id'], ['users.id']),
        )

    inspector = sa.inspect(bind)
    for index_name, columns in [
        ('ix_dispatch_incident_events_waste_removal_request_id', ['waste_removal_request_id']),
        ('ix_dispatch_incident_events_event_type', ['event_type']),
        ('ix_dispatch_incident_events_actor_user_id', ['actor_user_id']),
        ('ix_dispatch_incident_events_actor_email', ['actor_email']),
        ('ix_dispatch_incident_events_created_at', ['created_at']),
    ]:
        if not _has_index(inspector, table_name, index_name):
            op.create_index(index_name, table_name, columns, unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'dispatch_incident_events'

    if not _has_table(inspector, table_name):
        return

    for index_name in [
        'ix_dispatch_incident_events_created_at',
        'ix_dispatch_incident_events_actor_email',
        'ix_dispatch_incident_events_actor_user_id',
        'ix_dispatch_incident_events_event_type',
        'ix_dispatch_incident_events_waste_removal_request_id',
    ]:
        if _has_index(inspector, table_name, index_name):
            op.drop_index(index_name, table_name=table_name)

    op.drop_table(table_name)
