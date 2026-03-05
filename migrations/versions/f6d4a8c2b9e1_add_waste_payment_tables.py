"""Add waste payment charge/refund/payout tables.

Revision ID: f6d4a8c2b9e1
Revises: 7b9e1f2a4c6d
Create Date: 2026-02-28 10:40:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6d4a8c2b9e1'
down_revision = '7b9e1f2a4c6d'
branch_labels = None
depends_on = None


def _has_table(inspector, table_name):
    return table_name in inspector.get_table_names()


def _has_index(inspector, table_name, index_name):
    return any(index.get('name') == index_name for index in inspector.get_indexes(table_name))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    charges_table = 'waste_payment_charges'
    if not _has_table(inspector, charges_table):
        op.create_table(
            charges_table,
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('waste_removal_request_id', sa.Integer(), nullable=False),
            sa.Column('customer_user_id', sa.Integer(), nullable=True),
            sa.Column('processor', sa.String(length=32), nullable=False, server_default='stripe'),
            sa.Column('payment_intent_id', sa.String(length=120), nullable=True),
            sa.Column('charge_id', sa.String(length=120), nullable=True),
            sa.Column('amount_minor', sa.Integer(), nullable=False),
            sa.Column('currency', sa.String(length=8), nullable=False, server_default='gbp'),
            sa.Column('platform_fee_minor', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('driver_payout_minor', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('status', sa.String(length=32), nullable=False, server_default='initiated'),
            sa.Column('client_secret', sa.String(length=255), nullable=True),
            sa.Column('last_error', sa.Text(), nullable=True),
            sa.Column('paid_at', sa.DateTime(), nullable=True),
            sa.Column('refunded_at', sa.DateTime(), nullable=True),
            sa.Column('metadata_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column('processor_response', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['waste_removal_request_id'], ['waste_removal_requests.id']),
            sa.ForeignKeyConstraint(['customer_user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    inspector = sa.inspect(bind)
    if _has_table(inspector, charges_table):
        if not _has_index(inspector, charges_table, 'ix_waste_payment_charges_waste_removal_request_id'):
            op.create_index(
                'ix_waste_payment_charges_waste_removal_request_id',
                charges_table,
                ['waste_removal_request_id'],
                unique=False,
            )
        if not _has_index(inspector, charges_table, 'ix_waste_payment_charges_customer_user_id'):
            op.create_index(
                'ix_waste_payment_charges_customer_user_id',
                charges_table,
                ['customer_user_id'],
                unique=False,
            )
        if not _has_index(inspector, charges_table, 'ix_waste_payment_charges_payment_intent_id'):
            op.create_index(
                'ix_waste_payment_charges_payment_intent_id',
                charges_table,
                ['payment_intent_id'],
                unique=True,
            )
        if not _has_index(inspector, charges_table, 'ix_waste_payment_charges_charge_id'):
            op.create_index(
                'ix_waste_payment_charges_charge_id',
                charges_table,
                ['charge_id'],
                unique=False,
            )
        if not _has_index(inspector, charges_table, 'ix_waste_payment_charges_status'):
            op.create_index(
                'ix_waste_payment_charges_status',
                charges_table,
                ['status'],
                unique=False,
            )

    refunds_table = 'waste_payment_refunds'
    if not _has_table(inspector, refunds_table):
        op.create_table(
            refunds_table,
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('waste_removal_request_id', sa.Integer(), nullable=False),
            sa.Column('payment_charge_id', sa.Integer(), nullable=False),
            sa.Column('processor', sa.String(length=32), nullable=False, server_default='stripe'),
            sa.Column('refund_id', sa.String(length=120), nullable=True),
            sa.Column('amount_minor', sa.Integer(), nullable=False),
            sa.Column('currency', sa.String(length=8), nullable=False, server_default='gbp'),
            sa.Column('status', sa.String(length=32), nullable=False, server_default='pending'),
            sa.Column('reason', sa.String(length=120), nullable=True),
            sa.Column('processor_response', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['waste_removal_request_id'], ['waste_removal_requests.id']),
            sa.ForeignKeyConstraint(['payment_charge_id'], ['waste_payment_charges.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    inspector = sa.inspect(bind)
    if _has_table(inspector, refunds_table):
        if not _has_index(inspector, refunds_table, 'ix_waste_payment_refunds_waste_removal_request_id'):
            op.create_index(
                'ix_waste_payment_refunds_waste_removal_request_id',
                refunds_table,
                ['waste_removal_request_id'],
                unique=False,
            )
        if not _has_index(inspector, refunds_table, 'ix_waste_payment_refunds_payment_charge_id'):
            op.create_index(
                'ix_waste_payment_refunds_payment_charge_id',
                refunds_table,
                ['payment_charge_id'],
                unique=False,
            )
        if not _has_index(inspector, refunds_table, 'ix_waste_payment_refunds_refund_id'):
            op.create_index(
                'ix_waste_payment_refunds_refund_id',
                refunds_table,
                ['refund_id'],
                unique=True,
            )
        if not _has_index(inspector, refunds_table, 'ix_waste_payment_refunds_status'):
            op.create_index(
                'ix_waste_payment_refunds_status',
                refunds_table,
                ['status'],
                unique=False,
            )

    payouts_table = 'waste_driver_payouts'
    if not _has_table(inspector, payouts_table):
        op.create_table(
            payouts_table,
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('waste_removal_request_id', sa.Integer(), nullable=False),
            sa.Column('payment_charge_id', sa.Integer(), nullable=False),
            sa.Column('driver_user_id', sa.Integer(), nullable=False),
            sa.Column('processor', sa.String(length=32), nullable=False, server_default='stripe'),
            sa.Column('payout_id', sa.String(length=120), nullable=True),
            sa.Column('destination_account_id', sa.String(length=120), nullable=True),
            sa.Column('amount_minor', sa.Integer(), nullable=False),
            sa.Column('currency', sa.String(length=8), nullable=False, server_default='gbp'),
            sa.Column('status', sa.String(length=32), nullable=False, server_default='scheduled'),
            sa.Column('paid_out_at', sa.DateTime(), nullable=True),
            sa.Column('processor_response', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
            sa.ForeignKeyConstraint(['waste_removal_request_id'], ['waste_removal_requests.id']),
            sa.ForeignKeyConstraint(['payment_charge_id'], ['waste_payment_charges.id']),
            sa.ForeignKeyConstraint(['driver_user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )

    inspector = sa.inspect(bind)
    if _has_table(inspector, payouts_table):
        if not _has_index(inspector, payouts_table, 'ix_waste_driver_payouts_waste_removal_request_id'):
            op.create_index(
                'ix_waste_driver_payouts_waste_removal_request_id',
                payouts_table,
                ['waste_removal_request_id'],
                unique=False,
            )
        if not _has_index(inspector, payouts_table, 'ix_waste_driver_payouts_payment_charge_id'):
            op.create_index(
                'ix_waste_driver_payouts_payment_charge_id',
                payouts_table,
                ['payment_charge_id'],
                unique=False,
            )
        if not _has_index(inspector, payouts_table, 'ix_waste_driver_payouts_driver_user_id'):
            op.create_index(
                'ix_waste_driver_payouts_driver_user_id',
                payouts_table,
                ['driver_user_id'],
                unique=False,
            )
        if not _has_index(inspector, payouts_table, 'ix_waste_driver_payouts_payout_id'):
            op.create_index(
                'ix_waste_driver_payouts_payout_id',
                payouts_table,
                ['payout_id'],
                unique=True,
            )
        if not _has_index(inspector, payouts_table, 'ix_waste_driver_payouts_destination_account_id'):
            op.create_index(
                'ix_waste_driver_payouts_destination_account_id',
                payouts_table,
                ['destination_account_id'],
                unique=False,
            )
        if not _has_index(inspector, payouts_table, 'ix_waste_driver_payouts_status'):
            op.create_index(
                'ix_waste_driver_payouts_status',
                payouts_table,
                ['status'],
                unique=False,
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    payouts_table = 'waste_driver_payouts'
    if _has_table(inspector, payouts_table):
        if _has_index(inspector, payouts_table, 'ix_waste_driver_payouts_status'):
            op.drop_index('ix_waste_driver_payouts_status', table_name=payouts_table)
        if _has_index(inspector, payouts_table, 'ix_waste_driver_payouts_destination_account_id'):
            op.drop_index('ix_waste_driver_payouts_destination_account_id', table_name=payouts_table)
        if _has_index(inspector, payouts_table, 'ix_waste_driver_payouts_payout_id'):
            op.drop_index('ix_waste_driver_payouts_payout_id', table_name=payouts_table)
        if _has_index(inspector, payouts_table, 'ix_waste_driver_payouts_driver_user_id'):
            op.drop_index('ix_waste_driver_payouts_driver_user_id', table_name=payouts_table)
        if _has_index(inspector, payouts_table, 'ix_waste_driver_payouts_payment_charge_id'):
            op.drop_index('ix_waste_driver_payouts_payment_charge_id', table_name=payouts_table)
        if _has_index(inspector, payouts_table, 'ix_waste_driver_payouts_waste_removal_request_id'):
            op.drop_index('ix_waste_driver_payouts_waste_removal_request_id', table_name=payouts_table)
        op.drop_table(payouts_table)

    inspector = sa.inspect(bind)
    refunds_table = 'waste_payment_refunds'
    if _has_table(inspector, refunds_table):
        if _has_index(inspector, refunds_table, 'ix_waste_payment_refunds_status'):
            op.drop_index('ix_waste_payment_refunds_status', table_name=refunds_table)
        if _has_index(inspector, refunds_table, 'ix_waste_payment_refunds_refund_id'):
            op.drop_index('ix_waste_payment_refunds_refund_id', table_name=refunds_table)
        if _has_index(inspector, refunds_table, 'ix_waste_payment_refunds_payment_charge_id'):
            op.drop_index('ix_waste_payment_refunds_payment_charge_id', table_name=refunds_table)
        if _has_index(inspector, refunds_table, 'ix_waste_payment_refunds_waste_removal_request_id'):
            op.drop_index('ix_waste_payment_refunds_waste_removal_request_id', table_name=refunds_table)
        op.drop_table(refunds_table)

    inspector = sa.inspect(bind)
    charges_table = 'waste_payment_charges'
    if _has_table(inspector, charges_table):
        if _has_index(inspector, charges_table, 'ix_waste_payment_charges_status'):
            op.drop_index('ix_waste_payment_charges_status', table_name=charges_table)
        if _has_index(inspector, charges_table, 'ix_waste_payment_charges_charge_id'):
            op.drop_index('ix_waste_payment_charges_charge_id', table_name=charges_table)
        if _has_index(inspector, charges_table, 'ix_waste_payment_charges_payment_intent_id'):
            op.drop_index('ix_waste_payment_charges_payment_intent_id', table_name=charges_table)
        if _has_index(inspector, charges_table, 'ix_waste_payment_charges_customer_user_id'):
            op.drop_index('ix_waste_payment_charges_customer_user_id', table_name=charges_table)
        if _has_index(inspector, charges_table, 'ix_waste_payment_charges_waste_removal_request_id'):
            op.drop_index('ix_waste_payment_charges_waste_removal_request_id', table_name=charges_table)
        op.drop_table(charges_table)
