"""Add user role and waste mobile tables.

Revision ID: 5adbb35bb9f8
Revises: 23bbc60852fa
Create Date: 2026-02-21 11:35:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5adbb35bb9f8'
down_revision = '23bbc60852fa'
branch_labels = None
depends_on = None


def _has_index(inspector, table_name, index_name):
    return any(index.get('name') == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if 'users' not in table_names:
        op.create_table(
            'users',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('email', sa.String(length=255), nullable=False),
            sa.Column('password_hash', sa.String(length=255), nullable=False),
            sa.Column('name', sa.String(length=120), nullable=True),
            sa.Column('role', sa.String(length=32), nullable=False, server_default='customer'),
            sa.Column('is_active_user', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_users_email', 'users', ['email'], unique=True)
        table_names.add('users')
    else:
        user_columns = {column['name'] for column in inspector.get_columns('users')}
        if 'role' not in user_columns:
            op.add_column(
                'users',
                sa.Column('role', sa.String(length=32), nullable=False, server_default='customer'),
            )
        if 'is_active_user' not in user_columns:
            op.add_column(
                'users',
                sa.Column('is_active_user', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            )
        if not _has_index(inspector, 'users', 'ix_users_email'):
            op.create_index('ix_users_email', 'users', ['email'], unique=True)

    if 'waste_removal_requests' not in table_names:
        op.create_table(
            'waste_removal_requests',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('requester_name', sa.String(length=120), nullable=False),
            sa.Column('requester_email', sa.String(length=255), nullable=False),
            sa.Column('material_type', sa.String(length=120), nullable=False),
            sa.Column('waste_amount', sa.Float(), nullable=False),
            sa.Column('waste_unit', sa.String(length=32), nullable=False),
            sa.Column('pickup_address', sa.String(length=255), nullable=False),
            sa.Column('pickup_city', sa.String(length=120), nullable=True),
            sa.Column('pickup_county', sa.String(length=120), nullable=True),
            sa.Column('pickup_postcode', sa.String(length=32), nullable=False),
            sa.Column('scheduled_pickup_at', sa.DateTime(), nullable=False),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.PrimaryKeyConstraint('id'),
        )
        table_names.add('waste_removal_requests')

    if 'waste_removal_matches' not in table_names:
        op.create_table(
            'waste_removal_matches',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('waste_removal_request_id', sa.Integer(), nullable=False),
            sa.Column('provider_name', sa.String(length=255), nullable=False),
            sa.Column('provider_type', sa.String(length=120), nullable=True),
            sa.Column('provider_city', sa.String(length=120), nullable=True),
            sa.Column('provider_postcode', sa.String(length=32), nullable=True),
            sa.Column('provider_latitude', sa.Float(), nullable=False),
            sa.Column('provider_longitude', sa.Float(), nullable=False),
            sa.Column('distance_miles', sa.Float(), nullable=False),
            sa.Column('match_radius_miles', sa.Float(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(
                ['waste_removal_request_id'],
                ['waste_removal_requests.id'],
            ),
            sa.PrimaryKeyConstraint('id'),
        )
        table_names.add('waste_removal_matches')
    if not _has_index(
        inspector,
        'waste_removal_matches',
        'ix_waste_removal_matches_waste_removal_request_id',
    ):
        op.create_index(
            'ix_waste_removal_matches_waste_removal_request_id',
            'waste_removal_matches',
            ['waste_removal_request_id'],
            unique=False,
        )

    if 'waste_removal_vehicle_locations' not in table_names:
        op.create_table(
            'waste_removal_vehicle_locations',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('waste_removal_request_id', sa.Integer(), nullable=False),
            sa.Column('driver_id', sa.String(length=120), nullable=True),
            sa.Column('vehicle_id', sa.String(length=120), nullable=True),
            sa.Column('latitude', sa.Float(), nullable=False),
            sa.Column('longitude', sa.Float(), nullable=False),
            sa.Column('recorded_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('source', sa.String(length=32), nullable=False, server_default='mobile'),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(
                ['waste_removal_request_id'],
                ['waste_removal_requests.id'],
            ),
            sa.PrimaryKeyConstraint('id'),
        )
        table_names.add('waste_removal_vehicle_locations')
    if not _has_index(
        inspector,
        'waste_removal_vehicle_locations',
        'ix_waste_removal_vehicle_locations_waste_removal_request_id',
    ):
        op.create_index(
            'ix_waste_removal_vehicle_locations_waste_removal_request_id',
            'waste_removal_vehicle_locations',
            ['waste_removal_request_id'],
            unique=False,
        )
    if not _has_index(
        inspector,
        'waste_removal_vehicle_locations',
        'ix_waste_removal_vehicle_locations_recorded_at',
    ):
        op.create_index(
            'ix_waste_removal_vehicle_locations_recorded_at',
            'waste_removal_vehicle_locations',
            ['recorded_at'],
            unique=False,
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if 'waste_removal_vehicle_locations' in table_names:
        if _has_index(
            inspector,
            'waste_removal_vehicle_locations',
            'ix_waste_removal_vehicle_locations_recorded_at',
        ):
            op.drop_index(
                'ix_waste_removal_vehicle_locations_recorded_at',
                table_name='waste_removal_vehicle_locations',
            )
        if _has_index(
            inspector,
            'waste_removal_vehicle_locations',
            'ix_waste_removal_vehicle_locations_waste_removal_request_id',
        ):
            op.drop_index(
                'ix_waste_removal_vehicle_locations_waste_removal_request_id',
                table_name='waste_removal_vehicle_locations',
            )
        op.drop_table('waste_removal_vehicle_locations')

    if 'waste_removal_matches' in table_names:
        if _has_index(
            inspector,
            'waste_removal_matches',
            'ix_waste_removal_matches_waste_removal_request_id',
        ):
            op.drop_index(
                'ix_waste_removal_matches_waste_removal_request_id',
                table_name='waste_removal_matches',
            )
        op.drop_table('waste_removal_matches')

    if 'waste_removal_requests' in table_names:
        op.drop_table('waste_removal_requests')

    if 'users' in table_names:
        user_columns = {column['name'] for column in inspector.get_columns('users')}
        if 'role' in user_columns:
            op.drop_column('users', 'role')
