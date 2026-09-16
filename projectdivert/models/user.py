"""User models."""

from flask_login import UserMixin
from projectdivert.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120))
    role = db.Column(db.String(32), nullable=False, default='customer')
    is_active_user = db.Column(db.Boolean, nullable=False, default=True)
    # WhatsApp linkage: the assistant resolves an inbound message to an account
    # by this number, so it is unique and indexed.
    phone = db.Column(db.String(32), unique=True, index=True)
    whatsapp_linked_at = db.Column(db.DateTime, index=True)
    email_verified_at = db.Column(db.DateTime, index=True)
    access_token_revoked_at = db.Column(db.DateTime, index=True)
    carrier_company_id = db.Column(
        db.Integer,
        db.ForeignKey('carrier_companies.id'),
        index=True,
    )

    def __repr__(self):
        return '<User {}>'.format(self.email)

    @property
    def is_active(self):
        return self.is_active_user
