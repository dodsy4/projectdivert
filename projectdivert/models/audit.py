"""Audit models."""

from datetime import datetime
from projectdivert.extensions import db


class AuthAuditEvent(db.Model):
    __tablename__ = 'auth_audit_events'

    id = db.Column(db.Integer, primary_key=True)
    event = db.Column(db.String(64), nullable=False, index=True)
    success = db.Column(db.Boolean, nullable=False, index=True)
    status_code = db.Column(db.Integer, nullable=False, index=True)
    email = db.Column(db.String(255), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    ip = db.Column(db.String(64), index=True)
    user_agent = db.Column(db.String(255))
    details_json = db.Column(db.JSON, nullable=False, default=dict)
    occurred_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    def __repr__(self):
        return '<AuthAuditEvent event={} success={} user_id={}>'.format(
            self.event,
            self.success,
            self.user_id,
        )


class AuditEvent(db.Model):
    """Application-wide audit trail.

    Every state-changing request writes one row here (see ``record_audit_event``
    and the ``after_request`` hook). ``AuthAuditEvent`` remains the dedicated
    store for authentication events; this table is the superset for everything
    else (dispatch, payments, compliance, marketplace, admin actions).
    """

    __tablename__ = 'audit_events'

    id = db.Column(db.Integer, primary_key=True)
    occurred_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    entity_type = db.Column(db.String(64), index=True)
    entity_id = db.Column(db.String(64), index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    actor_role = db.Column(db.String(32), index=True)
    actor_email = db.Column(db.String(255), index=True)
    actor_ip = db.Column(db.String(64))
    user_agent = db.Column(db.String(255))
    source = db.Column(db.String(16), nullable=False, default='web', index=True)
    http_method = db.Column(db.String(8))
    path = db.Column(db.String(255))
    status_code = db.Column(db.Integer, index=True)
    request_id = db.Column(db.String(32), index=True)
    summary = db.Column(db.String(255))
    changes = db.Column(db.JSON, nullable=False, default=dict)

    __table_args__ = (
        db.Index('ix_audit_events_entity', 'entity_type', 'entity_id'),
    )

    def __repr__(self):
        return '<AuditEvent action={} entity={}:{} actor={}>'.format(
            self.action,
            self.entity_type,
            self.entity_id,
            self.actor_user_id,
        )
