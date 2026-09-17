"""Auth models."""

from projectdivert.extensions import db
from projectdivert.services.utils import utcnow


class AuthLifecycleToken(db.Model):
    __tablename__ = 'auth_lifecycle_tokens'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=False,
        index=True,
    )
    token_id = db.Column(db.String(64), nullable=False, unique=True, index=True)
    token_type = db.Column(db.String(32), nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    used_at = db.Column(db.DateTime, index=True)
    revoked_at = db.Column(db.DateTime, index=True)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    def __repr__(self):
        return '<AuthLifecycleToken user={} type={} token_id={}>'.format(
            self.user_id,
            self.token_type,
            self.token_id,
        )


class AuthSecurityBlocklist(db.Model):
    __tablename__ = 'auth_security_blocklist'

    id = db.Column(db.Integer, primary_key=True)
    identifier_type = db.Column(db.String(16), nullable=False, index=True)
    identifier_value = db.Column(db.String(255), nullable=False, index=True)
    reason = db.Column(db.String(255))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    expires_at = db.Column(db.DateTime, index=True)
    revoked_at = db.Column(db.DateTime, index=True)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    def __repr__(self):
        return '<AuthSecurityBlocklist type={} value={} id={}>'.format(
            self.identifier_type,
            self.identifier_value,
            self.id,
        )
