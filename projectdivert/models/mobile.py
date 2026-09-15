"""Mobile models."""

from datetime import datetime
from projectdivert.extensions import db


class MobilePushSubscription(db.Model):
    __tablename__ = 'mobile_push_subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=False,
        index=True,
    )
    provider = db.Column(db.String(32), nullable=False, default='expo')
    token = db.Column(db.String(255), nullable=False, unique=True, index=True)
    platform = db.Column(db.String(32))
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self):
        return '<MobilePushSubscription user_id={} provider={} active={}>'.format(
            self.user_id,
            self.provider,
            self.is_active,
        )
