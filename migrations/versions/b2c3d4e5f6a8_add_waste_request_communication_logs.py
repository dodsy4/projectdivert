"""Add waste request communication logs table.

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-03-12 22:55:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a8'
down_revision = 'a1b2c3d4e5f7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'waste_request_communication_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('waste_removal_request_id', sa.Integer(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('direction', sa.String(length=32), nullable=False),
        sa.Column('channel', sa.String(length=32), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('outcome', sa.String(length=120), nullable=True),
        sa.Column('contact_name', sa.String(length=120), nullable=True),
        sa.Column('contact_email', sa.String(length=255), nullable=True),
        sa.Column('contact_phone', sa.String(length=120), nullable=True),
        sa.Column('customer_visible', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['waste_removal_request_id'], ['waste_removal_requests.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_waste_request_communication_logs_waste_removal_request_id',
        'waste_request_communication_logs',
        ['waste_removal_request_id'],
        unique=False,
    )
    op.create_index(
        'ix_waste_request_communication_logs_created_by_user_id',
        'waste_request_communication_logs',
        ['created_by_user_id'],
        unique=False,
    )
    op.create_index(
        'ix_waste_request_communication_logs_direction',
        'waste_request_communication_logs',
        ['direction'],
        unique=False,
    )
    op.create_index(
        'ix_waste_request_communication_logs_channel',
        'waste_request_communication_logs',
        ['channel'],
        unique=False,
    )
    op.create_index(
        'ix_waste_request_communication_logs_customer_visible',
        'waste_request_communication_logs',
        ['customer_visible'],
        unique=False,
    )
    op.create_index(
        'ix_waste_request_communication_logs_occurred_at',
        'waste_request_communication_logs',
        ['occurred_at'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_waste_request_communication_logs_occurred_at', table_name='waste_request_communication_logs')
    op.drop_index('ix_waste_request_communication_logs_customer_visible', table_name='waste_request_communication_logs')
    op.drop_index('ix_waste_request_communication_logs_channel', table_name='waste_request_communication_logs')
    op.drop_index('ix_waste_request_communication_logs_direction', table_name='waste_request_communication_logs')
    op.drop_index('ix_waste_request_communication_logs_created_by_user_id', table_name='waste_request_communication_logs')
    op.drop_index('ix_waste_request_communication_logs_waste_removal_request_id', table_name='waste_request_communication_logs')
    op.drop_table('waste_request_communication_logs')
