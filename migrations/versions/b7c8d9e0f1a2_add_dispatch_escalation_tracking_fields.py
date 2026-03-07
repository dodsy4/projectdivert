"""Add dispatch escalation tracking fields to waste requests.

Revision ID: b7c8d9e0f1a2
Revises: f1a2b3c4d5e6
Create Date: 2026-03-07 12:15:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7c8d9e0f1a2'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name, column_name):
    return any(column.get('name') == column_name for column in inspector.get_columns(table_name))


def _has_index(inspector, table_name, index_name):
    return any(index.get('name') == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'waste_removal_requests'

    if not _has_table(inspector, table_name):
        return

    if not _has_column(inspector, table_name, 'incident_last_escalation_key'):
        op.add_column(table_name, sa.Column('incident_last_escalation_key', sa.String(length=120), nullable=True))
    if not _has_column(inspector, table_name, 'incident_last_escalated_at'):
        op.add_column(table_name, sa.Column('incident_last_escalated_at', sa.DateTime(), nullable=True))

    inspector = sa.inspect(bind)
    for index_name, columns in [
        ('ix_waste_removal_requests_incident_last_escalation_key', ['incident_last_escalation_key']),
        ('ix_waste_removal_requests_incident_last_escalated_at', ['incident_last_escalated_at']),
    ]:
        if not _has_index(inspector, table_name, index_name):
            op.create_index(index_name, table_name, columns, unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'waste_removal_requests'
    if not _has_table(inspector, table_name):
        return

    for index_name in [
        'ix_waste_removal_requests_incident_last_escalated_at',
        'ix_waste_removal_requests_incident_last_escalation_key',
    ]:
        if _has_index(inspector, table_name, index_name):
            op.drop_index(index_name, table_name=table_name)

    inspector = sa.inspect(bind)
    for column_name in [
        'incident_last_escalated_at',
        'incident_last_escalation_key',
    ]:
        if _has_column(inspector, table_name, column_name):
            op.drop_column(table_name, column_name)
        inspector = sa.inspect(bind)
