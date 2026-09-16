"""Add phone and WhatsApp linkage to users

Revision ID: f2a4b6c8d0e1
Revises: e7f8a9b0c1d2
Create Date: 2026-09-16

The WhatsApp assistant resolves an inbound message to an account by phone
number, so the column is unique and indexed.
"""

from alembic import op
import sqlalchemy as sa

revision = 'f2a4b6c8d0e1'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('phone', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('whatsapp_linked_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_users_phone', ['phone'], unique=True)
        batch_op.create_index('ix_users_whatsapp_linked_at', ['whatsapp_linked_at'], unique=False)


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_index('ix_users_whatsapp_linked_at')
        batch_op.drop_index('ix_users_phone')
        batch_op.drop_column('whatsapp_linked_at')
        batch_op.drop_column('phone')
