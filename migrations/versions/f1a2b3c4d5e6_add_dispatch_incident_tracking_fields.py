"""Add dispatch incident tracking fields to waste requests.

Revision ID: f1a2b3c4d5e6
Revises: e5b7c1a9d4f0
Create Date: 2026-03-07 11:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'e5b7c1a9d4f0'
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name, column_name):
    return any(column.get('name') == column_name for column in inspector.get_columns(table_name))


def _has_index(inspector, table_name, index_name):
    return any(index.get('name') == index_name for index in inspector.get_indexes(table_name))


def _has_fk_name(inspector, table_name, constraint_name):
    for foreign_key in inspector.get_foreign_keys(table_name):
        if foreign_key.get('name') == constraint_name:
            return True
    return False


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = 'waste_removal_requests'

    if not _has_table(inspector, table_name):
        return

    if not _has_column(inspector, table_name, 'incident_state'):
        op.add_column(table_name, sa.Column('incident_state', sa.String(length=32), nullable=True))
    if not _has_column(inspector, table_name, 'incident_severity'):
        op.add_column(table_name, sa.Column('incident_severity', sa.String(length=16), nullable=True))
    if not _has_column(inspector, table_name, 'incident_owner_admin_user_id'):
        op.add_column(table_name, sa.Column('incident_owner_admin_user_id', sa.Integer(), nullable=True))
    if not _has_column(inspector, table_name, 'incident_acknowledged_at'):
        op.add_column(table_name, sa.Column('incident_acknowledged_at', sa.DateTime(), nullable=True))
    if not _has_column(inspector, table_name, 'incident_resolved_at'):
        op.add_column(table_name, sa.Column('incident_resolved_at', sa.DateTime(), nullable=True))
    if not _has_column(inspector, table_name, 'incident_notes'):
        op.add_column(table_name, sa.Column('incident_notes', sa.Text(), nullable=True))
    if not _has_column(inspector, table_name, 'incident_updated_at'):
        op.add_column(table_name, sa.Column('incident_updated_at', sa.DateTime(), nullable=True))

    inspector = sa.inspect(bind)
    fk_name = 'fk_waste_removal_requests_incident_owner_admin_user_id_users'
    if (
        _has_column(inspector, table_name, 'incident_owner_admin_user_id')
        and not _has_fk_name(inspector, table_name, fk_name)
    ):
        op.create_foreign_key(
            fk_name,
            table_name,
            'users',
            ['incident_owner_admin_user_id'],
            ['id'],
        )

    for index_name, columns in [
        ('ix_waste_removal_requests_incident_state', ['incident_state']),
        ('ix_waste_removal_requests_incident_severity', ['incident_severity']),
        ('ix_waste_removal_requests_incident_owner_admin_user_id', ['incident_owner_admin_user_id']),
        ('ix_waste_removal_requests_incident_acknowledged_at', ['incident_acknowledged_at']),
        ('ix_waste_removal_requests_incident_resolved_at', ['incident_resolved_at']),
        ('ix_waste_removal_requests_incident_updated_at', ['incident_updated_at']),
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
        'ix_waste_removal_requests_incident_updated_at',
        'ix_waste_removal_requests_incident_resolved_at',
        'ix_waste_removal_requests_incident_acknowledged_at',
        'ix_waste_removal_requests_incident_owner_admin_user_id',
        'ix_waste_removal_requests_incident_severity',
        'ix_waste_removal_requests_incident_state',
    ]:
        if _has_index(inspector, table_name, index_name):
            op.drop_index(index_name, table_name=table_name)

    fk_name = 'fk_waste_removal_requests_incident_owner_admin_user_id_users'
    if _has_fk_name(inspector, table_name, fk_name):
        op.drop_constraint(fk_name, table_name, type_='foreignkey')

    inspector = sa.inspect(bind)
    for column_name in [
        'incident_updated_at',
        'incident_notes',
        'incident_resolved_at',
        'incident_acknowledged_at',
        'incident_owner_admin_user_id',
        'incident_severity',
        'incident_state',
    ]:
        if _has_column(inspector, table_name, column_name):
            op.drop_column(table_name, column_name)
        inspector = sa.inspect(bind)
