"""Add waste dispatch offers table.

Revision ID: 9f0d5d71d7b3
Revises: c2f8f5664d13
Create Date: 2026-02-27 13:10:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9f0d5d71d7b3'
down_revision = 'c2f8f5664d13'
branch_labels = None
depends_on = None


def _has_index(inspector, table_name, index_name):
    return any(index.get('name') == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if 'waste_removal_dispatch_offers' not in table_names:
        op.create_table(
            'waste_removal_dispatch_offers',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('waste_removal_request_id', sa.Integer(), nullable=False),
            sa.Column('provider_name', sa.String(length=255), nullable=False),
            sa.Column('provider_type', sa.String(length=120), nullable=True),
            sa.Column('provider_city', sa.String(length=120), nullable=True),
            sa.Column('provider_postcode', sa.String(length=32), nullable=True),
            sa.Column('provider_latitude', sa.Float(), nullable=False),
            sa.Column('provider_longitude', sa.Float(), nullable=False),
            sa.Column('provider_email', sa.String(length=255), nullable=True),
            sa.Column('provider_phone', sa.String(length=120), nullable=True),
            sa.Column('distance_miles', sa.Float(), nullable=False),
            sa.Column('match_radius_miles', sa.Float(), nullable=False),
            sa.Column('offer_rank', sa.Integer(), nullable=False),
            sa.Column('offer_token', sa.String(length=64), nullable=False),
            sa.Column('status', sa.String(length=32), nullable=False, server_default='offered'),
            sa.Column('notified_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('responded_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(
                ['waste_removal_request_id'],
                ['waste_removal_requests.id'],
            ),
            sa.PrimaryKeyConstraint('id'),
        )
        table_names.add('waste_removal_dispatch_offers')

    if not _has_index(
        inspector,
        'waste_removal_dispatch_offers',
        'ix_waste_removal_dispatch_offers_waste_removal_request_id',
    ):
        op.create_index(
            'ix_waste_removal_dispatch_offers_waste_removal_request_id',
            'waste_removal_dispatch_offers',
            ['waste_removal_request_id'],
            unique=False,
        )

    if not _has_index(
        inspector,
        'waste_removal_dispatch_offers',
        'ix_waste_removal_dispatch_offers_offer_token',
    ):
        op.create_index(
            'ix_waste_removal_dispatch_offers_offer_token',
            'waste_removal_dispatch_offers',
            ['offer_token'],
            unique=True,
        )

    if not _has_index(
        inspector,
        'waste_removal_dispatch_offers',
        'ix_waste_removal_dispatch_offers_status',
    ):
        op.create_index(
            'ix_waste_removal_dispatch_offers_status',
            'waste_removal_dispatch_offers',
            ['status'],
            unique=False,
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if 'waste_removal_dispatch_offers' in table_names:
        if _has_index(
            inspector,
            'waste_removal_dispatch_offers',
            'ix_waste_removal_dispatch_offers_status',
        ):
            op.drop_index(
                'ix_waste_removal_dispatch_offers_status',
                table_name='waste_removal_dispatch_offers',
            )
        if _has_index(
            inspector,
            'waste_removal_dispatch_offers',
            'ix_waste_removal_dispatch_offers_offer_token',
        ):
            op.drop_index(
                'ix_waste_removal_dispatch_offers_offer_token',
                table_name='waste_removal_dispatch_offers',
            )
        if _has_index(
            inspector,
            'waste_removal_dispatch_offers',
            'ix_waste_removal_dispatch_offers_waste_removal_request_id',
        ):
            op.drop_index(
                'ix_waste_removal_dispatch_offers_waste_removal_request_id',
                table_name='waste_removal_dispatch_offers',
            )
        op.drop_table('waste_removal_dispatch_offers')
