"""Payments models."""

from datetime import datetime
from projectdivert.extensions import db


class WastePaymentCharge(db.Model):
    __tablename__ = 'waste_payment_charges'

    id = db.Column(db.Integer, primary_key=True)
    waste_removal_request_id = db.Column(
        db.Integer,
        db.ForeignKey('waste_removal_requests.id'),
        nullable=False,
        index=True,
    )
    customer_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        index=True,
    )
    processor = db.Column(db.String(32), nullable=False, default='stripe')
    payment_intent_id = db.Column(db.String(120), unique=True, index=True)
    charge_id = db.Column(db.String(120), index=True)
    amount_minor = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(8), nullable=False, default='gbp')
    platform_fee_minor = db.Column(db.Integer, nullable=False, default=0)
    driver_payout_minor = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(32), nullable=False, default='initiated', index=True)
    client_secret = db.Column(db.String(255))
    last_error = db.Column(db.Text)
    paid_at = db.Column(db.DateTime)
    refunded_at = db.Column(db.DateTime)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    processor_response = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self):
        return '<WastePaymentCharge request={} amount_minor={} status={}>'.format(
            self.waste_removal_request_id,
            self.amount_minor,
            self.status,
        )


class WastePaymentRefund(db.Model):
    __tablename__ = 'waste_payment_refunds'

    id = db.Column(db.Integer, primary_key=True)
    waste_removal_request_id = db.Column(
        db.Integer,
        db.ForeignKey('waste_removal_requests.id'),
        nullable=False,
        index=True,
    )
    payment_charge_id = db.Column(
        db.Integer,
        db.ForeignKey('waste_payment_charges.id'),
        nullable=False,
        index=True,
    )
    processor = db.Column(db.String(32), nullable=False, default='stripe')
    refund_id = db.Column(db.String(120), unique=True, index=True)
    amount_minor = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(8), nullable=False, default='gbp')
    status = db.Column(db.String(32), nullable=False, default='pending', index=True)
    reason = db.Column(db.String(120))
    processor_response = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self):
        return '<WastePaymentRefund request={} amount_minor={} status={}>'.format(
            self.waste_removal_request_id,
            self.amount_minor,
            self.status,
        )


class WasteDriverPayout(db.Model):
    __tablename__ = 'waste_driver_payouts'

    id = db.Column(db.Integer, primary_key=True)
    waste_removal_request_id = db.Column(
        db.Integer,
        db.ForeignKey('waste_removal_requests.id'),
        nullable=False,
        index=True,
    )
    payment_charge_id = db.Column(
        db.Integer,
        db.ForeignKey('waste_payment_charges.id'),
        nullable=False,
        index=True,
    )
    driver_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=False,
        index=True,
    )
    processor = db.Column(db.String(32), nullable=False, default='stripe')
    payout_id = db.Column(db.String(120), unique=True, index=True)
    destination_account_id = db.Column(db.String(120), index=True)
    amount_minor = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(8), nullable=False, default='gbp')
    status = db.Column(db.String(32), nullable=False, default='scheduled', index=True)
    paid_out_at = db.Column(db.DateTime)
    processor_response = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self):
        return '<WasteDriverPayout request={} amount_minor={} status={}>'.format(
            self.waste_removal_request_id,
            self.amount_minor,
            self.status,
        )
