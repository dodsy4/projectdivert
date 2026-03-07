#----------------------------------------------------------------------------#
# Imports
#----------------------------------------------------------------------------#
import sys
import json
import os
import io
import csv
import uuid
import hmac
import hashlib
import queue
import threading
from collections import deque
from datetime import datetime, timedelta, timezone
from functools import wraps
import dateutil.parser
import babel
import jwt
import requests
import click
import pandas as pd
try:
    import redis
except Exception:  # pragma: no cover - optional dependency
    redis = None
from flask import Flask, Response, g, jsonify, render_template, request, flash, redirect, stream_with_context, url_for
from flask_moment import Moment
from forms import *
import logging
from logging import Formatter, FileHandler
from sqlalchemy import and_, func, inspect, or_
from sqlalchemy.exc import SQLAlchemyError
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from project_divert_functions import *
import math
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
#----------------------------------------------------------------------------#
# App Config.
#----------------------------------------------------------------------------#
app = Flask(__name__)
app.config.from_object('config')
db = SQLAlchemy(app)
moment = Moment(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login_page'
login_manager.login_message = 'Please log in to continue.'

class c(db.Model):
    __tablename__ = 'c'

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(120))
    name = db.Column(db.String(120))
    email = db.Column(db.String(120))
    reg_num = db.Column(db.String(120))
    address1 = db.Column(db.String(120))
    city1 = db.Column(db.String(120))
    county1 = db.Column(db.String(120))
    postcode1 = db.Column(db.String(120))
    address2 = db.Column(db.String(120))
    city2 = db.Column(db.String(120))
    county2 = db.Column(db.String(120))
    postcode2 = db.Column(db.String(120))
    address3 = db.Column(db.String(120))
    city3 = db.Column(db.String(120))
    county3 = db.Column(db.String(120))
    postcode3 = db.Column(db.String(120))
    phone = db.Column(db.String(120))
    facebook_link = db.Column(db.String(120))
    linkedin_link = db.Column(db.String(120))
    website = db.Column(db.String(120))

    def __repr__(self):
        return '<Charity {}>'.format(self.name)


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120))
    role = db.Column(db.String(32), nullable=False, default='customer')
    is_active_user = db.Column(db.Boolean, nullable=False, default=True)
    email_verified_at = db.Column(db.DateTime, index=True)
    access_token_revoked_at = db.Column(db.DateTime, index=True)

    def __repr__(self):
        return '<User {}>'.format(self.email)

    @property
    def is_active(self):
        return self.is_active_user


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
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self):
        return '<AuthLifecycleToken user={} type={} token_id={}>'.format(
            self.user_id,
            self.token_type,
            self.token_id,
        )


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
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self):
        return '<AuthSecurityBlocklist type={} value={} id={}>'.format(
            self.identifier_type,
            self.identifier_value,
            self.id,
        )


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

class m(db.Model):
    __tablename__ = 'm'

    id = db.Column(db.Integer, primary_key=True)
    waste_stream = db.Column(db.String)
    amount = db.Column(db.Integer)
    address = db.Column(db.String(120))
    city = db.Column(db.String(120))
    county = db.Column(db.String(120))
    postcode = db.Column(db.String(120))
    condition = db.Column(db.String(120))
    dimensions = db.Column(db.String(120)) 
    image_link1 = db.Column(db.String(120))
    image_link2 = db.Column(db.String(120))
    image_link3 = db.Column(db.String(120))
    longitude = db.Column(db.Float(5))
    latitude = db.Column(db.Float(5))
    
    def __repr__(self):
        return '<Material {}>'.format(self.waste_stream)

class output(db.Model):
    __tablename__ = 'output'

    id = db.Column(db.Integer, primary_key=True)
    material = db.Column(db.String(120))
    amount = db.Column(db.String(120))
    unit = db.Column(db.String(120))
    site_address = db.Column(db.String(120))
    traditional_address = db.Column(db.String(120))
    divert_address = db.Column(db.String(120))
    traditional_cost = db.Column(db.String(120))
    divert_cost = db.Column(db.String(120))

    # TODO: implement any missing fields, as a database migration using Flask-Migrate
    def __repr__(self):
        return '<Output {}>'.format(self.material)

class r(db.Model):
    __tablename__ = 'r'
    id = db.Column(db.Integer, primary_key=True)
    mat_id = db.Column(db.Integer, nullable=False)
    e_id = db.Column(db.String(120), nullable=False)
    message = db.Column(db.String(120))

    def __repr__(self):
        return '<Request {}>'.format(self.mat_id)


class WasteRemovalRequest(db.Model):
    __tablename__ = 'waste_removal_requests'

    id = db.Column(db.Integer, primary_key=True)
    requester_name = db.Column(db.String(120), nullable=False)
    requester_email = db.Column(db.String(255), nullable=False)
    material_type = db.Column(db.String(120), nullable=False)
    waste_amount = db.Column(db.Float, nullable=False)
    waste_unit = db.Column(db.String(32), nullable=False)
    pickup_address = db.Column(db.String(255), nullable=False)
    pickup_city = db.Column(db.String(120))
    pickup_county = db.Column(db.String(120))
    pickup_postcode = db.Column(db.String(32), nullable=False)
    scheduled_pickup_at = db.Column(db.DateTime, nullable=False)
    notes = db.Column(db.Text)
    status = db.Column(db.String(32), nullable=False, default='pending')
    assigned_driver_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        index=True,
    )
    incident_state = db.Column(db.String(32), index=True)
    incident_severity = db.Column(db.String(16), index=True)
    incident_owner_admin_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        index=True,
    )
    incident_acknowledged_at = db.Column(db.DateTime, index=True)
    incident_resolved_at = db.Column(db.DateTime, index=True)
    incident_notes = db.Column(db.Text)
    incident_updated_at = db.Column(db.DateTime, index=True)
    incident_last_escalation_key = db.Column(db.String(120), index=True)
    incident_last_escalated_at = db.Column(db.DateTime, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return '<WasteRemovalRequest {} {}>'.format(self.id, self.material_type)


class WasteRemovalMatch(db.Model):
    __tablename__ = 'waste_removal_matches'

    id = db.Column(db.Integer, primary_key=True)
    waste_removal_request_id = db.Column(
        db.Integer,
        db.ForeignKey('waste_removal_requests.id'),
        nullable=False,
        index=True,
    )
    provider_name = db.Column(db.String(255), nullable=False)
    provider_type = db.Column(db.String(120))
    provider_city = db.Column(db.String(120))
    provider_postcode = db.Column(db.String(32))
    provider_latitude = db.Column(db.Float, nullable=False)
    provider_longitude = db.Column(db.Float, nullable=False)
    distance_miles = db.Column(db.Float, nullable=False)
    match_radius_miles = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return '<WasteRemovalMatch request={} provider={}>'.format(
            self.waste_removal_request_id,
            self.provider_name,
        )


class WasteRemovalDispatchOffer(db.Model):
    __tablename__ = 'waste_removal_dispatch_offers'

    id = db.Column(db.Integer, primary_key=True)
    waste_removal_request_id = db.Column(
        db.Integer,
        db.ForeignKey('waste_removal_requests.id'),
        nullable=False,
        index=True,
    )
    provider_name = db.Column(db.String(255), nullable=False)
    provider_type = db.Column(db.String(120))
    provider_city = db.Column(db.String(120))
    provider_postcode = db.Column(db.String(32))
    provider_latitude = db.Column(db.Float, nullable=False)
    provider_longitude = db.Column(db.Float, nullable=False)
    provider_email = db.Column(db.String(255))
    provider_phone = db.Column(db.String(120))
    distance_miles = db.Column(db.Float, nullable=False)
    match_radius_miles = db.Column(db.Float, nullable=False)
    offer_rank = db.Column(db.Integer, nullable=False)
    offer_token = db.Column(db.String(64), nullable=False, unique=True, index=True)
    status = db.Column(db.String(32), nullable=False, default='offered', index=True)
    notified_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return '<WasteRemovalDispatchOffer request={} provider={} status={}>'.format(
            self.waste_removal_request_id,
            self.provider_name,
            self.status,
        )


class WasteRemovalVehicleLocation(db.Model):
    __tablename__ = 'waste_removal_vehicle_locations'

    id = db.Column(db.Integer, primary_key=True)
    waste_removal_request_id = db.Column(
        db.Integer,
        db.ForeignKey('waste_removal_requests.id'),
        nullable=False,
        index=True,
    )
    driver_id = db.Column(db.String(120))
    vehicle_id = db.Column(db.String(120))
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    recorded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    source = db.Column(db.String(32), nullable=False, default='mobile')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return '<WasteRemovalVehicleLocation request={} lat={} lon={}>'.format(
            self.waste_removal_request_id,
            self.latitude,
            self.longitude,
        )


class DispatchIncidentEvent(db.Model):
    __tablename__ = 'dispatch_incident_events'

    id = db.Column(db.Integer, primary_key=True)
    waste_removal_request_id = db.Column(
        db.Integer,
        db.ForeignKey('waste_removal_requests.id'),
        nullable=False,
        index=True,
    )
    event_type = db.Column(db.String(64), nullable=False, index=True)
    actor_user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        index=True,
    )
    actor_email = db.Column(db.String(255), index=True)
    source = db.Column(db.String(64), nullable=False, default='system')
    details_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    def __repr__(self):
        return '<DispatchIncidentEvent request={} event={} actor={}>'.format(
            self.waste_removal_request_id,
            self.event_type,
            self.actor_user_id,
        )


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


class SupplierReference(db.Model):
    __tablename__ = 'supplier_reference'

    id = db.Column(db.Integer, primary_key=True)
    source_row_index = db.Column(db.Integer, nullable=False, unique=True, index=True)
    sup_type = db.Column(db.String(120), index=True)
    name = db.Column(db.String(255), index=True)
    address_street = db.Column(db.String(255))
    city = db.Column(db.String(120))
    postcode = db.Column(db.String(32), index=True)
    lat = db.Column(db.Float)
    long = db.Column(db.Float)
    website = db.Column(db.String(255))
    email = db.Column(db.String(255))
    telephone = db.Column(db.String(120))
    supplier_contact = db.Column(db.String(255))
    supplier_contact_email = db.Column(db.String(255))
    supplier_contact_telephone = db.Column(db.String(120))
    percent_recyclablenum = db.Column(db.Float)
    percent_efwnum = db.Column(db.Float)
    provides_a_rebateyn = db.Column(db.Float)
    supplier_auditislist_yes_no_na = db.Column(db.String(32))
    supplier_audit_date_completed = db.Column(db.String(64))
    notes = db.Column(db.Text)
    hierarchy = db.Column(db.String(120))
    origin = db.Column(db.String(120))
    row_data = db.Column(db.JSON, nullable=False, default=dict)

    def __repr__(self):
        return '<SupplierReference {} {}>'.format(self.id, self.name)


class SiteReference(db.Model):
    __tablename__ = 'site_reference'

    id = db.Column(db.Integer, primary_key=True)
    source_row_index = db.Column(db.Integer, nullable=False, unique=True, index=True)
    row_data = db.Column(db.JSON, nullable=False, default=dict)

    def __repr__(self):
        return '<SiteReference {}>'.format(self.id)


class DivertOutputReference(db.Model):
    __tablename__ = 'divert_output_reference'

    id = db.Column(db.Integer, primary_key=True)
    source_row_index = db.Column(db.Integer, nullable=False, unique=True, index=True)
    row_data = db.Column(db.JSON, nullable=False, default=dict)

    def __repr__(self):
        return '<DivertOutputReference {}>'.format(self.id)


class ReuseOffsetReference(db.Model):
    __tablename__ = 'reuse_offset_reference'

    id = db.Column(db.Integer, primary_key=True)
    source_row_index = db.Column(db.Integer, nullable=False, unique=True, index=True)
    material = db.Column(db.String(255), index=True)
    emission_factor = db.Column(db.Float)
    source = db.Column(db.String(255))
    explanation = db.Column(db.Text)
    row_data = db.Column(db.JSON, nullable=False, default=dict)

    def __repr__(self):
        return '<ReuseOffsetReference {}>'.format(self.material)


class RecycleOffsetReference(db.Model):
    __tablename__ = 'recycle_offset_reference'

    id = db.Column(db.Integer, primary_key=True)
    source_row_index = db.Column(db.Integer, nullable=False, unique=True, index=True)
    material = db.Column(db.String(255), index=True)
    emission_factor = db.Column(db.Float)
    source = db.Column(db.String(255))
    explanation = db.Column(db.Text)
    row_data = db.Column(db.JSON, nullable=False, default=dict)

    def __repr__(self):
        return '<RecycleOffsetReference {}>'.format(self.material)


class CarbonEquivalencyReference(db.Model):
    __tablename__ = 'carbon_equivalency_reference'

    id = db.Column(db.Integer, primary_key=True)
    source_row_index = db.Column(db.Integer, nullable=False, unique=True, index=True)
    equivalency = db.Column(db.String(255), index=True)
    emission_factor = db.Column(db.Float)
    row_data = db.Column(db.JSON, nullable=False, default=dict)

    def __repr__(self):
        return '<CarbonEquivalencyReference {}>'.format(self.equivalency)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def _jwt_secret():
    return app.config.get('JWT_SECRET_KEY') or app.config.get('SECRET_KEY')


def _jwt_exp_hours():
    value = app.config.get('JWT_EXP_HOURS', 24)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 24


def _jwt_refresh_exp_days():
    value = app.config.get('JWT_REFRESH_EXP_DAYS', 30)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 30


def _email_verification_token_exp_hours():
    value = app.config.get('EMAIL_VERIFICATION_TOKEN_EXP_HOURS', 24)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 24


def _password_reset_token_exp_minutes():
    value = app.config.get('PASSWORD_RESET_TOKEN_EXP_MINUTES', 30)
    try:
        return max(5, int(value))
    except (TypeError, ValueError):
        return 30


def _auth_verify_request_cooldown_seconds():
    value = app.config.get('AUTH_VERIFY_REQUEST_COOLDOWN_SECONDS', 60)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 60


def _auth_password_reset_request_cooldown_seconds():
    value = app.config.get('AUTH_PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS', 60)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 60


def _auth_max_active_refresh_tokens():
    value = app.config.get('AUTH_MAX_ACTIVE_REFRESH_TOKENS', 10)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 10


def _auth_blocklist_enabled():
    return _is_truthy(app.config.get('AUTH_BLOCKLIST_ENABLED', True))


def _auth_blocklist_default_duration_seconds():
    value = app.config.get('AUTH_BLOCKLIST_DEFAULT_DURATION_SECONDS', 86400)
    try:
        return max(60, int(value))
    except (TypeError, ValueError):
        return 86400


def _auth_require_email_verification():
    return _is_truthy(app.config.get('AUTH_REQUIRE_EMAIL_VERIFICATION', False))


def _auth_return_tokens_in_response():
    return _is_truthy(app.config.get('AUTH_RETURN_TOKENS_IN_RESPONSE', False))


def _auth_rate_limit_enabled():
    return _is_truthy(app.config.get('AUTH_RATE_LIMIT_ENABLED', True))


def _auth_rate_limit_admin_enabled():
    return _is_truthy(app.config.get('AUTH_RATE_LIMIT_ADMIN_ENABLED', True))


def _auth_rate_limit_window_seconds(action=''):
    value = app.config.get('AUTH_RATE_LIMIT_WINDOW_SECONDS', 300)
    try:
        return max(10, int(value))
    except (TypeError, ValueError):
        return 300


def _auth_rate_limit_redis_url():
    return str(app.config.get('AUTH_RATE_LIMIT_REDIS_URL') or '').strip()


def _auth_rate_limit_redis_prefix():
    value = str(app.config.get('AUTH_RATE_LIMIT_REDIS_PREFIX') or '').strip()
    return value or 'projectdivert:auth-rate-limit'


def _auth_rate_limit_max_attempts(action):
    config_key = {
        'login': 'AUTH_RATE_LIMIT_LOGIN_MAX_ATTEMPTS',
        'signup': 'AUTH_RATE_LIMIT_SIGNUP_MAX_ATTEMPTS',
        'refresh': 'AUTH_RATE_LIMIT_REFRESH_MAX_ATTEMPTS',
        'verify_request': 'AUTH_RATE_LIMIT_VERIFY_REQUEST_MAX_ATTEMPTS',
        'verify_confirm': 'AUTH_RATE_LIMIT_VERIFY_CONFIRM_MAX_ATTEMPTS',
        'password_reset_request': 'AUTH_RATE_LIMIT_PASSWORD_RESET_REQUEST_MAX_ATTEMPTS',
        'password_reset_confirm': 'AUTH_RATE_LIMIT_PASSWORD_RESET_CONFIRM_MAX_ATTEMPTS',
        'logout': 'AUTH_RATE_LIMIT_REFRESH_MAX_ATTEMPTS',
        'admin_api': 'AUTH_RATE_LIMIT_ADMIN_MAX_ATTEMPTS',
    }.get(action, 'AUTH_RATE_LIMIT_LOGIN_MAX_ATTEMPTS')
    value = app.config.get(config_key, 10)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 10


def _auth_login_lockout_enabled():
    return _is_truthy(app.config.get('AUTH_LOGIN_LOCKOUT_ENABLED', True))


def _auth_login_lockout_window_seconds():
    value = app.config.get('AUTH_LOGIN_LOCKOUT_WINDOW_SECONDS', 900)
    try:
        return max(60, int(value))
    except (TypeError, ValueError):
        return 900


def _auth_login_lockout_max_attempts():
    value = app.config.get('AUTH_LOGIN_LOCKOUT_MAX_ATTEMPTS', 5)
    try:
        return max(2, int(value))
    except (TypeError, ValueError):
        return 5


def _auth_login_lockout_duration_seconds():
    value = app.config.get('AUTH_LOGIN_LOCKOUT_DURATION_SECONDS', 900)
    try:
        return max(60, int(value))
    except (TypeError, ValueError):
        return 900


def _auth_login_lockout_escalation_enabled():
    return _is_truthy(app.config.get('AUTH_LOGIN_LOCKOUT_ESCALATION_ENABLED', True))


def _auth_login_lockout_escalation_factor():
    value = app.config.get('AUTH_LOGIN_LOCKOUT_ESCALATION_FACTOR', 2)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 2


def _auth_login_lockout_escalation_reset_seconds():
    value = app.config.get('AUTH_LOGIN_LOCKOUT_ESCALATION_RESET_SECONDS', 86400)
    try:
        return max(60, int(value))
    except (TypeError, ValueError):
        return 86400


def _auth_login_lockout_max_duration_seconds():
    value = app.config.get('AUTH_LOGIN_LOCKOUT_MAX_DURATION_SECONDS', 86400)
    try:
        return max(60, int(value))
    except (TypeError, ValueError):
        return 86400


def _auth_suspicious_activity_revoke_sessions_enabled():
    return _is_truthy(app.config.get('AUTH_SUSPICIOUS_ACTIVITY_REVOKE_SESSIONS', True))


def _auth_suspicious_activity_revoke_min_lockout_level():
    value = app.config.get('AUTH_SUSPICIOUS_ACTIVITY_REVOKE_MIN_LOCKOUT_LEVEL', 1)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _normalize_email(email):
    return str(email or '').strip().lower()


def _request_client_ip():
    forwarded = str(request.headers.get('X-Forwarded-For') or '').strip()
    if forwarded:
        return forwarded.split(',')[0].strip()
    real_ip = str(request.headers.get('X-Real-IP') or '').strip()
    if real_ip:
        return real_ip
    return str(request.remote_addr or '').strip() or 'unknown'


_auth_rate_limit_lock = threading.Lock()
_auth_rate_limit_events = {}
_auth_rate_limit_redis_client = None
_auth_rate_limit_redis_disabled = False
_auth_login_lockout_lock = threading.Lock()
_auth_login_lockouts = {}


def _auth_rate_limit_bucket_key(action, identifier):
    return '{}:{}:{}'.format(_auth_rate_limit_redis_prefix(), action, identifier)


def _auth_login_lockout_identifiers(email=None):
    identifiers = ['ip:{}'.format(_request_client_ip())]
    normalized_email = _normalize_email(email)
    if normalized_email:
        identifiers.append('email:{}'.format(normalized_email))
    return identifiers


def _auth_login_lockout_retry_after(identifier):
    if not _auth_login_lockout_enabled():
        return 0

    now = datetime.utcnow()
    window_seconds = _auth_login_lockout_window_seconds()
    bucket = str(identifier or '').strip()
    if not bucket:
        return 0

    with _auth_login_lockout_lock:
        state = _auth_login_lockouts.get(bucket)
        if not state:
            return 0

        locked_until = state.get('locked_until')
        if locked_until and locked_until > now:
            return max(1, int((locked_until - now).total_seconds()))

        first_failed_at = state.get('first_failed_at')
        if first_failed_at and (now - first_failed_at).total_seconds() > window_seconds:
            _auth_login_lockouts.pop(bucket, None)
            return 0

        if not locked_until:
            return 0
        if locked_until <= now:
            state['count'] = 0
            state['first_failed_at'] = None
            state['locked_until'] = None
            _auth_login_lockouts[bucket] = state
            return 0
        return 0


def _auth_login_lockout_level(identifier):
    bucket = str(identifier or '').strip()
    if not bucket:
        return 0
    with _auth_login_lockout_lock:
        state = _auth_login_lockouts.get(bucket) or {}
        try:
            return max(0, int(state.get('lockout_level') or 0))
        except (TypeError, ValueError):
            return 0


def _record_auth_login_failure(identifier):
    if not _auth_login_lockout_enabled():
        return 0

    now = datetime.utcnow()
    window_seconds = _auth_login_lockout_window_seconds()
    max_attempts = _auth_login_lockout_max_attempts()
    lockout_seconds = _auth_login_lockout_duration_seconds()
    bucket = str(identifier or '').strip()
    if not bucket:
        return 0

    with _auth_login_lockout_lock:
        state = _auth_login_lockouts.get(bucket) or {
            'count': 0,
            'first_failed_at': None,
            'locked_until': None,
            'lockout_level': 0,
            'last_lockout_at': None,
        }
        first_failed_at = state.get('first_failed_at')
        locked_until = state.get('locked_until')

        if locked_until and locked_until > now:
            return max(1, int((locked_until - now).total_seconds()))

        if not first_failed_at or (now - first_failed_at).total_seconds() > window_seconds:
            state['count'] = 1
            state['first_failed_at'] = now
            state['locked_until'] = None
        else:
            state['count'] = int(state.get('count') or 0) + 1

        retry_after = 0
        if state['count'] >= max_attempts:
            lockout_level = 1
            if _auth_login_lockout_escalation_enabled():
                last_lockout_at = state.get('last_lockout_at')
                reset_seconds = _auth_login_lockout_escalation_reset_seconds()
                previous_level = max(0, _to_int_or_none(state.get('lockout_level')) or 0)
                if (
                    isinstance(last_lockout_at, datetime)
                    and (now - last_lockout_at).total_seconds() <= reset_seconds
                ):
                    lockout_level = previous_level + 1
                else:
                    lockout_level = 1

            factor = _auth_login_lockout_escalation_factor()
            if lockout_level <= 1:
                duration_seconds = lockout_seconds
            else:
                duration_seconds = lockout_seconds * (factor ** (lockout_level - 1))
            duration_seconds = min(duration_seconds, _auth_login_lockout_max_duration_seconds())
            duration_seconds = max(60, int(duration_seconds))

            state['lockout_level'] = lockout_level
            state['last_lockout_at'] = now
            state['locked_until'] = now + timedelta(seconds=duration_seconds)
            retry_after = duration_seconds

        _auth_login_lockouts[bucket] = state
        return retry_after


def _clear_auth_login_failure(identifier):
    bucket = str(identifier or '').strip()
    if not bucket:
        return
    with _auth_login_lockout_lock:
        _auth_login_lockouts.pop(bucket, None)


def _auth_login_lockout_response(email=None):
    retry_after = 0
    for identifier in _auth_login_lockout_identifiers(email=email):
        retry_after = max(retry_after, _auth_login_lockout_retry_after(identifier))

    if retry_after <= 0:
        return None

    response = jsonify({'error': 'Too many failed login attempts. Please try again later.'})
    response.status_code = 429
    response.headers['Retry-After'] = str(retry_after)
    return response


def _get_auth_rate_limit_redis_client():
    global _auth_rate_limit_redis_client
    global _auth_rate_limit_redis_disabled

    if _auth_rate_limit_redis_disabled:
        return None
    if _auth_rate_limit_redis_client is not None:
        return _auth_rate_limit_redis_client

    redis_url = _auth_rate_limit_redis_url()
    if not redis_url or redis is None:
        if redis_url and redis is None and not _auth_rate_limit_redis_disabled:
            app.logger.warning(
                'AUTH_RATE_LIMIT_REDIS_URL is set but redis package is unavailable; using in-memory rate limits.',
            )
        _auth_rate_limit_redis_disabled = True
        return None

    try:
        client = redis.Redis.from_url(redis_url, decode_responses=True)
        client.ping()
        _auth_rate_limit_redis_client = client
        app.logger.info('Auth rate limiting using Redis backend.')
        return _auth_rate_limit_redis_client
    except Exception:
        _auth_rate_limit_redis_disabled = True
        app.logger.exception('Failed to initialize Redis auth rate limiter; using in-memory fallback.')
        return None


def _check_auth_rate_limit_memory(action, identifier):
    now = datetime.utcnow()
    window_seconds = _auth_rate_limit_window_seconds(action=action)
    max_attempts = _auth_rate_limit_max_attempts(action)
    cutoff = now - timedelta(seconds=window_seconds)
    bucket = '{}:{}'.format(action, identifier)

    with _auth_rate_limit_lock:
        attempts = _auth_rate_limit_events.get(bucket, [])
        attempts = [ts for ts in attempts if ts > cutoff]
        if len(attempts) >= max_attempts:
            oldest = min(attempts)
            retry_after = max(1, window_seconds - int((now - oldest).total_seconds()))
            _auth_rate_limit_events[bucket] = attempts
            return retry_after

        attempts.append(now)
        _auth_rate_limit_events[bucket] = attempts
    return 0


def _check_auth_rate_limit_redis(action, identifier):
    global _auth_rate_limit_redis_client
    global _auth_rate_limit_redis_disabled

    client = _get_auth_rate_limit_redis_client()
    if client is None:
        return None

    window_seconds = _auth_rate_limit_window_seconds(action=action)
    max_attempts = _auth_rate_limit_max_attempts(action)
    now_ms = int(datetime.utcnow().timestamp() * 1000)
    oldest_allowed_ms = now_ms - (window_seconds * 1000)
    key = _auth_rate_limit_bucket_key(action, identifier)
    member = '{}:{}'.format(now_ms, uuid.uuid4().hex)

    try:
        pipeline = client.pipeline(transaction=True)
        pipeline.zremrangebyscore(key, 0, oldest_allowed_ms)
        pipeline.zcard(key)
        pipeline.zadd(key, {member: now_ms})
        pipeline.expire(key, window_seconds + 2)
        _trimmed, current_count, _added, _expire_set = pipeline.execute()

        if int(current_count) >= max_attempts:
            # Remove the just-added member so blocked attempts don't inflate the bucket.
            client.zrem(key, member)
            oldest = client.zrange(key, 0, 0, withscores=True)
            if oldest:
                oldest_ts_ms = int(float(oldest[0][1]))
                retry_after = max(1, window_seconds - int((now_ms - oldest_ts_ms) / 1000))
                return retry_after
            return window_seconds
        return 0
    except Exception:
        _auth_rate_limit_redis_client = None
        _auth_rate_limit_redis_disabled = True
        app.logger.exception(
            'Redis auth rate limiter query failed; disabling Redis limiter and using in-memory fallback.',
        )
        return None


def _check_auth_rate_limit(action, identifier):
    if not _auth_rate_limit_enabled():
        return 0

    redis_retry = _check_auth_rate_limit_redis(action, identifier)
    if redis_retry is not None:
        return redis_retry
    return _check_auth_rate_limit_memory(action, identifier)


def _auth_rate_limit_response(action, email=None):
    retry_values = []
    ip_retry = _check_auth_rate_limit(action, 'ip:{}'.format(_request_client_ip()))
    if ip_retry:
        retry_values.append(ip_retry)

    normalized_email = _normalize_email(email)
    if normalized_email:
        email_retry = _check_auth_rate_limit(action, 'email:{}'.format(normalized_email))
        if email_retry:
            retry_values.append(email_retry)

    if not retry_values:
        return None

    retry_after = max(retry_values)
    response = jsonify({'error': 'Too many attempts. Please try again later.'})
    response.status_code = 429
    response.headers['Retry-After'] = str(retry_after)
    return response


def _auth_admin_rate_limit_response(user_id=None):
    if not _auth_rate_limit_enabled() or not _auth_rate_limit_admin_enabled():
        return None

    retry_values = []
    ip_retry = _check_auth_rate_limit('admin_api', 'ip:{}'.format(_request_client_ip()))
    if ip_retry:
        retry_values.append(ip_retry)

    normalized_user_id = _to_int_or_none(user_id)
    if normalized_user_id is not None:
        user_retry = _check_auth_rate_limit('admin_api', 'user:{}'.format(normalized_user_id))
        if user_retry:
            retry_values.append(user_retry)

    if not retry_values:
        return None

    retry_after = max(retry_values)
    response = jsonify({'error': 'Too many admin API requests. Please try again later.'})
    response.status_code = 429
    response.headers['Retry-After'] = str(retry_after)
    return response


def _normalize_auth_audit_details(details):
    if details is None:
        return {}

    if isinstance(details, dict):
        payload = details
    else:
        payload = {'value': str(details)}

    try:
        json.dumps(payload)
        return payload
    except Exception:
        normalized = {}
        for key, value in payload.items():
            json_key = str(key)
            try:
                json.dumps(value)
                normalized[json_key] = value
            except Exception:
                normalized[json_key] = str(value)
        return normalized


def _persist_auth_audit_event(payload, occurred_at=None):
    try:
        with db.engine.begin() as connection:
            connection.execute(
                AuthAuditEvent.__table__.insert().values(
                    event=(str(payload.get('event') or 'unknown').strip().lower() or 'unknown')[:64],
                    success=bool(payload.get('success')),
                    status_code=int(payload.get('status_code') or 0),
                    email=_normalize_email(payload.get('email')),
                    user_id=_to_int_or_none(payload.get('user_id')),
                    ip=(str(payload.get('ip') or '').strip()[:64] or None),
                    user_agent=(str(payload.get('user_agent') or '').strip()[:255] or None),
                    details_json=_normalize_auth_audit_details(payload.get('details')),
                    occurred_at=occurred_at or datetime.utcnow(),
                )
            )
    except Exception:
        # Audit persistence should never break auth endpoints.
        app.logger.exception('Failed to persist auth audit event.')


def _serialize_auth_audit_event(row):
    if not row:
        return None
    return {
        'id': row.id,
        'event': row.event,
        'success': bool(row.success),
        'status_code': row.status_code,
        'email': row.email,
        'user_id': row.user_id,
        'ip': row.ip,
        'user_agent': row.user_agent,
        'details': row.details_json or {},
        'occurred_at': row.occurred_at.isoformat() + 'Z' if row.occurred_at else None,
    }


def _normalize_auth_block_identifier(identifier_type, identifier_value):
    id_type = str(identifier_type or '').strip().lower()
    raw_value = str(identifier_value or '').strip()
    if id_type == 'email':
        return id_type, _normalize_email(raw_value)
    if id_type == 'ip':
        return id_type, raw_value[:64]
    return id_type, raw_value


def _serialize_auth_blocklist_entry(row):
    if not row:
        return None
    return {
        'id': row.id,
        'identifier_type': row.identifier_type,
        'identifier_value': row.identifier_value,
        'reason': row.reason,
        'created_by_user_id': row.created_by_user_id,
        'expires_at': row.expires_at.isoformat() + 'Z' if row.expires_at else None,
        'revoked_at': row.revoked_at.isoformat() + 'Z' if row.revoked_at else None,
        'metadata': row.metadata_json or {},
        'created_at': row.created_at.isoformat() + 'Z' if row.created_at else None,
        'updated_at': row.updated_at.isoformat() + 'Z' if row.updated_at else None,
        'is_active': bool((row.revoked_at is None) and (row.expires_at is None or row.expires_at > datetime.utcnow())),
    }


def _active_blocklist_entries(identifier_type, identifier_value):
    if not _auth_blocklist_enabled():
        return []
    id_type, id_value = _normalize_auth_block_identifier(identifier_type, identifier_value)
    if not id_type or not id_value:
        return []
    now = datetime.utcnow()
    return (
        AuthSecurityBlocklist.query.filter(
            AuthSecurityBlocklist.identifier_type == id_type,
            AuthSecurityBlocklist.identifier_value == id_value,
            AuthSecurityBlocklist.revoked_at.is_(None),
            or_(
                AuthSecurityBlocklist.expires_at.is_(None),
                AuthSecurityBlocklist.expires_at > now,
            ),
        )
        .order_by(AuthSecurityBlocklist.created_at.desc(), AuthSecurityBlocklist.id.desc())
        .all()
    )


def _current_blocklist_match(email=None):
    matches = []
    ip_value = _request_client_ip()
    matches.extend(_active_blocklist_entries('ip', ip_value))

    normalized_email = _normalize_email(email)
    if normalized_email:
        matches.extend(_active_blocklist_entries('email', normalized_email))

    if not matches:
        return None

    retry_after_seconds = 0
    now = datetime.utcnow()
    for entry in matches:
        if entry.expires_at:
            retry_after_seconds = max(
                retry_after_seconds,
                max(1, int((entry.expires_at - now).total_seconds())),
            )

    return {
        'entries': matches,
        'retry_after_seconds': retry_after_seconds,
    }


def _auth_blocklist_response(email=None):
    blocked = _current_blocklist_match(email=email)
    if not blocked:
        return None

    first_match = blocked['entries'][0]
    response = jsonify(
        {
            'error': 'Access temporarily blocked',
            'reason': first_match.reason or 'security_block',
            'retry_after_seconds': blocked['retry_after_seconds'] or None,
        }
    )
    response.status_code = 403
    if blocked['retry_after_seconds'] > 0:
        response.headers['Retry-After'] = str(blocked['retry_after_seconds'])
    return response


def _parse_optional_bool_query(value, label):
    raw = str(value or '').strip().lower()
    if not raw:
        return None
    if raw in {'1', 'true', 'yes', 'on'}:
        return True
    if raw in {'0', 'false', 'no', 'off'}:
        return False
    raise ValueError('Invalid {} filter. Use true or false.'.format(label))


def _parse_optional_int_query(value, label, min_value=None, max_value=None):
    raw = str(value or '').strip()
    if not raw:
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        raise ValueError('Invalid {} filter. Use an integer.'.format(label))
    if min_value is not None and parsed < min_value:
        raise ValueError('{} must be at least {}.'.format(label, min_value))
    if max_value is not None and parsed > max_value:
        raise ValueError('{} must be at most {}.'.format(label, max_value))
    return parsed


def _parse_query_datetime_utc(value, label):
    raw = str(value or '').strip()
    if not raw:
        return None
    try:
        parsed = dateutil.parser.parse(raw)
    except (TypeError, ValueError, OverflowError):
        raise ValueError('Invalid {} datetime. Use ISO-8601 format.'.format(label))

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _ops_health_auth_window_minutes(value=None):
    if value is None:
        value = app.config.get('OPS_HEALTH_AUTH_WINDOW_MINUTES', 60)
    try:
        return max(5, min(10080, int(value)))
    except (TypeError, ValueError):
        return 60


def _ops_health_dispatch_limit(value=None):
    if value is None:
        value = app.config.get('OPS_HEALTH_DISPATCH_LIMIT', 500)
    try:
        return max(1, min(5000, int(value)))
    except (TypeError, ValueError):
        return 500


def _ops_health_thresholds():
    def _int_threshold(key, default, min_value=0, max_value=100000):
        value = app.config.get(key, default)
        try:
            return max(min_value, min(max_value, int(value)))
        except (TypeError, ValueError):
            return default

    return {
        'dispatch_backlog_warn': _int_threshold('OPS_HEALTH_DISPATCH_BACKLOG_WARN', 25, min_value=1),
        'dispatch_backlog_critical': _int_threshold('OPS_HEALTH_DISPATCH_BACKLOG_CRITICAL', 60, min_value=1),
        'incident_critical_breach_warn': _int_threshold('OPS_HEALTH_INCIDENT_CRITICAL_BREACH_WARN', 1, min_value=1),
        'incident_total_breach_warn': _int_threshold('OPS_HEALTH_INCIDENT_TOTAL_BREACH_WARN', 5, min_value=1),
        'lockout_events_warn': _int_threshold('OPS_HEALTH_LOCKOUT_EVENTS_WARN', 5, min_value=1),
        'admin_rate_limit_events_warn': _int_threshold('OPS_HEALTH_ADMIN_RATE_LIMIT_EVENTS_WARN', 5, min_value=1),
        'audit_5xx_events_warn': _int_threshold('OPS_HEALTH_AUDIT_5XX_EVENTS_WARN', 1, min_value=1),
    }


def _collect_ops_health_snapshot(auth_window_minutes=None, dispatch_limit=None, now=None):
    now = now or datetime.utcnow()
    auth_window_minutes = _ops_health_auth_window_minutes(auth_window_minutes)
    dispatch_limit = _ops_health_dispatch_limit(dispatch_limit)
    thresholds = _ops_health_thresholds()

    since = now - timedelta(minutes=auth_window_minutes)
    auth_rows = (
        AuthAuditEvent.query.filter(AuthAuditEvent.occurred_at >= since)
        .order_by(AuthAuditEvent.occurred_at.desc(), AuthAuditEvent.id.desc())
        .limit(10000)
        .all()
    )

    failed_login_events = 0
    lockout_events = 0
    blocklist_events = 0
    rate_limited_events = 0
    admin_rate_limit_events = 0
    audit_5xx_events = 0
    failed_email_buckets = {}
    failed_ip_buckets = {}

    for row in auth_rows:
        event_name = str(row.event or '').strip().lower()
        details = row.details_json or {}
        reason = str(details.get('reason') or '').strip().lower()

        if row.status_code >= 500:
            audit_5xx_events += 1
        if event_name == 'admin_rate_limit' and row.status_code == 429:
            admin_rate_limit_events += 1

        if event_name == 'login' and not row.success:
            failed_login_events += 1
            if reason in {'lockout_triggered', 'lockout_active'}:
                lockout_events += 1
            if reason == 'blocklist':
                blocklist_events += 1
            if reason == 'rate_limited':
                rate_limited_events += 1

            if row.email:
                failed_email_buckets[row.email] = failed_email_buckets.get(row.email, 0) + 1
            if row.ip:
                failed_ip_buckets[row.ip] = failed_ip_buckets.get(row.ip, 0) + 1

    top_failed_emails = [
        {'email': email, 'failed_attempts': attempts}
        for email, attempts in sorted(
            failed_email_buckets.items(),
            key=lambda item: (-item[1], item[0]),
        )[:10]
    ]
    top_failed_ips = [
        {'ip': ip, 'failed_attempts': attempts}
        for ip, attempts in sorted(
            failed_ip_buckets.items(),
            key=lambda item: (-item[1], item[0]),
        )[:10]
    ]

    active_statuses = ['pending_match', 'matched', 'accepted', 'en_route', 'arrived', 'collected']
    dispatch_rows = (
        WasteRemovalRequest.query.filter(WasteRemovalRequest.status.in_(active_statuses))
        .order_by(WasteRemovalRequest.created_at.asc(), WasteRemovalRequest.id.asc())
        .limit(dispatch_limit)
        .all()
    )

    incident_total = 0
    incident_open = 0
    incident_acknowledged = 0
    incident_resolved = 0
    incident_breach_total = 0
    incident_breach_critical = 0
    incident_breach_ack_sla = 0
    incident_breach_resolve_sla = 0
    incident_status_counts = {}
    max_breach_minutes = 0
    oldest_pending_match_minutes = 0
    oldest_unassigned_match_minutes = 0

    for booking in dispatch_rows:
        status_key = (booking.status or '').strip().lower() or 'unknown'
        incident_status_counts[status_key] = incident_status_counts.get(status_key, 0) + 1

        latest_location = (
            WasteRemovalVehicleLocation.query.filter_by(waste_removal_request_id=booking.id)
            .order_by(WasteRemovalVehicleLocation.recorded_at.desc(), WasteRemovalVehicleLocation.id.desc())
            .first()
        )
        queue_item = _serialize_dispatch_queue_item(
            booking,
            driver=None,
            latest_location=latest_location,
            now=now,
        )

        incident_flags = queue_item.get('incident_flags') or []
        incident_info = queue_item.get('incident') or {}
        if incident_flags:
            incident_total += 1

        incident_state = str(incident_info.get('state') or '').strip().lower()
        if incident_state == 'open':
            incident_open += 1
        elif incident_state == 'acknowledged':
            incident_acknowledged += 1
        elif incident_state == 'resolved':
            incident_resolved += 1

        breach_type = str(incident_info.get('breach_type') or '').strip().lower()
        breach_minutes = max(0, int(incident_info.get('breach_minutes') or 0))
        if breach_type:
            incident_breach_total += 1
            if breach_type == 'ack_sla':
                incident_breach_ack_sla += 1
            elif breach_type == 'resolve_sla':
                incident_breach_resolve_sla += 1
            if (str(incident_info.get('severity') or '').strip().lower()) == 'critical':
                incident_breach_critical += 1
            max_breach_minutes = max(max_breach_minutes, breach_minutes)

        age_minutes = int(queue_item.get('age_minutes') or 0)
        if status_key == 'pending_match':
            oldest_pending_match_minutes = max(oldest_pending_match_minutes, age_minutes)
        if status_key in {'matched', 'accepted'} and booking.assigned_driver_user_id is None:
            oldest_unassigned_match_minutes = max(oldest_unassigned_match_minutes, age_minutes)

    alerts = []

    def _add_alert(code, severity, message, current_value, threshold_value):
        alerts.append(
            {
                'code': str(code),
                'severity': str(severity),
                'message': str(message),
                'current': current_value,
                'threshold': threshold_value,
            }
        )

    backlog_count = len(dispatch_rows)
    if backlog_count >= thresholds['dispatch_backlog_critical']:
        _add_alert(
            'dispatch_backlog_critical',
            'critical',
            'Dispatch backlog exceeded critical threshold.',
            backlog_count,
            thresholds['dispatch_backlog_critical'],
        )
    elif backlog_count >= thresholds['dispatch_backlog_warn']:
        _add_alert(
            'dispatch_backlog_warn',
            'warning',
            'Dispatch backlog exceeded warning threshold.',
            backlog_count,
            thresholds['dispatch_backlog_warn'],
        )

    if incident_breach_critical >= thresholds['incident_critical_breach_warn']:
        _add_alert(
            'incident_critical_breach',
            'critical',
            'Critical incident SLA breaches detected.',
            incident_breach_critical,
            thresholds['incident_critical_breach_warn'],
        )

    if incident_breach_total >= thresholds['incident_total_breach_warn']:
        _add_alert(
            'incident_breach_total',
            'warning',
            'Total incident SLA breaches exceeded warning threshold.',
            incident_breach_total,
            thresholds['incident_total_breach_warn'],
        )

    if lockout_events >= thresholds['lockout_events_warn']:
        _add_alert(
            'auth_lockout_events',
            'warning',
            'Lockout events exceeded warning threshold.',
            lockout_events,
            thresholds['lockout_events_warn'],
        )

    if admin_rate_limit_events >= thresholds['admin_rate_limit_events_warn']:
        _add_alert(
            'auth_admin_rate_limit_events',
            'warning',
            'Admin API rate-limit events exceeded warning threshold.',
            admin_rate_limit_events,
            thresholds['admin_rate_limit_events_warn'],
        )

    if audit_5xx_events >= thresholds['audit_5xx_events_warn']:
        _add_alert(
            'auth_audit_5xx_events',
            'warning',
            'Auth/audit 5xx events exceeded warning threshold.',
            audit_5xx_events,
            thresholds['audit_5xx_events_warn'],
        )

    status = 'ok'
    if any(alert['severity'] == 'critical' for alert in alerts):
        status = 'critical'
    elif alerts:
        status = 'warning'

    return {
        'status': status,
        'generated_at': now.isoformat() + 'Z',
        'window': {
            'auth_minutes': auth_window_minutes,
            'dispatch_rows_limit': dispatch_limit,
        },
        'alerts': alerts,
        'thresholds': thresholds,
        'metrics': {
            'auth': {
                'failed_login_events': failed_login_events,
                'lockout_events': lockout_events,
                'blocklist_events': blocklist_events,
                'rate_limited_events': rate_limited_events,
                'admin_rate_limit_events': admin_rate_limit_events,
                'audit_5xx_events': audit_5xx_events,
                'top_failed_emails': top_failed_emails,
                'top_failed_ips': top_failed_ips,
            },
            'dispatch': {
                'queue_rows_considered': backlog_count,
                'status_counts': incident_status_counts,
                'incident_rows': incident_total,
                'incident_open': incident_open,
                'incident_acknowledged': incident_acknowledged,
                'incident_resolved': incident_resolved,
                'incident_breach_total': incident_breach_total,
                'incident_breach_critical': incident_breach_critical,
                'incident_breach_ack_sla': incident_breach_ack_sla,
                'incident_breach_resolve_sla': incident_breach_resolve_sla,
                'max_breach_minutes': max_breach_minutes,
                'oldest_pending_match_minutes': oldest_pending_match_minutes,
                'oldest_unassigned_match_minutes': oldest_unassigned_match_minutes,
            },
        },
    }


def _format_ops_health_digest_text(snapshot):
    generated_at = snapshot.get('generated_at') or ''
    status = str(snapshot.get('status') or 'unknown').upper()
    alerts = list(snapshot.get('alerts') or [])
    auth = (snapshot.get('metrics') or {}).get('auth') or {}
    dispatch = (snapshot.get('metrics') or {}).get('dispatch') or {}
    lines = [
        '[Project Divert] Ops Health Digest',
        'Status: {}'.format(status),
        'Generated: {}'.format(generated_at),
        '',
        'Auth metrics:',
        '  failed_login_events={}'.format(auth.get('failed_login_events', 0)),
        '  lockout_events={}'.format(auth.get('lockout_events', 0)),
        '  admin_rate_limit_events={}'.format(auth.get('admin_rate_limit_events', 0)),
        '  audit_5xx_events={}'.format(auth.get('audit_5xx_events', 0)),
        '',
        'Dispatch metrics:',
        '  queue_rows_considered={}'.format(dispatch.get('queue_rows_considered', 0)),
        '  incident_rows={}'.format(dispatch.get('incident_rows', 0)),
        '  incident_breach_total={}'.format(dispatch.get('incident_breach_total', 0)),
        '  incident_breach_critical={}'.format(dispatch.get('incident_breach_critical', 0)),
        '  oldest_pending_match_minutes={}'.format(dispatch.get('oldest_pending_match_minutes', 0)),
    ]
    if alerts:
        lines.extend(['', 'Active alerts:'])
        for alert in alerts:
            lines.append(
                '  - [{severity}] {code}: {message} (current={current}, threshold={threshold})'.format(
                    severity=str(alert.get('severity') or '').upper(),
                    code=alert.get('code'),
                    message=alert.get('message'),
                    current=alert.get('current'),
                    threshold=alert.get('threshold'),
                )
            )
    else:
        lines.extend(['', 'Active alerts: none'])
    return '\n'.join(lines)


def _serialize_auth_lifecycle_token(row):
    if not row:
        return None
    return {
        'id': row.id,
        'user_id': row.user_id,
        'token_id': row.token_id,
        'token_type': row.token_type,
        'expires_at': row.expires_at.isoformat() + 'Z' if row.expires_at else None,
        'used_at': row.used_at.isoformat() + 'Z' if row.used_at else None,
        'revoked_at': row.revoked_at.isoformat() + 'Z' if row.revoked_at else None,
        'metadata': row.metadata_json or {},
        'created_at': row.created_at.isoformat() + 'Z' if row.created_at else None,
        'updated_at': row.updated_at.isoformat() + 'Z' if row.updated_at else None,
    }


def _parse_admin_auth_audit_filters(args):
    try:
        status_code = _parse_optional_int_query(
            args.get('status_code'),
            'status_code',
            min_value=100,
            max_value=599,
        )
        user_id = _parse_optional_int_query(args.get('user_id'), 'user_id', min_value=1)
        success = _parse_optional_bool_query(args.get('success'), 'success')
        occurred_from = _parse_query_datetime_utc(args.get('from'), 'from')
        occurred_to = _parse_query_datetime_utc(args.get('to'), 'to')
    except ValueError as exc:
        raise ValueError(str(exc))

    event = (str(args.get('event') or '').strip().lower() or None)
    email = _normalize_email(args.get('email'))
    ip = (str(args.get('ip') or '').strip()[:64] or None)
    if event and len(event) > 64:
        raise ValueError('event filter is too long')
    if occurred_from and occurred_to and occurred_from > occurred_to:
        raise ValueError('from must be before to')

    return {
        'event': event,
        'email': email,
        'ip': ip,
        'success': success,
        'status_code': status_code,
        'user_id': user_id,
        'from': occurred_from,
        'to': occurred_to,
    }


def _build_admin_auth_audit_query(filters):
    query = AuthAuditEvent.query
    if filters.get('event'):
        query = query.filter(AuthAuditEvent.event == filters['event'])
    if filters.get('email'):
        query = query.filter(func.lower(AuthAuditEvent.email) == filters['email'])
    if filters.get('ip'):
        query = query.filter(AuthAuditEvent.ip == filters['ip'])
    if filters.get('success') is not None:
        query = query.filter(AuthAuditEvent.success == filters['success'])
    if filters.get('status_code') is not None:
        query = query.filter(AuthAuditEvent.status_code == filters['status_code'])
    if filters.get('user_id') is not None:
        query = query.filter(AuthAuditEvent.user_id == filters['user_id'])
    if filters.get('from') is not None:
        query = query.filter(AuthAuditEvent.occurred_at >= filters['from'])
    if filters.get('to') is not None:
        query = query.filter(AuthAuditEvent.occurred_at <= filters['to'])
    return query


def _audit_auth_event(event_type, success, status_code, email=None, user_id=None, details=None):
    occurred_at = datetime.utcnow()
    payload = {
        'event': str(event_type or '').strip().lower() or 'unknown',
        'success': bool(success),
        'status_code': int(status_code or 0),
        'email': _normalize_email(email),
        'user_id': _to_int_or_none(user_id),
        'ip': _request_client_ip(),
        'user_agent': str((request.user_agent.string or '')[:255]),
        'timestamp': occurred_at.isoformat() + 'Z',
        'details': _normalize_auth_audit_details(details),
    }
    try:
        app.logger.info('auth_audit %s', json.dumps(payload, separators=(',', ':')))
    except Exception:
        app.logger.info(
            'auth_audit event=%s success=%s status=%s email=%s user_id=%s',
            payload['event'],
            payload['success'],
            payload['status_code'],
            payload['email'],
            payload['user_id'],
        )
    _persist_auth_audit_event(payload, occurred_at=occurred_at)


def _is_valid_email(email):
    value = _normalize_email(email)
    if not value or len(value) > 255:
        return False
    if '@' not in value:
        return False
    local, _, domain = value.partition('@')
    if not local or not domain or '.' not in domain:
        return False
    return True


def _validate_password_strength(password):
    value = str(password or '')
    if len(value) < 8:
        return 'Password must be at least 8 characters.'
    if not any(ch.isalpha() for ch in value):
        return 'Password must include at least one letter.'
    if not any(ch.isdigit() for ch in value):
        return 'Password must include at least one number.'
    return None


def _token_expired(expires_at):
    return bool(expires_at and expires_at <= datetime.utcnow())


def _serialize_auth_user(user):
    return {
        'id': user.id,
        'email': user.email,
        'name': user.name,
        'role': user.role,
        'is_active': bool(user.is_active),
        'email_verified': bool(user.email_verified_at),
        'email_verified_at': user.email_verified_at.isoformat() if user.email_verified_at else None,
        'access_token_revoked_at': user.access_token_revoked_at.isoformat() if user.access_token_revoked_at else None,
    }


def _issue_jwt_token(user, token_type, expires_delta, token_id=None, extra_claims=None):
    now = datetime.utcnow()
    if token_type == 'access' and user.access_token_revoked_at and now <= user.access_token_revoked_at:
        # Ensure newly-issued tokens are considered newer than the revocation cutoff.
        now = user.access_token_revoked_at + timedelta(milliseconds=1)
    payload = {
        'sub': str(user.id),
        'email': _normalize_email(user.email),
        'name': (user.name or '').strip(),
        'role': (user.role or 'customer').strip().lower(),
        'token_type': token_type,
        'iat': int(now.timestamp()),
        'iat_ms': int(now.timestamp() * 1000),
        'exp': int((now + expires_delta).timestamp()),
    }
    if token_id:
        payload['jti'] = token_id
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, _jwt_secret(), algorithm='HS256')


def _create_auth_lifecycle_token(user_id, token_type, token_id, expires_at, metadata=None):
    token_row = AuthLifecycleToken(
        user_id=user_id,
        token_type=token_type,
        token_id=token_id,
        expires_at=expires_at,
        metadata_json=metadata or {},
    )
    db.session.add(token_row)
    return token_row


def _revoke_active_tokens_for_user(user_id, token_type):
    now = datetime.utcnow()
    tokens = AuthLifecycleToken.query.filter(
        AuthLifecycleToken.user_id == user_id,
        AuthLifecycleToken.token_type == token_type,
        AuthLifecycleToken.revoked_at.is_(None),
        AuthLifecycleToken.used_at.is_(None),
    ).all()
    for token_row in tokens:
        token_row.revoked_at = now
        token_row.used_at = token_row.used_at or now


def _encode_lifecycle_token_from_row(user, token_row):
    expires_at = token_row.expires_at
    if not expires_at:
        expires_delta = timedelta(minutes=1)
    else:
        expires_delta = max(timedelta(seconds=1), expires_at - datetime.utcnow())
    return _issue_jwt_token(
        user,
        token_type=token_row.token_type,
        token_id=token_row.token_id,
        expires_delta=expires_delta,
    )


def _latest_valid_one_time_token(user_id, token_type):
    now = datetime.utcnow()
    return (
        AuthLifecycleToken.query.filter(
            AuthLifecycleToken.user_id == user_id,
            AuthLifecycleToken.token_type == token_type,
            AuthLifecycleToken.revoked_at.is_(None),
            AuthLifecycleToken.used_at.is_(None),
            AuthLifecycleToken.expires_at > now,
        )
        .order_by(AuthLifecycleToken.created_at.desc(), AuthLifecycleToken.id.desc())
        .first()
    )


def _recent_valid_one_time_token(user_id, token_type, cooldown_seconds):
    cooldown = max(0, int(cooldown_seconds or 0))
    if cooldown <= 0:
        return None, 0

    token_row = _latest_valid_one_time_token(user_id, token_type)
    if not token_row:
        return None, 0

    now = datetime.utcnow()
    created_at = token_row.created_at or now
    elapsed_seconds = max(0, int((now - created_at).total_seconds()))
    retry_after = max(0, cooldown - elapsed_seconds)
    if retry_after <= 0:
        return None, 0
    return token_row, retry_after


def _enforce_refresh_token_limit(user_id):
    max_active = _auth_max_active_refresh_tokens()
    now = datetime.utcnow()
    active_rows = (
        AuthLifecycleToken.query.filter(
            AuthLifecycleToken.user_id == user_id,
            AuthLifecycleToken.token_type == 'refresh',
            AuthLifecycleToken.revoked_at.is_(None),
            AuthLifecycleToken.expires_at > now,
        )
        .order_by(AuthLifecycleToken.created_at.desc(), AuthLifecycleToken.id.desc())
        .all()
    )
    for token_row in active_rows[max_active:]:
        token_row.revoked_at = token_row.revoked_at or now
        token_row.used_at = token_row.used_at or now


def _issue_access_token(user):
    token_id = uuid.uuid4().hex
    return _issue_jwt_token(
        user,
        token_type='access',
        token_id=token_id,
        expires_delta=timedelta(hours=_jwt_exp_hours()),
    )


def _issue_refresh_token(user):
    token_id = uuid.uuid4().hex
    expires_at = datetime.utcnow() + timedelta(days=_jwt_refresh_exp_days())
    _create_auth_lifecycle_token(
        user_id=user.id,
        token_type='refresh',
        token_id=token_id,
        expires_at=expires_at,
        metadata={'role': (user.role or '').strip().lower()},
    )
    _enforce_refresh_token_limit(user.id)
    return _issue_jwt_token(
        user,
        token_type='refresh',
        token_id=token_id,
        expires_delta=timedelta(days=_jwt_refresh_exp_days()),
    )


def _issue_one_time_token(user, token_type, expires_delta):
    _revoke_active_tokens_for_user(user.id, token_type)
    token_id = uuid.uuid4().hex
    expires_at = datetime.utcnow() + expires_delta
    _create_auth_lifecycle_token(
        user_id=user.id,
        token_type=token_type,
        token_id=token_id,
        expires_at=expires_at,
        metadata={},
    )
    return _issue_jwt_token(
        user,
        token_type=token_type,
        token_id=token_id,
        expires_delta=expires_delta,
    )


def _issue_email_verification_token(user):
    return _issue_one_time_token(
        user,
        token_type='email_verify',
        expires_delta=timedelta(hours=_email_verification_token_exp_hours()),
    )


def _issue_password_reset_token(user):
    return _issue_one_time_token(
        user,
        token_type='password_reset',
        expires_delta=timedelta(minutes=_password_reset_token_exp_minutes()),
    )


def _decode_access_token(token):
    return jwt.decode(token, _jwt_secret(), algorithms=['HS256'])


def _refresh_row_from_claims(claims):
    token_id = str(claims.get('jti') or '').strip()
    if not token_id:
        return None
    return AuthLifecycleToken.query.filter_by(token_id=token_id, token_type='refresh').first()


def _one_time_row_from_claims(claims, expected_type):
    token_id = str(claims.get('jti') or '').strip()
    if not token_id:
        return None
    return AuthLifecycleToken.query.filter_by(token_id=token_id, token_type=expected_type).first()


def _issue_auth_payload(user):
    access_token = _issue_access_token(user)
    refresh_token = _issue_refresh_token(user)
    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'token_type': 'Bearer',
        'expires_in_hours': _jwt_exp_hours(),
        'refresh_expires_in_days': _jwt_refresh_exp_days(),
        'user': _serialize_auth_user(user),
    }


def _send_account_email(to_email, subject, text_body):
    return _send_material_request_email(to_email, subject, text_body)


def _verification_url_for_token(token):
    base_url = (app.config.get('APP_BASE_URL') or '').strip().rstrip('/')
    if not base_url:
        return ''
    return '{}/verify-email?token={}'.format(base_url, token)


def _password_reset_url_for_token(token):
    base_url = (app.config.get('APP_BASE_URL') or '').strip().rstrip('/')
    if not base_url:
        return ''
    return '{}/reset-password?token={}'.format(base_url, token)


def _current_jwt_claims():
    return getattr(g, 'jwt_claims', None)


def _current_jwt_role():
    claims = _current_jwt_claims() or {}
    return str(claims.get('role') or '').strip().lower()


def _current_jwt_email():
    claims = _current_jwt_claims() or {}
    return str(claims.get('email') or '').strip().lower()


def _current_jwt_user_id():
    claims = _current_jwt_claims() or {}
    raw = str(claims.get('sub') or '').strip()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _parse_lifecycle_token(raw_token, expected_type):
    token = str(raw_token or '').strip()
    if not token:
        raise ValueError('token is required')
    try:
        claims = _decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise ValueError('Token expired')
    except jwt.InvalidTokenError:
        raise ValueError('Invalid token')

    token_type = str(claims.get('token_type') or '').strip().lower()
    if token_type != expected_type:
        raise ValueError('Invalid token type')

    user_id = _to_int_or_none(claims.get('sub'))
    if user_id is None:
        raise ValueError('Token missing subject')
    return claims, user_id


def _consume_one_time_lifecycle_token(raw_token, expected_type):
    claims, user_id = _parse_lifecycle_token(raw_token, expected_type)
    token_row = _one_time_row_from_claims(claims, expected_type)
    if not token_row or token_row.user_id != user_id:
        raise ValueError('Token not found')
    if token_row.revoked_at:
        raise ValueError('Token revoked')
    if token_row.used_at:
        raise ValueError('Token already used')
    if _token_expired(token_row.expires_at):
        raise ValueError('Token expired')

    user = db.session.get(User, user_id)
    if not user:
        raise ValueError('User not found')

    token_row.used_at = datetime.utcnow()
    return user, token_row


def _rotate_refresh_token(raw_refresh_token):
    claims, user_id = _parse_lifecycle_token(raw_refresh_token, 'refresh')
    token_row = _refresh_row_from_claims(claims)
    if not token_row or token_row.user_id != user_id:
        raise ValueError('Refresh token not found')
    if token_row.revoked_at:
        raise ValueError('Refresh token revoked')
    if _token_expired(token_row.expires_at):
        raise ValueError('Refresh token expired')

    user = db.session.get(User, user_id)
    if not user:
        raise ValueError('User not found')
    if not user.is_active:
        raise ValueError('User is inactive')
    if _auth_require_email_verification() and not user.email_verified_at:
        raise ValueError('Email verification required')

    token_row.revoked_at = datetime.utcnow()
    token_row.used_at = token_row.used_at or datetime.utcnow()
    return user


def _revoke_all_refresh_tokens_for_user(user_id):
    now = datetime.utcnow()
    tokens = AuthLifecycleToken.query.filter_by(user_id=user_id, token_type='refresh').all()
    for token_row in tokens:
        if not token_row.revoked_at:
            token_row.revoked_at = now
        if not token_row.used_at:
            token_row.used_at = now


def _access_revoke_token_key(token_id):
    raw = str(token_id or '').strip()
    if not raw:
        return ''
    return 'access:{}'.format(raw)


def _claims_exp_datetime(claims):
    exp_unix = _to_int_or_none((claims or {}).get('exp'))
    if exp_unix is None:
        return datetime.utcnow() + timedelta(hours=_jwt_exp_hours())
    try:
        return datetime.utcfromtimestamp(exp_unix)
    except (TypeError, ValueError, OSError):
        return datetime.utcnow() + timedelta(hours=_jwt_exp_hours())


def _claims_iat_ms(claims):
    iat_ms = _to_int_or_none((claims or {}).get('iat_ms'))
    if iat_ms is not None:
        return iat_ms
    iat = _to_int_or_none((claims or {}).get('iat'))
    if iat is None:
        return None
    return int(iat * 1000)


def _revoke_access_token_jti(claims, reason='revoked'):
    user_id = _to_int_or_none((claims or {}).get('sub'))
    token_id = _access_revoke_token_key((claims or {}).get('jti'))
    if user_id is None or not token_id:
        return False

    now = datetime.utcnow()
    expires_at = _claims_exp_datetime(claims)
    token_row = AuthLifecycleToken.query.filter_by(
        token_id=token_id,
        token_type='access_revoke',
    ).first()
    if not token_row:
        token_row = _create_auth_lifecycle_token(
            user_id=user_id,
            token_type='access_revoke',
            token_id=token_id,
            expires_at=expires_at,
            metadata={'reason': str(reason or 'revoked')},
        )
    else:
        token_row.expires_at = max(token_row.expires_at or expires_at, expires_at)
        metadata = token_row.metadata_json or {}
        metadata['reason'] = str(reason or metadata.get('reason') or 'revoked')
        token_row.metadata_json = metadata

    if not token_row.revoked_at:
        token_row.revoked_at = now
    if not token_row.used_at:
        token_row.used_at = now
    return True


def _revoke_all_access_tokens_for_user(user_id, reason='revoked'):
    user = db.session.get(User, user_id)
    if not user:
        return False
    now = datetime.utcnow()
    if not user.access_token_revoked_at or user.access_token_revoked_at < now:
        user.access_token_revoked_at = now
    return True


def _revoke_sessions_for_suspicious_activity(user_id, reason='suspicious_activity'):
    normalized_user_id = _to_int_or_none(user_id)
    if normalized_user_id is None:
        return False
    _revoke_all_refresh_tokens_for_user(normalized_user_id)
    revoked = _revoke_all_access_tokens_for_user(normalized_user_id, reason=reason)
    return bool(revoked)


def _access_token_revocation_reason(claims):
    user_id = _to_int_or_none((claims or {}).get('sub'))
    if user_id is None:
        return 'Token missing subject'

    user = db.session.get(User, user_id)
    if not user:
        return 'User not found'
    if not user.is_active:
        return 'User is inactive'

    issued_at_ms = _claims_iat_ms(claims)
    if user.access_token_revoked_at and issued_at_ms is not None:
        revoked_at_ms = int(user.access_token_revoked_at.timestamp() * 1000)
        if issued_at_ms < revoked_at_ms:
            return 'Token revoked'

    token_id = _access_revoke_token_key((claims or {}).get('jti'))
    if token_id:
        token_row = AuthLifecycleToken.query.filter_by(
            token_id=token_id,
            token_type='access_revoke',
        ).first()
        if token_row and not _token_expired(token_row.expires_at):
            return 'Token revoked'

    return ''


def _extract_bearer_token():
    auth_header = request.headers.get('Authorization', '')
    if not auth_header:
        return ''
    parts = auth_header.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return ''
    return parts[1].strip()


def _request_access_allowed(booking):
    role = _current_jwt_role()
    if role == 'admin':
        return True
    if role == 'driver':
        current_user_id = _current_jwt_user_id()
        return bool(
            current_user_id
            and booking.assigned_driver_user_id
            and booking.assigned_driver_user_id == current_user_id
        )
    if role == 'customer':
        return (booking.requester_email or '').strip().lower() == _current_jwt_email()
    return False


def jwt_required(roles=None):
    roles = {str(role).strip().lower() for role in (roles or set()) if str(role).strip()}

    def _decorator(fn):
        @wraps(fn)
        def _wrapped(*args, **kwargs):
            token = _extract_bearer_token()
            if not token:
                return jsonify({'error': 'Missing Bearer token'}), 401
            try:
                claims = _decode_access_token(token)
            except jwt.ExpiredSignatureError:
                return jsonify({'error': 'Token expired'}), 401
            except jwt.InvalidTokenError:
                return jsonify({'error': 'Invalid token'}), 401

            token_type = str(claims.get('token_type') or '').strip().lower()
            if token_type and token_type != 'access':
                return jsonify({'error': 'Invalid token type for this endpoint'}), 401

            revocation_reason = _access_token_revocation_reason(claims)
            if revocation_reason:
                return jsonify({'error': revocation_reason}), 401

            role = str(claims.get('role') or '').strip().lower()
            if roles and role not in roles:
                return jsonify({'error': 'Forbidden'}), 403

            if role == 'admin' and request.path.startswith('/api/v1/admin/'):
                admin_rate_limited = _auth_admin_rate_limit_response(user_id=claims.get('sub'))
                if admin_rate_limited:
                    _audit_auth_event(
                        'admin_rate_limit',
                        success=False,
                        status_code=429,
                        email=claims.get('email'),
                        user_id=claims.get('sub'),
                        details={
                            'reason': 'rate_limited',
                            'path': request.path,
                            'method': request.method,
                        },
                    )
                    return admin_rate_limited

            g.jwt_claims = claims
            return fn(*args, **kwargs)

        return _wrapped

    return _decorator


def _to_int_or_none(value):
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float_or_none(value):
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_reference_data_refresh_attempted = False


def _clean_reference_value(value):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if hasattr(value, 'item'):
        try:
            value = value.item()
        except Exception:
            pass

    if isinstance(value, datetime):
        return value.isoformat()

    return value


def _clean_reference_row(row):
    row_data = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
    return {str(key): _clean_reference_value(value) for key, value in row_data.items()}


def _normalize_material_column(frame):
    if 'material' not in frame.columns:
        return frame
    normalized = frame.copy()
    normalized['material'] = (
        normalized['material']
        .astype(str)
        .str.replace('\xa0', ' ', regex=False)
        .str.strip()
    )
    return normalized


def _build_supplier_reference_row(source_row_index, row):
    row_data = _clean_reference_row(row)
    return SupplierReference(
        source_row_index=int(source_row_index),
        sup_type=(str(row_data.get('sup_type') or '').strip()[:120] or None),
        name=(str(row_data.get('name') or '').strip()[:255] or None),
        address_street=(str(row_data.get('address_street') or '').strip()[:255] or None),
        city=(str(row_data.get('city') or '').strip()[:120] or None),
        postcode=(str(row_data.get('postcode') or '').strip()[:32] or None),
        lat=_to_float_or_none(row_data.get('lat')),
        long=_to_float_or_none(row_data.get('long')),
        website=(str(row_data.get('website') or '').strip()[:255] or None),
        email=(str(row_data.get('email') or '').strip()[:255] or None),
        telephone=(str(row_data.get('telephone') or '').strip()[:120] or None),
        supplier_contact=(str(row_data.get('supplier_contact') or '').strip()[:255] or None),
        supplier_contact_email=(str(row_data.get('supplier_contact_email') or '').strip()[:255] or None),
        supplier_contact_telephone=(str(row_data.get('supplier_contact_telephone') or '').strip()[:120] or None),
        percent_recyclablenum=_to_float_or_none(row_data.get('percent_recyclablenum')),
        percent_efwnum=_to_float_or_none(row_data.get('percent_efwnum')),
        provides_a_rebateyn=_to_float_or_none(row_data.get('provides_a_rebateyn')),
        supplier_auditislist_yes_no_na=(
            str(row_data.get('supplier_auditislist_yes_no_na') or '').strip()[:32] or None
        ),
        supplier_audit_date_completed=(
            str(row_data.get('supplier_audit_date_completed') or '').strip()[:64] or None
        ),
        notes=(str(row_data.get('notes') or '').strip() or None),
        hierarchy=(str(row_data.get('hierarchy') or '').strip()[:120] or None),
        origin=(str(row_data.get('origin') or '').strip()[:120] or None),
        row_data=row_data,
    )


def _seed_reference_model_from_frame(model, frame, row_builder, force=False):
    existing = model.query.count()
    if existing and not force:
        return {'inserted': 0, 'existing': existing, 'skipped': True}

    if existing:
        model.query.delete()
        db.session.flush()

    objects = [row_builder(index, row) for index, row in frame.iterrows()]
    if objects:
        db.session.bulk_save_objects(objects)

    return {'inserted': len(objects), 'existing': existing, 'skipped': False}


def _seed_reference_data_from_files(force=False):
    supplier_frame = pd.read_csv('data/df3.csv')
    site_frame = pd.read_excel('sites.xlsx')
    divert_output_frame = pd.read_csv('divert_db.csv')
    reuse_frame = _normalize_material_column(pd.read_csv('reuse_offset.csv'))
    recycle_frame = _normalize_material_column(pd.read_excel('recycle_offset.csv'))
    carbon_frame = pd.read_excel('carbon_equivalencies.csv')

    summary = {
        'supplier_reference': _seed_reference_model_from_frame(
            SupplierReference,
            supplier_frame,
            _build_supplier_reference_row,
            force=force,
        ),
        'site_reference': _seed_reference_model_from_frame(
            SiteReference,
            site_frame,
            lambda index, row: SiteReference(source_row_index=int(index), row_data=_clean_reference_row(row)),
            force=force,
        ),
        'divert_output_reference': _seed_reference_model_from_frame(
            DivertOutputReference,
            divert_output_frame,
            lambda index, row: DivertOutputReference(
                source_row_index=int(index),
                row_data=_clean_reference_row(row),
            ),
            force=force,
        ),
        'reuse_offset_reference': _seed_reference_model_from_frame(
            ReuseOffsetReference,
            reuse_frame,
            lambda index, row: ReuseOffsetReference(
                source_row_index=int(index),
                material=(str(row.get('material') or '').strip()[:255] or None),
                emission_factor=_to_float_or_none(row.get('Emission Factor (kg CO2 equivalents/ tonne)')),
                source=(str(row.get('Source') or '').strip()[:255] or None),
                explanation=(str(row.get('Explanation') or '').strip() or None),
                row_data=_clean_reference_row(row),
            ),
            force=force,
        ),
        'recycle_offset_reference': _seed_reference_model_from_frame(
            RecycleOffsetReference,
            recycle_frame,
            lambda index, row: RecycleOffsetReference(
                source_row_index=int(index),
                material=(str(row.get('material') or '').strip()[:255] or None),
                emission_factor=_to_float_or_none(row.get('Emission Factor (kg CO2 equivalents/ tonne)')),
                source=(str(row.get('Source') or '').strip()[:255] or None),
                explanation=(str(row.get('Explanation') or '').strip() or None),
                row_data=_clean_reference_row(row),
            ),
            force=force,
        ),
        'carbon_equivalency_reference': _seed_reference_model_from_frame(
            CarbonEquivalencyReference,
            carbon_frame,
            lambda index, row: CarbonEquivalencyReference(
                source_row_index=int(index),
                equivalency=(str(row.get('equivalency') or '').strip()[:255] or None),
                emission_factor=_to_float_or_none(
                    row.get('emission factor (kg co2 equivalents/ tonne)')
                ),
                row_data=_clean_reference_row(row),
            ),
            force=force,
        ),
    }
    db.session.commit()
    return summary


def _refresh_reference_dataframes_from_db():
    global suppliers, sites, divert_output, reuse_offset, recycle_offset, carbon_equivalencies

    required_tables = {
        'supplier_reference',
        'site_reference',
        'divert_output_reference',
        'reuse_offset_reference',
        'recycle_offset_reference',
        'carbon_equivalency_reference',
    }

    try:
        table_names = set(inspect(db.engine).get_table_names())
    except SQLAlchemyError:
        return False

    if not required_tables.issubset(table_names):
        return False

    loaded_any = False

    supplier_rows = SupplierReference.query.order_by(SupplierReference.source_row_index.asc()).all()
    if supplier_rows:
        supplier_records = []
        for row in supplier_rows:
            record = dict(row.row_data or {})
            record.setdefault('sup_type', row.sup_type)
            record.setdefault('name', row.name)
            record.setdefault('address_street', row.address_street)
            record.setdefault('city', row.city)
            record.setdefault('postcode', row.postcode)
            record.setdefault('lat', row.lat)
            record.setdefault('long', row.long)
            record.setdefault('website', row.website)
            record.setdefault('email', row.email)
            record.setdefault('telephone', row.telephone)
            record.setdefault('supplier_contact', row.supplier_contact)
            record.setdefault('supplier_contact_email', row.supplier_contact_email)
            record.setdefault('supplier_contact_telephone', row.supplier_contact_telephone)
            record.setdefault('percent_recyclablenum', row.percent_recyclablenum)
            record.setdefault('percent_efwnum', row.percent_efwnum)
            record.setdefault('provides_a_rebateyn', row.provides_a_rebateyn)
            record.setdefault('supplier_auditislist_yes_no_na', row.supplier_auditislist_yes_no_na)
            record.setdefault('supplier_audit_date_completed', row.supplier_audit_date_completed)
            record.setdefault('notes', row.notes)
            record.setdefault('hierarchy', row.hierarchy)
            record.setdefault('origin', row.origin)
            supplier_records.append(record)
        suppliers = pd.DataFrame(supplier_records)
        loaded_any = True

    site_rows = SiteReference.query.order_by(SiteReference.source_row_index.asc()).all()
    if site_rows:
        sites = pd.DataFrame([dict(row.row_data or {}) for row in site_rows])
        loaded_any = True

    divert_rows = DivertOutputReference.query.order_by(DivertOutputReference.source_row_index.asc()).all()
    if divert_rows:
        divert_output = pd.DataFrame([dict(row.row_data or {}) for row in divert_rows])
        if 'reuse_offset' not in divert_output.columns:
            divert_output['reuse_offset'] = ''
        if 'recycle_offset' not in divert_output.columns:
            divert_output['recycle_offset'] = ''
        divert_output['reuse_offset'] = pd.to_numeric(divert_output['reuse_offset'], errors='coerce')
        divert_output['recycle_offset'] = pd.to_numeric(divert_output['recycle_offset'], errors='coerce')
        loaded_any = True

    reuse_rows = ReuseOffsetReference.query.order_by(ReuseOffsetReference.source_row_index.asc()).all()
    if reuse_rows:
        reuse_records = []
        for row in reuse_rows:
            record = dict(row.row_data or {})
            record.setdefault('material', row.material)
            record.setdefault('Emission Factor (kg CO2 equivalents/ tonne)', row.emission_factor)
            record.setdefault('Source', row.source)
            record.setdefault('Explanation', row.explanation)
            reuse_records.append(record)
        reuse_offset = _normalize_material_column(pd.DataFrame(reuse_records))
        if 'material' in reuse_offset.columns:
            reuse_offset.set_index(keys='material', inplace=True)
        loaded_any = True

    recycle_rows = RecycleOffsetReference.query.order_by(RecycleOffsetReference.source_row_index.asc()).all()
    if recycle_rows:
        recycle_records = []
        for row in recycle_rows:
            record = dict(row.row_data or {})
            record.setdefault('material', row.material)
            record.setdefault('Emission Factor (kg CO2 equivalents/ tonne)', row.emission_factor)
            record.setdefault('Source', row.source)
            record.setdefault('Explanation', row.explanation)
            recycle_records.append(record)
        recycle_offset = _normalize_material_column(pd.DataFrame(recycle_records))
        if 'material' in recycle_offset.columns:
            recycle_offset.set_index(keys='material', inplace=True)
        loaded_any = True

    carbon_rows = CarbonEquivalencyReference.query.order_by(
        CarbonEquivalencyReference.source_row_index.asc()
    ).all()
    if carbon_rows:
        carbon_equivalencies = pd.DataFrame([dict(row.row_data or {}) for row in carbon_rows])
        loaded_any = True

    return loaded_any


def _ensure_reference_data_loaded():
    global _reference_data_refresh_attempted
    if _reference_data_refresh_attempted:
        return
    _reference_data_refresh_attempted = True
    try:
        _refresh_reference_dataframes_from_db()
    except Exception:
        app.logger.exception('Failed to refresh reference data from database.')


def _auth_token_cleanup_retention_days():
    value = app.config.get('AUTH_TOKEN_CLEANUP_RETENTION_DAYS', 30)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 30


def _auth_token_cleanup_query(cutoff):
    return AuthLifecycleToken.query.filter(
        or_(
            AuthLifecycleToken.expires_at <= cutoff,
            and_(
                AuthLifecycleToken.revoked_at.isnot(None),
                AuthLifecycleToken.revoked_at <= cutoff,
            ),
        )
    )


@app.cli.command('seed-reference-data')
@click.option('--force', is_flag=True, help='Replace existing reference rows with file data.')
def seed_reference_data(force):
    """Load CSV/XLSX reference data into SQL tables."""
    summary = _seed_reference_data_from_files(force=force)
    loaded_from_db = _refresh_reference_dataframes_from_db()
    click.echo('Reference data seed complete.')
    click.echo('Loaded from DB: {}'.format('yes' if loaded_from_db else 'no'))
    for table_name in sorted(summary.keys()):
        table_summary = summary[table_name]
        click.echo(
            '{} -> inserted={}, existing_before={}, skipped={}'.format(
                table_name,
                table_summary['inserted'],
                table_summary['existing'],
                table_summary['skipped'],
            )
        )


@app.cli.command('auth-token-cleanup')
@click.option(
    '--retention-days',
    type=int,
    default=None,
    help='Delete tokens expired/revoked before now - retention-days (default from AUTH_TOKEN_CLEANUP_RETENTION_DAYS).',
)
@click.option('--batch-size', type=int, default=500, show_default=True)
@click.option('--dry-run', is_flag=True, help='Show candidate rows without deleting.')
def auth_token_cleanup(retention_days, batch_size, dry_run):
    """Delete stale auth lifecycle token rows."""
    if retention_days is None:
        retention_days = _auth_token_cleanup_retention_days()
    if retention_days < 0:
        raise click.BadParameter('retention-days must be >= 0')
    if batch_size < 1:
        raise click.BadParameter('batch-size must be >= 1')

    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    query = _auth_token_cleanup_query(cutoff)
    total = query.count()
    type_counts = dict(
        db.session.query(
            AuthLifecycleToken.token_type,
            func.count(AuthLifecycleToken.id),
        )
        .filter(
            or_(
                AuthLifecycleToken.expires_at <= cutoff,
                and_(
                    AuthLifecycleToken.revoked_at.isnot(None),
                    AuthLifecycleToken.revoked_at <= cutoff,
                ),
            )
        )
        .group_by(AuthLifecycleToken.token_type)
        .all()
    )

    click.echo('Auth token cleanup cutoff: {}'.format(cutoff.isoformat() + 'Z'))
    click.echo('Candidates: {}'.format(total))
    if type_counts:
        for token_type in sorted(type_counts.keys()):
            click.echo('  {} -> {}'.format(token_type, type_counts[token_type]))

    if dry_run or total == 0:
        click.echo('Dry run: no rows deleted.' if dry_run else 'No rows to delete.')
        return

    deleted = 0
    while True:
        ids = [row.id for row in _auth_token_cleanup_query(cutoff).order_by(AuthLifecycleToken.id.asc()).limit(batch_size).all()]
        if not ids:
            break
        deleted += (
            AuthLifecycleToken.query.filter(AuthLifecycleToken.id.in_(ids)).delete(synchronize_session=False)
            or 0
        )
        db.session.commit()

    click.echo('Deleted rows: {}'.format(deleted))


@app.cli.command('ops-health-digest')
@click.option('--auth-window-minutes', type=int, default=None, help='Auth/audit lookback window.')
@click.option('--dispatch-limit', type=int, default=None, help='Max active dispatch rows to inspect.')
@click.option('--include-ok', is_flag=True, help='Send notifications even when status is ok.')
@click.option('--webhook-url', default=None, help='Override OPS_HEALTH_DIGEST_WEBHOOK_URL.')
@click.option('--email-to', default=None, help='Override OPS_HEALTH_DIGEST_EMAIL_TO.')
@click.option('--dry-run', is_flag=True, help='Compute and print digest without sending.')
@click.option('--fail-on-critical', is_flag=True, help='Return non-zero if status is critical.')
def ops_health_digest(
    auth_window_minutes,
    dispatch_limit,
    include_ok,
    webhook_url,
    email_to,
    dry_run,
    fail_on_critical,
):
    """Generate and optionally send an ops health digest."""
    if auth_window_minutes is not None and auth_window_minutes < 5:
        raise click.BadParameter('auth-window-minutes must be >= 5')
    if dispatch_limit is not None and dispatch_limit < 1:
        raise click.BadParameter('dispatch-limit must be >= 1')

    snapshot = _collect_ops_health_snapshot(
        auth_window_minutes=auth_window_minutes,
        dispatch_limit=dispatch_limit,
    )
    digest_text = _format_ops_health_digest_text(snapshot)
    click.echo(json.dumps(snapshot, indent=2, sort_keys=True))

    should_include_ok = bool(include_ok or _is_truthy(app.config.get('OPS_HEALTH_DIGEST_INCLUDE_OK', False)))
    should_notify = should_include_ok or snapshot.get('status') != 'ok'
    if not should_notify:
        click.echo('Status is ok and include-ok is disabled; no notifications sent.')
        return

    if dry_run:
        click.echo('Dry run: notifications not sent.')
        click.echo(digest_text)
        if fail_on_critical and snapshot.get('status') == 'critical':
            raise click.ClickException('Ops health is critical.')
        return

    final_webhook_url = str(webhook_url or app.config.get('OPS_HEALTH_DIGEST_WEBHOOK_URL') or '').strip()
    final_email_to = str(email_to or app.config.get('OPS_HEALTH_DIGEST_EMAIL_TO') or '').strip()

    if final_webhook_url:
        timeout = app.config.get('OPS_HEALTH_DIGEST_WEBHOOK_TIMEOUT_SECONDS', 8)
        try:
            timeout = max(2, int(timeout))
        except (TypeError, ValueError):
            timeout = 8

        try:
            response = requests.post(
                final_webhook_url,
                json={'text': digest_text, 'ops_health': snapshot},
                timeout=timeout,
            )
            if response.status_code >= 400:
                click.echo('Webhook send failed status={} body={}'.format(response.status_code, response.text[:500]))
            else:
                click.echo('Webhook digest sent.')
        except Exception:
            app.logger.exception('Ops health digest webhook send failed.')
            click.echo('Webhook digest send failed.')

    if final_email_to:
        email_subject = '[Project Divert] Ops Health {}'.format(str(snapshot.get('status') or 'unknown').upper())
        email_sent = _send_account_email(final_email_to, email_subject, digest_text)
        click.echo('Email digest {}.'.format('sent' if email_sent else 'failed'))

    if fail_on_critical and snapshot.get('status') == 'critical':
        raise click.ClickException('Ops health is critical.')


@app.cli.command('dispatch-incident-maintenance')
@click.option('--limit', type=int, default=None, help='Max active dispatch rows to inspect.')
@click.option('--auto-assign', is_flag=True, help='Auto-assign owner for unowned active incidents.')
@click.option('--auto-resolve-test', is_flag=True, help='Auto-resolve stale test incidents.')
@click.option('--owner-admin-email', default=None, help='Preferred admin email for owner assignment.')
@click.option(
    '--resolve-test-minutes',
    type=int,
    default=None,
    help='Minimum incident age (minutes) before auto-resolving test incidents.',
)
@click.option('--dry-run', is_flag=True, help='Compute actions without persisting changes.')
def dispatch_incident_maintenance(
    limit,
    auto_assign,
    auto_resolve_test,
    owner_admin_email,
    resolve_test_minutes,
    dry_run,
):
    """Auto-maintain dispatch incidents (owner assignment and stale test cleanup)."""
    if limit is not None and limit < 1:
        raise click.BadParameter('limit must be >= 1')
    if resolve_test_minutes is not None and resolve_test_minutes < 1:
        raise click.BadParameter('resolve-test-minutes must be >= 1')

    effective_auto_assign = bool(auto_assign or _dispatch_incident_auto_assign_enabled())
    effective_auto_resolve_test = bool(
        auto_resolve_test or _dispatch_incident_auto_resolve_test_enabled()
    )

    if not effective_auto_assign and not effective_auto_resolve_test:
        click.echo(
            'No maintenance actions enabled. '
            'Pass --auto-assign and/or --auto-resolve-test or enable related config flags.'
        )
        return

    result = _run_dispatch_incident_maintenance(
        auto_assign=effective_auto_assign,
        auto_resolve_test=effective_auto_resolve_test,
        resolve_test_minutes=resolve_test_minutes,
        owner_admin_email=owner_admin_email,
        limit=limit,
        dry_run=dry_run,
        actor_user_id=None,
        actor_email='dispatch-incident-maintenance@system.local',
        source='cli_dispatch_incident_maintenance',
    )
    click.echo(json.dumps(result, indent=2, sort_keys=True))


def _postcode_coordinates(postcode):
    endpoint = "http://api.postcodes.io/postcodes/{}".format(postcode)
    response = requests.get(endpoint, timeout=10)
    payload = response.json()
    result = payload.get('result') if isinstance(payload, dict) else None
    if not result:
        raise ValueError('Please enter a valid pickup postcode.')

    longitude = _to_float_or_none(result.get('longitude'))
    latitude = _to_float_or_none(result.get('latitude'))
    if longitude is None or latitude is None:
        raise ValueError('Please enter a valid pickup postcode.')
    return latitude, longitude


def _haversine_miles(lat1, lon1, lat2, lon2):
    radius_miles = 3958.8
    lat1_r = math.radians(lat1)
    lon1_r = math.radians(lon1)
    lat2_r = math.radians(lat2)
    lon2_r = math.radians(lon2)
    delta_lat = lat2_r - lat1_r
    delta_lon = lon2_r - lon1_r
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return radius_miles * c


def _parse_yes_no_flag(value):
    normalized = str(value or '').strip().lower()
    if normalized in {'1', 'true', 'yes', 'y'}:
        return True
    if normalized in {'0', 'false', 'no', 'n'}:
        return False
    numeric = _to_float_or_none(normalized)
    if numeric is not None:
        if numeric == 1.0:
            return True
        if numeric == 0.0:
            return False
    return None


def _to_percent_or_none(value):
    parsed = _to_float_or_none(value)
    if parsed is None:
        return None
    return max(0.0, min(100.0, parsed))


def _dispatch_sort_key(candidate):
    # Distance is primary. If equal, prefer higher recycling, lower EfW, audited suppliers, then rebates.
    recyclable = candidate.get('percent_recyclable')
    efw = candidate.get('percent_efw')
    audited = candidate.get('is_audited')
    rebate = candidate.get('provides_rebate')
    return (
        candidate.get('distance_miles_raw', candidate['distance_miles']),
        -(recyclable if recyclable is not None else -1.0),
        efw if efw is not None else 101.0,
        0 if audited is True else 1,
        0 if rebate is True else 1,
        candidate['provider_name'].lower(),
    )


def _dispatch_offer_fanout():
    value = app.config.get('DISPATCH_OFFER_FANOUT', 10)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 10


def _dispatch_pending_match_sla_minutes():
    value = app.config.get('DISPATCH_PENDING_MATCH_SLA_MINUTES', 30)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 30


def _dispatch_unassigned_match_sla_minutes():
    value = app.config.get('DISPATCH_UNASSIGNED_MATCH_SLA_MINUTES', 20)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 20


def _dispatch_location_stale_minutes():
    value = app.config.get('DISPATCH_LOCATION_STALE_MINUTES', 20)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 20


def _dispatch_escalation_ack_sla_minutes(severity):
    severity = str(severity or '').strip().lower()
    config_map = {
        'critical': 'DISPATCH_ESCALATION_ACK_SLA_CRITICAL_MINUTES',
        'high': 'DISPATCH_ESCALATION_ACK_SLA_HIGH_MINUTES',
        'medium': 'DISPATCH_ESCALATION_ACK_SLA_MEDIUM_MINUTES',
        'low': 'DISPATCH_ESCALATION_ACK_SLA_LOW_MINUTES',
    }
    value = app.config.get(config_map.get(severity, 'DISPATCH_ESCALATION_ACK_SLA_LOW_MINUTES'), 90)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 90


def _dispatch_escalation_resolve_sla_minutes(severity):
    severity = str(severity or '').strip().lower()
    config_map = {
        'critical': 'DISPATCH_ESCALATION_RESOLVE_SLA_CRITICAL_MINUTES',
        'high': 'DISPATCH_ESCALATION_RESOLVE_SLA_HIGH_MINUTES',
        'medium': 'DISPATCH_ESCALATION_RESOLVE_SLA_MEDIUM_MINUTES',
        'low': 'DISPATCH_ESCALATION_RESOLVE_SLA_LOW_MINUTES',
    }
    value = app.config.get(config_map.get(severity, 'DISPATCH_ESCALATION_RESOLVE_SLA_LOW_MINUTES'), 720)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 720


def _dispatch_escalation_webhook_url():
    return (str(app.config.get('DISPATCH_ESCALATION_WEBHOOK_URL') or '').strip() or '')


def _dispatch_escalation_webhook_timeout_seconds():
    value = app.config.get('DISPATCH_ESCALATION_WEBHOOK_TIMEOUT_SECONDS', 8)
    try:
        return max(2, int(value))
    except (TypeError, ValueError):
        return 8


def _dispatch_escalation_cooldown_minutes():
    value = app.config.get('DISPATCH_ESCALATION_COOLDOWN_MINUTES', 30)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 30


def _dispatch_incident_maintenance_limit(value=None):
    if value is None:
        value = app.config.get('DISPATCH_INCIDENT_MAINTENANCE_LIMIT', 500)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 500


def _dispatch_incident_auto_assign_enabled(value=None):
    if value is None:
        value = app.config.get('DISPATCH_INCIDENT_AUTO_ASSIGN_ENABLED', False)
    return _is_truthy(value)


def _dispatch_incident_auto_assign_admin_email(value=None):
    if value is None:
        value = app.config.get('DISPATCH_INCIDENT_AUTO_ASSIGN_ADMIN_EMAIL', '')
    return (_normalize_email(value) or '')


def _dispatch_incident_auto_resolve_test_enabled(value=None):
    if value is None:
        value = app.config.get('DISPATCH_INCIDENT_AUTO_RESOLVE_TEST_ENABLED', False)
    return _is_truthy(value)


def _dispatch_incident_auto_resolve_test_minutes(value=None):
    if value is None:
        value = app.config.get('DISPATCH_INCIDENT_AUTO_RESOLVE_TEST_MINUTES', 720)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 720


def _select_provider_candidates_within_radius(
    pickup_latitude,
    pickup_longitude,
    radius_miles,
    limit=None,
):
    _ensure_reference_data_loaded()

    if radius_miles <= 0:
        raise ValueError('Provider match radius must be greater than zero.')

    if suppliers is None or getattr(suppliers, 'empty', True):
        return []

    candidates = []
    for _, row in suppliers.iterrows():
        provider_name = str(row.get('name') or '').strip()
        provider_latitude = _to_float_or_none(row.get('lat'))
        provider_longitude = _to_float_or_none(row.get('long'))
        if not provider_name or provider_latitude is None or provider_longitude is None:
            continue

        distance_miles = _haversine_miles(
            pickup_latitude,
            pickup_longitude,
            provider_latitude,
            provider_longitude,
        )
        if distance_miles <= radius_miles:
            percent_recyclable = _to_percent_or_none(row.get('percent_recyclablenum'))
            percent_efw = _to_percent_or_none(row.get('percent_efwnum'))
            candidates.append(
                {
                    'provider_name': provider_name[:255],
                    'provider_type': str(row.get('sup_type') or '').strip()[:120] or None,
                    'provider_city': str(row.get('city') or '').strip()[:120] or None,
                    'provider_postcode': str(row.get('postcode') or '').strip()[:32] or None,
                    'provider_latitude': provider_latitude,
                    'provider_longitude': provider_longitude,
                    'provider_email': (
                        str(row.get('supplier_contact_email') or row.get('email') or '').strip()[:255] or None
                    ),
                    'provider_phone': (
                        str(row.get('supplier_contact_telephone') or row.get('telephone') or '').strip()[:120] or None
                    ),
                    'distance_miles_raw': distance_miles,
                    'distance_miles': round(distance_miles, 2),
                    'percent_recyclable': percent_recyclable,
                    'percent_efw': percent_efw,
                    'is_audited': _parse_yes_no_flag(row.get('supplier_auditislist_yes_no_na')),
                    'provides_rebate': _parse_yes_no_flag(row.get('provides_a_rebateyn')),
                }
            )

    if not candidates:
        return []
    candidates.sort(key=_dispatch_sort_key)
    if limit is not None:
        return candidates[: max(1, int(limit))]
    return candidates


def _select_best_provider_within_radius(pickup_latitude, pickup_longitude, radius_miles):
    candidates = _select_provider_candidates_within_radius(
        pickup_latitude,
        pickup_longitude,
        radius_miles,
        limit=1,
    )
    if not candidates:
        return None
    return candidates[0]


def _create_dispatch_offers_for_request(
    booking,
    pickup_latitude,
    pickup_longitude,
    match_radius_miles,
):
    candidates = _select_provider_candidates_within_radius(
        pickup_latitude,
        pickup_longitude,
        match_radius_miles,
        limit=_dispatch_offer_fanout(),
    )
    offer_rows = []
    for rank, candidate in enumerate(candidates, start=1):
        offer_rows.append(
            WasteRemovalDispatchOffer(
                waste_removal_request_id=booking.id,
                provider_name=candidate['provider_name'],
                provider_type=candidate['provider_type'],
                provider_city=candidate['provider_city'],
                provider_postcode=candidate['provider_postcode'],
                provider_latitude=candidate['provider_latitude'],
                provider_longitude=candidate['provider_longitude'],
                provider_email=candidate['provider_email'],
                provider_phone=candidate['provider_phone'],
                distance_miles=candidate['distance_miles'],
                match_radius_miles=match_radius_miles,
                offer_rank=rank,
                offer_token=uuid.uuid4().hex,
                status='offered',
            )
        )
    return candidates, offer_rows


def _notify_dispatch_offers(booking, offer_rows, base_url):
    success_count = 0
    for offer in offer_rows:
        to_email = (offer.provider_email or '').strip()
        if not to_email:
            continue

        subject = 'New waste collection job offer #{}'.format(booking.id)
        text_body = (
            'A new waste collection job is available.\n\n'
            'Request ID: {request_id}\n'
            'Material: {material}\n'
            'Waste Amount: {amount} {unit}\n'
            'Pickup Postcode: {postcode}\n'
            'Scheduled Pickup: {scheduled_pickup}\n'
            'Distance to pickup: {distance} miles\n'
            'Offer rank: {rank}\n\n'
            'To accept this job, POST to:\n'
            '{base_url}/api/v1/waste-requests/{request_id}/dispatch/accept\n'
            'with Authorization header:\n'
            'Bearer <driver access token>\n'
            'with JSON body:\n'
            '{{"offer_token":"{offer_token}"}}\n'
        ).format(
            request_id=booking.id,
            material=booking.material_type,
            amount=booking.waste_amount,
            unit=booking.waste_unit,
            postcode=booking.pickup_postcode,
            scheduled_pickup=booking.scheduled_pickup_at.strftime('%Y-%m-%d %H:%M'),
            distance=offer.distance_miles,
            rank=offer.offer_rank,
            base_url=base_url.rstrip('/'),
            offer_token=offer.offer_token,
        )
        if _send_material_request_email(to_email, subject, text_body):
            success_count += 1
    return success_count


def _get_latest_match_for_request(request_id):
    return (
        WasteRemovalMatch.query.filter_by(waste_removal_request_id=request_id)
        .order_by(WasteRemovalMatch.created_at.desc(), WasteRemovalMatch.id.desc())
        .first()
    )


def _dispatch_summary_for_request(request_id):
    offers = WasteRemovalDispatchOffer.query.filter_by(waste_removal_request_id=request_id)
    offers_sent = offers.count()
    offers_open = offers.filter_by(status='offered').count()
    accepted_offer = (
        offers.filter_by(status='accepted')
        .order_by(WasteRemovalDispatchOffer.responded_at.desc(), WasteRemovalDispatchOffer.id.desc())
        .first()
    )
    return {
        'offers_sent': offers_sent,
        'offers_open': offers_open,
        'accepted_offer': _serialize_dispatch_offer(accepted_offer),
    }


def _accept_dispatch_offer(booking, offer, assigned_driver_user_id=None):
    if not booking or not offer:
        return None, 'invalid_offer'

    if offer.waste_removal_request_id != booking.id:
        return None, 'invalid_offer'

    if assigned_driver_user_id is not None:
        if booking.assigned_driver_user_id and booking.assigned_driver_user_id != assigned_driver_user_id:
            return None, 'driver_mismatch'

    if (offer.status or '').strip().lower() != 'offered':
        return None, 'offer_unavailable'

    existing_match = _get_latest_match_for_request(booking.id)
    if existing_match:
        return existing_match, 'already_matched'

    now = datetime.utcnow()
    offer.status = 'accepted'
    offer.responded_at = now

    (
        WasteRemovalDispatchOffer.query.filter(
            WasteRemovalDispatchOffer.waste_removal_request_id == booking.id,
            WasteRemovalDispatchOffer.id != offer.id,
            WasteRemovalDispatchOffer.status == 'offered',
        ).update(
            {
                WasteRemovalDispatchOffer.status: 'expired',
                WasteRemovalDispatchOffer.responded_at: now,
            },
            synchronize_session=False,
        )
    )

    match_row = WasteRemovalMatch(
        waste_removal_request_id=booking.id,
        provider_name=offer.provider_name,
        provider_type=offer.provider_type,
        provider_city=offer.provider_city,
        provider_postcode=offer.provider_postcode,
        provider_latitude=offer.provider_latitude,
        provider_longitude=offer.provider_longitude,
        distance_miles=offer.distance_miles,
        match_radius_miles=offer.match_radius_miles,
    )
    db.session.add(match_row)
    if assigned_driver_user_id is not None:
        booking.assigned_driver_user_id = assigned_driver_user_id
    booking.status = 'matched'
    db.session.commit()
    return match_row, 'accepted'


def _drive_time_between_points(origin_latitude, origin_longitude, dest_latitude, dest_longitude):
    api_key = (app.config.get('GOOGLE_MAPS_API_KEY') or '').strip()
    if not api_key:
        return None

    endpoint = 'https://maps.googleapis.com/maps/api/distancematrix/json'
    params = {
        'units': 'imperial',
        'key': api_key,
        'origins': '{},{}'.format(origin_latitude, origin_longitude),
        'destinations': '{},{}'.format(dest_latitude, dest_longitude),
    }
    try:
        response = requests.get(endpoint, params=params, timeout=10)
        payload = response.json()
        if payload.get('status') != 'OK':
            return None
        rows = payload.get('rows') or []
        if not rows:
            return None
        elements = rows[0].get('elements') or []
        if not elements or elements[0].get('status') != 'OK':
            return None
        duration = elements[0].get('duration') or {}
        seconds = _to_int_or_none(duration.get('value'))
        text = (duration.get('text') or '').strip() or None
        if seconds is None:
            return None
        return {
            'minutes': round(seconds / 60.0, 1),
            'text': text or '{} mins'.format(round(seconds / 60.0)),
        }
    except Exception:
        return None


def _require_form_fields(form_data, required_fields):
    """Return stripped field values and raise ValueError for missing required fields."""
    cleaned = {}
    missing = []
    for field in required_fields:
        value = (form_data.get(field) or '').strip()
        cleaned[field] = value
        if not value:
            missing.append(field)
    if missing:
        raise ValueError('Missing required field(s): {}.'.format(', '.join(missing)))
    return cleaned


def _parse_datetime_or_error(value, label):
    try:
        parsed = dateutil.parser.parse(str(value).strip())
    except (TypeError, ValueError, OverflowError):
        raise ValueError('Please provide a valid {}.'.format(label))

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _serialize_waste_request(booking):
    return {
        'id': booking.id,
        'requester_name': booking.requester_name,
        'requester_email': booking.requester_email,
        'material_type': booking.material_type,
        'waste_amount': booking.waste_amount,
        'waste_unit': booking.waste_unit,
        'pickup_address': booking.pickup_address,
        'pickup_city': booking.pickup_city,
        'pickup_county': booking.pickup_county,
        'pickup_postcode': booking.pickup_postcode,
        'scheduled_pickup_at': booking.scheduled_pickup_at.isoformat() if booking.scheduled_pickup_at else None,
        'notes': booking.notes,
        'status': booking.status,
        'assigned_driver_user_id': booking.assigned_driver_user_id,
        'incident_state': booking.incident_state,
        'incident_severity': booking.incident_severity,
        'incident_owner_admin_user_id': booking.incident_owner_admin_user_id,
        'incident_acknowledged_at': (
            booking.incident_acknowledged_at.isoformat() if booking.incident_acknowledged_at else None
        ),
        'incident_resolved_at': booking.incident_resolved_at.isoformat() if booking.incident_resolved_at else None,
        'incident_notes': booking.incident_notes,
        'incident_updated_at': booking.incident_updated_at.isoformat() if booking.incident_updated_at else None,
        'incident_last_escalation_key': booking.incident_last_escalation_key,
        'incident_last_escalated_at': (
            booking.incident_last_escalated_at.isoformat() if booking.incident_last_escalated_at else None
        ),
        'created_at': booking.created_at.isoformat() if booking.created_at else None,
    }


def _serialize_waste_match(match):
    if not match:
        return None
    return {
        'id': match.id,
        'waste_removal_request_id': match.waste_removal_request_id,
        'provider_name': match.provider_name,
        'provider_type': match.provider_type,
        'provider_city': match.provider_city,
        'provider_postcode': match.provider_postcode,
        'provider_latitude': match.provider_latitude,
        'provider_longitude': match.provider_longitude,
        'distance_miles': match.distance_miles,
        'match_radius_miles': match.match_radius_miles,
        'created_at': match.created_at.isoformat() if match.created_at else None,
    }


def _serialize_dispatch_offer(offer, include_token=False):
    if not offer:
        return None
    data = {
        'id': offer.id,
        'waste_removal_request_id': offer.waste_removal_request_id,
        'provider_name': offer.provider_name,
        'provider_type': offer.provider_type,
        'provider_city': offer.provider_city,
        'provider_postcode': offer.provider_postcode,
        'provider_latitude': offer.provider_latitude,
        'provider_longitude': offer.provider_longitude,
        'provider_email': offer.provider_email,
        'provider_phone': offer.provider_phone,
        'distance_miles': offer.distance_miles,
        'match_radius_miles': offer.match_radius_miles,
        'offer_rank': offer.offer_rank,
        'status': offer.status,
        'notified_at': offer.notified_at.isoformat() if offer.notified_at else None,
        'responded_at': offer.responded_at.isoformat() if offer.responded_at else None,
        'created_at': offer.created_at.isoformat() if offer.created_at else None,
    }
    if include_token:
        data['offer_token'] = offer.offer_token
    return data


def _serialize_vehicle_location(location):
    if not location:
        return None
    return {
        'id': location.id,
        'waste_removal_request_id': location.waste_removal_request_id,
        'driver_id': location.driver_id,
        'vehicle_id': location.vehicle_id,
        'latitude': location.latitude,
        'longitude': location.longitude,
        'recorded_at': location.recorded_at.isoformat() if location.recorded_at else None,
        'source': location.source,
        'created_at': location.created_at.isoformat() if location.created_at else None,
    }


def _serialize_dispatch_driver(user):
    if not user:
        return None
    return {
        'id': user.id,
        'email': user.email,
        'name': user.name,
        'role': user.role,
        'is_active': bool(user.is_active_user),
    }


def _minutes_since(timestamp, now=None):
    if not timestamp:
        return None
    now = now or datetime.utcnow()
    return max(0, int((now - timestamp).total_seconds() // 60))


def _dispatch_incident_flags(booking, latest_location=None, now=None):
    if not booking:
        return []

    now = now or datetime.utcnow()
    status = (booking.status or '').strip().lower()
    age_minutes = _minutes_since(booking.created_at, now=now) or 0
    pickup_due_minutes = None
    if booking.scheduled_pickup_at:
        pickup_due_minutes = int((now - booking.scheduled_pickup_at).total_seconds() // 60)

    flags = []
    if status == 'pending_match' and age_minutes >= _dispatch_pending_match_sla_minutes():
        flags.append('stale_pending_match')

    if status in {'matched', 'accepted'} and not booking.assigned_driver_user_id:
        if age_minutes >= _dispatch_unassigned_match_sla_minutes():
            flags.append('matched_without_driver')

    if status in {'en_route', 'arrived', 'collected'}:
        location_age = _minutes_since(getattr(latest_location, 'recorded_at', None), now=now)
        if location_age is None:
            flags.append('missing_driver_location')
        elif location_age >= _dispatch_location_stale_minutes():
            flags.append('stale_driver_location')

    if pickup_due_minutes is not None and pickup_due_minutes > 0 and status not in {'completed', 'cancelled'}:
        flags.append('pickup_overdue')

    return flags


def _dispatch_incident_severity(flags):
    flags = list(flags or [])
    if not flags:
        return None
    if 'pickup_overdue' in flags:
        return 'critical'
    if 'stale_pending_match' in flags or 'matched_without_driver' in flags:
        return 'high'
    if 'stale_driver_location' in flags:
        return 'medium'
    return 'low'


def _dispatch_effective_incident_state(booking, flags):
    flags = list(flags or [])
    stored_state = str(getattr(booking, 'incident_state', '') or '').strip().lower()
    if flags:
        if stored_state in {'acknowledged', 'resolved'}:
            return stored_state
        return 'open'
    if stored_state in {'open', 'acknowledged', 'resolved'}:
        return 'resolved'
    return None


def _dispatch_incident_summary(booking, flags, now=None):
    now = now or datetime.utcnow()
    flags = list(flags or [])
    state = _dispatch_effective_incident_state(booking, flags)
    severity = _dispatch_incident_severity(flags)
    ack_minutes = _minutes_since(getattr(booking, 'incident_acknowledged_at', None), now=now)
    resolve_minutes = _minutes_since(getattr(booking, 'incident_resolved_at', None), now=now)
    created_age_minutes = _minutes_since(getattr(booking, 'created_at', None), now=now) or 0
    ack_sla_minutes = _dispatch_escalation_ack_sla_minutes(severity) if severity else None
    resolve_sla_minutes = _dispatch_escalation_resolve_sla_minutes(severity) if severity else None

    breach_type = None
    breach_minutes = 0
    if state == 'open' and ack_sla_minutes is not None and created_age_minutes > ack_sla_minutes:
        breach_type = 'ack_sla'
        breach_minutes = created_age_minutes - ack_sla_minutes
    elif state == 'acknowledged' and resolve_sla_minutes is not None:
        resolve_window_age = ack_minutes if ack_minutes is not None else created_age_minutes
        if resolve_window_age > resolve_sla_minutes:
            breach_type = 'resolve_sla'
            breach_minutes = resolve_window_age - resolve_sla_minutes

    return {
        'state': state,
        'severity': severity,
        'owner_admin_user_id': booking.incident_owner_admin_user_id,
        'acknowledged_at': (
            booking.incident_acknowledged_at.isoformat() if booking.incident_acknowledged_at else None
        ),
        'resolved_at': booking.incident_resolved_at.isoformat() if booking.incident_resolved_at else None,
        'notes': booking.incident_notes,
        'updated_at': booking.incident_updated_at.isoformat() if booking.incident_updated_at else None,
        'ack_age_minutes': ack_minutes,
        'resolve_age_minutes': resolve_minutes,
        'ack_sla_minutes': ack_sla_minutes,
        'resolve_sla_minutes': resolve_sla_minutes,
        'breach_type': breach_type,
        'breach_minutes': breach_minutes if breach_type else 0,
    }


def _dispatch_escalation_key_for_item(queue_item):
    incident = queue_item.get('incident') or {}
    breach_type = str(incident.get('breach_type') or '').strip().lower()
    severity = str(incident.get('severity') or '').strip().lower()
    request_id = (queue_item.get('request') or {}).get('id')
    if not breach_type or not severity or request_id is None:
        return ''
    return '{}:{}:{}'.format(breach_type, severity, request_id)


def _dispatch_send_escalation_webhook(booking, queue_item, now=None, source=''):
    webhook_url = _dispatch_escalation_webhook_url()
    if not webhook_url:
        return False

    incident = queue_item.get('incident') or {}
    breach_type = str(incident.get('breach_type') or '').strip().lower()
    severity = str(incident.get('severity') or '').strip().lower()
    if not breach_type or not severity:
        return False

    now = now or datetime.utcnow()
    escalation_key = _dispatch_escalation_key_for_item(queue_item)
    if not escalation_key:
        return False

    cooldown_minutes = _dispatch_escalation_cooldown_minutes()
    if (
        booking.incident_last_escalation_key == escalation_key
        and booking.incident_last_escalated_at
        and (now - booking.incident_last_escalated_at).total_seconds() < (cooldown_minutes * 60)
    ):
        return False

    request_data = queue_item.get('request') or {}
    payload = {
        'text': (
            '[Project Divert] Dispatch incident escalation: request #{request_id} '
            '{severity} {breach_type} breach (+{breach_minutes}m)'
        ).format(
            request_id=request_data.get('id'),
            severity=severity.upper(),
            breach_type=breach_type,
            breach_minutes=int(incident.get('breach_minutes') or 0),
        ),
        'request_id': request_data.get('id'),
        'request_status': request_data.get('status'),
        'severity': severity,
        'incident_state': incident.get('state'),
        'breach_type': breach_type,
        'breach_minutes': int(incident.get('breach_minutes') or 0),
        'incident_flags': queue_item.get('incident_flags') or [],
        'assigned_driver_user_id': request_data.get('assigned_driver_user_id'),
        'pickup_postcode': request_data.get('pickup_postcode'),
        'owner_admin_user_id': incident.get('owner_admin_user_id'),
        'source': str(source or ''),
        'occurred_at': now.isoformat() + 'Z',
    }

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=_dispatch_escalation_webhook_timeout_seconds(),
        )
        if response.status_code >= 400:
            app.logger.warning(
                'Dispatch escalation webhook failed status=%s request_id=%s',
                response.status_code,
                request_data.get('id'),
            )
            return False
    except Exception:
        app.logger.exception(
            'Dispatch escalation webhook request failed for request_id=%s',
            request_data.get('id'),
        )
        return False

    booking.incident_last_escalation_key = escalation_key
    booking.incident_last_escalated_at = now
    booking.incident_updated_at = now
    return True


def _serialize_dispatch_queue_item(booking, driver=None, latest_location=None, now=None):
    now = now or datetime.utcnow()
    pickup_due_minutes = None
    if booking.scheduled_pickup_at:
        pickup_due_minutes = int((now - booking.scheduled_pickup_at).total_seconds() // 60)

    incident_flags = _dispatch_incident_flags(booking, latest_location=latest_location, now=now)
    incident = _dispatch_incident_summary(booking, incident_flags, now=now)

    return {
        'request': _serialize_waste_request(booking),
        'driver': _serialize_dispatch_driver(driver),
        'latest_location': _serialize_vehicle_location(latest_location),
        'age_minutes': _minutes_since(booking.created_at, now=now),
        'pickup_due_minutes': pickup_due_minutes,
        'incident_flags': incident_flags,
        'incident': incident,
    }


def _serialize_payment_charge(charge):
    if not charge:
        return None
    return {
        'id': charge.id,
        'waste_removal_request_id': charge.waste_removal_request_id,
        'customer_user_id': charge.customer_user_id,
        'processor': charge.processor,
        'payment_intent_id': charge.payment_intent_id,
        'charge_id': charge.charge_id,
        'amount_minor': charge.amount_minor,
        'currency': charge.currency,
        'platform_fee_minor': charge.platform_fee_minor,
        'driver_payout_minor': charge.driver_payout_minor,
        'status': charge.status,
        'client_secret': charge.client_secret,
        'last_error': charge.last_error,
        'paid_at': charge.paid_at.isoformat() if charge.paid_at else None,
        'refunded_at': charge.refunded_at.isoformat() if charge.refunded_at else None,
        'metadata': charge.metadata_json or {},
        'created_at': charge.created_at.isoformat() if charge.created_at else None,
        'updated_at': charge.updated_at.isoformat() if charge.updated_at else None,
    }


def _serialize_payment_refund(refund):
    if not refund:
        return None
    return {
        'id': refund.id,
        'waste_removal_request_id': refund.waste_removal_request_id,
        'payment_charge_id': refund.payment_charge_id,
        'processor': refund.processor,
        'refund_id': refund.refund_id,
        'amount_minor': refund.amount_minor,
        'currency': refund.currency,
        'status': refund.status,
        'reason': refund.reason,
        'created_at': refund.created_at.isoformat() if refund.created_at else None,
        'updated_at': refund.updated_at.isoformat() if refund.updated_at else None,
    }


def _serialize_driver_payout(payout):
    if not payout:
        return None
    return {
        'id': payout.id,
        'waste_removal_request_id': payout.waste_removal_request_id,
        'payment_charge_id': payout.payment_charge_id,
        'driver_user_id': payout.driver_user_id,
        'processor': payout.processor,
        'payout_id': payout.payout_id,
        'destination_account_id': payout.destination_account_id,
        'amount_minor': payout.amount_minor,
        'currency': payout.currency,
        'status': payout.status,
        'paid_out_at': payout.paid_out_at.isoformat() if payout.paid_out_at else None,
        'created_at': payout.created_at.isoformat() if payout.created_at else None,
        'updated_at': payout.updated_at.isoformat() if payout.updated_at else None,
    }


def _financial_summary_for_request(request_id):
    charges = (
        WastePaymentCharge.query.filter_by(waste_removal_request_id=request_id)
        .order_by(WastePaymentCharge.created_at.desc(), WastePaymentCharge.id.desc())
        .all()
    )
    refunds = (
        WastePaymentRefund.query.filter_by(waste_removal_request_id=request_id)
        .order_by(WastePaymentRefund.created_at.desc(), WastePaymentRefund.id.desc())
        .all()
    )
    payouts = (
        WasteDriverPayout.query.filter_by(waste_removal_request_id=request_id)
        .order_by(WasteDriverPayout.created_at.desc(), WasteDriverPayout.id.desc())
        .all()
    )
    total_charged_minor = sum(
        charge.amount_minor
        for charge in charges
        if (charge.status or '').lower() in {'succeeded', 'requires_capture', 'partially_refunded', 'refunded'}
    )
    total_refunded_minor = sum(refund.amount_minor for refund in refunds if (refund.status or '').lower() != 'failed')
    total_payout_minor = sum(payout.amount_minor for payout in payouts if (payout.status or '').lower() in {'paid', 'completed'})
    return {
        'charges': [_serialize_payment_charge(charge) for charge in charges],
        'refunds': [_serialize_payment_refund(refund) for refund in refunds],
        'payouts': [_serialize_driver_payout(payout) for payout in payouts],
        'totals': {
            'charged_minor': total_charged_minor,
            'refunded_minor': total_refunded_minor,
            'paid_out_minor': total_payout_minor,
            'platform_net_minor': total_charged_minor - total_refunded_minor - total_payout_minor,
        },
    }


_waste_request_event_subscribers = {}
_waste_request_event_lock = threading.Lock()
_waste_request_event_queue_size = 100
_waste_request_event_history = {}
_waste_request_event_sequence = 0
_waste_request_event_history_size = max(
    20,
    int(app.config.get('WASTE_REQUEST_STREAM_HISTORY_SIZE') or 200),
)


def _serialize_waste_request_snapshot(booking):
    if not booking:
        return None

    match_row = _get_latest_match_for_request(booking.id)
    latest_location = (
        WasteRemovalVehicleLocation.query.filter_by(waste_removal_request_id=booking.id)
        .order_by(WasteRemovalVehicleLocation.recorded_at.desc(), WasteRemovalVehicleLocation.id.desc())
        .first()
    )
    return {
        'request': _serialize_waste_request(booking),
        'match': _serialize_waste_match(match_row),
        'latest_location': _serialize_vehicle_location(latest_location),
        'dispatch': _dispatch_summary_for_request(booking.id),
        'financials': _financial_summary_for_request(booking.id),
    }


def _record_dispatch_incident_event(
    waste_removal_request_id,
    event_type,
    actor_user_id=None,
    actor_email=None,
    source='system',
    details=None,
    occurred_at=None,
):
    request_id = _to_int_or_none(waste_removal_request_id)
    if request_id is None:
        return None
    normalized_type = (str(event_type or '').strip().lower() or 'unknown')[:64]
    normalized_source = (str(source or '').strip().lower() or 'system')[:64]
    row = DispatchIncidentEvent(
        waste_removal_request_id=request_id,
        event_type=normalized_type,
        actor_user_id=_to_int_or_none(actor_user_id),
        actor_email=(_normalize_email(actor_email) or None),
        source=normalized_source,
        details_json=_normalize_auth_audit_details(details),
        created_at=occurred_at or datetime.utcnow(),
    )
    db.session.add(row)
    return row


def _build_dispatch_request_timeline(
    booking,
    include_actor_auth=True,
    auth_window_hours=168,
    limit=200,
):
    if not booking:
        return [], {'total_events': 0, 'category_counts': {}}

    try:
        limit = max(1, min(500, int(limit)))
    except (TypeError, ValueError):
        limit = 200
    try:
        auth_window_hours = max(1, min(24 * 30, int(auth_window_hours)))
    except (TypeError, ValueError):
        auth_window_hours = 168

    rows = []
    actor_user_ids = set()

    def _append_event(
        category,
        event_type,
        occurred_at,
        source='system',
        event_id='',
        actor_user_id=None,
        actor_email=None,
        details=None,
    ):
        if not occurred_at:
            return
        normalized_actor_user_id = _to_int_or_none(actor_user_id)
        if normalized_actor_user_id is not None:
            actor_user_ids.add(normalized_actor_user_id)

        rows.append(
            {
                '_occurred_at': occurred_at,
                '_sort_id': str(event_id or ''),
                'id': str(event_id or ''),
                'category': str(category or 'system'),
                'event_type': str(event_type or 'unknown'),
                'source': str(source or 'system'),
                'occurred_at': occurred_at.isoformat() + 'Z',
                'actor_user_id': normalized_actor_user_id,
                'actor_email': _normalize_email(actor_email) or None,
                'actor_name': None,
                'details': _normalize_auth_audit_details(details),
            }
        )

    _append_event(
        'system',
        'request_created',
        booking.created_at,
        source='waste_request',
        event_id='request_created:{}'.format(booking.id),
        actor_email=booking.requester_email,
        details={
            'status': booking.status,
            'material_type': booking.material_type,
            'scheduled_pickup_at': booking.scheduled_pickup_at.isoformat() if booking.scheduled_pickup_at else None,
        },
    )

    match_rows = (
        WasteRemovalMatch.query.filter_by(waste_removal_request_id=booking.id)
        .order_by(WasteRemovalMatch.created_at.asc(), WasteRemovalMatch.id.asc())
        .all()
    )
    for match_row in match_rows:
        _append_event(
            'system',
            'dispatch_match_created',
            match_row.created_at,
            source='matching',
            event_id='match:{}'.format(match_row.id),
            details={
                'provider_name': match_row.provider_name,
                'provider_type': match_row.provider_type,
                'distance_miles': match_row.distance_miles,
                'match_radius_miles': match_row.match_radius_miles,
            },
        )

    accepted_offer_rows = (
        WasteRemovalDispatchOffer.query.filter_by(
            waste_removal_request_id=booking.id,
            status='accepted',
        )
        .order_by(WasteRemovalDispatchOffer.responded_at.asc(), WasteRemovalDispatchOffer.id.asc())
        .all()
    )
    for offer_row in accepted_offer_rows:
        _append_event(
            'system',
            'dispatch_offer_accepted',
            offer_row.responded_at or offer_row.created_at,
            source='dispatch_offer',
            event_id='offer:{}'.format(offer_row.id),
            details={
                'provider_name': offer_row.provider_name,
                'distance_miles': offer_row.distance_miles,
                'offer_rank': offer_row.offer_rank,
            },
        )

    if booking.incident_acknowledged_at:
        _append_event(
            'system',
            'incident_acknowledged_state',
            booking.incident_acknowledged_at,
            source='incident_state',
            event_id='incident_ack_state:{}'.format(booking.id),
            actor_user_id=booking.incident_owner_admin_user_id,
            details={'incident_state': booking.incident_state, 'incident_severity': booking.incident_severity},
        )
    if booking.incident_resolved_at:
        _append_event(
            'system',
            'incident_resolved_state',
            booking.incident_resolved_at,
            source='incident_state',
            event_id='incident_resolved_state:{}'.format(booking.id),
            actor_user_id=booking.incident_owner_admin_user_id,
            details={'incident_state': booking.incident_state, 'incident_severity': booking.incident_severity},
        )

    incident_event_rows = (
        DispatchIncidentEvent.query.filter_by(waste_removal_request_id=booking.id)
        .order_by(DispatchIncidentEvent.created_at.asc(), DispatchIncidentEvent.id.asc())
        .all()
    )
    for incident_row in incident_event_rows:
        _append_event(
            'dispatch',
            incident_row.event_type,
            incident_row.created_at,
            source=incident_row.source,
            event_id='dispatch_event:{}'.format(incident_row.id),
            actor_user_id=incident_row.actor_user_id,
            actor_email=incident_row.actor_email,
            details=incident_row.details_json or {},
        )

    if include_actor_auth and actor_user_ids:
        auth_since = datetime.utcnow() - timedelta(hours=auth_window_hours)
        auth_rows = (
            AuthAuditEvent.query.filter(
                AuthAuditEvent.user_id.in_(sorted(actor_user_ids)),
                AuthAuditEvent.occurred_at >= auth_since,
            )
            .order_by(AuthAuditEvent.occurred_at.asc(), AuthAuditEvent.id.asc())
            .all()
        )
        for auth_row in auth_rows:
            _append_event(
                'auth',
                'auth_{}'.format(auth_row.event),
                auth_row.occurred_at,
                source='auth_audit',
                event_id='auth_audit:{}'.format(auth_row.id),
                actor_user_id=auth_row.user_id,
                actor_email=auth_row.email,
                details={
                    'success': bool(auth_row.success),
                    'status_code': auth_row.status_code,
                    'ip': auth_row.ip,
                    'user_agent': auth_row.user_agent,
                    'auth_details': auth_row.details_json or {},
                },
            )

    user_map = {}
    if actor_user_ids:
        user_rows = User.query.filter(User.id.in_(sorted(actor_user_ids))).all()
        user_map = {row.id: row for row in user_rows}

    for row in rows:
        actor_user_id = row.get('actor_user_id')
        actor_user = user_map.get(actor_user_id) if actor_user_id is not None else None
        if actor_user:
            row['actor_name'] = (actor_user.name or actor_user.email or '').strip() or None
            if not row.get('actor_email'):
                row['actor_email'] = _normalize_email(actor_user.email) or None

    rows.sort(key=lambda item: (item['_occurred_at'], item['_sort_id']), reverse=True)
    rows = rows[:limit]
    category_counts = {}
    for row in rows:
        category_key = row.get('category') or 'unknown'
        category_counts[category_key] = category_counts.get(category_key, 0) + 1
        row.pop('_occurred_at', None)
        row.pop('_sort_id', None)

    return rows, {
        'total_events': len(rows),
        'category_counts': category_counts,
    }


def _subscribe_waste_request_events(request_id):
    channel = queue.Queue(maxsize=_waste_request_event_queue_size)
    with _waste_request_event_lock:
        subscribers = _waste_request_event_subscribers.setdefault(request_id, set())
        subscribers.add(channel)
    return channel


def _unsubscribe_waste_request_events(request_id, channel):
    with _waste_request_event_lock:
        subscribers = _waste_request_event_subscribers.get(request_id)
        if not subscribers:
            return
        subscribers.discard(channel)
        if not subscribers:
            _waste_request_event_subscribers.pop(request_id, None)


def _parse_waste_request_last_event_id(value):
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def _waste_request_replay_events_since(request_id, event_id):
    if event_id is None:
        return []
    with _waste_request_event_lock:
        history = list(_waste_request_event_history.get(request_id, ()))
    return [row for row in history if _parse_waste_request_last_event_id(row.get('event_id')) is not None and int(row['event_id']) > event_id]


def _publish_waste_request_event(request_id, event_name, payload=None, metadata=None):
    global _waste_request_event_sequence
    with _waste_request_event_lock:
        _waste_request_event_sequence += 1
        event_payload = {
            'event_id': _waste_request_event_sequence,
            'event': str(event_name or 'update').strip() or 'update',
            'request_id': request_id,
            'occurred_at': datetime.utcnow().isoformat() + 'Z',
            'payload': payload,
            'metadata': metadata or {},
        }
        history = _waste_request_event_history.setdefault(
            request_id,
            deque(maxlen=_waste_request_event_history_size),
        )
        history.append(event_payload)
        channels = list(_waste_request_event_subscribers.get(request_id, set()))

    for channel in channels:
        try:
            channel.put_nowait(event_payload)
        except queue.Full:
            try:
                channel.get_nowait()
                channel.put_nowait(event_payload)
            except Exception:
                _unsubscribe_waste_request_events(request_id, channel)
        except Exception:
            _unsubscribe_waste_request_events(request_id, channel)


def _format_sse_event(event_name, payload, event_id=None):
    frame_lines = []
    if event_id is not None:
        frame_lines.append('id: {}'.format(event_id))
    frame_lines.append('event: {}'.format(event_name))
    frame_lines.append('data: {}'.format(json.dumps(payload, separators=(',', ':'))))
    return '\n'.join(frame_lines) + '\n\n'


def _is_truthy(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _expo_push_is_enabled():
    return _is_truthy(app.config.get('EXPO_PUSH_ENABLED', True))


def _requester_user_id_for_booking(booking):
    if not booking:
        return None
    email = (booking.requester_email or '').strip().lower()
    if not email:
        return None
    user = User.query.filter(func.lower(User.email) == email).first()
    return user.id if user else None


def _active_push_tokens_for_users(user_ids):
    if not user_ids:
        return []
    rows = (
        MobilePushSubscription.query.filter(
            MobilePushSubscription.user_id.in_(list(user_ids)),
            MobilePushSubscription.is_active.is_(True),
            MobilePushSubscription.provider == 'expo',
        )
        .order_by(MobilePushSubscription.updated_at.desc(), MobilePushSubscription.id.desc())
        .all()
    )
    tokens = []
    seen = set()
    for row in rows:
        token = (row.token or '').strip()
        if not token or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _send_expo_push_messages(messages):
    if not messages or not _expo_push_is_enabled():
        return 0

    endpoint = (
        app.config.get('EXPO_PUSH_API_URL')
        or 'https://exp.host/--/api/v2/push/send'
    )
    access_token = (app.config.get('EXPO_PUSH_ACCESS_TOKEN') or '').strip()
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    if access_token:
        headers['Authorization'] = 'Bearer {}'.format(access_token)

    delivered = 0
    chunk_size = 100
    for start in range(0, len(messages), chunk_size):
        chunk = messages[start:start + chunk_size]
        try:
            response = requests.post(endpoint, json=chunk, headers=headers, timeout=8)
            if response.status_code >= 400:
                app.logger.warning(
                    'Expo push request failed status=%s body=%s',
                    response.status_code,
                    response.text[:400],
                )
                continue
            delivered += len(chunk)
        except Exception:
            app.logger.exception('Expo push delivery failed.')
    return delivered


def _send_push_notification_to_users(user_ids, title, body, data=None):
    tokens = _active_push_tokens_for_users(user_ids)
    if not tokens:
        return 0
    messages = []
    for token in tokens:
        messages.append(
            {
                'to': token,
                'title': title,
                'body': body,
                'sound': 'default',
                'priority': 'high',
                'data': data or {},
            }
        )
    return _send_expo_push_messages(messages)


def _notify_mobile_push_for_waste_event(booking, event_name, metadata=None):
    if not booking:
        return 0

    requester_user_id = _requester_user_id_for_booking(booking)
    recipients = set()
    if requester_user_id:
        recipients.add(requester_user_id)
    if booking.assigned_driver_user_id:
        recipients.add(booking.assigned_driver_user_id)
    if not recipients:
        return 0

    metadata = metadata or {}
    status = (booking.status or '').strip().lower() or 'unknown'
    if event_name == 'request_created':
        title = 'Request submitted'
        body = 'Request #{} is now live.'.format(booking.id)
    elif event_name == 'dispatch_offer_accepted':
        title = 'Driver matched'
        body = 'Request #{} has been matched.'.format(booking.id)
    elif event_name == 'status_updated':
        title = 'Status update'
        body = 'Request #{} is now {}.'.format(
            booking.id,
            status.replace('_', ' '),
        )
    elif event_name == 'payment_succeeded':
        title = 'Payment received'
        body = 'Payment succeeded for request #{}.'.format(booking.id)
    elif event_name == 'refund_processed':
        title = 'Refund processed'
        body = 'Refund issued for request #{}.'.format(booking.id)
    elif event_name == 'payout_processed':
        title = 'Driver payout sent'
        body = 'Driver payout was processed for request #{}.'.format(booking.id)
    elif event_name == 'admin_dispatch_override':
        title = 'Dispatch assignment updated'
        if booking.assigned_driver_user_id:
            body = 'Driver assignment updated for request #{}.'.format(booking.id)
        else:
            body = 'Driver assignment removed for request #{}.'.format(booking.id)
    else:
        return 0

    return _send_push_notification_to_users(
        recipients,
        title,
        body,
        data={
            'event': event_name,
            'request_id': booking.id,
            'status': status,
            'metadata': metadata,
        },
    )


def _platform_fee_bps():
    raw = app.config.get('PLATFORM_FEE_BPS', 1500)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 1500
    return max(0, min(9500, value))


def _platform_currency():
    return (app.config.get('PLATFORM_CURRENCY') or 'gbp').strip().lower() or 'gbp'


def _payments_enabled():
    return _is_truthy(app.config.get('PAYMENTS_ENABLED', False))


def _compute_fee_split(amount_minor, platform_fee_bps=None):
    fee_bps = _platform_fee_bps() if platform_fee_bps is None else int(platform_fee_bps)
    fee_bps = max(0, min(9500, fee_bps))
    platform_fee_minor = int(round((amount_minor * fee_bps) / 10000.0))
    driver_payout_minor = max(0, amount_minor - platform_fee_minor)
    return platform_fee_minor, driver_payout_minor


def _stripe_secret_key():
    return (app.config.get('STRIPE_SECRET_KEY') or '').strip()


def _stripe_webhook_secret():
    return (app.config.get('STRIPE_WEBHOOK_SECRET') or '').strip()


def _stripe_api_base():
    return (app.config.get('STRIPE_API_BASE_URL') or 'https://api.stripe.com').strip().rstrip('/')


def _stripe_is_configured():
    return bool(_stripe_secret_key())


def _stripe_request(method, path, data=None, idempotency_key=None):
    secret_key = _stripe_secret_key()
    if not secret_key:
        raise ValueError('Stripe is not configured. Set STRIPE_SECRET_KEY.')

    url = '{}{}'.format(_stripe_api_base(), path)
    headers = {
        'Authorization': 'Bearer {}'.format(secret_key),
        'Accept': 'application/json',
    }
    if idempotency_key:
        headers['Idempotency-Key'] = str(idempotency_key).strip()

    request_data = {}
    for key, value in (data or {}).items():
        if value is None:
            continue
        request_data[key] = str(value)

    try:
        response = requests.request(
            method.upper(),
            url,
            data=request_data,
            headers=headers,
            timeout=20,
        )
    except Exception as exc:
        raise ValueError('Stripe request failed: {}'.format(exc))

    try:
        payload = response.json()
    except Exception:
        payload = {'raw': response.text}

    if response.status_code >= 400:
        error_info = payload.get('error') if isinstance(payload, dict) else None
        if isinstance(error_info, dict):
            message = error_info.get('message') or 'Stripe request failed'
        else:
            message = 'Stripe request failed'
        raise ValueError('{} (HTTP {})'.format(message, response.status_code))

    if not isinstance(payload, dict):
        raise ValueError('Stripe response was invalid.')
    return payload


def _payment_status_from_stripe_intent(intent_status):
    status = (intent_status or '').strip().lower()
    if status == 'succeeded':
        return 'succeeded'
    if status in {'requires_payment_method', 'requires_confirmation', 'requires_action'}:
        return 'requires_payment_method'
    if status in {'requires_capture'}:
        return 'requires_capture'
    if status in {'processing'}:
        return 'processing'
    if status in {'canceled'}:
        return 'cancelled'
    return status or 'pending'


def _stripe_charge_id_from_payment_intent(payment_intent_payload):
    if not isinstance(payment_intent_payload, dict):
        return None
    latest_charge = payment_intent_payload.get('latest_charge')
    if isinstance(latest_charge, str):
        return latest_charge.strip() or None
    charges = ((payment_intent_payload.get('charges') or {}).get('data') or [])
    if charges and isinstance(charges[0], dict):
        return (charges[0].get('id') or '').strip() or None
    return None


def _sync_charge_from_payment_intent(charge_row, payment_intent_payload):
    mapped_status = _payment_status_from_stripe_intent(payment_intent_payload.get('status'))
    charge_row.status = mapped_status
    charge_row.payment_intent_id = (payment_intent_payload.get('id') or '').strip() or charge_row.payment_intent_id
    charge_row.client_secret = (payment_intent_payload.get('client_secret') or '').strip() or charge_row.client_secret
    charge_row.charge_id = _stripe_charge_id_from_payment_intent(payment_intent_payload)
    charge_row.processor_response = payment_intent_payload
    if mapped_status == 'succeeded':
        charge_row.paid_at = datetime.utcnow()
        charge_row.last_error = None
    return charge_row


def _parse_stripe_signature_header(signature_header):
    parts = {}
    for raw_part in str(signature_header or '').split(','):
        segment = raw_part.strip()
        if '=' not in segment:
            continue
        key, value = segment.split('=', 1)
        parts.setdefault(key.strip(), []).append(value.strip())
    return parts


def _verify_stripe_webhook_signature(payload_raw, signature_header):
    webhook_secret = _stripe_webhook_secret()
    if not webhook_secret:
        return False
    parsed = _parse_stripe_signature_header(signature_header)
    timestamp = (parsed.get('t') or [None])[0]
    v1_signatures = parsed.get('v1') or []
    if not timestamp or not v1_signatures:
        return False

    signed_payload = '{}.{}'.format(timestamp, payload_raw.decode('utf-8'))
    expected = hmac.new(
        webhook_secret.encode('utf-8'),
        signed_payload.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    for candidate in v1_signatures:
        if hmac.compare_digest(expected, candidate):
            return True
    return False


def _refund_status_from_stripe(refund_status):
    status = (refund_status or '').strip().lower()
    if status in {'succeeded'}:
        return 'succeeded'
    if status in {'pending', 'requires_action'}:
        return 'pending'
    if status in {'failed', 'canceled'}:
        return 'failed'
    return status or 'pending'


def _payout_status_from_stripe(payload):
    if not isinstance(payload, dict):
        return 'unknown'

    status = (payload.get('status') or '').strip().lower()
    if status in {'paid', 'completed'}:
        return 'paid'
    if status in {'pending', 'in_transit'}:
        return 'processing'
    if status in {'failed', 'canceled'}:
        return 'failed'

    try:
        amount_reversed = int(payload.get('amount_reversed') or 0)
    except (TypeError, ValueError):
        amount_reversed = 0
    if amount_reversed > 0:
        return 'reversed'

    # Stripe transfer objects often have no status field; success means accepted.
    return 'paid'


def _remaining_refundable_minor(charge_row):
    if not charge_row:
        return 0
    refunded_minor = (
        db.session.query(func.coalesce(func.sum(WastePaymentRefund.amount_minor), 0))
        .filter(
            WastePaymentRefund.payment_charge_id == charge_row.id,
            WastePaymentRefund.status.notin_(['failed']),
        )
        .scalar()
    ) or 0
    return max(0, int(charge_row.amount_minor or 0) - int(refunded_minor))


def _remaining_driver_payout_minor(charge_row):
    if not charge_row:
        return 0
    paid_out_minor = (
        db.session.query(func.coalesce(func.sum(WasteDriverPayout.amount_minor), 0))
        .filter(
            WasteDriverPayout.payment_charge_id == charge_row.id,
            WasteDriverPayout.status.notin_(['failed', 'cancelled', 'reversed']),
        )
        .scalar()
    ) or 0
    return max(0, int(charge_row.driver_payout_minor or 0) - int(paid_out_minor))


def _normalize_material_name(value):
    if value is None:
        return ''
    cleaned = str(value).replace('\xa0', ' ').strip().lower()
    return ' '.join(cleaned.split())


def _material_factor_key(frame, material_name):
    target = _normalize_material_name(material_name)
    if not target:
        return None
    for key in frame.index.to_list():
        if _normalize_material_name(key) == target:
            return key
    return None


def _factor_value(frame, row_key, column_name):
    value = frame.loc[row_key, column_name]
    if hasattr(value, 'iloc'):
        value = value.iloc[0]
    return float(value)


def _seed_materials_if_empty():
    try:
        if m.query.first() is not None:
            return

        csv_path = os.path.join(app.root_path, 'material_sheet.csv')
        if not os.path.exists(csv_path):
            app.logger.warning('No material seed file found at %s', csv_path)
            return

        seeded_count = 0
        with open(csv_path, newline='', encoding='utf-8-sig') as handle:
            for row in csv.DictReader(handle):
                waste_stream = (row.get('waste_stream') or '').strip()
                if not waste_stream:
                    continue

                db.session.add(
                    m(
                        waste_stream=waste_stream,
                        amount=_to_int_or_none(row.get('amount')),
                        address=(row.get('address') or '').strip() or None,
                        city=(row.get('city') or '').strip() or None,
                        county=(row.get('county') or '').strip() or None,
                        postcode=(row.get('postcode') or '').strip() or None,
                        condition=(row.get('condition') or '').strip() or None,
                        dimensions=(row.get('dimensions') or '').strip() or None,
                        image_link1=(row.get('image_link1') or '').strip() or None,
                        image_link2=(row.get('image_link2') or '').strip() or None,
                        image_link3=(row.get('image_link3') or '').strip() or None,
                        longitude=_to_float_or_none(row.get('longitude')),
                        latitude=_to_float_or_none(row.get('latitude')),
                    )
                )
                seeded_count += 1

        if seeded_count:
            db.session.commit()
            app.logger.info('Seeded %s materials from material_sheet.csv', seeded_count)
    except Exception:
        db.session.rollback()
        app.logger.exception('Failed to seed materials from material_sheet.csv.')


@app.before_request
def ensure_core_tables():
    # Create core tables on first request if missing.
    if getattr(app, '_core_tables_checked', False):
        return
    try:
        db.create_all()
        _seed_materials_if_empty()
        app._core_tables_checked = True
    except Exception:
        app.logger.exception('Failed creating core tables on startup.')
#----------------------------------------------------------------------------#
# Filters.
#----------------------------------------------------------------------------#

def format_datetime(value, format='medium'):
    date = dateutil.parser.parse(value)
    if format == 'full':
        format="EEEE MMMM, d, y 'at' h:mma"
    elif format == 'medium':
        format="EE MM, dd, y h:mma"
    return babel.dates.format_datetime(date, format)

app.jinja_env.filters['datetime'] = format_datetime

ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}
MAX_MATERIAL_IMAGES = 10


def normalize_image_filename(image_ref):
    value = str(image_ref or '').strip()
    if not value:
        return ''
    basename = os.path.basename(value)
    if '.' in basename:
        return basename
    return basename + '.png'


app.jinja_env.filters['image_file'] = normalize_image_filename


def _save_material_image(uploaded_file):
    if not uploaded_file or not uploaded_file.filename:
        return ''

    original_name = secure_filename(uploaded_file.filename)
    _stem, ext = os.path.splitext(original_name)
    ext = ext.lower()

    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError('Only PNG, JPG, JPEG, and WEBP images are supported.')

    unique_name = '{}{}'.format(uuid.uuid4().hex[:12], ext)
    target_dir = os.path.join(app.static_folder, 'img')
    os.makedirs(target_dir, exist_ok=True)
    uploaded_file.save(os.path.join(target_dir, unique_name))
    return unique_name


def _save_material_images(uploaded_files, limit=MAX_MATERIAL_IMAGES):
    saved = []
    for uploaded_file in uploaded_files[:limit]:
        saved_name = _save_material_image(uploaded_file)
        if saved_name:
            saved.append(saved_name)
    return saved


def _send_material_request_email(to_email, subject, text_body, html_body=None):
    provider = (app.config.get('MAIL_PROVIDER') or 'console').strip().lower()

    if provider == 'console':
        app.logger.info('MAIL(console) to=%s subject=%s body=%s', to_email, subject, text_body)
        return True

    if provider == 'sendgrid':
        api_key = app.config.get('SENDGRID_API_KEY', '')
        from_email = app.config.get('MAIL_FROM_EMAIL', 'noreply@example.com')
        if not api_key:
            app.logger.error('SENDGRID_API_KEY missing; email not sent.')
            return False

        payload = {
            'personalizations': [{'to': [{'email': to_email}], 'subject': subject}],
            'from': {'email': from_email},
            'content': [{'type': 'text/plain', 'value': text_body}],
        }
        if html_body:
            payload['content'].append({'type': 'text/html', 'value': html_body})

        try:
            response = requests.post(
                'https://api.sendgrid.com/v3/mail/send',
                headers={
                    'Authorization': 'Bearer {}'.format(api_key),
                    'Content-Type': 'application/json',
                },
                data=json.dumps(payload),
                timeout=15,
            )
            if 200 <= response.status_code < 300:
                return True
            app.logger.error('SendGrid email failed status=%s body=%s', response.status_code, response.text[:500])
            return False
        except Exception:
            app.logger.exception('SendGrid email request failed.')
            return False

    app.logger.error('Unknown MAIL_PROVIDER=%s', provider)
    return False


def _decode_material_images(image_link1, image_link2, image_link3):
    refs = [
        str(image_link1 or '').strip(),
        str(image_link2 or '').strip(),
        str(image_link3 or '').strip(),
    ]
    if not any(refs):
        return []

    combined = ''.join(refs)
    images = []
    if combined.startswith('multi:'):
        payload = combined[len('multi:'):]
        images = [normalize_image_filename(item) for item in payload.split(',') if item.strip()]
    else:
        images = [normalize_image_filename(item) for item in refs if item]

    return images[:MAX_MATERIAL_IMAGES]


def _encode_material_images(image_refs):
    normalized = [normalize_image_filename(item) for item in image_refs if str(item or '').strip()]
    normalized = normalized[:MAX_MATERIAL_IMAGES]
    if not normalized:
        return '', '', ''

    payload = 'multi:' + ','.join(normalized)
    if len(payload) > 360:
        raise ValueError('Image filenames are too long. Please use fewer images or shorter filenames.')

    part1 = payload[:120]
    part2 = payload[120:240] if len(payload) > 120 else ''
    part3 = payload[240:360] if len(payload) > 240 else ''
    return part1, part2, part3


def _serialize_material(material):
    image_links = _decode_material_images(material.image_link1, material.image_link2, material.image_link3)
    return {
        "id": material.id,
        "material": material.waste_stream,
        "amount": material.amount,
        "condition": material.condition,
        "postcode": material.postcode,
        "image_link1": material.image_link1,
        "image_link2": material.image_link2,
        "image_link3": material.image_link3,
        "image_links": image_links,
    }


def _group_materials(materials):
    grouped = {}
    for material in materials:
        city = material.city if material.city else "Unknown"
        county = material.county if material.county else "Unknown"
        key = (city, county)
        grouped.setdefault(key, []).append(_serialize_material(material))

    data = []
    for city, county in sorted(grouped.keys()):
        data.append(
            {
                "city": city,
                "county": county,
                "materials": grouped[(city, county)],
            }
        )
    return data

#----------------------------------------------------------------------------#
# Controllers.
#----------------------------------------------------------------------------#
@app.route('/first', methods=['GET'])
def first_get():
    form = FilterForm()
    return render_template('forms/first.html', form=form)

@app.route('/first', methods=['POST'])
def first_post():
    postcode = request.form.get('postcode', '').strip()
    radius = request.form.get('radius', '').strip()
    if not postcode or not radius:
        flash('Please provide both postcode and radius.')
        return redirect('/first')
    return redirect(f"/materials?postcode={postcode}&radius={radius}")

@app.route('/map')
def map():
    postcode = request.args.get('postcode', '').strip()
    radius_raw = request.args.get('radius', '').strip()
    filter_applied = False

    materials_query = m.query.filter(m.latitude.isnot(None), m.longitude.isnot(None))
    materials_with_coords = materials_query.all()

    if postcode and radius_raw:
        try:
            radius_miles = int(radius_raw)
            if radius_miles <= 0:
                raise ValueError
            endpoint = "http://api.postcodes.io/postcodes/{}".format(postcode)
            resp = requests.get(endpoint, timeout=10)
            payload = resp.json()
            result = payload.get('result')
            if not result:
                raise ValueError

            target_long = result.get('longitude')
            target_lat = result.get('latitude')
            radius_km = radius_miles * 1.60934
            materials_with_coords = materials_query.filter(
                func.acos(
                    func.sin(func.radians(target_lat)) * func.sin(func.radians(m.latitude))
                    + func.cos(func.radians(target_lat))
                    * func.cos(func.radians(m.latitude))
                    * func.cos(func.radians(m.longitude) - (func.radians(target_long)))
                )
                * 6371
                <= radius_km
            ).all()
            filter_applied = True
        except Exception:
            flash('Could not apply postcode/radius map filter. Showing all mapped materials.')

    markers = []
    for material in materials_with_coords:
        image_links = _decode_material_images(material.image_link1, material.image_link2, material.image_link3)
        markers.append(
            {
                "id": material.id,
                "material": material.waste_stream,
                "amount": material.amount,
                "city": material.city,
                "county": material.county,
                "postcode": material.postcode,
                "lat": material.latitude,
                "lng": material.longitude,
                "preview_image": image_links[0] if image_links else '',
            }
        )
    return render_template(
        'pages/map.html',
        markers=markers,
        google_maps_api_key=app.config.get('GOOGLE_MAPS_API_KEY') or '',
        filter_postcode=postcode,
        filter_radius=radius_raw,
        filter_applied=filter_applied,
    )

@app.route('/')
def index():
    return redirect('/materials')

@app.route('/home')
def home():
    return render_template('pages/home.html')

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    setup_form = CharityForm1()

    if current_user.is_authenticated:
        return redirect('/materials')

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()

        if not email or not password:
            flash('Please enter both email and password.')
            return render_template('pages/login.html', form=setup_form), 400

        user = User.query.filter(func.lower(User.email) == email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash('Invalid email or password.')
            return render_template('pages/login.html', form=setup_form), 401

        login_user(user)
        flash('Logged in successfully.')
        next_url = request.args.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('/materials')

    return render_template('pages/login.html', form=setup_form)


@app.route('/register', methods=['GET', 'POST'])
def register_page():
    if current_user.is_authenticated:
        return redirect('/materials')

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not name or not email or not password:
            flash('Please complete all required fields.')
            return render_template('pages/register.html'), 400
        if password != confirm_password:
            flash('Passwords do not match.')
            return render_template('pages/register.html'), 400
        if len(password) < 8:
            flash('Password must be at least 8 characters.')
            return render_template('pages/register.html'), 400
        if User.query.filter(func.lower(User.email) == email).first():
            flash('An account with that email already exists.')
            return render_template('pages/register.html'), 409

        try:
            user = User(
                name=name[:120],
                email=email,
                password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
                role='customer',
            )
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash('Account created successfully.')
            return redirect('/materials')
        except Exception:
            db.session.rollback()
            app.logger.exception('Registration failed.')
            flash('Could not create account right now.')
            return render_template('pages/register.html'), 500

    return render_template('pages/register.html')


@app.route('/logout', methods=['POST'])
@login_required
def logout_page():
    logout_user()
    flash('You have been logged out.')
    return redirect('/materials')


def _current_user_is_admin():
    return bool(
        current_user.is_authenticated
        and str(getattr(current_user, 'role', '') or '').strip().lower() == 'admin'
    )


@app.route('/admin/dispatch', methods=['GET'])
@login_required
def admin_dispatch_board():
    if not _current_user_is_admin():
        flash('Admin access is required.')
        return redirect('/login'), 403

    status_options = [
        'pending_match',
        'matched',
        'accepted',
        'en_route',
        'arrived',
        'collected',
        'completed',
        'cancelled',
    ]
    default_statuses = [
        'pending_match',
        'matched',
        'accepted',
        'en_route',
        'arrived',
        'collected',
    ]

    statuses_raw = str(request.args.get('statuses') or '').strip().lower()
    if statuses_raw:
        selected_statuses = [part.strip() for part in statuses_raw.split(',') if part.strip()]
        invalid_statuses = sorted({status for status in selected_statuses if status not in status_options})
        if invalid_statuses:
            flash('Ignoring invalid statuses: {}.'.format(', '.join(invalid_statuses)))
            selected_statuses = [status for status in selected_statuses if status in status_options]
    else:
        selected_statuses = list(default_statuses)
    if not selected_statuses:
        selected_statuses = list(default_statuses)

    try:
        assigned_filter = _parse_optional_bool_query(request.args.get('assigned'), 'assigned')
        incidents_only = bool(_parse_optional_bool_query(request.args.get('incidents_only'), 'incidents_only'))
        incident_state_filter = (
            str(request.args.get('incident_state') or '').strip().lower() or 'all'
        )
        if incident_state_filter not in {'all', 'open', 'acknowledged', 'resolved'}:
            raise ValueError('incident_state must be one of all, open, acknowledged, resolved')
    except ValueError:
        flash('Invalid filters supplied. Showing default queue.')
        assigned_filter = None
        incidents_only = False
        incident_state_filter = 'all'

    drivers = (
        User.query.filter(func.lower(User.role) == 'driver', User.is_active_user.is_(True))
        .order_by(func.lower(func.coalesce(User.name, User.email)).asc(), User.id.asc())
        .all()
    )
    admins = (
        User.query.filter(func.lower(User.role) == 'admin', User.is_active_user.is_(True))
        .order_by(func.lower(func.coalesce(User.name, User.email)).asc(), User.id.asc())
        .all()
    )

    query = WasteRemovalRequest.query.filter(WasteRemovalRequest.status.in_(selected_statuses))
    if assigned_filter is True:
        query = query.filter(WasteRemovalRequest.assigned_driver_user_id.isnot(None))
    elif assigned_filter is False:
        query = query.filter(WasteRemovalRequest.assigned_driver_user_id.is_(None))

    rows = query.order_by(WasteRemovalRequest.created_at.asc(), WasteRemovalRequest.id.asc()).all()

    now = datetime.utcnow()
    queue_items = []
    status_counts = {}
    incident_counts = {}
    escalation_dirty = False
    for booking in rows:
        status_key = (booking.status or '').strip().lower() or 'unknown'
        status_counts[status_key] = status_counts.get(status_key, 0) + 1
        driver = db.session.get(User, booking.assigned_driver_user_id) if booking.assigned_driver_user_id else None
        latest_location = (
            WasteRemovalVehicleLocation.query.filter_by(waste_removal_request_id=booking.id)
            .order_by(WasteRemovalVehicleLocation.recorded_at.desc(), WasteRemovalVehicleLocation.id.desc())
            .first()
        )
        queue_item = (
            _serialize_dispatch_queue_item(
                booking,
                driver=driver,
                latest_location=latest_location,
                now=now,
            )
        )
        for flag in queue_item.get('incident_flags') or []:
            incident_counts[flag] = incident_counts.get(flag, 0) + 1
        if _dispatch_send_escalation_webhook(booking, queue_item, now=now, source='admin_dispatch_board'):
            escalation_dirty = True
        queue_items.append(queue_item)
    if escalation_dirty:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            app.logger.exception('Failed to persist dispatch board escalation markers.')
    if incidents_only:
        queue_items = [item for item in queue_items if item.get('incident_flags')]
    if incident_state_filter != 'all':
        queue_items = [
            item
            for item in queue_items
            if (item.get('incident') or {}).get('state') == incident_state_filter
        ]

    # Prioritize incident rows for triage.
    def _incident_sort_key(item):
        flags = item.get('incident_flags') or []
        pickup_due = item.get('pickup_due_minutes')
        overdue_rank = pickup_due if isinstance(pickup_due, int) and pickup_due > 0 else -1
        age = item.get('age_minutes') or 0
        return (-len(flags), -overdue_rank, -age, item.get('request', {}).get('id') or 0)

    queue_items = sorted(queue_items, key=_incident_sort_key)
    incident_rows = [item for item in queue_items if item.get('incident_flags')][:20]
    requests_overdue = sum(
        1
        for item in queue_items
        if isinstance(item.get('pickup_due_minutes'), int) and item['pickup_due_minutes'] > 0
    )
    requests_with_incidents = len([item for item in queue_items if item.get('incident_flags')])
    incident_total = sum(len(item.get('incident_flags') or []) for item in queue_items)
    incident_state_counts = {}
    incident_severity_counts = {}
    for item in queue_items:
        state = (item.get('incident') or {}).get('state')
        severity = (item.get('incident') or {}).get('severity')
        if state:
            incident_state_counts[state] = incident_state_counts.get(state, 0) + 1
        if severity:
            incident_severity_counts[severity] = incident_severity_counts.get(severity, 0) + 1

    return render_template(
        'pages/admin_dispatch.html',
        queue_items=queue_items,
        incident_rows=incident_rows,
        summary={
            'total_rows': len(queue_items),
            'requests_with_incidents': requests_with_incidents,
            'incident_total': incident_total,
            'requests_overdue': requests_overdue,
            'status_counts': status_counts,
            'incident_counts': incident_counts,
            'incident_state_counts': incident_state_counts,
            'incident_severity_counts': incident_severity_counts,
        },
        drivers=[_serialize_dispatch_driver(row) for row in drivers],
        admins=[_serialize_dispatch_driver(row) for row in admins],
        statuses=selected_statuses,
        status_options=status_options,
        assigned_filter=assigned_filter,
        incidents_only=incidents_only,
        incident_state_filter=incident_state_filter,
        filter_query_string=(request.query_string or b'').decode('utf-8'),
        sla_thresholds={
            'pending_match_minutes': _dispatch_pending_match_sla_minutes(),
            'unassigned_match_minutes': _dispatch_unassigned_match_sla_minutes(),
            'location_stale_minutes': _dispatch_location_stale_minutes(),
        },
    )


@app.route('/admin/dispatch/override', methods=['POST'])
@login_required
def admin_dispatch_override_form():
    if not _current_user_is_admin():
        flash('Admin access is required.')
        return redirect('/login'), 403

    request_id = _to_int_or_none(request.form.get('request_id'))
    return_query = str(request.form.get('return_query') or '').strip()
    redirect_target = url_for('admin_dispatch_board')
    if return_query:
        redirect_target = '{}?{}'.format(redirect_target, return_query.lstrip('?'))

    if request_id is None:
        flash('request_id is required.')
        return redirect(redirect_target)

    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        flash('Waste request not found.')
        return redirect(redirect_target)

    raw_driver_user_id = str(request.form.get('driver_user_id') or '').strip()
    if not raw_driver_user_id:
        new_driver_user_id = None
        driver = None
    else:
        new_driver_user_id = _to_int_or_none(raw_driver_user_id)
        if new_driver_user_id is None:
            flash('driver_user_id must be an integer or empty.')
            return redirect(redirect_target)
        driver = db.session.get(User, new_driver_user_id)
        if not driver:
            flash('Driver not found.')
            return redirect(redirect_target)
        if (driver.role or '').strip().lower() != 'driver':
            flash('Selected user is not a driver.')
            return redirect(redirect_target)
        if not driver.is_active_user:
            flash('Selected driver is inactive.')
            return redirect(redirect_target)

    previous_driver_user_id = booking.assigned_driver_user_id
    if previous_driver_user_id == new_driver_user_id:
        flash('No assignment change.')
        return redirect(redirect_target)

    reason = (str(request.form.get('reason') or '').strip()[:255] or None)
    now = datetime.utcnow()
    booking.assigned_driver_user_id = new_driver_user_id
    _record_dispatch_incident_event(
        booking.id,
        event_type='dispatch_override',
        actor_user_id=getattr(current_user, 'id', None),
        actor_email=getattr(current_user, 'email', None),
        source='web_admin_dispatch',
        details={
            'previous_assigned_driver_user_id': previous_driver_user_id,
            'assigned_driver_user_id': new_driver_user_id,
            'reason': reason,
        },
        occurred_at=now,
    )
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception('Failed admin dispatch override form for request %s.', request_id)
        flash('Failed to update dispatch assignment.')
        return redirect(redirect_target)

    metadata = {
        'previous_assigned_driver_user_id': previous_driver_user_id,
        'assigned_driver_user_id': booking.assigned_driver_user_id,
        'admin_user_id': getattr(current_user, 'id', None),
        'reason': reason,
    }
    _publish_waste_request_event(
        booking.id,
        'admin_dispatch_override',
        payload=_serialize_waste_request_snapshot(booking),
        metadata=metadata,
    )
    _notify_mobile_push_for_waste_event(
        booking,
        'admin_dispatch_override',
        metadata=metadata,
    )

    if booking.assigned_driver_user_id:
        flash('Driver assignment updated for request #{}.'.format(booking.id))
    else:
        flash('Driver assignment removed for request #{}.'.format(booking.id))
    return redirect(redirect_target)


@app.route('/admin/dispatch/timeline/<int:request_id>', methods=['GET'])
@login_required
def admin_dispatch_timeline(request_id):
    if not _current_user_is_admin():
        flash('Admin access is required.')
        return redirect('/login'), 403

    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        flash('Waste request not found.')
        return redirect(url_for('admin_dispatch_board'))

    try:
        include_actor_auth = _parse_optional_bool_query(
            request.args.get('include_actor_auth'),
            'include_actor_auth',
        )
        auth_window_hours = _parse_optional_int_query(
            request.args.get('auth_window_hours'),
            'auth_window_hours',
            min_value=1,
            max_value=24 * 30,
        )
        limit = _parse_optional_int_query(
            request.args.get('limit'),
            'limit',
            min_value=1,
            max_value=500,
        )
    except ValueError:
        flash('Invalid timeline filters. Showing defaults.')
        include_actor_auth = None
        auth_window_hours = None
        limit = None

    include_actor_auth = True if include_actor_auth is None else bool(include_actor_auth)
    auth_window_hours = auth_window_hours or 168
    limit = limit or 200
    timeline_rows, timeline_summary = _build_dispatch_request_timeline(
        booking,
        include_actor_auth=include_actor_auth,
        auth_window_hours=auth_window_hours,
        limit=limit,
    )
    return render_template(
        'pages/admin_dispatch_timeline.html',
        booking=_serialize_waste_request(booking),
        timeline_rows=timeline_rows,
        timeline_summary=timeline_summary,
        filters={
            'include_actor_auth': include_actor_auth,
            'auth_window_hours': auth_window_hours,
            'limit': limit,
        },
    )


def _get_dispatch_incident_context(booking, now=None):
    now = now or datetime.utcnow()
    latest_location = (
        WasteRemovalVehicleLocation.query.filter_by(waste_removal_request_id=booking.id)
        .order_by(WasteRemovalVehicleLocation.recorded_at.desc(), WasteRemovalVehicleLocation.id.desc())
        .first()
    )
    flags = _dispatch_incident_flags(booking, latest_location=latest_location, now=now)
    incident = _dispatch_incident_summary(booking, flags, now=now)
    driver = db.session.get(User, booking.assigned_driver_user_id) if booking.assigned_driver_user_id else None
    item = _serialize_dispatch_queue_item(
        booking,
        driver=driver,
        latest_location=latest_location,
        now=now,
    )
    return item


def _dispatch_incident_active_statuses():
    return ['pending_match', 'matched', 'accepted', 'en_route', 'arrived', 'collected']


def _resolve_dispatch_incident_owner_candidate(owner_admin_user_id=None, owner_admin_email=None):
    candidate_id = _to_int_or_none(owner_admin_user_id)
    if candidate_id is not None:
        candidate = db.session.get(User, candidate_id)
        if candidate and (candidate.role or '').strip().lower() == 'admin' and candidate.is_active_user:
            return candidate
        return None

    normalized_email = _normalize_email(owner_admin_email or _dispatch_incident_auto_assign_admin_email())
    if normalized_email:
        candidate = User.query.filter(func.lower(User.email) == normalized_email).first()
        if candidate and (candidate.role or '').strip().lower() == 'admin' and candidate.is_active_user:
            return candidate
        return None

    return (
        User.query.filter(
            func.lower(User.role) == 'admin',
            User.is_active_user.is_(True),
        )
        .order_by(User.id.asc())
        .first()
    )


def _dispatch_incident_is_test_candidate(booking):
    email = _normalize_email(getattr(booking, 'requester_email', None))
    if email:
        if email.endswith('@example.com'):
            return True
        domain = email.split('@')[-1] if '@' in email else ''
        if domain in {'localhost', 'projectdivert.local'} or domain.endswith('.test'):
            return True

    requester_name = (str(getattr(booking, 'requester_name', '') or '').strip().lower())
    if requester_name.startswith(('smoke', 'test', 'qa')):
        return True

    notes = (str(getattr(booking, 'incident_notes', '') or '').strip().lower())
    if 'smoke' in notes or 'test incident' in notes:
        return True

    return False


def _run_dispatch_incident_maintenance(
    *,
    auto_assign=False,
    auto_resolve_test=False,
    resolve_test_minutes=None,
    owner_admin_user_id=None,
    owner_admin_email=None,
    limit=None,
    dry_run=False,
    actor_user_id=None,
    actor_email=None,
    source='system_dispatch_incident_maintenance',
    now=None,
):
    now = now or datetime.utcnow()
    limit = _dispatch_incident_maintenance_limit(limit)
    resolve_test_minutes = _dispatch_incident_auto_resolve_test_minutes(resolve_test_minutes)
    auto_assign = bool(auto_assign)
    auto_resolve_test = bool(auto_resolve_test)

    owner_user = None
    if auto_assign or auto_resolve_test:
        owner_user = _resolve_dispatch_incident_owner_candidate(
            owner_admin_user_id=owner_admin_user_id,
            owner_admin_email=owner_admin_email,
        )

    query = WasteRemovalRequest.query.filter(
        WasteRemovalRequest.status.in_(_dispatch_incident_active_statuses())
    )
    rows = (
        query.order_by(WasteRemovalRequest.created_at.asc(), WasteRemovalRequest.id.asc())
        .limit(limit)
        .all()
    )

    scanned = 0
    incident_rows = 0
    actions_planned = 0
    actions_applied = 0
    auto_assigned = 0
    auto_resolved = 0
    skipped_owner_unavailable = 0
    changed_request_ids = []
    items = []
    publish_jobs = []

    for booking in rows:
        scanned += 1
        queue_item = _get_dispatch_incident_context(booking, now=now)
        incident_flags = list(queue_item.get('incident_flags') or [])
        if not incident_flags:
            continue

        incident_rows += 1
        incident_info = queue_item.get('incident') or {}
        incident_state = str(incident_info.get('state') or '').strip().lower()
        created_age_minutes = _minutes_since(getattr(booking, 'created_at', None), now=now) or 0
        is_test_candidate = _dispatch_incident_is_test_candidate(booking)

        can_assign_owner = (
            auto_assign
            and booking.incident_owner_admin_user_id is None
            and incident_state != 'resolved'
            and owner_user is not None
        )
        can_resolve_test = (
            auto_resolve_test
            and incident_state != 'resolved'
            and is_test_candidate
            and created_age_minutes >= resolve_test_minutes
        )

        if auto_assign and booking.incident_owner_admin_user_id is None and owner_user is None:
            skipped_owner_unavailable += 1

        planned_actions = []
        if can_assign_owner:
            planned_actions.append('auto_assign_owner')
        if can_resolve_test:
            planned_actions.append('auto_resolve_test')
        if not planned_actions:
            continue

        actions_planned += len(planned_actions)
        item_summary = {
            'request_id': booking.id,
            'status': booking.status,
            'incident_state': incident_state,
            'incident_flags': incident_flags,
            'created_age_minutes': created_age_minutes,
            'test_candidate': is_test_candidate,
            'planned_actions': planned_actions,
            'applied_actions': [],
        }
        items.append(item_summary)

        if dry_run:
            continue

        if can_assign_owner:
            previous_owner_user_id = booking.incident_owner_admin_user_id
            booking.incident_owner_admin_user_id = owner_user.id
            booking.incident_updated_at = now
            _record_dispatch_incident_event(
                booking.id,
                event_type='incident_owner_auto_assign',
                actor_user_id=actor_user_id,
                actor_email=actor_email,
                source=source,
                details={
                    'previous_owner_admin_user_id': previous_owner_user_id,
                    'owner_admin_user_id': owner_user.id,
                    'automation': True,
                },
                occurred_at=now,
            )
            publish_jobs.append(
                {
                    'request_id': booking.id,
                    'event_name': 'admin_dispatch_incident_owner_reassign',
                    'metadata': {
                        'action': 'owner_reassign',
                        'previous_owner_admin_user_id': previous_owner_user_id,
                        'owner_admin_user_id': owner_user.id,
                        'admin_user_id': actor_user_id,
                        'automation': True,
                    },
                }
            )
            item_summary['applied_actions'].append('auto_assign_owner')
            auto_assigned += 1
            actions_applied += 1

        if can_resolve_test:
            if booking.incident_owner_admin_user_id is None and owner_user is not None:
                previous_owner_user_id = booking.incident_owner_admin_user_id
                booking.incident_owner_admin_user_id = owner_user.id
                _record_dispatch_incident_event(
                    booking.id,
                    event_type='incident_owner_auto_assign',
                    actor_user_id=actor_user_id,
                    actor_email=actor_email,
                    source=source,
                    details={
                        'previous_owner_admin_user_id': previous_owner_user_id,
                        'owner_admin_user_id': owner_user.id,
                        'automation': True,
                        'reason': 'auto_resolve_test',
                    },
                    occurred_at=now,
                )
                publish_jobs.append(
                    {
                        'request_id': booking.id,
                        'event_name': 'admin_dispatch_incident_owner_reassign',
                        'metadata': {
                            'action': 'owner_reassign',
                            'previous_owner_admin_user_id': previous_owner_user_id,
                            'owner_admin_user_id': owner_user.id,
                            'admin_user_id': actor_user_id,
                            'automation': True,
                            'reason': 'auto_resolve_test',
                        },
                    }
                )
                auto_assigned += 1
                actions_applied += 1
                item_summary['applied_actions'].append('auto_assign_owner')

            booking.incident_state = 'resolved'
            booking.incident_updated_at = now
            booking.incident_resolved_at = now
            if not booking.incident_acknowledged_at:
                booking.incident_acknowledged_at = now

            existing_notes = (booking.incident_notes or '').strip()
            note_prefix = '[{} AUTO-RESOLVE] '.format(now.isoformat())
            auto_note = (
                'Resolved stale test incident automatically '
                '(age_minutes={}, threshold_minutes={}).'
            ).format(created_age_minutes, resolve_test_minutes)
            booking.incident_notes = (existing_notes + '\n' if existing_notes else '') + note_prefix + auto_note

            _record_dispatch_incident_event(
                booking.id,
                event_type='incident_auto_resolve_test',
                actor_user_id=actor_user_id,
                actor_email=actor_email,
                source=source,
                details={
                    'incident_state': booking.incident_state,
                    'incident_severity': booking.incident_severity,
                    'incident_flags': incident_flags,
                    'age_minutes': created_age_minutes,
                    'threshold_minutes': resolve_test_minutes,
                    'automation': True,
                },
                occurred_at=now,
            )
            publish_jobs.append(
                {
                    'request_id': booking.id,
                    'event_name': 'admin_dispatch_incident_resolve',
                    'metadata': {
                        'action': 'resolve',
                        'admin_user_id': actor_user_id,
                        'incident_state': booking.incident_state,
                        'incident_severity': booking.incident_severity,
                        'automation': True,
                        'reason': 'stale_test_incident',
                    },
                }
            )
            item_summary['applied_actions'].append('auto_resolve_test')
            auto_resolved += 1
            actions_applied += 1

        if item_summary['applied_actions']:
            changed_request_ids.append(booking.id)

    if not dry_run and changed_request_ids:
        db.session.commit()
        for job in publish_jobs:
            booking = db.session.get(WasteRemovalRequest, job['request_id'])
            if not booking:
                continue
            _publish_waste_request_event(
                booking.id,
                job['event_name'],
                payload=_serialize_waste_request_snapshot(booking),
                metadata=job['metadata'],
            )
            _notify_mobile_push_for_waste_event(
                booking,
                job['event_name'],
                metadata=job['metadata'],
            )

    return {
        'executed_at': now.isoformat() + 'Z',
        'dry_run': bool(dry_run),
        'options': {
            'auto_assign': auto_assign,
            'auto_resolve_test': auto_resolve_test,
            'resolve_test_minutes': resolve_test_minutes,
            'limit': limit,
            'owner_admin_user_id': owner_user.id if owner_user else None,
            'owner_admin_email': _normalize_email(getattr(owner_user, 'email', None)) if owner_user else None,
        },
        'summary': {
            'scanned': scanned,
            'incident_rows': incident_rows,
            'actions_planned': actions_planned,
            'actions_applied': actions_applied if not dry_run else 0,
            'auto_assigned': auto_assigned if not dry_run else 0,
            'auto_resolved_test': auto_resolved if not dry_run else 0,
            'skipped_owner_unavailable': skipped_owner_unavailable,
            'changed_request_count': len(set(changed_request_ids)) if not dry_run else 0,
        },
        'items': items,
    }


@app.route('/admin/dispatch/incident', methods=['POST'])
@login_required
def admin_dispatch_incident_form():
    if not _current_user_is_admin():
        flash('Admin access is required.')
        return redirect('/login'), 403

    request_id = _to_int_or_none(request.form.get('request_id'))
    action = (str(request.form.get('action') or '').strip().lower() or '')
    notes = (str(request.form.get('notes') or '').strip()[:1000] or None)
    return_query = str(request.form.get('return_query') or '').strip()
    redirect_target = url_for('admin_dispatch_board')
    if return_query:
        redirect_target = '{}?{}'.format(redirect_target, return_query.lstrip('?'))

    if action not in {'ack', 'resolve'}:
        flash('Unsupported incident action.')
        return redirect(redirect_target)
    if request_id is None:
        flash('request_id is required.')
        return redirect(redirect_target)

    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        flash('Waste request not found.')
        return redirect(redirect_target)

    queue_item = _get_dispatch_incident_context(booking)
    flags = queue_item.get('incident_flags') or []
    if action == 'ack' and not flags:
        flash('No active incident to acknowledge for request #{}.'.format(request_id))
        return redirect(redirect_target)

    now = datetime.utcnow()
    if action == 'ack':
        booking.incident_state = 'acknowledged'
        booking.incident_severity = _dispatch_incident_severity(flags)
        booking.incident_owner_admin_user_id = getattr(current_user, 'id', None)
        booking.incident_acknowledged_at = now
        booking.incident_resolved_at = None
        booking.incident_updated_at = now
    else:
        booking.incident_state = 'resolved'
        booking.incident_owner_admin_user_id = getattr(current_user, 'id', None)
        booking.incident_resolved_at = now
        booking.incident_updated_at = now
        if not booking.incident_acknowledged_at:
            booking.incident_acknowledged_at = now
        if not flags:
            booking.incident_severity = None

    if notes:
        existing = (booking.incident_notes or '').strip()
        prefix = '[{} {}] '.format(now.isoformat(), action.upper())
        booking.incident_notes = (existing + '\n' if existing else '') + prefix + notes

    _record_dispatch_incident_event(
        booking.id,
        event_type='incident_{}'.format(action),
        actor_user_id=getattr(current_user, 'id', None),
        actor_email=getattr(current_user, 'email', None),
        source='web_admin_dispatch',
        details={
            'incident_state': booking.incident_state,
            'incident_severity': booking.incident_severity,
            'notes': notes,
            'incident_flags': flags,
        },
        occurred_at=now,
    )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception('Failed admin incident action %s for request %s.', action, request_id)
        flash('Failed to update incident state.')
        return redirect(redirect_target)

    metadata = {
        'action': action,
        'admin_user_id': getattr(current_user, 'id', None),
        'incident_state': booking.incident_state,
        'incident_severity': booking.incident_severity,
        'notes': notes,
    }
    _publish_waste_request_event(
        booking.id,
        'admin_dispatch_incident_{}'.format(action),
        payload=_serialize_waste_request_snapshot(booking),
        metadata=metadata,
    )
    _notify_mobile_push_for_waste_event(
        booking,
        'admin_dispatch_incident_{}'.format(action),
        metadata=metadata,
    )

    if action == 'ack':
        flash('Incident acknowledged for request #{}.'.format(request_id))
    else:
        flash('Incident resolved for request #{}.'.format(request_id))
    return redirect(redirect_target)


@app.route('/admin/dispatch/incident-owner', methods=['POST'])
@login_required
def admin_dispatch_incident_owner_form():
    if not _current_user_is_admin():
        flash('Admin access is required.')
        return redirect('/login'), 403

    request_id = _to_int_or_none(request.form.get('request_id'))
    raw_owner_user_id = str(request.form.get('owner_admin_user_id') or '').strip()
    notes = (str(request.form.get('notes') or '').strip()[:1000] or None)
    return_query = str(request.form.get('return_query') or '').strip()
    redirect_target = url_for('admin_dispatch_board')
    if return_query:
        redirect_target = '{}?{}'.format(redirect_target, return_query.lstrip('?'))

    if request_id is None:
        flash('request_id is required.')
        return redirect(redirect_target)

    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        flash('Waste request not found.')
        return redirect(redirect_target)

    if not raw_owner_user_id:
        new_owner_user_id = None
        owner_user = None
    else:
        new_owner_user_id = _to_int_or_none(raw_owner_user_id)
        if new_owner_user_id is None:
            flash('owner_admin_user_id must be an integer or empty.')
            return redirect(redirect_target)
        owner_user = db.session.get(User, new_owner_user_id)
        if not owner_user:
            flash('Owner admin user not found.')
            return redirect(redirect_target)
        if (owner_user.role or '').strip().lower() != 'admin':
            flash('Selected user is not an admin.')
            return redirect(redirect_target)
        if not owner_user.is_active_user:
            flash('Selected admin user is inactive.')
            return redirect(redirect_target)

    previous_owner_user_id = booking.incident_owner_admin_user_id
    if previous_owner_user_id == new_owner_user_id:
        flash('No owner change.')
        return redirect(redirect_target)

    now = datetime.utcnow()
    booking.incident_owner_admin_user_id = new_owner_user_id
    booking.incident_updated_at = now
    if notes:
        existing = (booking.incident_notes or '').strip()
        prefix = '[{} OWNER] '.format(now.isoformat())
        booking.incident_notes = (existing + '\n' if existing else '') + prefix + notes

    _record_dispatch_incident_event(
        booking.id,
        event_type='incident_owner_reassign',
        actor_user_id=getattr(current_user, 'id', None),
        actor_email=getattr(current_user, 'email', None),
        source='web_admin_dispatch',
        details={
            'previous_owner_admin_user_id': previous_owner_user_id,
            'owner_admin_user_id': new_owner_user_id,
            'notes': notes,
        },
        occurred_at=now,
    )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception('Failed incident owner reassignment for request %s.', request_id)
        flash('Failed to update incident owner.')
        return redirect(redirect_target)

    metadata = {
        'action': 'owner_reassign',
        'previous_owner_admin_user_id': previous_owner_user_id,
        'owner_admin_user_id': booking.incident_owner_admin_user_id,
        'admin_user_id': getattr(current_user, 'id', None),
        'notes': notes,
    }
    _publish_waste_request_event(
        booking.id,
        'admin_dispatch_incident_owner_reassign',
        payload=_serialize_waste_request_snapshot(booking),
        metadata=metadata,
    )
    _notify_mobile_push_for_waste_event(
        booking,
        'admin_dispatch_incident_owner_reassign',
        metadata=metadata,
    )

    if booking.incident_owner_admin_user_id:
        flash('Incident owner updated for request #{}.'.format(request_id))
    else:
        flash('Incident owner cleared for request #{}.'.format(request_id))
    return redirect(redirect_target)


@app.route('/output', methods=['GET'])
def create_output_form():
    form = OutputForm()
    return render_template('forms/calculator.html', form=form)

@app.route('/output', methods=['POST'])
def create_output_submission():
    # TODO: insert form data as a new Venue record in the db, instead
    # TODO: modify data to be the data object returned from db insertion
    error=False
    try:
        form = _require_form_fields(
            request.form,
            [
                'material',
                'amount',
                'unit',
                'site_address',
                'traditional_address',
                'divert_address',
                'traditional_cost',
                'divert_cost',
            ],
        )

        material = form['material']
        if material == 'Other':
            custom_material = request.form.get('custom_output_material', '').strip()
            if not custom_material:
                raise ValueError('Please enter a material when selecting Other.')
            material = custom_material[:120]
        amount = form['amount']
        unit = form['unit']
        site_address = form['site_address']
        traditional_address = form['traditional_address']
        divert_address = form['divert_address']
        traditional_cost = form['traditional_cost']
        divert_cost = form['divert_cost']

        g = output(material=material, amount=amount, unit=unit, site_address=site_address, traditional_address=traditional_address, 
                        divert_address=divert_address, traditional_cost=traditional_cost, divert_cost=divert_cost)
        db.session.add(g)
        db.session.commit()
    
    except ValueError as exc:
        error=True
        db.session.rollback()
        flash(str(exc))
    except Exception:
        error=True
        db.session.rollback()
        app.logger.exception('Output submission failed.')

    finally:
        db.session.close()
    
    if error:
        flash('An error occurred. Output for ' + request.form.get('material', 'material')+ ' could not be calculated.')

    if not error:
        flash('Output for ' + material + ' was successfully listed.')
    
    return redirect("/result")

def fun(material, amount, unit, site_address, traditional_address, divert_address, traditional_cost):
    _ensure_reference_data_loaded()
    
    if _normalize_material_name(material) == 'carpet tiles':
        if unit == 'Square Meters':
            amount=(amount*4.3)/1000

    reuse_key = _material_factor_key(reuse_offset, material)
    if reuse_key is None:
        raise ValueError('No reuse factor configured for material "{}".'.format(material))
    reuse_factor = _factor_value(reuse_offset, reuse_key, 'Emission Factor (kg CO2 equivalents/ tonne)')
    reuse_embodied_carbon = amount * reuse_factor

    recycle_key = _material_factor_key(recycle_offset, material)
    if recycle_key is not None:
        recycle_column = 'Emission Factor (kg CO2 equivalents/ tonne or sq m)'
        if recycle_column not in recycle_offset.columns:
            recycle_column = 'Emission Factor (kg CO2 equivalents/ tonne)'
        recycle_factor = _factor_value(recycle_offset, recycle_key, recycle_column)
        recycle_embodied_carbon = amount * recycle_factor
    else:
        recycle_embodied_carbon = reuse_embodied_carbon * 0.85

    traditional_distance = numeric_distance(
        traditional_address,
        site_address,
        return_none_on_failure=True,
    )
    divert_distance = numeric_distance(
        divert_address,
        site_address,
        return_none_on_failure=True,
    )
    if traditional_distance is None or divert_distance is None:
        raise ValueError(
            'Could not calculate transport distance because the Google Maps API is unavailable. '
            'Please check API key and billing.'
        )

    mrf_transport_carbon  = traditional_distance * 0.85
    landfill_transport_carbon = mrf_transport_carbon * 1.2
    landfill_monetary_cost = traditional_cost + 114
    mrf_to_reprocessor_cost = traditional_cost
    mrf_to_reprocessor_transport_carbon = mrf_transport_carbon * 1.2
    divert_transport_carbon  = divert_distance * 0.85
        
    return mrf_transport_carbon, landfill_transport_carbon, landfill_monetary_cost, mrf_to_reprocessor_cost, mrf_to_reprocessor_transport_carbon, divert_transport_carbon, reuse_embodied_carbon, recycle_embodied_carbon


@app.route('/result')
def show_output():
  output_query = db.session.query(output).order_by(output.id.desc()).first()
  

  if not output_query: 
    return render_template('errors/404.html')

  try:
    g = fun(
      output_query.material,
      float(output_query.amount),
      output_query.unit,
      output_query.site_address,
      output_query.traditional_address,
      output_query.divert_address,
      float(output_query.traditional_cost),
    )
  except ValueError as exc:
    flash(str(exc))
    return redirect('/output')
  
  mrf_transport_carbon = g[0]
  landfill_transport_carbon = g[1]
  landfill_monetary_cost = g[2]
  mrf_to_reprocessor_cost = g[3]
  mrf_to_reprocessor_transport_carbon = g[4]
  divert_transport_carbon = g[5]
  reuse_embodied_carbon = g[6]
  recycle_embodied_carbon = g[7]

  

  data = {
    "mrf_transport_carbon": mrf_transport_carbon,
    "landfill_transport_carbon": landfill_transport_carbon,
    "landfill_monetary_cost": landfill_monetary_cost,
    "mrf_to_reprocessor_cost": mrf_to_reprocessor_cost,
    "mrf_to_reprocessor_transport_carbon": mrf_to_reprocessor_transport_carbon,
    "mrf_to_reprocessor_embodied_carbon": (recycle_embodied_carbon * 0.7),
    "divert_transport_carbon": divert_transport_carbon,
    "reuse_embodied_carbon": reuse_embodied_carbon,
    "recycle_embodied_carbon": recycle_embodied_carbon,
    "divert_cost": output_query.divert_cost,
    "traditional_cost": output_query.traditional_cost,
    "traditional_carbon": (mrf_transport_carbon - (recycle_embodied_carbon * 0.7)),
    "divert_recycle_total_carbon": (-recycle_embodied_carbon + divert_transport_carbon),
    "divert_reuse_total_carbon": (-reuse_embodied_carbon + divert_transport_carbon),
    "mrf_to_reprocessor_carbon": (mrf_to_reprocessor_transport_carbon - (recycle_embodied_carbon * 0.7))
  }

  return render_template('pages/output.html', output=data)
#  Create Account
#  ----------------------------------------------------------------

def _create_account_submission(account_type):
    error = False
    try:
        form = request.form
        selected_type = form.get('account_type', '').strip()
        if selected_type == 'Other':
            selected_type = (
                form.get('other_description', '').strip()
                or form.get('other_type', '').strip()
                or form.get('other', '').strip()
                or 'Other'
            )
            selected_type = selected_type[:120]
        if not selected_type:
            selected_type = account_type
        if not selected_type:
            selected_type = 'Charity'

        charity = c(
            name=form.get('name'),
            type=selected_type,
            email=form.get('email'),
            reg_num=form.get('reg_num'),
            address1=form.get('address1'),
            city1=form.get('city1'),
            county1=form.get('county1'),
            postcode1=form.get('postcode1'),
            address2=form.get('address2'),
            city2=form.get('city2'),
            county2=form.get('county2'),
            postcode2=form.get('postcode2'),
            address3=form.get('address3'),
            city3=form.get('city3'),
            county3=form.get('county3'),
            postcode3=form.get('postcode3'),
            phone=form.get('phone'),
            facebook_link=form.get('facebook_link'),
            website=form.get('website'),
        )
        db.session.add(charity)
        db.session.commit()
    except Exception:
        error = True
        db.session.rollback()
        app.logger.exception('Account submission failed.')
    finally:
        db.session.close()

    if error:
        flash('Error. Account was not uploaded.')
    else:
        flash('Account was successfully uploaded.')

    return redirect('/first')


@app.route('/submitdetails1', methods=['GET'])
@app.route('/submit_details1', methods=['GET'])
def create_account_form1():
    form = CharityForm1()
    return render_template('forms/new_account.html', form=form)


@app.route('/submit_details1', methods=['POST'])
def create_account_submission1():
    return _create_account_submission('Charity')


@app.route('/submit_details2', methods=['GET'])
def create_account_form2():
    form = CharityForm2()
    return render_template('forms/new_account.html', form=form)


@app.route('/submit_details2', methods=['POST'])
def create_account_submission2():
    return _create_account_submission('Community Group')


@app.route('/submit_details3', methods=['GET'])
def create_account_form3():
    form = CharityForm3()
    return render_template('forms/new_account.html', form=form)


@app.route('/submit_details3', methods=['POST'])
def create_account_submission3():
    return _create_account_submission('Education')


@app.route('/submit_details4', methods=['GET'])
def create_account_form4():
    form = CharityForm4()
    return render_template('forms/new_account.html', form=form)


@app.route('/submit_details4', methods=['POST'])
def create_account_submission4():
    return _create_account_submission('Social Enterprise')


@app.route('/submit_details5', methods=['GET'])
def create_account_form5():
    form = CharityForm5()
    return render_template('forms/new_account_other.html', form=form)


@app.route('/submit_details5', methods=['POST'])
def create_account_submission5():
    return _create_account_submission(request.form.get('other'))



#----------------------------------------------------------------------------#
# Materials Dashboard
#----------------------------------------------------------------------------#
@app.route('/material_input', methods=['GET'])
def create_material_form():
    form = MaterialForm()
    return render_template('forms/new_material.html', form=form)

@app.route('/material_input', methods=['POST'])
def create_material_submission():
    
    error=False
    try:
        form = _require_form_fields(
            request.form,
            ['waste_stream', 'amount', 'county', 'postcode'],
        )

        waste_stream = form['waste_stream']
        if waste_stream == 'Other':
            custom_waste_stream = request.form.get('custom_waste_stream', '').strip()
            if not custom_waste_stream:
                raise ValueError('Please enter a custom material type when selecting Other.')
            waste_stream = custom_waste_stream[:120]
        amount = form['amount']
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip()
        county = form['county']
        postcode = form['postcode']
        endpoint = "http://api.postcodes.io/postcodes/{}".format(postcode)
        response = requests.get(endpoint, timeout=10)
        payload = response.json()
        result = payload.get('result') if isinstance(payload, dict) else None
        if not result:
            raise ValueError('Please enter a valid postcode.')
        longitude = result.get('longitude')
        latitude = result.get('latitude')
        if longitude is None or latitude is None:
            raise ValueError('Please enter a valid postcode.')
        dimensions = request.form.get('dimensions', '').strip()
        condition = request.form.get('condition', '').strip()
        uploaded_images = request.files.getlist('image_files')
        if uploaded_images:
            image_refs = _save_material_images(uploaded_images, limit=MAX_MATERIAL_IMAGES)
        else:
            image_refs = [
                request.form.get('image_link1', '').strip(),
                request.form.get('image_link2', '').strip(),
                request.form.get('image_link3', '').strip(),
            ]

        image_link1, image_link2, image_link3 = _encode_material_images(image_refs)


        charity = m(waste_stream=waste_stream, amount=amount, address=address, city=city, county=county, postcode=postcode, dimensions=dimensions, condition=condition, 
                    image_link1=image_link1, image_link2=image_link2, image_link3=image_link3, longitude=longitude, latitude=latitude)
        
        db.session.add(charity)
        db.session.commit()
    
    except ValueError as exc:
        error=True
        db.session.rollback()
        flash(str(exc))
    except Exception:
        error=True
        db.session.rollback()
        app.logger.exception('Material submission failed.')

    finally:
        db.session.close()
    
    if error:
        flash('Error. Material was not uploaded.')

    if not error:
        flash('Material was successfully uploaded.')
        
    return redirect('/materials')
  

@app.route('/materials')
def materials():
    search_term = request.args.get('search_term', '').strip()
    postcode = request.args.get('postcode', '').strip()
    radius_raw = request.args.get('radius', '').strip()
    filter_applied = False
    materials_data = []
    base_query = m.query

    if search_term:
        base_query = base_query.filter(m.waste_stream.ilike(f'%{search_term}%'))
        filter_applied = True

    if postcode and radius_raw:
        try:
            radius_miles = int(radius_raw)
            if radius_miles <= 0:
                raise ValueError
            endpoint = "http://api.postcodes.io/postcodes/{}".format(postcode)
            resp = requests.get(endpoint, timeout=10)
            payload = resp.json()
            result = payload.get('result')
            if not result:
                raise ValueError

            target_long = result.get('longitude')
            target_lat = result.get('latitude')
            radius_km = radius_miles * 1.60934
            filtered_materials = base_query.filter(
                func.acos(
                    func.sin(func.radians(target_lat)) * func.sin(func.radians(m.latitude))
                    + func.cos(func.radians(target_lat))
                    * func.cos(func.radians(m.latitude))
                    * func.cos(func.radians(m.longitude) - (func.radians(target_long)))
                )
                * 6371
                <= radius_km
            ).all()
            materials_data = [_serialize_material(material) for material in filtered_materials]
            filter_applied = True
        except Exception:
            flash('Could not apply postcode/radius filter. Showing all materials.')

    if not filter_applied:
        all_materials = base_query.all()
        materials_data = [_serialize_material(material) for material in all_materials]

    return render_template(
        'pages/materials.html',
        materials=materials_data,
        search_term=search_term,
        filter_postcode=postcode,
        filter_radius=radius_raw,
        filter_applied=filter_applied,
    )


@app.route('/materials/search', methods=['POST'])
def search_materials():

    search_term = request.form.get('search_term', '')
    search_result = db.session.query(m).filter(m.waste_stream.ilike(f'%{search_term}%')).all()
    data = []

    for result in search_result:
        data.append({
            "id": result.id,
            "name": result.waste_stream,
        })
  
    response={
        "count": len(search_result),
        "data": data
    }
  
    return render_template('pages/search_materials.html', results=response, search_term=request.form.get('search_term', ''))


@app.route('/materials/<int:material_id>')
def show_material(material_id):
  
    material = m.query.get(material_id)

    if not material: 
        return render_template('errors/404.html')

    data = {
        "id": material.id,
        "material": material.waste_stream,
        "amount": material.amount,
        "city": material.city,
        "county": material.county,
        "address": material.address,
        "dimensions": material.dimensions,
        "condition": material.condition,
        "image_link1": material.image_link1,
        "image_link2": material.image_link2,
        "image_link3": material.image_link3,
        "image_links": _decode_material_images(material.image_link1, material.image_link2, material.image_link3),
    }

    return render_template('pages/show_material.html', material=data)


@app.route('/materials_filtered/<string:location_id>')
def show_site_material(location_id):
    all_areas = m.query.filter(m.city == location_id)
    all_areas = m.query.with_entities(func.count(m.id), m.city, m.county).group_by(m.city, m.county).all()
    data = []

    for area in all_areas:
        if area.city == location_id:
            area_projects = m.query.filter_by(county=area.county).filter_by(city=area.city).all()
        
            project_data = []
        
            for material in area_projects:
                project_data.append({
                    "id": material.id,
                    "material": material.waste_stream, 
                    "amount": material.amount,
                    "condition": material.condition,
                    "postcode": material.postcode,
                    })
        
        
            data.append({
                "city": area.city,
                "county": area.county, 
                "materials": project_data
                })

    
    return render_template('pages/materials.html', areas=data)

#  Create Request
#  ----------------------------------------------------------------
@app.route('/material/<int:mat_id>/request', methods=['GET'])
def create_material_request(mat_id):
    form = RequestForm()
    return render_template('forms/new_request.html', form=form)

@app.route('/material/<int:mat_id>/request', methods=['POST'])
def request_material_form(mat_id):

    error=False
    email_sent = False
    try:
        mat_id = mat_id
        material = m.query.get(mat_id)
        if not material:
            return render_template('errors/404.html'), 404

        email = request.form.get('email', '').strip()
        if not email and current_user.is_authenticated:
            email = current_user.email
        if not email:
            raise ValueError('Requester email is required.')

        message = request.form['message']
        
        qui = r(mat_id=mat_id, e_id=email, message=message)
        db.session.add(qui)
        db.session.commit()

        company_email = (app.config.get('REQUEST_NOTIFICATION_EMAIL') or '').strip()
        if company_email:
            base_url = (app.config.get('APP_BASE_URL') or request.url_root.rstrip('/')).rstrip('/')
            listing_url = '{}{}'.format(base_url, url_for('show_material', material_id=mat_id))
            subject = 'New material request: {}'.format(material.waste_stream or 'Material')
            body = (
                'You received a new material request.\n\n'
                'Material: {material}\n'
                'Material ID: {mat_id}\n'
                'Requester Email: {email}\n'
                'Message: {message}\n'
                'Listing URL: {listing_url}\n'
            ).format(
                material=material.waste_stream or 'Material',
                mat_id=mat_id,
                email=email,
                message=message or '(no message)',
                listing_url=listing_url,
            )
            email_sent = _send_material_request_email(company_email, subject, body)
        else:
            app.logger.warning('REQUEST_NOTIFICATION_EMAIL not set; request email notification skipped.')
    
    except ValueError as exc:
        error=True
        db.session.rollback()
        flash(str(exc))
    except Exception:
        error=True
        db.session.rollback()
        app.logger.exception('Material request submission failed.')

    finally:
        db.session.close()
    
    if error:
        flash('Error. Request was not sent.')

    if not error:
        if email_sent:
            flash('Request sent and emailed to the company.')
        else:
            flash('Request saved. Email notification is not configured yet.')
        
    return redirect('/materials')


@app.route('/waste-removal/request', methods=['GET'])
@app.route('/waste_removal/request', methods=['GET'])
def create_waste_removal_request_form():
    form = WasteRemovalRequestForm()
    if not form.match_radius_miles.data:
        form.match_radius_miles.data = 25
    if current_user.is_authenticated:
        if current_user.name:
            form.requester_name.data = current_user.name
        if current_user.email:
            form.requester_email.data = current_user.email
    min_pickup_iso = datetime.now().replace(second=0, microsecond=0).strftime('%Y-%m-%dT%H:%M')
    return render_template('forms/waste_removal_request.html', form=form, min_pickup_iso=min_pickup_iso)


@app.route('/waste-removal/request', methods=['POST'])
@app.route('/waste_removal/request', methods=['POST'])
def create_waste_removal_request_submission():
    error = False
    email_sent = False
    email_configured = False
    provider_candidates = []
    closest_candidate = None
    dispatch_offer_rows = []
    provider_notifications_sent = 0
    match_radius_miles = None
    pickup_latitude = None
    pickup_longitude = None
    drive_time_info = None
    try:
        form = _require_form_fields(
            request.form,
            [
                'requester_name',
                'requester_email',
                'material_type',
                'waste_amount',
                'waste_unit',
                'match_radius_miles',
                'pickup_address',
                'pickup_postcode',
                'scheduled_pickup_at',
            ],
        )

        material_type = form['material_type']
        if material_type == 'Other':
            custom_material_type = request.form.get('custom_material_type', '').strip()
            if not custom_material_type:
                raise ValueError('Please enter a material type when selecting Other.')
            material_type = custom_material_type[:120]

        waste_amount = _to_float_or_none(form['waste_amount'])
        if waste_amount is None or waste_amount <= 0:
            raise ValueError('Waste amount must be a positive number.')

        match_radius_miles = _to_float_or_none(form['match_radius_miles'])
        if match_radius_miles is None or match_radius_miles <= 0:
            raise ValueError('Provider match radius must be a positive number of miles.')

        try:
            scheduled_pickup_at = dateutil.parser.parse(form['scheduled_pickup_at'])
        except (TypeError, ValueError, OverflowError):
            raise ValueError('Please provide a valid scheduled pickup date and time.')

        if scheduled_pickup_at.tzinfo is not None:
            scheduled_pickup_at = scheduled_pickup_at.astimezone().replace(tzinfo=None)
        if scheduled_pickup_at <= datetime.now():
            raise ValueError('Scheduled pickup time must be in the future.')

        pickup_latitude, pickup_longitude = _postcode_coordinates(form['pickup_postcode'])

        booking = WasteRemovalRequest(
            requester_name=form['requester_name'][:120],
            requester_email=form['requester_email'][:255],
            material_type=material_type,
            waste_amount=waste_amount,
            waste_unit=form['waste_unit'][:32],
            pickup_address=form['pickup_address'][:255],
            pickup_city=(request.form.get('pickup_city') or '').strip()[:120] or None,
            pickup_county=(request.form.get('pickup_county') or '').strip()[:120] or None,
            pickup_postcode=form['pickup_postcode'][:32],
            scheduled_pickup_at=scheduled_pickup_at,
            notes=(request.form.get('notes') or '').strip() or None,
            status='pending_match',
        )
        db.session.add(booking)
        db.session.flush()

        provider_candidates, dispatch_offer_rows = _create_dispatch_offers_for_request(
            booking,
            pickup_latitude,
            pickup_longitude,
            match_radius_miles,
        )
        closest_candidate = provider_candidates[0] if provider_candidates else None
        if closest_candidate:
            drive_time_info = _drive_time_between_points(
                pickup_latitude,
                pickup_longitude,
                closest_candidate['provider_latitude'],
                closest_candidate['provider_longitude'],
            )
        if dispatch_offer_rows:
            db.session.add_all(dispatch_offer_rows)

        db.session.commit()

        base_url = (app.config.get('APP_BASE_URL') or request.url_root.rstrip('/')).rstrip('/')
        provider_notifications_sent = _notify_dispatch_offers(booking, dispatch_offer_rows, base_url)

        notification_email = (app.config.get('WASTE_REMOVAL_NOTIFICATION_EMAIL') or '').strip()
        email_configured = bool(notification_email)
        if notification_email:
            local_pickup = scheduled_pickup_at.strftime('%Y-%m-%d %H:%M')
            subject = 'New waste removal request: {}'.format(material_type)
            text_body = (
                'A new waste removal request was submitted.\n\n'
                'Request ID: {request_id}\n'
                'Requester Name: {requester_name}\n'
                'Requester Email: {requester_email}\n'
                'Material Type: {material_type}\n'
                'Waste Amount: {waste_amount} {waste_unit}\n'
                'Pickup Address: {pickup_address}\n'
                'Pickup City: {pickup_city}\n'
                'Pickup County: {pickup_county}\n'
                'Pickup Postcode: {pickup_postcode}\n'
                'Scheduled Pickup: {scheduled_pickup}\n'
                'Match Radius (miles): {match_radius_miles}\n'
                'Dispatch Offers Created: {offers_created}\n'
                'Closest Provider Candidate: {closest_provider}\n'
                'Provider Notifications Sent: {provider_notifications_sent}\n'
                'Estimated Drive Time: {drive_time}\n'
                'Notes: {notes}\n'
                'Status: {status}\n'
            ).format(
                request_id=booking.id,
                requester_name=booking.requester_name,
                requester_email=booking.requester_email,
                material_type=booking.material_type,
                waste_amount=booking.waste_amount,
                waste_unit=booking.waste_unit,
                pickup_address=booking.pickup_address,
                pickup_city=booking.pickup_city or '(not provided)',
                pickup_county=booking.pickup_county or '(not provided)',
                pickup_postcode=booking.pickup_postcode,
                scheduled_pickup=local_pickup,
                match_radius_miles=match_radius_miles,
                offers_created=len(dispatch_offer_rows),
                closest_provider=(
                    '{} ({} miles)'.format(
                        closest_candidate['provider_name'],
                        closest_candidate['distance_miles'],
                    )
                    if closest_candidate
                    else 'No provider found within radius'
                ),
                provider_notifications_sent=provider_notifications_sent,
                drive_time=(
                    drive_time_info['text']
                    if drive_time_info
                    else (
                        'Unable to calculate (Google Maps API unavailable)'
                        if closest_candidate
                        else 'N/A'
                    )
                ),
                notes=booking.notes or '(none)',
                status=booking.status,
            )
            email_sent = _send_material_request_email(notification_email, subject, text_body)
        else:
            app.logger.warning(
                'WASTE_REMOVAL_NOTIFICATION_EMAIL not set; waste removal email notification skipped.'
            )
    except ValueError as exc:
        error = True
        db.session.rollback()
        flash(str(exc))
    except Exception:
        error = True
        db.session.rollback()
        app.logger.exception('Waste removal request submission failed.')
    finally:
        db.session.close()

    if error:
        flash('Waste removal request could not be submitted.')
    else:
        if dispatch_offer_rows:
            flash(
                'Waste removal request submitted. Notified {} closest providers; awaiting first acceptance.'.format(
                    len(dispatch_offer_rows),
                )
            )
        else:
            flash(
                'Waste removal request submitted. No provider found within {} miles yet.'.format(
                    round(match_radius_miles or 0, 2),
                )
            )
        if provider_notifications_sent:
            flash('Provider notifications sent: {}.'.format(provider_notifications_sent))
        if email_sent:
            flash('Request details emailed to the team.')
        elif email_configured:
            flash('Request saved but email delivery failed.')
        else:
            flash('Request saved. Email notification is not configured yet.')

    return redirect('/waste-removal/request')


@app.route('/api/v1/auth/login', methods=['POST'])
def api_auth_login():
    payload = request.get_json(silent=True) or {}
    email = _normalize_email(payload.get('email'))
    password = str(payload.get('password') or '').strip()
    block_response = _auth_blocklist_response(email=email)
    if block_response:
        _audit_auth_event(
            'login',
            success=False,
            status_code=403,
            email=email,
            details={'reason': 'blocklist'},
        )
        return block_response
    lockout_response = _auth_login_lockout_response(email=email)
    if lockout_response:
        _audit_auth_event(
            'login',
            success=False,
            status_code=429,
            email=email,
            details={'reason': 'lockout_active'},
        )
        return lockout_response
    rate_limited = _auth_rate_limit_response('login', email=email)
    if rate_limited:
        _audit_auth_event(
            'login',
            success=False,
            status_code=429,
            email=email,
            details={'reason': 'rate_limited'},
        )
        return rate_limited
    if not email or not password:
        _audit_auth_event(
            'login',
            success=False,
            status_code=400,
            email=email,
            details={'reason': 'missing_credentials'},
        )
        return jsonify({'error': 'email and password are required'}), 400

    user = User.query.filter(func.lower(User.email) == email).first()
    if not user or not user.is_active or not check_password_hash(user.password_hash, password):
        lockout_retry_after = 0
        lockout_level = 0
        lockout_identifiers = _auth_login_lockout_identifiers(email=email)
        for identifier in lockout_identifiers:
            lockout_retry_after = max(lockout_retry_after, _record_auth_login_failure(identifier))
            lockout_level = max(lockout_level, _auth_login_lockout_level(identifier))
        if lockout_retry_after > 0:
            sessions_revoked = False
            suspicious_revocation_enabled = (
                user is not None
                and _auth_suspicious_activity_revoke_sessions_enabled()
                and lockout_level >= _auth_suspicious_activity_revoke_min_lockout_level()
            )
            if suspicious_revocation_enabled:
                try:
                    sessions_revoked = _revoke_sessions_for_suspicious_activity(
                        user.id,
                        reason='suspicious_login_lockout',
                    )
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    sessions_revoked = False
                    app.logger.exception(
                        'Failed revoking sessions for suspicious login lockout user_id=%s.',
                        user.id,
                    )

            response = jsonify({'error': 'Too many failed login attempts. Please try again later.'})
            response.status_code = 429
            response.headers['Retry-After'] = str(lockout_retry_after)
            _audit_auth_event(
                'login',
                success=False,
                status_code=429,
                email=email,
                user_id=user.id if user else None,
                details={
                    'reason': 'lockout_triggered',
                    'retry_after_seconds': lockout_retry_after,
                    'lockout_level': lockout_level,
                    'sessions_revoked': sessions_revoked,
                },
            )
            return response

        _audit_auth_event(
            'login',
            success=False,
            status_code=401,
            email=email,
            user_id=user.id if user else None,
            details={'reason': 'invalid_credentials'},
        )
        return jsonify({'error': 'Invalid email or password'}), 401

    if _auth_require_email_verification() and not user.email_verified_at:
        _audit_auth_event(
            'login',
            success=False,
            status_code=403,
            email=email,
            user_id=user.id,
            details={'reason': 'email_unverified'},
        )
        return jsonify({'error': 'Email verification required'}), 403

    try:
        for identifier in _auth_login_lockout_identifiers(email=email):
            _clear_auth_login_failure(identifier)
        auth_payload = _issue_auth_payload(user)
        db.session.commit()
        _audit_auth_event(
            'login',
            success=True,
            status_code=200,
            email=email,
            user_id=user.id,
        )
        return jsonify(auth_payload)
    except Exception:
        db.session.rollback()
        app.logger.exception('Failed issuing auth tokens for login.')
        _audit_auth_event(
            'login',
            success=False,
            status_code=500,
            email=email,
            user_id=user.id,
            details={'reason': 'server_error'},
        )
        return jsonify({'error': 'Failed to create session'}), 500


@app.route('/api/v1/auth/signup', methods=['POST'])
def api_auth_signup():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get('name') or '').strip()
    email = _normalize_email(payload.get('email'))
    password = str(payload.get('password') or '')
    role = 'customer'

    rate_limited = _auth_rate_limit_response('signup', email=email)
    if rate_limited:
        _audit_auth_event(
            'signup',
            success=False,
            status_code=429,
            email=email,
            details={'reason': 'rate_limited'},
        )
        return rate_limited

    if not name:
        _audit_auth_event(
            'signup',
            success=False,
            status_code=400,
            email=email,
            details={'reason': 'missing_name'},
        )
        return jsonify({'error': 'name is required'}), 400
    if not _is_valid_email(email):
        _audit_auth_event(
            'signup',
            success=False,
            status_code=400,
            email=email,
            details={'reason': 'invalid_email'},
        )
        return jsonify({'error': 'A valid email is required'}), 400
    password_error = _validate_password_strength(password)
    if password_error:
        _audit_auth_event(
            'signup',
            success=False,
            status_code=400,
            email=email,
            details={'reason': 'weak_password'},
        )
        return jsonify({'error': password_error}), 400

    if User.query.filter(func.lower(User.email) == email).first():
        _audit_auth_event(
            'signup',
            success=False,
            status_code=409,
            email=email,
            details={'reason': 'email_exists'},
        )
        return jsonify({'error': 'An account with this email already exists'}), 409

    try:
        user = User(
            name=name[:120],
            email=email,
            password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
            role=role,
            is_active_user=True,
            email_verified_at=None if _auth_require_email_verification() else datetime.utcnow(),
        )
        db.session.add(user)
        db.session.flush()

        if user.email_verified_at:
            auth_payload = _issue_auth_payload(user)
            db.session.commit()
            auth_payload['created'] = True
            _audit_auth_event(
                'signup',
                success=True,
                status_code=201,
                email=email,
                user_id=user.id,
                details={'verification_required': False},
            )
            return jsonify(auth_payload), 201

        verification_token = _issue_email_verification_token(user)
        verify_url = _verification_url_for_token(verification_token)
        message_lines = [
            'Verify your Project Divert account by using this token:',
            verification_token,
        ]
        if verify_url:
            message_lines.extend(['', 'Or open:', verify_url])
        verification_email_sent = _send_account_email(
            user.email,
            'Verify your Project Divert account',
            '\n'.join(message_lines),
        )
        db.session.commit()

        response_payload = {
            'created': True,
            'verification_required': True,
            'verification_email_sent': bool(verification_email_sent),
            'user': _serialize_auth_user(user),
        }
        if _auth_return_tokens_in_response():
            response_payload['verification_token'] = verification_token
        _audit_auth_event(
            'signup',
            success=True,
            status_code=201,
            email=email,
            user_id=user.id,
            details={
                'verification_required': True,
                'verification_email_sent': bool(verification_email_sent),
            },
        )
        return jsonify(response_payload), 201
    except Exception:
        db.session.rollback()
        app.logger.exception('API signup failed.')
        _audit_auth_event(
            'signup',
            success=False,
            status_code=500,
            email=email,
            details={'reason': 'server_error'},
        )
        return jsonify({'error': 'Failed to create account'}), 500


@app.route('/api/v1/auth/refresh', methods=['POST'])
def api_auth_refresh():
    rate_limited = _auth_rate_limit_response('refresh')
    if rate_limited:
        _audit_auth_event(
            'refresh',
            success=False,
            status_code=429,
            details={'reason': 'rate_limited'},
        )
        return rate_limited

    payload = request.get_json(silent=True) or {}
    refresh_token = str(payload.get('refresh_token') or '').strip()
    if not refresh_token:
        refresh_token = _extract_bearer_token()
    if not refresh_token:
        _audit_auth_event(
            'refresh',
            success=False,
            status_code=400,
            details={'reason': 'missing_refresh_token'},
        )
        return jsonify({'error': 'refresh_token is required'}), 400

    try:
        user = _rotate_refresh_token(refresh_token)
        auth_payload = _issue_auth_payload(user)
        db.session.commit()
        _audit_auth_event(
            'refresh',
            success=True,
            status_code=200,
            email=user.email,
            user_id=user.id,
        )
        return jsonify(auth_payload)
    except ValueError as exc:
        db.session.rollback()
        message = str(exc)
        status = 403 if message == 'Email verification required' else 401
        _audit_auth_event(
            'refresh',
            success=False,
            status_code=status,
            details={'reason': message},
        )
        return jsonify({'error': message}), status
    except Exception:
        db.session.rollback()
        app.logger.exception('API refresh token failed.')
        _audit_auth_event(
            'refresh',
            success=False,
            status_code=500,
            details={'reason': 'server_error'},
        )
        return jsonify({'error': 'Failed to refresh session'}), 500


@app.route('/api/v1/auth/logout', methods=['POST'])
def api_auth_logout():
    rate_limited = _auth_rate_limit_response('logout')
    if rate_limited:
        _audit_auth_event(
            'logout',
            success=False,
            status_code=429,
            details={'reason': 'rate_limited'},
        )
        return rate_limited

    payload = request.get_json(silent=True) or {}
    refresh_token = str(payload.get('refresh_token') or '').strip()
    if not refresh_token:
        refresh_token = _extract_bearer_token()
    if not refresh_token:
        _audit_auth_event(
            'logout',
            success=False,
            status_code=400,
            details={'reason': 'missing_refresh_token'},
        )
        return jsonify({'error': 'refresh_token is required'}), 400

    try:
        claims, user_id = _parse_lifecycle_token(refresh_token, 'refresh')
        token_row = _refresh_row_from_claims(claims)
        now = datetime.utcnow()
        if token_row and token_row.user_id == user_id:
            if not token_row.revoked_at:
                token_row.revoked_at = now
            if not token_row.used_at:
                token_row.used_at = now

        _revoke_all_access_tokens_for_user(user_id, reason='logout')

        raw_access_token = _extract_bearer_token()
        if raw_access_token:
            try:
                access_claims = _decode_access_token(raw_access_token)
                token_type = str(access_claims.get('token_type') or '').strip().lower()
                access_user_id = _to_int_or_none(access_claims.get('sub'))
                if token_type == 'access' and access_user_id == user_id:
                    _revoke_access_token_jti(access_claims, reason='logout')
            except jwt.InvalidTokenError:
                pass

        db.session.commit()
        user = db.session.get(User, user_id)
        _audit_auth_event(
            'logout',
            success=True,
            status_code=200,
            email=user.email if user else '',
            user_id=user_id,
        )
        return jsonify({'revoked': True})
    except ValueError as exc:
        db.session.rollback()
        _audit_auth_event(
            'logout',
            success=False,
            status_code=200,
            details={'reason': str(exc)},
        )
        return jsonify({'revoked': False, 'message': str(exc)})
    except Exception:
        db.session.rollback()
        app.logger.exception('API logout failed.')
        _audit_auth_event(
            'logout',
            success=False,
            status_code=500,
            details={'reason': 'server_error'},
        )
        return jsonify({'error': 'Failed to revoke session'}), 500


@app.route('/api/v1/auth/verify/request', methods=['POST'])
def api_auth_verify_request():
    payload = request.get_json(silent=True) or {}
    email = _normalize_email(payload.get('email'))

    rate_limited = _auth_rate_limit_response('verify_request', email=email)
    if rate_limited:
        _audit_auth_event(
            'verify_request',
            success=False,
            status_code=429,
            email=email,
            details={'reason': 'rate_limited'},
        )
        return rate_limited

    if not _is_valid_email(email):
        _audit_auth_event(
            'verify_request',
            success=False,
            status_code=400,
            email=email,
            details={'reason': 'invalid_email'},
        )
        return jsonify({'error': 'A valid email is required'}), 400

    response_payload = {
        'message': 'If an account exists, a verification message has been sent.',
    }
    try:
        user = User.query.filter(func.lower(User.email) == email).first()
        if user and user.is_active and not user.email_verified_at:
            existing_token_row, retry_after = _recent_valid_one_time_token(
                user.id,
                'email_verify',
                _auth_verify_request_cooldown_seconds(),
            )
            if existing_token_row:
                response_payload['verification_email_sent'] = False
                response_payload['retry_after_seconds'] = retry_after
                if _auth_return_tokens_in_response():
                    response_payload['verification_token'] = _encode_lifecycle_token_from_row(
                        user,
                        existing_token_row,
                    )
            else:
                verification_token = _issue_email_verification_token(user)
                verify_url = _verification_url_for_token(verification_token)
                lines = [
                    'Verify your Project Divert account by using this token:',
                    verification_token,
                ]
                if verify_url:
                    lines.extend(['', 'Or open:', verify_url])
                response_payload['verification_email_sent'] = bool(
                    _send_account_email(
                        user.email,
                        'Verify your Project Divert account',
                        '\n'.join(lines),
                    )
                )
                if _auth_return_tokens_in_response():
                    response_payload['verification_token'] = verification_token
                db.session.commit()

            _audit_auth_event(
                'verify_request',
                success=True,
                status_code=200,
                email=email,
                user_id=user.id,
                details={
                    'verification_email_sent': bool(response_payload.get('verification_email_sent')),
                    'retry_after_seconds': _to_int_or_none(response_payload.get('retry_after_seconds')),
                },
            )
        else:
            response_payload['verification_email_sent'] = False
            _audit_auth_event(
                'verify_request',
                success=True,
                status_code=200,
                email=email,
                user_id=user.id if user else None,
                details={'verification_email_sent': False},
            )
    except Exception:
        db.session.rollback()
        app.logger.exception('API verify request failed.')
        _audit_auth_event(
            'verify_request',
            success=False,
            status_code=500,
            email=email,
            details={'reason': 'server_error'},
        )
        # Intentionally keep a generic response to avoid account enumeration.
    return jsonify(response_payload)


@app.route('/api/v1/auth/verify/confirm', methods=['POST'])
def api_auth_verify_confirm():
    rate_limited = _auth_rate_limit_response('verify_confirm')
    if rate_limited:
        _audit_auth_event(
            'verify_confirm',
            success=False,
            status_code=429,
            details={'reason': 'rate_limited'},
        )
        return rate_limited

    payload = request.get_json(silent=True) or {}
    raw_token = payload.get('token')

    try:
        user, _token_row = _consume_one_time_lifecycle_token(raw_token, 'email_verify')
        user.email_verified_at = user.email_verified_at or datetime.utcnow()
        auth_payload = _issue_auth_payload(user)
        db.session.commit()
        auth_payload['email_verified'] = True
        _audit_auth_event(
            'verify_confirm',
            success=True,
            status_code=200,
            email=user.email,
            user_id=user.id,
        )
        return jsonify(auth_payload)
    except ValueError as exc:
        db.session.rollback()
        _audit_auth_event(
            'verify_confirm',
            success=False,
            status_code=400,
            details={'reason': str(exc)},
        )
        return jsonify({'error': str(exc)}), 400
    except Exception:
        db.session.rollback()
        app.logger.exception('API verify confirm failed.')
        _audit_auth_event(
            'verify_confirm',
            success=False,
            status_code=500,
            details={'reason': 'server_error'},
        )
        return jsonify({'error': 'Failed to verify email'}), 500


@app.route('/api/v1/auth/password-reset/request', methods=['POST'])
def api_auth_password_reset_request():
    payload = request.get_json(silent=True) or {}
    email = _normalize_email(payload.get('email'))

    rate_limited = _auth_rate_limit_response('password_reset_request', email=email)
    if rate_limited:
        _audit_auth_event(
            'password_reset_request',
            success=False,
            status_code=429,
            email=email,
            details={'reason': 'rate_limited'},
        )
        return rate_limited

    if not _is_valid_email(email):
        _audit_auth_event(
            'password_reset_request',
            success=False,
            status_code=400,
            email=email,
            details={'reason': 'invalid_email'},
        )
        return jsonify({'error': 'A valid email is required'}), 400

    response_payload = {
        'message': 'If an account exists, a password reset message has been sent.',
    }
    try:
        user = User.query.filter(func.lower(User.email) == email).first()
        if user and user.is_active:
            existing_token_row, retry_after = _recent_valid_one_time_token(
                user.id,
                'password_reset',
                _auth_password_reset_request_cooldown_seconds(),
            )
            if existing_token_row:
                response_payload['reset_email_sent'] = False
                response_payload['retry_after_seconds'] = retry_after
                if _auth_return_tokens_in_response():
                    response_payload['reset_token'] = _encode_lifecycle_token_from_row(
                        user,
                        existing_token_row,
                    )
            else:
                reset_token = _issue_password_reset_token(user)
                reset_url = _password_reset_url_for_token(reset_token)
                lines = [
                    'Reset your Project Divert password with this token:',
                    reset_token,
                ]
                if reset_url:
                    lines.extend(['', 'Or open:', reset_url])
                response_payload['reset_email_sent'] = bool(
                    _send_account_email(
                        user.email,
                        'Reset your Project Divert password',
                        '\n'.join(lines),
                    )
                )
                if _auth_return_tokens_in_response():
                    response_payload['reset_token'] = reset_token
                db.session.commit()

            _audit_auth_event(
                'password_reset_request',
                success=True,
                status_code=200,
                email=email,
                user_id=user.id,
                details={
                    'reset_email_sent': bool(response_payload.get('reset_email_sent')),
                    'retry_after_seconds': _to_int_or_none(response_payload.get('retry_after_seconds')),
                },
            )
        else:
            response_payload['reset_email_sent'] = False
            _audit_auth_event(
                'password_reset_request',
                success=True,
                status_code=200,
                email=email,
                user_id=user.id if user else None,
                details={'reset_email_sent': False},
            )
    except Exception:
        db.session.rollback()
        app.logger.exception('API password reset request failed.')
        _audit_auth_event(
            'password_reset_request',
            success=False,
            status_code=500,
            email=email,
            details={'reason': 'server_error'},
        )
        # Intentionally keep a generic response to avoid account enumeration.
    return jsonify(response_payload)


@app.route('/api/v1/auth/password-reset/confirm', methods=['POST'])
def api_auth_password_reset_confirm():
    rate_limited = _auth_rate_limit_response('password_reset_confirm')
    if rate_limited:
        _audit_auth_event(
            'password_reset_confirm',
            success=False,
            status_code=429,
            details={'reason': 'rate_limited'},
        )
        return rate_limited

    payload = request.get_json(silent=True) or {}
    raw_token = payload.get('token')
    new_password = str(payload.get('new_password') or '')
    password_error = _validate_password_strength(new_password)
    if password_error:
        _audit_auth_event(
            'password_reset_confirm',
            success=False,
            status_code=400,
            details={'reason': 'weak_password'},
        )
        return jsonify({'error': password_error}), 400

    try:
        user, _token_row = _consume_one_time_lifecycle_token(raw_token, 'password_reset')
        user.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
        _revoke_all_refresh_tokens_for_user(user.id)
        _revoke_all_access_tokens_for_user(user.id, reason='password_reset')
        auth_payload = _issue_auth_payload(user)
        db.session.commit()
        auth_payload['password_reset'] = True
        _audit_auth_event(
            'password_reset_confirm',
            success=True,
            status_code=200,
            email=user.email,
            user_id=user.id,
        )
        return jsonify(auth_payload)
    except ValueError as exc:
        db.session.rollback()
        _audit_auth_event(
            'password_reset_confirm',
            success=False,
            status_code=400,
            details={'reason': str(exc)},
        )
        return jsonify({'error': str(exc)}), 400
    except Exception:
        db.session.rollback()
        app.logger.exception('API password reset confirm failed.')
        _audit_auth_event(
            'password_reset_confirm',
            success=False,
            status_code=500,
            details={'reason': 'server_error'},
        )
        return jsonify({'error': 'Failed to reset password'}), 500


@app.route('/api/v1/admin/auth-audit', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_auth_audit():
    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=500)
        offset = _parse_optional_int_query(request.args.get('offset'), 'offset', min_value=0)
        filters = _parse_admin_auth_audit_filters(request.args)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    limit = limit or 50
    offset = offset or 0

    try:
        query = _build_admin_auth_audit_query(filters)
        total = query.count()
        rows = (
            query.order_by(AuthAuditEvent.occurred_at.desc(), AuthAuditEvent.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
    except SQLAlchemyError:
        app.logger.exception('Failed to query auth audit events.')
        return jsonify({'error': 'Failed to query auth audit events'}), 500

    return jsonify(
        {
            'items': [_serialize_auth_audit_event(row) for row in rows],
            'pagination': {
                'limit': limit,
                'offset': offset,
                'returned': len(rows),
                'total': total,
                'has_more': (offset + len(rows)) < total,
            },
            'filters': {
                'event': filters.get('event'),
                'email': filters.get('email'),
                'ip': filters.get('ip'),
                'success': filters.get('success'),
                'status_code': filters.get('status_code'),
                'user_id': filters.get('user_id'),
                'from': filters['from'].isoformat() + 'Z' if filters.get('from') else None,
                'to': filters['to'].isoformat() + 'Z' if filters.get('to') else None,
            },
        }
    )


@app.route('/api/v1/admin/auth-audit/export', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_auth_audit_export():
    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=5000)
        filters = _parse_admin_auth_audit_filters(request.args)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    limit = limit or 1000
    try:
        rows = (
            _build_admin_auth_audit_query(filters)
            .order_by(AuthAuditEvent.occurred_at.desc(), AuthAuditEvent.id.desc())
            .limit(limit)
            .all()
        )
    except SQLAlchemyError:
        app.logger.exception('Failed to export auth audit events.')
        return jsonify({'error': 'Failed to export auth audit events'}), 500

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            'id',
            'event',
            'success',
            'status_code',
            'email',
            'user_id',
            'ip',
            'user_agent',
            'occurred_at',
            'details_json',
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.id,
                row.event,
                bool(row.success),
                row.status_code,
                row.email or '',
                row.user_id or '',
                row.ip or '',
                row.user_agent or '',
                row.occurred_at.isoformat() + 'Z' if row.occurred_at else '',
                json.dumps(row.details_json or {}, separators=(',', ':')),
            ]
        )

    output = buffer.getvalue()
    filename = 'auth_audit_export_{}.csv'.format(datetime.utcnow().strftime('%Y%m%d_%H%M%S'))
    response = Response(output, mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename={}'.format(filename)
    return response


@app.route('/api/v1/admin/auth-security/blocks', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_auth_security_blocks():
    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=500)
        offset = _parse_optional_int_query(request.args.get('offset'), 'offset', min_value=0)
        active = _parse_optional_bool_query(request.args.get('active'), 'active')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    limit = limit or 50
    offset = offset or 0
    identifier_type = (str(request.args.get('identifier_type') or '').strip().lower() or None)
    identifier_value = str(request.args.get('identifier_value') or '').strip()
    if identifier_type and identifier_type not in {'ip', 'email'}:
        return jsonify({'error': 'identifier_type must be ip or email'}), 400

    if identifier_type and identifier_value:
        _id_type, identifier_value = _normalize_auth_block_identifier(identifier_type, identifier_value)

    try:
        query = AuthSecurityBlocklist.query
        if identifier_type:
            query = query.filter(AuthSecurityBlocklist.identifier_type == identifier_type)
        if identifier_value:
            query = query.filter(AuthSecurityBlocklist.identifier_value == identifier_value)
        if active is True:
            now = datetime.utcnow()
            query = query.filter(
                AuthSecurityBlocklist.revoked_at.is_(None),
                or_(AuthSecurityBlocklist.expires_at.is_(None), AuthSecurityBlocklist.expires_at > now),
            )
        elif active is False:
            now = datetime.utcnow()
            query = query.filter(
                or_(
                    AuthSecurityBlocklist.revoked_at.isnot(None),
                    AuthSecurityBlocklist.expires_at <= now,
                )
            )

        total = query.count()
        rows = (
            query.order_by(AuthSecurityBlocklist.created_at.desc(), AuthSecurityBlocklist.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
    except SQLAlchemyError:
        app.logger.exception('Failed to query auth security blocks.')
        return jsonify({'error': 'Failed to query auth security blocks'}), 500

    return jsonify(
        {
            'items': [_serialize_auth_blocklist_entry(row) for row in rows],
            'pagination': {
                'limit': limit,
                'offset': offset,
                'returned': len(rows),
                'total': total,
                'has_more': (offset + len(rows)) < total,
            },
            'filters': {
                'identifier_type': identifier_type,
                'identifier_value': identifier_value or None,
                'active': active,
            },
        }
    )


@app.route('/api/v1/admin/auth-security/blocks', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_auth_security_block_create():
    payload = request.get_json(silent=True) or {}
    identifier_type = str(payload.get('identifier_type') or '').strip().lower()
    identifier_value = str(payload.get('identifier_value') or '').strip()
    if identifier_type not in {'ip', 'email'}:
        return jsonify({'error': 'identifier_type must be ip or email'}), 400
    identifier_type, identifier_value = _normalize_auth_block_identifier(identifier_type, identifier_value)
    if not identifier_value:
        return jsonify({'error': 'identifier_value is required'}), 400

    permanent = bool(payload.get('permanent'))
    expires_at = None
    if not permanent:
        try:
            expires_in_seconds = _parse_optional_int_query(
                payload.get('expires_in_seconds'),
                'expires_in_seconds',
                min_value=60,
                max_value=60 * 60 * 24 * 365,
            )
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

        expires_at_raw = payload.get('expires_at')
        if expires_at_raw:
            try:
                expires_at = _parse_query_datetime_utc(expires_at_raw, 'expires_at')
            except ValueError as exc:
                return jsonify({'error': str(exc)}), 400
        elif expires_in_seconds is not None:
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in_seconds)
        else:
            expires_at = datetime.utcnow() + timedelta(seconds=_auth_blocklist_default_duration_seconds())

    reason = (str(payload.get('reason') or '').strip()[:255] or None)
    admin_user_id = _current_jwt_user_id()
    now = datetime.utcnow()

    try:
        existing = (
            AuthSecurityBlocklist.query.filter(
                AuthSecurityBlocklist.identifier_type == identifier_type,
                AuthSecurityBlocklist.identifier_value == identifier_value,
                AuthSecurityBlocklist.revoked_at.is_(None),
                or_(AuthSecurityBlocklist.expires_at.is_(None), AuthSecurityBlocklist.expires_at > now),
            )
            .order_by(AuthSecurityBlocklist.created_at.desc(), AuthSecurityBlocklist.id.desc())
            .first()
        )
        if existing:
            existing.reason = reason or existing.reason
            existing.expires_at = expires_at
            metadata = existing.metadata_json or {}
            metadata['updated_by_user_id'] = admin_user_id
            existing.metadata_json = metadata
            row = existing
            created = False
        else:
            row = AuthSecurityBlocklist(
                identifier_type=identifier_type,
                identifier_value=identifier_value,
                reason=reason,
                created_by_user_id=admin_user_id,
                expires_at=expires_at,
                metadata_json={'created_by_user_id': admin_user_id},
            )
            db.session.add(row)
            created = True

        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception('Failed to create auth security block.')
        return jsonify({'error': 'Failed to create auth security block'}), 500

    _audit_auth_event(
        'admin_security_block_create',
        success=True,
        status_code=201 if created else 200,
        user_id=admin_user_id,
        details={
            'block_id': row.id,
            'identifier_type': row.identifier_type,
            'identifier_value': row.identifier_value,
            'created': created,
        },
    )
    return jsonify({'created': created, 'block': _serialize_auth_blocklist_entry(row)}), (201 if created else 200)


@app.route('/api/v1/admin/auth-security/blocks/<int:block_id>/unblock', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_auth_security_block_unblock(block_id):
    row = db.session.get(AuthSecurityBlocklist, block_id)
    if not row:
        return jsonify({'error': 'Block not found'}), 404

    if row.revoked_at is None:
        row.revoked_at = datetime.utcnow()
    reason = (str((request.get_json(silent=True) or {}).get('reason') or '').strip()[:255] or None)
    if reason:
        metadata = row.metadata_json or {}
        metadata['unblock_reason'] = reason
        row.metadata_json = metadata

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception('Failed to unblock auth security block %s.', block_id)
        return jsonify({'error': 'Failed to unblock auth security block'}), 500

    _audit_auth_event(
        'admin_security_block_unblock',
        success=True,
        status_code=200,
        user_id=_current_jwt_user_id(),
        details={'block_id': row.id},
    )
    return jsonify({'revoked': True, 'block': _serialize_auth_blocklist_entry(row)})


@app.route('/api/v1/admin/auth-security/telemetry', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_auth_security_telemetry():
    try:
        minutes = _parse_optional_int_query(request.args.get('minutes'), 'minutes', min_value=1, max_value=10080)
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=200)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    minutes = minutes or 60
    limit = limit or 25
    since = datetime.utcnow() - timedelta(minutes=minutes)
    sample_cap = 5000

    try:
        failed_rows = (
            AuthAuditEvent.query.filter(
                AuthAuditEvent.event == 'login',
                AuthAuditEvent.success.is_(False),
                AuthAuditEvent.occurred_at >= since,
            )
            .order_by(AuthAuditEvent.occurred_at.desc(), AuthAuditEvent.id.desc())
            .limit(sample_cap)
            .all()
        )
    except SQLAlchemyError:
        app.logger.exception('Failed to generate auth security telemetry.')
        return jsonify({'error': 'Failed to query auth security telemetry'}), 500

    email_stats = {}
    ip_stats = {}
    lockout_events = 0
    blocklist_events = 0

    for row in failed_rows:
        details = row.details_json or {}
        reason = str(details.get('reason') or '').strip().lower()
        if reason in {'lockout_triggered', 'lockout_active'}:
            lockout_events += 1
        if reason == 'blocklist':
            blocklist_events += 1

        if row.email:
            bucket = email_stats.setdefault(
                row.email,
                {'email': row.email, 'failed_attempts': 0, 'lockout_events': 0, 'blocklist_events': 0},
            )
            bucket['failed_attempts'] += 1
            if reason in {'lockout_triggered', 'lockout_active'}:
                bucket['lockout_events'] += 1
            if reason == 'blocklist':
                bucket['blocklist_events'] += 1

        if row.ip:
            bucket = ip_stats.setdefault(
                row.ip,
                {'ip': row.ip, 'failed_attempts': 0, 'lockout_events': 0, 'blocklist_events': 0},
            )
            bucket['failed_attempts'] += 1
            if reason in {'lockout_triggered', 'lockout_active'}:
                bucket['lockout_events'] += 1
            if reason == 'blocklist':
                bucket['blocklist_events'] += 1

    top_failed_emails = sorted(
        email_stats.values(),
        key=lambda item: (-item['failed_attempts'], item['email']),
    )[:limit]
    top_failed_ips = sorted(
        ip_stats.values(),
        key=lambda item: (-item['failed_attempts'], item['ip']),
    )[:limit]

    return jsonify(
        {
            'window_minutes': minutes,
            'considered_events': len(failed_rows),
            'sample_truncated': len(failed_rows) >= sample_cap,
            'lockout_events': lockout_events,
            'blocklist_events': blocklist_events,
            'top_failed_emails': top_failed_emails,
            'top_failed_ips': top_failed_ips,
            'recent_failures': [_serialize_auth_audit_event(row) for row in failed_rows[:limit]],
        }
    )


@app.route('/api/v1/admin/ops/health', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_ops_health():
    try:
        auth_window_minutes = _parse_optional_int_query(
            request.args.get('auth_window_minutes'),
            'auth_window_minutes',
            min_value=5,
            max_value=10080,
        )
        dispatch_limit = _parse_optional_int_query(
            request.args.get('dispatch_limit'),
            'dispatch_limit',
            min_value=1,
            max_value=5000,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    try:
        snapshot = _collect_ops_health_snapshot(
            auth_window_minutes=auth_window_minutes,
            dispatch_limit=dispatch_limit,
        )
    except SQLAlchemyError:
        app.logger.exception('Failed to collect ops health snapshot.')
        return jsonify({'error': 'Failed to collect ops health'}), 500

    return jsonify(snapshot)


@app.route('/api/v1/admin/auth-tokens', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_auth_tokens():
    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=500)
        offset = _parse_optional_int_query(request.args.get('offset'), 'offset', min_value=0)
        user_id = _parse_optional_int_query(request.args.get('user_id'), 'user_id', min_value=1)
        revoked = _parse_optional_bool_query(request.args.get('revoked'), 'revoked')
        expired = _parse_optional_bool_query(request.args.get('expired'), 'expired')
        used = _parse_optional_bool_query(request.args.get('used'), 'used')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    limit = limit or 50
    offset = offset or 0
    token_type = (str(request.args.get('token_type') or '').strip().lower() or None)
    if token_type and len(token_type) > 32:
        return jsonify({'error': 'token_type filter is too long'}), 400

    try:
        query = AuthLifecycleToken.query
        if user_id is not None:
            query = query.filter(AuthLifecycleToken.user_id == user_id)
        if token_type:
            query = query.filter(AuthLifecycleToken.token_type == token_type)
        if revoked is True:
            query = query.filter(AuthLifecycleToken.revoked_at.isnot(None))
        elif revoked is False:
            query = query.filter(AuthLifecycleToken.revoked_at.is_(None))
        if used is True:
            query = query.filter(AuthLifecycleToken.used_at.isnot(None))
        elif used is False:
            query = query.filter(AuthLifecycleToken.used_at.is_(None))
        if expired is not None:
            now = datetime.utcnow()
            if expired:
                query = query.filter(AuthLifecycleToken.expires_at <= now)
            else:
                query = query.filter(AuthLifecycleToken.expires_at > now)

        total = query.count()
        rows = (
            query.order_by(AuthLifecycleToken.created_at.desc(), AuthLifecycleToken.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
    except SQLAlchemyError:
        app.logger.exception('Failed to query auth lifecycle tokens.')
        return jsonify({'error': 'Failed to query auth tokens'}), 500

    return jsonify(
        {
            'items': [_serialize_auth_lifecycle_token(row) for row in rows],
            'pagination': {
                'limit': limit,
                'offset': offset,
                'returned': len(rows),
                'total': total,
                'has_more': (offset + len(rows)) < total,
            },
            'filters': {
                'user_id': user_id,
                'token_type': token_type,
                'revoked': revoked,
                'expired': expired,
                'used': used,
            },
        }
    )


@app.route('/api/v1/admin/auth-tokens/<int:token_row_id>/revoke', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_revoke_auth_token(token_row_id):
    token_row = db.session.get(AuthLifecycleToken, token_row_id)
    if not token_row:
        return jsonify({'error': 'Auth token not found'}), 404

    now = datetime.utcnow()
    token_row.revoked_at = token_row.revoked_at or now
    token_row.used_at = token_row.used_at or now
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception('Failed to revoke auth token %s.', token_row_id)
        return jsonify({'error': 'Failed to revoke auth token'}), 500

    _audit_auth_event(
        'admin_token_revoke',
        success=True,
        status_code=200,
        user_id=token_row.user_id,
        details={'token_row_id': token_row_id, 'token_type': token_row.token_type},
    )
    return jsonify({'revoked': True, 'token': _serialize_auth_lifecycle_token(token_row)})


@app.route('/api/v1/admin/users/<int:user_id>/sessions/revoke', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_revoke_user_sessions(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    active_refresh_before = (
        AuthLifecycleToken.query.filter(
            AuthLifecycleToken.user_id == user_id,
            AuthLifecycleToken.token_type == 'refresh',
            AuthLifecycleToken.revoked_at.is_(None),
        ).count()
    )
    _revoke_all_refresh_tokens_for_user(user_id)
    _revoke_all_access_tokens_for_user(user_id, reason='admin_revoke')

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception('Failed to revoke sessions for user %s.', user_id)
        return jsonify({'error': 'Failed to revoke sessions'}), 500

    _audit_auth_event(
        'admin_user_sessions_revoke',
        success=True,
        status_code=200,
        email=user.email,
        user_id=user.id,
        details={'active_refresh_tokens_revoked': active_refresh_before},
    )
    return jsonify(
        {
            'revoked': True,
            'user': _serialize_auth_user(user),
            'active_refresh_tokens_revoked': active_refresh_before,
        }
    )


@app.route('/api/v1/admin/drivers', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_list_drivers():
    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=500)
        offset = _parse_optional_int_query(request.args.get('offset'), 'offset', min_value=0)
        active = _parse_optional_bool_query(request.args.get('active'), 'active')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    limit = limit or 50
    offset = offset or 0
    search = (str(request.args.get('search') or '').strip().lower() or None)

    try:
        query = User.query.filter(func.lower(User.role) == 'driver')
        if active is True:
            query = query.filter(User.is_active_user.is_(True))
        elif active is False:
            query = query.filter(User.is_active_user.is_(False))
        if search:
            pattern = '%{}%'.format(search)
            query = query.filter(
                or_(
                    func.lower(User.email).like(pattern),
                    func.lower(func.coalesce(User.name, '')).like(pattern),
                )
            )

        total = query.count()
        rows = (
            query.order_by(
                func.lower(func.coalesce(User.name, User.email)).asc(),
                User.id.asc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
    except SQLAlchemyError:
        app.logger.exception('Failed to query driver list for admin.')
        return jsonify({'error': 'Failed to query drivers'}), 500

    return jsonify(
        {
            'items': [_serialize_dispatch_driver(row) for row in rows],
            'pagination': {
                'limit': limit,
                'offset': offset,
                'returned': len(rows),
                'total': total,
                'has_more': (offset + len(rows)) < total,
            },
            'filters': {
                'active': active,
                'search': search,
            },
        }
    )


@app.route('/api/v1/admin/dispatch/queue', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_dispatch_queue():
    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=500)
        offset = _parse_optional_int_query(request.args.get('offset'), 'offset', min_value=0)
        assigned = _parse_optional_bool_query(request.args.get('assigned'), 'assigned')
        incidents_only = _parse_optional_bool_query(request.args.get('incidents_only'), 'incidents_only')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    limit = limit or 50
    offset = offset or 0
    incidents_only = bool(incidents_only)
    incident_state = (str(request.args.get('incident_state') or '').strip().lower() or 'all')
    if incident_state not in {'all', 'open', 'acknowledged', 'resolved'}:
        return jsonify({'error': 'incident_state must be one of all, open, acknowledged, resolved'}), 400
    allowed_statuses = {
        'pending_match',
        'matched',
        'accepted',
        'rejected',
        'en_route',
        'arrived',
        'collected',
        'completed',
        'cancelled',
    }
    default_statuses = [
        'pending_match',
        'matched',
        'accepted',
        'en_route',
        'arrived',
        'collected',
    ]

    statuses_raw = str(request.args.get('statuses') or '').strip().lower()
    if statuses_raw:
        statuses = [part.strip() for part in statuses_raw.split(',') if part.strip()]
        invalid_statuses = sorted({status for status in statuses if status not in allowed_statuses})
        if invalid_statuses:
            return jsonify(
                {
                    'error': 'Invalid status value(s).',
                    'invalid_statuses': invalid_statuses,
                    'allowed_statuses': sorted(allowed_statuses),
                }
            ), 400
    else:
        statuses = default_statuses

    try:
        query = WasteRemovalRequest.query.filter(WasteRemovalRequest.status.in_(statuses))
        if assigned is True:
            query = query.filter(WasteRemovalRequest.assigned_driver_user_id.isnot(None))
        elif assigned is False:
            query = query.filter(WasteRemovalRequest.assigned_driver_user_id.is_(None))

        total = query.count()
        rows = (
            query.order_by(
                WasteRemovalRequest.created_at.asc(),
                WasteRemovalRequest.id.asc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
    except SQLAlchemyError:
        app.logger.exception('Failed to query dispatch queue.')
        return jsonify({'error': 'Failed to query dispatch queue'}), 500

    now = datetime.utcnow()
    items = []
    status_counts = {}
    incident_counts = {}
    incident_state_counts = {}
    incident_severity_counts = {}
    escalation_dirty = False
    for booking in rows:
        status_key = (booking.status or '').strip().lower() or 'unknown'
        status_counts[status_key] = status_counts.get(status_key, 0) + 1

        driver = db.session.get(User, booking.assigned_driver_user_id) if booking.assigned_driver_user_id else None
        latest_location = (
            WasteRemovalVehicleLocation.query.filter_by(waste_removal_request_id=booking.id)
            .order_by(WasteRemovalVehicleLocation.recorded_at.desc(), WasteRemovalVehicleLocation.id.desc())
            .first()
        )
        queue_item = _serialize_dispatch_queue_item(
            booking,
            driver=driver,
            latest_location=latest_location,
            now=now,
        )
        for flag in queue_item['incident_flags']:
            incident_counts[flag] = incident_counts.get(flag, 0) + 1
        state = (queue_item.get('incident') or {}).get('state')
        severity = (queue_item.get('incident') or {}).get('severity')
        if state:
            incident_state_counts[state] = incident_state_counts.get(state, 0) + 1
        if severity:
            incident_severity_counts[severity] = incident_severity_counts.get(severity, 0) + 1
        if _dispatch_send_escalation_webhook(booking, queue_item, now=now, source='api_admin_dispatch_queue'):
            escalation_dirty = True
        items.append(queue_item)
    if escalation_dirty:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            app.logger.exception('Failed to persist dispatch queue escalation markers.')

    if incidents_only:
        items = [item for item in items if item.get('incident_flags')]
    if incident_state != 'all':
        items = [item for item in items if (item.get('incident') or {}).get('state') == incident_state]

    return jsonify(
        {
            'items': items,
            'pagination': {
                'limit': limit,
                'offset': offset,
                'returned': len(items),
                'total': total,
                'has_more': (offset + len(items)) < total,
            },
            'filters': {
                'statuses': statuses,
                'assigned': assigned,
                'incidents_only': incidents_only,
                'incident_state': incident_state,
            },
            'sla_thresholds': {
                'pending_match_minutes': _dispatch_pending_match_sla_minutes(),
                'unassigned_match_minutes': _dispatch_unassigned_match_sla_minutes(),
                'location_stale_minutes': _dispatch_location_stale_minutes(),
            },
            'summary': {
                'status_counts': status_counts,
                'incident_counts': incident_counts,
                'incident_state_counts': incident_state_counts,
                'incident_severity_counts': incident_severity_counts,
            },
        }
    )


@app.route('/api/v1/admin/dispatch/incidents', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_dispatch_incidents():
    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=500)
        offset = _parse_optional_int_query(request.args.get('offset'), 'offset', min_value=0)
        active_only = _parse_optional_bool_query(request.args.get('active_only'), 'active_only')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    limit = limit or 50
    offset = offset or 0
    active_only = True if active_only is None else bool(active_only)
    incident_state = (str(request.args.get('incident_state') or '').strip().lower() or 'all')
    if incident_state not in {'all', 'open', 'acknowledged', 'resolved'}:
        return jsonify({'error': 'incident_state must be one of all, open, acknowledged, resolved'}), 400

    allowed_statuses = {
        'pending_match',
        'matched',
        'accepted',
        'rejected',
        'en_route',
        'arrived',
        'collected',
        'completed',
        'cancelled',
    }
    statuses_raw = str(request.args.get('statuses') or '').strip().lower()
    if statuses_raw:
        statuses = [part.strip() for part in statuses_raw.split(',') if part.strip()]
        invalid_statuses = sorted({status for status in statuses if status not in allowed_statuses})
        if invalid_statuses:
            return jsonify(
                {
                    'error': 'Invalid status value(s).',
                    'invalid_statuses': invalid_statuses,
                    'allowed_statuses': sorted(allowed_statuses),
                }
            ), 400
    else:
        statuses = ['pending_match', 'matched', 'accepted', 'en_route', 'arrived', 'collected']

    try:
        query = WasteRemovalRequest.query.filter(WasteRemovalRequest.status.in_(statuses))
        rows = query.order_by(WasteRemovalRequest.created_at.asc(), WasteRemovalRequest.id.asc()).all()
    except SQLAlchemyError:
        app.logger.exception('Failed to query dispatch incidents.')
        return jsonify({'error': 'Failed to query dispatch incidents'}), 500

    now = datetime.utcnow()
    items = []
    escalation_dirty = False
    for booking in rows:
        queue_item = _get_dispatch_incident_context(booking, now=now)
        has_flags = bool(queue_item.get('incident_flags'))
        state = (queue_item.get('incident') or {}).get('state')
        if active_only and (not has_flags or state == 'resolved'):
            continue
        if incident_state != 'all' and state != incident_state:
            continue
        if _dispatch_send_escalation_webhook(booking, queue_item, now=now, source='api_admin_dispatch_incidents'):
            escalation_dirty = True
        items.append(queue_item)
    if escalation_dirty:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            app.logger.exception('Failed to persist dispatch incidents escalation markers.')

    def _incident_sort_key(item):
        flags = item.get('incident_flags') or []
        incident_state_value = (item.get('incident') or {}).get('state') or ''
        state_rank = {'open': 0, 'acknowledged': 1, 'resolved': 2}.get(incident_state_value, 3)
        pickup_due = item.get('pickup_due_minutes')
        overdue_rank = pickup_due if isinstance(pickup_due, int) and pickup_due > 0 else -1
        age = item.get('age_minutes') or 0
        return (state_rank, -len(flags), -overdue_rank, -age, item.get('request', {}).get('id') or 0)

    items = sorted(items, key=_incident_sort_key)
    total = len(items)
    page_items = items[offset : offset + limit]
    return jsonify(
        {
            'items': page_items,
            'pagination': {
                'limit': limit,
                'offset': offset,
                'returned': len(page_items),
                'total': total,
                'has_more': (offset + len(page_items)) < total,
            },
            'filters': {
                'statuses': statuses,
                'active_only': active_only,
                'incident_state': incident_state,
            },
        }
    )


@app.route('/api/v1/admin/dispatch/incidents/maintenance', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_dispatch_incident_maintenance():
    payload = request.get_json(silent=True) or {}
    raw_limit = payload.get('limit')
    raw_resolve_test_minutes = payload.get('resolve_test_minutes')
    raw_owner_admin_user_id = payload.get('owner_admin_user_id')
    owner_admin_email = _normalize_email(payload.get('owner_admin_email'))

    limit = _to_int_or_none(raw_limit)
    resolve_test_minutes = _to_int_or_none(raw_resolve_test_minutes)
    owner_admin_user_id = _to_int_or_none(raw_owner_admin_user_id)

    if raw_limit not in (None, '') and limit is None:
        return jsonify({'error': 'limit must be an integer >= 1'}), 400
    if limit is not None and limit < 1:
        return jsonify({'error': 'limit must be an integer >= 1'}), 400
    if raw_resolve_test_minutes not in (None, '') and resolve_test_minutes is None:
        return jsonify({'error': 'resolve_test_minutes must be an integer >= 1'}), 400
    if resolve_test_minutes is not None and resolve_test_minutes < 1:
        return jsonify({'error': 'resolve_test_minutes must be an integer >= 1'}), 400
    if raw_owner_admin_user_id not in (None, '') and owner_admin_user_id is None:
        return jsonify({'error': 'owner_admin_user_id must be an integer'}), 400

    if 'auto_assign' in payload:
        auto_assign = _is_truthy(payload.get('auto_assign'))
    else:
        auto_assign = _dispatch_incident_auto_assign_enabled()

    if 'auto_resolve_test' in payload:
        auto_resolve_test = _is_truthy(payload.get('auto_resolve_test'))
    else:
        auto_resolve_test = _dispatch_incident_auto_resolve_test_enabled()

    dry_run = _is_truthy(payload.get('dry_run'))
    if not auto_assign and not auto_resolve_test:
        return (
            jsonify(
                {
                    'error': 'No maintenance actions enabled.',
                    'hint': 'Set auto_assign and/or auto_resolve_test to true.',
                }
            ),
            400,
        )

    try:
        result = _run_dispatch_incident_maintenance(
            auto_assign=auto_assign,
            auto_resolve_test=auto_resolve_test,
            resolve_test_minutes=resolve_test_minutes,
            owner_admin_user_id=owner_admin_user_id,
            owner_admin_email=owner_admin_email,
            limit=limit,
            dry_run=dry_run,
            actor_user_id=_current_jwt_user_id(),
            actor_email=_current_jwt_email(),
            source='api_admin_dispatch_incident_maintenance',
        )
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception('Dispatch incident maintenance failed.')
        return jsonify({'error': 'Failed to run dispatch incident maintenance'}), 500

    return jsonify(result)


@app.route('/api/v1/admin/dispatch/incidents/<int:request_id>/ack', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_dispatch_incident_ack(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404

    payload = request.get_json(silent=True) or {}
    notes = (str(payload.get('notes') or '').strip()[:1000] or None)
    now = datetime.utcnow()
    queue_item = _get_dispatch_incident_context(booking, now=now)
    flags = queue_item.get('incident_flags') or []
    if not flags:
        return jsonify({'error': 'No active incident to acknowledge'}), 409

    booking.incident_state = 'acknowledged'
    booking.incident_severity = _dispatch_incident_severity(flags)
    booking.incident_owner_admin_user_id = _current_jwt_user_id()
    booking.incident_acknowledged_at = now
    booking.incident_resolved_at = None
    booking.incident_updated_at = now
    if notes:
        existing = (booking.incident_notes or '').strip()
        prefix = '[{} ACK] '.format(now.isoformat())
        booking.incident_notes = (existing + '\n' if existing else '') + prefix + notes

    _record_dispatch_incident_event(
        booking.id,
        event_type='incident_ack',
        actor_user_id=_current_jwt_user_id(),
        actor_email=_current_jwt_email(),
        source='api_admin_dispatch',
        details={
            'incident_state': booking.incident_state,
            'incident_severity': booking.incident_severity,
            'notes': notes,
            'incident_flags': flags,
        },
        occurred_at=now,
    )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception('Failed to acknowledge incident for request %s.', request_id)
        return jsonify({'error': 'Failed to acknowledge incident'}), 500

    metadata = {
        'action': 'ack',
        'admin_user_id': _current_jwt_user_id(),
        'incident_state': booking.incident_state,
        'incident_severity': booking.incident_severity,
        'notes': notes,
    }
    _publish_waste_request_event(
        booking.id,
        'admin_dispatch_incident_ack',
        payload=_serialize_waste_request_snapshot(booking),
        metadata=metadata,
    )
    _notify_mobile_push_for_waste_event(
        booking,
        'admin_dispatch_incident_ack',
        metadata=metadata,
    )
    refreshed_item = _get_dispatch_incident_context(booking)
    return jsonify(
        {
            'updated': True,
            'request': _serialize_waste_request_snapshot(booking),
            'incident': refreshed_item.get('incident'),
            'incident_flags': refreshed_item.get('incident_flags'),
        }
    )


@app.route('/api/v1/admin/dispatch/incidents/<int:request_id>/resolve', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_dispatch_incident_resolve(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404

    payload = request.get_json(silent=True) or {}
    notes = (str(payload.get('notes') or '').strip()[:1000] or None)
    now = datetime.utcnow()
    queue_item = _get_dispatch_incident_context(booking, now=now)
    flags = queue_item.get('incident_flags') or []

    booking.incident_state = 'resolved'
    booking.incident_owner_admin_user_id = _current_jwt_user_id()
    booking.incident_resolved_at = now
    booking.incident_updated_at = now
    if not booking.incident_acknowledged_at:
        booking.incident_acknowledged_at = now
    if not flags:
        booking.incident_severity = None
    if notes:
        existing = (booking.incident_notes or '').strip()
        prefix = '[{} RESOLVE] '.format(now.isoformat())
        booking.incident_notes = (existing + '\n' if existing else '') + prefix + notes

    _record_dispatch_incident_event(
        booking.id,
        event_type='incident_resolve',
        actor_user_id=_current_jwt_user_id(),
        actor_email=_current_jwt_email(),
        source='api_admin_dispatch',
        details={
            'incident_state': booking.incident_state,
            'incident_severity': booking.incident_severity,
            'notes': notes,
            'incident_flags': flags,
        },
        occurred_at=now,
    )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception('Failed to resolve incident for request %s.', request_id)
        return jsonify({'error': 'Failed to resolve incident'}), 500

    metadata = {
        'action': 'resolve',
        'admin_user_id': _current_jwt_user_id(),
        'incident_state': booking.incident_state,
        'incident_severity': booking.incident_severity,
        'notes': notes,
    }
    _publish_waste_request_event(
        booking.id,
        'admin_dispatch_incident_resolve',
        payload=_serialize_waste_request_snapshot(booking),
        metadata=metadata,
    )
    _notify_mobile_push_for_waste_event(
        booking,
        'admin_dispatch_incident_resolve',
        metadata=metadata,
    )
    refreshed_item = _get_dispatch_incident_context(booking)
    return jsonify(
        {
            'updated': True,
            'request': _serialize_waste_request_snapshot(booking),
            'incident': refreshed_item.get('incident'),
            'incident_flags': refreshed_item.get('incident_flags'),
        }
    )


@app.route('/api/v1/admin/dispatch/incidents/<int:request_id>/owner', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_dispatch_incident_owner(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404

    payload = request.get_json(silent=True) or {}
    if 'owner_admin_user_id' not in payload:
        return jsonify({'error': 'owner_admin_user_id is required (set null to unassign)'}), 400

    raw_owner_user_id = payload.get('owner_admin_user_id')
    if raw_owner_user_id in (None, ''):
        new_owner_user_id = None
        owner_user = None
    else:
        new_owner_user_id = _to_int_or_none(raw_owner_user_id)
        if new_owner_user_id is None:
            return jsonify({'error': 'owner_admin_user_id must be an integer or null'}), 400
        owner_user = db.session.get(User, new_owner_user_id)
        if not owner_user:
            return jsonify({'error': 'Owner admin user not found'}), 404
        if (owner_user.role or '').strip().lower() != 'admin':
            return jsonify({'error': 'Selected user is not an admin'}), 400
        if not owner_user.is_active_user:
            return jsonify({'error': 'Selected admin user is inactive'}), 409

    notes = (str(payload.get('notes') or '').strip()[:1000] or None)
    previous_owner_user_id = booking.incident_owner_admin_user_id
    if previous_owner_user_id == new_owner_user_id:
        queue_item = _get_dispatch_incident_context(booking)
        return jsonify(
            {
                'updated': False,
                'message': 'No owner change',
                'request': _serialize_waste_request_snapshot(booking),
                'incident': queue_item.get('incident'),
                'incident_flags': queue_item.get('incident_flags'),
                'previous_owner_admin_user_id': previous_owner_user_id,
                'owner_admin_user_id': booking.incident_owner_admin_user_id,
            }
        )

    now = datetime.utcnow()
    booking.incident_owner_admin_user_id = new_owner_user_id
    booking.incident_updated_at = now
    if notes:
        existing = (booking.incident_notes or '').strip()
        prefix = '[{} OWNER] '.format(now.isoformat())
        booking.incident_notes = (existing + '\n' if existing else '') + prefix + notes

    _record_dispatch_incident_event(
        booking.id,
        event_type='incident_owner_reassign',
        actor_user_id=_current_jwt_user_id(),
        actor_email=_current_jwt_email(),
        source='api_admin_dispatch',
        details={
            'previous_owner_admin_user_id': previous_owner_user_id,
            'owner_admin_user_id': new_owner_user_id,
            'notes': notes,
        },
        occurred_at=now,
    )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception('Failed to update incident owner for request %s.', request_id)
        return jsonify({'error': 'Failed to update incident owner'}), 500

    metadata = {
        'action': 'owner_reassign',
        'previous_owner_admin_user_id': previous_owner_user_id,
        'owner_admin_user_id': booking.incident_owner_admin_user_id,
        'admin_user_id': _current_jwt_user_id(),
        'notes': notes,
    }
    _publish_waste_request_event(
        booking.id,
        'admin_dispatch_incident_owner_reassign',
        payload=_serialize_waste_request_snapshot(booking),
        metadata=metadata,
    )
    _notify_mobile_push_for_waste_event(
        booking,
        'admin_dispatch_incident_owner_reassign',
        metadata=metadata,
    )
    refreshed_item = _get_dispatch_incident_context(booking)
    return jsonify(
        {
            'updated': True,
            'request': _serialize_waste_request_snapshot(booking),
            'incident': refreshed_item.get('incident'),
            'incident_flags': refreshed_item.get('incident_flags'),
            'previous_owner_admin_user_id': previous_owner_user_id,
            'owner_admin_user_id': booking.incident_owner_admin_user_id,
        }
    )


@app.route('/api/v1/admin/dispatch/telemetry', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_dispatch_telemetry():
    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=200)
        assigned = _parse_optional_bool_query(request.args.get('assigned'), 'assigned')
        incidents_only = _parse_optional_bool_query(request.args.get('incidents_only'), 'incidents_only')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    limit = limit or 50
    incidents_only = bool(incidents_only)
    incident_state = (str(request.args.get('incident_state') or '').strip().lower() or 'all')
    if incident_state not in {'all', 'open', 'acknowledged', 'resolved'}:
        return jsonify({'error': 'incident_state must be one of all, open, acknowledged, resolved'}), 400
    allowed_statuses = {
        'pending_match',
        'matched',
        'accepted',
        'rejected',
        'en_route',
        'arrived',
        'collected',
        'completed',
        'cancelled',
    }
    default_statuses = ['pending_match', 'matched', 'accepted', 'en_route', 'arrived', 'collected']

    statuses_raw = str(request.args.get('statuses') or '').strip().lower()
    if statuses_raw:
        statuses = [part.strip() for part in statuses_raw.split(',') if part.strip()]
        invalid_statuses = sorted({status for status in statuses if status not in allowed_statuses})
        if invalid_statuses:
            return jsonify(
                {
                    'error': 'Invalid status value(s).',
                    'invalid_statuses': invalid_statuses,
                    'allowed_statuses': sorted(allowed_statuses),
                }
            ), 400
    else:
        statuses = list(default_statuses)

    try:
        query = WasteRemovalRequest.query.filter(WasteRemovalRequest.status.in_(statuses))
        if assigned is True:
            query = query.filter(WasteRemovalRequest.assigned_driver_user_id.isnot(None))
        elif assigned is False:
            query = query.filter(WasteRemovalRequest.assigned_driver_user_id.is_(None))
        rows = query.order_by(WasteRemovalRequest.created_at.asc(), WasteRemovalRequest.id.asc()).all()
    except SQLAlchemyError:
        app.logger.exception('Failed to query dispatch telemetry.')
        return jsonify({'error': 'Failed to query dispatch telemetry'}), 500

    now = datetime.utcnow()
    items = []
    status_counts = {}
    incident_counts = {}
    incident_state_counts = {}
    incident_severity_counts = {}
    ack_latency_values = []
    resolve_latency_values = []
    escalation_dirty = False
    for booking in rows:
        status_key = (booking.status or '').strip().lower() or 'unknown'
        status_counts[status_key] = status_counts.get(status_key, 0) + 1

        driver = db.session.get(User, booking.assigned_driver_user_id) if booking.assigned_driver_user_id else None
        latest_location = (
            WasteRemovalVehicleLocation.query.filter_by(waste_removal_request_id=booking.id)
            .order_by(WasteRemovalVehicleLocation.recorded_at.desc(), WasteRemovalVehicleLocation.id.desc())
            .first()
        )
        queue_item = _serialize_dispatch_queue_item(
            booking,
            driver=driver,
            latest_location=latest_location,
            now=now,
        )
        for flag in queue_item.get('incident_flags') or []:
            incident_counts[flag] = incident_counts.get(flag, 0) + 1
        incident_info = queue_item.get('incident') or {}
        state = incident_info.get('state')
        severity = incident_info.get('severity')
        if state:
            incident_state_counts[state] = incident_state_counts.get(state, 0) + 1
        if severity:
            incident_severity_counts[severity] = incident_severity_counts.get(severity, 0) + 1
        if booking.incident_acknowledged_at and booking.created_at:
            ack_latency_values.append(
                max(0, int((booking.incident_acknowledged_at - booking.created_at).total_seconds() // 60))
            )
        if booking.incident_resolved_at and booking.created_at:
            resolve_latency_values.append(
                max(0, int((booking.incident_resolved_at - booking.created_at).total_seconds() // 60))
            )
        if _dispatch_send_escalation_webhook(booking, queue_item, now=now, source='api_admin_dispatch_telemetry'):
            escalation_dirty = True
        items.append(queue_item)
    if escalation_dirty:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            app.logger.exception('Failed to persist dispatch telemetry escalation markers.')

    if incidents_only:
        items = [item for item in items if item.get('incident_flags')]
    if incident_state != 'all':
        items = [item for item in items if (item.get('incident') or {}).get('state') == incident_state]

    def _incident_sort_key(item):
        flags = item.get('incident_flags') or []
        pickup_due = item.get('pickup_due_minutes')
        overdue_rank = pickup_due if isinstance(pickup_due, int) and pickup_due > 0 else -1
        age = item.get('age_minutes') or 0
        return (-len(flags), -overdue_rank, -age, item.get('request', {}).get('id') or 0)

    items = sorted(items, key=_incident_sort_key)
    requests_overdue = sum(
        1
        for item in items
        if isinstance(item.get('pickup_due_minutes'), int) and item['pickup_due_minutes'] > 0
    )
    requests_with_incidents = len([item for item in items if item.get('incident_flags')])
    incident_total = sum(len(item.get('incident_flags') or []) for item in items)

    return jsonify(
        {
            'items': items[:limit],
            'summary': {
                'total_rows': len(items),
                'requests_with_incidents': requests_with_incidents,
                'incident_total': incident_total,
                'requests_overdue': requests_overdue,
                'status_counts': status_counts,
                'incident_counts': incident_counts,
                'incident_state_counts': incident_state_counts,
                'incident_severity_counts': incident_severity_counts,
                'ack_latency_minutes_avg': (
                    round(sum(ack_latency_values) / len(ack_latency_values), 1) if ack_latency_values else None
                ),
                'resolve_latency_minutes_avg': (
                    round(sum(resolve_latency_values) / len(resolve_latency_values), 1)
                    if resolve_latency_values
                    else None
                ),
            },
            'filters': {
                'statuses': statuses,
                'assigned': assigned,
                'incidents_only': incidents_only,
                'incident_state': incident_state,
                'limit': limit,
            },
            'sla_thresholds': {
                'pending_match_minutes': _dispatch_pending_match_sla_minutes(),
                'unassigned_match_minutes': _dispatch_unassigned_match_sla_minutes(),
                'location_stale_minutes': _dispatch_location_stale_minutes(),
            },
        }
    )


@app.route('/api/v1/admin/waste-requests/<int:request_id>/dispatch/override', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_dispatch_override(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404

    payload = request.get_json(silent=True) or {}
    if 'driver_user_id' not in payload:
        return jsonify({'error': 'driver_user_id is required (set null to unassign)'}), 400

    raw_driver_user_id = payload.get('driver_user_id')
    if raw_driver_user_id in (None, ''):
        new_driver_user_id = None
        driver = None
    else:
        new_driver_user_id = _to_int_or_none(raw_driver_user_id)
        if new_driver_user_id is None:
            return jsonify({'error': 'driver_user_id must be an integer or null'}), 400
        driver = db.session.get(User, new_driver_user_id)
        if not driver:
            return jsonify({'error': 'Driver not found'}), 404
        if (driver.role or '').strip().lower() != 'driver':
            return jsonify({'error': 'Selected user is not a driver'}), 400
        if not driver.is_active_user:
            return jsonify({'error': 'Selected driver is inactive'}), 409

    reason = (str(payload.get('reason') or '').strip()[:255] or None)
    previous_driver_user_id = booking.assigned_driver_user_id
    if previous_driver_user_id == new_driver_user_id:
        current_driver = db.session.get(User, booking.assigned_driver_user_id) if booking.assigned_driver_user_id else None
        return jsonify(
            {
                'updated': False,
                'message': 'No assignment change',
                'request': _serialize_waste_request_snapshot(booking),
                'driver': _serialize_dispatch_driver(current_driver),
                'previous_assigned_driver_user_id': previous_driver_user_id,
                'assigned_driver_user_id': booking.assigned_driver_user_id,
            }
        )

    now = datetime.utcnow()
    booking.assigned_driver_user_id = new_driver_user_id
    _record_dispatch_incident_event(
        booking.id,
        event_type='dispatch_override',
        actor_user_id=_current_jwt_user_id(),
        actor_email=_current_jwt_email(),
        source='api_admin_dispatch',
        details={
            'previous_assigned_driver_user_id': previous_driver_user_id,
            'assigned_driver_user_id': new_driver_user_id,
            'reason': reason,
        },
        occurred_at=now,
    )
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception('Failed admin dispatch override for request %s.', request_id)
        return jsonify({'error': 'Failed to update dispatch assignment'}), 500

    metadata = {
        'previous_assigned_driver_user_id': previous_driver_user_id,
        'assigned_driver_user_id': booking.assigned_driver_user_id,
        'admin_user_id': _current_jwt_user_id(),
        'reason': reason,
    }
    _publish_waste_request_event(
        booking.id,
        'admin_dispatch_override',
        payload=_serialize_waste_request_snapshot(booking),
        metadata=metadata,
    )
    _notify_mobile_push_for_waste_event(
        booking,
        'admin_dispatch_override',
        metadata=metadata,
    )

    assigned_driver = db.session.get(User, booking.assigned_driver_user_id) if booking.assigned_driver_user_id else None
    return jsonify(
        {
            'updated': True,
            'request': _serialize_waste_request_snapshot(booking),
            'driver': _serialize_dispatch_driver(assigned_driver),
            'previous_assigned_driver_user_id': previous_driver_user_id,
            'assigned_driver_user_id': booking.assigned_driver_user_id,
            'reason': reason,
        }
    )


@app.route('/api/v1/admin/waste-requests/<int:request_id>/timeline', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_waste_request_timeline(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404

    try:
        include_actor_auth = _parse_optional_bool_query(
            request.args.get('include_actor_auth'),
            'include_actor_auth',
        )
        auth_window_hours = _parse_optional_int_query(
            request.args.get('auth_window_hours'),
            'auth_window_hours',
            min_value=1,
            max_value=24 * 30,
        )
        limit = _parse_optional_int_query(
            request.args.get('limit'),
            'limit',
            min_value=1,
            max_value=500,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    include_actor_auth = True if include_actor_auth is None else bool(include_actor_auth)
    auth_window_hours = auth_window_hours or 168
    limit = limit or 200

    timeline_rows, timeline_summary = _build_dispatch_request_timeline(
        booking,
        include_actor_auth=include_actor_auth,
        auth_window_hours=auth_window_hours,
        limit=limit,
    )
    return jsonify(
        {
            'request': _serialize_waste_request_snapshot(booking),
            'timeline': timeline_rows,
            'summary': timeline_summary,
            'filters': {
                'include_actor_auth': include_actor_auth,
                'auth_window_hours': auth_window_hours,
                'limit': limit,
            },
        }
    )


def _serialize_push_subscription(subscription):
    if not subscription:
        return None
    return {
        'id': subscription.id,
        'user_id': subscription.user_id,
        'provider': subscription.provider,
        'platform': subscription.platform,
        'token': subscription.token,
        'is_active': subscription.is_active,
        'last_seen_at': subscription.last_seen_at.isoformat() if subscription.last_seen_at else None,
        'created_at': subscription.created_at.isoformat() if subscription.created_at else None,
        'updated_at': subscription.updated_at.isoformat() if subscription.updated_at else None,
    }


@app.route('/api/v1/push-subscriptions', methods=['POST'])
@jwt_required(roles={'customer', 'driver', 'admin'})
def api_upsert_push_subscription():
    payload = request.get_json(silent=True) or {}
    token = str(payload.get('token') or '').strip()
    if not token:
        return jsonify({'error': 'token is required'}), 400
    if len(token) > 255:
        return jsonify({'error': 'token is too long'}), 400

    user_id = _current_jwt_user_id()
    if user_id is None:
        return jsonify({'error': 'Token missing valid user id claim'}), 401

    provider = (str(payload.get('provider') or 'expo').strip().lower() or 'expo')[:32]
    platform = (str(payload.get('platform') or '').strip().lower() or None)
    if platform:
        platform = platform[:32]

    subscription = MobilePushSubscription.query.filter_by(token=token).first()
    if not subscription:
        subscription = MobilePushSubscription(
            user_id=user_id,
            provider=provider,
            token=token,
            platform=platform,
            is_active=True,
            last_seen_at=datetime.utcnow(),
        )
        db.session.add(subscription)
    else:
        subscription.user_id = user_id
        subscription.provider = provider
        subscription.platform = platform
        subscription.is_active = True
        subscription.last_seen_at = datetime.utcnow()

    db.session.commit()
    return jsonify({'subscription': _serialize_push_subscription(subscription)})


@app.route('/api/v1/push-subscriptions', methods=['DELETE'])
@jwt_required(roles={'customer', 'driver', 'admin'})
def api_deactivate_push_subscription():
    payload = request.get_json(silent=True) or {}
    token = str(payload.get('token') or '').strip()
    if not token:
        return jsonify({'error': 'token is required'}), 400

    user_id = _current_jwt_user_id()
    if user_id is None:
        return jsonify({'error': 'Token missing valid user id claim'}), 401

    subscription = MobilePushSubscription.query.filter_by(
        token=token,
        user_id=user_id,
    ).first()
    if not subscription:
        return jsonify({'deactivated': False}), 200

    subscription.is_active = False
    subscription.last_seen_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'deactivated': True})


@app.route('/api/v1/waste-requests/<int:request_id>/payments', methods=['GET'])
@jwt_required(roles={'customer', 'driver', 'admin'})
def api_get_waste_request_financials(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_access_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403

    return jsonify(
        {
            'request_id': booking.id,
            'request_status': booking.status,
            'payments_enabled': _payments_enabled(),
            'financials': _financial_summary_for_request(booking.id),
        }
    )


@app.route('/api/v1/waste-requests/<int:request_id>/payments/charge', methods=['POST'])
@jwt_required(roles={'customer', 'admin'})
def api_create_payment_charge(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_access_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403
    if not _payments_enabled():
        return jsonify({'error': 'Payments are disabled by feature flag'}), 503
    if not _stripe_is_configured():
        return jsonify({'error': 'Payments are not configured. Set STRIPE_SECRET_KEY.'}), 503

    payload = request.get_json(silent=True) or {}
    amount_minor = _to_int_or_none(payload.get('amount_minor'))
    if amount_minor is None:
        amount_major = _to_float_or_none(payload.get('amount'))
        if amount_major is not None:
            amount_minor = int(round(amount_major * 100))
    if amount_minor is None or amount_minor <= 0:
        return jsonify({'error': 'amount_minor (or amount) must be a positive value'}), 400

    currency = (str(payload.get('currency') or _platform_currency()).strip().lower() or _platform_currency())
    if len(currency) != 3:
        return jsonify({'error': 'currency must be a 3-letter code'}), 400

    platform_fee_bps = _to_int_or_none(payload.get('platform_fee_bps'))
    if platform_fee_bps is None:
        platform_fee_bps = _platform_fee_bps()
    platform_fee_minor, driver_payout_minor = _compute_fee_split(amount_minor, platform_fee_bps)
    customer_user_id = _current_jwt_user_id()

    idempotency_key = str(payload.get('idempotency_key') or '').strip() or uuid.uuid4().hex
    payment_method_id = str(payload.get('payment_method_id') or '').strip() or None
    stripe_customer_id = str(payload.get('stripe_customer_id') or '').strip() or None
    return_url = str(payload.get('return_url') or '').strip() or None
    description = (
        str(payload.get('description') or '').strip()
        or 'Waste removal request #{}'.format(booking.id)
    )[:255]

    charge_row = WastePaymentCharge(
        waste_removal_request_id=booking.id,
        customer_user_id=customer_user_id,
        processor='stripe',
        amount_minor=amount_minor,
        currency=currency,
        platform_fee_minor=platform_fee_minor,
        driver_payout_minor=driver_payout_minor,
        status='initiated',
        metadata_json={
            'platform_fee_bps': platform_fee_bps,
            'request_id': booking.id,
            'assigned_driver_user_id': booking.assigned_driver_user_id,
        },
    )
    db.session.add(charge_row)

    try:
        db.session.flush()
        stripe_payload = {
            'amount': amount_minor,
            'currency': currency,
            'description': description,
            'automatic_payment_methods[enabled]': 'true',
            'metadata[request_id]': booking.id,
            'metadata[payment_charge_id]': charge_row.id,
            'metadata[platform_fee_bps]': platform_fee_bps,
        }
        if customer_user_id:
            stripe_payload['metadata[customer_user_id]'] = customer_user_id
        if booking.assigned_driver_user_id:
            stripe_payload['metadata[driver_user_id]'] = booking.assigned_driver_user_id
        if stripe_customer_id:
            stripe_payload['customer'] = stripe_customer_id
        if payment_method_id:
            stripe_payload['payment_method'] = payment_method_id
            stripe_payload['confirm'] = 'true'
        elif _is_truthy(payload.get('confirm')):
            stripe_payload['confirm'] = 'true'
            if return_url:
                stripe_payload['return_url'] = return_url

        payment_intent_payload = _stripe_request(
            'POST',
            '/v1/payment_intents',
            data=stripe_payload,
            idempotency_key=idempotency_key,
        )
        _sync_charge_from_payment_intent(charge_row, payment_intent_payload)
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    except Exception:
        db.session.rollback()
        app.logger.exception('Failed to create payment charge for request %s.', booking.id)
        return jsonify({'error': 'Failed to create payment charge'}), 500

    if (charge_row.status or '').lower() == 'succeeded':
        _publish_waste_request_event(
            booking.id,
            'payment_succeeded',
            payload=_serialize_waste_request_snapshot(booking),
            metadata={
                'payment_charge_id': charge_row.id,
                'payment_intent_id': charge_row.payment_intent_id,
            },
        )
        _notify_mobile_push_for_waste_event(
            booking,
            'payment_succeeded',
            metadata={
                'payment_charge_id': charge_row.id,
            },
        )

    return jsonify(
        {
            'charge': _serialize_payment_charge(charge_row),
            'financials': _financial_summary_for_request(booking.id),
        }
    ), 201


@app.route('/api/v1/waste-requests/<int:request_id>/payments/<int:charge_id>/refund', methods=['POST'])
@jwt_required(roles={'customer', 'admin'})
def api_create_payment_refund(request_id, charge_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_access_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403
    if not _payments_enabled():
        return jsonify({'error': 'Payments are disabled by feature flag'}), 503
    if not _stripe_is_configured():
        return jsonify({'error': 'Payments are not configured. Set STRIPE_SECRET_KEY.'}), 503

    charge_row = WastePaymentCharge.query.filter_by(
        id=charge_id,
        waste_removal_request_id=booking.id,
    ).first()
    if not charge_row:
        return jsonify({'error': 'Payment charge not found'}), 404

    if not charge_row.payment_intent_id and not charge_row.charge_id:
        return jsonify({'error': 'Charge is missing processor references and cannot be refunded'}), 409

    payload = request.get_json(silent=True) or {}
    remaining_refundable_minor = _remaining_refundable_minor(charge_row)
    if remaining_refundable_minor <= 0:
        return jsonify({'error': 'Charge is already fully refunded'}), 409

    amount_minor = _to_int_or_none(payload.get('amount_minor'))
    if amount_minor is None:
        amount_minor = remaining_refundable_minor
    if amount_minor <= 0:
        return jsonify({'error': 'amount_minor must be positive'}), 400
    if amount_minor > remaining_refundable_minor:
        return jsonify(
            {
                'error': 'amount_minor exceeds refundable balance',
                'remaining_refundable_minor': remaining_refundable_minor,
            }
        ), 400

    reason_raw = str(payload.get('reason') or '').strip().lower()
    stripe_reason = reason_raw if reason_raw in {'duplicate', 'fraudulent', 'requested_by_customer'} else None
    refund_reason = reason_raw or 'requested_by_customer'
    idempotency_key = str(payload.get('idempotency_key') or '').strip() or uuid.uuid4().hex

    try:
        stripe_payload = {
            'amount': amount_minor,
        }
        if charge_row.payment_intent_id:
            stripe_payload['payment_intent'] = charge_row.payment_intent_id
        elif charge_row.charge_id:
            stripe_payload['charge'] = charge_row.charge_id
        if stripe_reason:
            stripe_payload['reason'] = stripe_reason

        stripe_refund_payload = _stripe_request(
            'POST',
            '/v1/refunds',
            data=stripe_payload,
            idempotency_key=idempotency_key,
        )
        refund_status = _refund_status_from_stripe(stripe_refund_payload.get('status'))
        refund_row = WastePaymentRefund(
            waste_removal_request_id=booking.id,
            payment_charge_id=charge_row.id,
            processor='stripe',
            refund_id=(stripe_refund_payload.get('id') or '').strip() or None,
            amount_minor=_to_int_or_none(stripe_refund_payload.get('amount')) or amount_minor,
            currency=(stripe_refund_payload.get('currency') or charge_row.currency or _platform_currency()).strip().lower(),
            status=refund_status,
            reason=refund_reason[:120],
            processor_response=stripe_refund_payload,
        )
        db.session.add(refund_row)
        db.session.flush()

        remaining_after_refund = _remaining_refundable_minor(charge_row)
        if refund_status == 'succeeded':
            charge_row.refunded_at = datetime.utcnow()
            charge_row.status = 'refunded' if remaining_after_refund <= 0 else 'partially_refunded'
            charge_row.last_error = None
        elif refund_status == 'failed':
            charge_row.last_error = 'Refund failed'
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    except Exception:
        db.session.rollback()
        app.logger.exception('Failed to refund payment charge %s.', charge_row.id)
        return jsonify({'error': 'Failed to create refund'}), 500

    _publish_waste_request_event(
        booking.id,
        'refund_processed',
        payload=_serialize_waste_request_snapshot(booking),
        metadata={
            'payment_charge_id': charge_row.id,
            'refund_id': refund_row.id,
        },
    )
    _notify_mobile_push_for_waste_event(
        booking,
        'refund_processed',
        metadata={
            'payment_charge_id': charge_row.id,
            'refund_id': refund_row.id,
        },
    )

    return jsonify(
        {
            'refund': _serialize_payment_refund(refund_row),
            'charge': _serialize_payment_charge(charge_row),
            'financials': _financial_summary_for_request(booking.id),
        }
    ), 201


@app.route('/api/v1/waste-requests/<int:request_id>/payouts', methods=['POST'])
@jwt_required(roles={'admin'})
def api_create_driver_payout(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _payments_enabled():
        return jsonify({'error': 'Payments are disabled by feature flag'}), 503
    if not _stripe_is_configured():
        return jsonify({'error': 'Payments are not configured. Set STRIPE_SECRET_KEY.'}), 503

    payload = request.get_json(silent=True) or {}
    charge_id = _to_int_or_none(payload.get('payment_charge_id'))
    if charge_id is not None:
        charge_row = WastePaymentCharge.query.filter_by(
            id=charge_id,
            waste_removal_request_id=booking.id,
        ).first()
    else:
        charge_row = (
            WastePaymentCharge.query.filter(
                WastePaymentCharge.waste_removal_request_id == booking.id,
                WastePaymentCharge.status.in_(['succeeded', 'partially_refunded']),
            )
            .order_by(WastePaymentCharge.paid_at.desc(), WastePaymentCharge.id.desc())
            .first()
        )
    if not charge_row:
        return jsonify({'error': 'No eligible succeeded charge found for payout'}), 409

    driver_user_id = _to_int_or_none(payload.get('driver_user_id')) or booking.assigned_driver_user_id
    if not driver_user_id:
        return jsonify({'error': 'No assigned driver for payout'}), 409

    destination_account_id = str(payload.get('destination_account_id') or '').strip()
    if not destination_account_id:
        return jsonify({'error': 'destination_account_id is required (Stripe connected account id)'}), 400

    remaining_payout_minor = _remaining_driver_payout_minor(charge_row)
    if remaining_payout_minor <= 0:
        return jsonify({'error': 'No remaining driver payout balance'}), 409

    amount_minor = _to_int_or_none(payload.get('amount_minor'))
    if amount_minor is None:
        amount_minor = remaining_payout_minor
    if amount_minor <= 0:
        return jsonify({'error': 'amount_minor must be positive'}), 400
    if amount_minor > remaining_payout_minor:
        return jsonify(
            {
                'error': 'amount_minor exceeds driver payout balance',
                'remaining_driver_payout_minor': remaining_payout_minor,
            }
        ), 400

    idempotency_key = str(payload.get('idempotency_key') or '').strip() or uuid.uuid4().hex
    description = (
        str(payload.get('description') or '').strip()
        or 'Driver payout for request #{}'.format(booking.id)
    )[:255]

    try:
        stripe_transfer_payload = _stripe_request(
            'POST',
            '/v1/transfers',
            data={
                'amount': amount_minor,
                'currency': (charge_row.currency or _platform_currency()),
                'destination': destination_account_id,
                'description': description,
                'metadata[request_id]': booking.id,
                'metadata[payment_charge_id]': charge_row.id,
                'metadata[driver_user_id]': driver_user_id,
                'transfer_group': 'waste_request_{}'.format(booking.id),
            },
            idempotency_key=idempotency_key,
        )
        payout_status = _payout_status_from_stripe(stripe_transfer_payload)
        payout_row = WasteDriverPayout(
            waste_removal_request_id=booking.id,
            payment_charge_id=charge_row.id,
            driver_user_id=driver_user_id,
            processor='stripe',
            payout_id=(stripe_transfer_payload.get('id') or '').strip() or None,
            destination_account_id=destination_account_id[:120],
            amount_minor=amount_minor,
            currency=(stripe_transfer_payload.get('currency') or charge_row.currency or _platform_currency()).strip().lower(),
            status=payout_status,
            paid_out_at=datetime.utcnow() if payout_status == 'paid' else None,
            processor_response=stripe_transfer_payload,
        )
        db.session.add(payout_row)
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    except Exception:
        db.session.rollback()
        app.logger.exception('Failed to create driver payout for request %s.', booking.id)
        return jsonify({'error': 'Failed to create driver payout'}), 500

    _publish_waste_request_event(
        booking.id,
        'payout_processed',
        payload=_serialize_waste_request_snapshot(booking),
        metadata={
            'payment_charge_id': charge_row.id,
            'payout_id': payout_row.id,
        },
    )
    _notify_mobile_push_for_waste_event(
        booking,
        'payout_processed',
        metadata={
            'payment_charge_id': charge_row.id,
            'payout_id': payout_row.id,
        },
    )
    return jsonify(
        {
            'payout': _serialize_driver_payout(payout_row),
            'financials': _financial_summary_for_request(booking.id),
        }
    ), 201


@app.route('/api/v1/payments/stripe/webhook', methods=['POST'])
def api_stripe_webhook():
    if not _payments_enabled():
        return jsonify({'received': True, 'handled': False, 'disabled': True})

    raw_payload = request.get_data(cache=False, as_text=False) or b''
    signature_header = request.headers.get('Stripe-Signature', '')
    if _stripe_webhook_secret() and not _verify_stripe_webhook_signature(raw_payload, signature_header):
        return jsonify({'error': 'Invalid Stripe signature'}), 400

    event_payload = request.get_json(silent=True) or {}
    if not isinstance(event_payload, dict):
        return jsonify({'error': 'Invalid webhook payload'}), 400

    event_type = str(event_payload.get('type') or '').strip()
    stripe_object = ((event_payload.get('data') or {}).get('object') or {})
    handled = False

    try:
        if event_type.startswith('payment_intent.') and isinstance(stripe_object, dict):
            payment_intent_id = str(stripe_object.get('id') or '').strip()
            if payment_intent_id:
                charge_row = WastePaymentCharge.query.filter_by(payment_intent_id=payment_intent_id).first()
                if not charge_row:
                    metadata = stripe_object.get('metadata') or {}
                    metadata_charge_id = _to_int_or_none(metadata.get('payment_charge_id'))
                    if metadata_charge_id:
                        charge_row = db.session.get(WastePaymentCharge, metadata_charge_id)

                if charge_row:
                    previous_status = charge_row.status
                    _sync_charge_from_payment_intent(charge_row, stripe_object)
                    if event_type == 'payment_intent.payment_failed':
                        charge_row.status = 'failed'
                        payment_error = stripe_object.get('last_payment_error') or {}
                        if isinstance(payment_error, dict):
                            charge_row.last_error = (payment_error.get('message') or 'Payment failed')[:2000]
                        else:
                            charge_row.last_error = 'Payment failed'
                    db.session.commit()
                    handled = True

                    booking = db.session.get(WasteRemovalRequest, charge_row.waste_removal_request_id)
                    if (
                        booking
                        and (charge_row.status or '').lower() == 'succeeded'
                        and (previous_status or '').lower() != 'succeeded'
                    ):
                        _publish_waste_request_event(
                            booking.id,
                            'payment_succeeded',
                            payload=_serialize_waste_request_snapshot(booking),
                            metadata={
                                'payment_charge_id': charge_row.id,
                                'payment_intent_id': charge_row.payment_intent_id,
                                'source': 'stripe_webhook',
                            },
                        )
                        _notify_mobile_push_for_waste_event(
                            booking,
                            'payment_succeeded',
                            metadata={
                                'payment_charge_id': charge_row.id,
                                'source': 'stripe_webhook',
                            },
                        )

        if event_type in {'refund.created', 'refund.updated'} and isinstance(stripe_object, dict):
            payment_intent_id = str(stripe_object.get('payment_intent') or '').strip()
            charge_id = str(stripe_object.get('charge') or '').strip()
            charge_row = None
            if payment_intent_id:
                charge_row = WastePaymentCharge.query.filter_by(payment_intent_id=payment_intent_id).first()
            if not charge_row and charge_id:
                charge_row = WastePaymentCharge.query.filter_by(charge_id=charge_id).first()

            if charge_row:
                stripe_refund_id = str(stripe_object.get('id') or '').strip()
                refund_row = WastePaymentRefund.query.filter_by(refund_id=stripe_refund_id).first()
                if not refund_row:
                    refund_row = WastePaymentRefund(
                        waste_removal_request_id=charge_row.waste_removal_request_id,
                        payment_charge_id=charge_row.id,
                        processor='stripe',
                        refund_id=stripe_refund_id or None,
                        amount_minor=_to_int_or_none(stripe_object.get('amount')) or 0,
                        currency=(stripe_object.get('currency') or charge_row.currency or _platform_currency()).strip().lower(),
                        status=_refund_status_from_stripe(stripe_object.get('status')),
                        reason=(str(stripe_object.get('reason') or '').strip() or None),
                        processor_response=stripe_object,
                    )
                    db.session.add(refund_row)
                else:
                    refund_row.amount_minor = _to_int_or_none(stripe_object.get('amount')) or refund_row.amount_minor
                    refund_row.currency = (stripe_object.get('currency') or refund_row.currency or _platform_currency()).strip().lower()
                    refund_row.status = _refund_status_from_stripe(stripe_object.get('status'))
                    refund_row.reason = (str(stripe_object.get('reason') or '').strip() or refund_row.reason)
                    refund_row.processor_response = stripe_object

                if (refund_row.status or '').lower() != 'failed':
                    remaining_refundable_minor = _remaining_refundable_minor(charge_row)
                    if remaining_refundable_minor <= 0:
                        charge_row.status = 'refunded'
                        charge_row.refunded_at = datetime.utcnow()
                    else:
                        charge_row.status = 'partially_refunded'

                db.session.commit()
                handled = True

                booking = db.session.get(WasteRemovalRequest, charge_row.waste_removal_request_id)
                if booking:
                    _publish_waste_request_event(
                        booking.id,
                        'refund_processed',
                        payload=_serialize_waste_request_snapshot(booking),
                        metadata={
                            'payment_charge_id': charge_row.id,
                            'stripe_refund_id': stripe_refund_id,
                            'source': 'stripe_webhook',
                        },
                    )
                    _notify_mobile_push_for_waste_event(
                        booking,
                        'refund_processed',
                        metadata={
                            'payment_charge_id': charge_row.id,
                            'stripe_refund_id': stripe_refund_id,
                            'source': 'stripe_webhook',
                        },
                    )

        if event_type.startswith('transfer.') and isinstance(stripe_object, dict):
            transfer_id = str(stripe_object.get('id') or '').strip()
            if transfer_id:
                payout_row = WasteDriverPayout.query.filter_by(payout_id=transfer_id).first()
                if payout_row:
                    payout_row.status = _payout_status_from_stripe(stripe_object)
                    if event_type == 'transfer.failed':
                        payout_row.status = 'failed'
                    elif event_type in {'transfer.reversed', 'transfer.updated'}:
                        try:
                            amount_reversed = int(stripe_object.get('amount_reversed') or 0)
                        except (TypeError, ValueError):
                            amount_reversed = 0
                        if amount_reversed > 0:
                            payout_row.status = 'reversed'
                    if payout_row.status == 'paid':
                        payout_row.paid_out_at = payout_row.paid_out_at or datetime.utcnow()
                    payout_row.processor_response = stripe_object
                    db.session.commit()
                    handled = True

                    booking = db.session.get(WasteRemovalRequest, payout_row.waste_removal_request_id)
                    if booking and payout_row.status == 'paid':
                        _publish_waste_request_event(
                            booking.id,
                            'payout_processed',
                            payload=_serialize_waste_request_snapshot(booking),
                            metadata={
                                'payment_charge_id': payout_row.payment_charge_id,
                                'payout_id': payout_row.id,
                                'source': 'stripe_webhook',
                            },
                        )
                        _notify_mobile_push_for_waste_event(
                            booking,
                            'payout_processed',
                            metadata={
                                'payment_charge_id': payout_row.payment_charge_id,
                                'payout_id': payout_row.id,
                                'source': 'stripe_webhook',
                            },
                        )
    except Exception:
        db.session.rollback()
        app.logger.exception('Failed processing Stripe webhook event %s.', event_type)
        return jsonify({'error': 'Webhook processing failed'}), 500

    return jsonify({'received': True, 'handled': handled, 'type': event_type})


@app.route('/api/v1/waste-requests', methods=['POST'])
@jwt_required(roles={'customer', 'admin'})
def api_create_waste_request():
    data = request.get_json(silent=True) or {}
    try:
        role = _current_jwt_role()
        required_fields = [
            'requester_name',
            'requester_email',
            'material_type',
            'waste_amount',
            'waste_unit',
            'match_radius_miles',
            'pickup_address',
            'pickup_postcode',
            'scheduled_pickup_at',
        ]
        cleaned = {}
        missing = []
        for field in required_fields:
            value = str(data.get(field) or '').strip()
            cleaned[field] = value
            if not value:
                missing.append(field)
        if missing:
            return jsonify({'error': 'Missing required field(s)', 'fields': missing}), 400

        requester_email = cleaned['requester_email'].strip().lower()
        if role == 'customer':
            token_email = _current_jwt_email()
            if not token_email:
                return jsonify({'error': 'Token missing email claim'}), 403
            requester_email = token_email

        material_type = cleaned['material_type']
        if material_type == 'Other':
            custom_material_type = str(data.get('custom_material_type') or '').strip()
            if not custom_material_type:
                return jsonify({'error': 'custom_material_type is required when material_type is Other'}), 400
            material_type = custom_material_type[:120]

        waste_amount = _to_float_or_none(cleaned['waste_amount'])
        if waste_amount is None or waste_amount <= 0:
            return jsonify({'error': 'waste_amount must be a positive number'}), 400

        match_radius_miles = _to_float_or_none(cleaned['match_radius_miles'])
        if match_radius_miles is None or match_radius_miles <= 0:
            return jsonify({'error': 'match_radius_miles must be a positive number'}), 400

        scheduled_pickup_at = _parse_datetime_or_error(cleaned['scheduled_pickup_at'], 'scheduled_pickup_at')
        if scheduled_pickup_at <= datetime.now():
            return jsonify({'error': 'scheduled_pickup_at must be in the future'}), 400

        pickup_latitude, pickup_longitude = _postcode_coordinates(cleaned['pickup_postcode'])

        booking = WasteRemovalRequest(
            requester_name=cleaned['requester_name'][:120],
            requester_email=requester_email[:255],
            material_type=material_type,
            waste_amount=waste_amount,
            waste_unit=cleaned['waste_unit'][:32],
            pickup_address=cleaned['pickup_address'][:255],
            pickup_city=(str(data.get('pickup_city') or '').strip()[:120] or None),
            pickup_county=(str(data.get('pickup_county') or '').strip()[:120] or None),
            pickup_postcode=cleaned['pickup_postcode'][:32],
            scheduled_pickup_at=scheduled_pickup_at,
            notes=(str(data.get('notes') or '').strip() or None),
            status='pending_match',
        )
        db.session.add(booking)
        db.session.flush()

        provider_candidates, dispatch_offer_rows = _create_dispatch_offers_for_request(
            booking,
            pickup_latitude,
            pickup_longitude,
            match_radius_miles,
        )
        closest_candidate = provider_candidates[0] if provider_candidates else None
        drive_time_info = None
        if closest_candidate:
            drive_time_info = _drive_time_between_points(
                pickup_latitude,
                pickup_longitude,
                closest_candidate['provider_latitude'],
                closest_candidate['provider_longitude'],
            )
        if dispatch_offer_rows:
            db.session.add_all(dispatch_offer_rows)

        db.session.commit()
        base_url = (app.config.get('APP_BASE_URL') or request.url_root.rstrip('/')).rstrip('/')
        provider_notifications_sent = _notify_dispatch_offers(booking, dispatch_offer_rows, base_url)
        _publish_waste_request_event(
            booking.id,
            'request_created',
            payload=_serialize_waste_request_snapshot(booking),
            metadata={
                'offers_created': len(dispatch_offer_rows),
                'provider_notifications_sent': provider_notifications_sent,
            },
        )
        _notify_mobile_push_for_waste_event(
            booking,
            'request_created',
            metadata={
                'offers_created': len(dispatch_offer_rows),
            },
        )
        return (
            jsonify(
                {
                    'request': _serialize_waste_request(booking),
                    'match': None,
                    'drive_time': drive_time_info,
                    'dispatch': {
                        'offers_created': len(dispatch_offer_rows),
                        'provider_notifications_sent': provider_notifications_sent,
                        'closest_candidate': closest_candidate,
                    },
                }
            ),
            201,
        )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    except Exception:
        db.session.rollback()
        app.logger.exception('API waste request creation failed.')
        return jsonify({'error': 'Failed to create waste request'}), 500


@app.route('/api/v1/waste-requests/<int:request_id>/dispatch/accept', methods=['POST'])
@jwt_required(roles={'driver'})
def api_accept_dispatch_offer(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404

    payload = request.get_json(silent=True) or {}
    offer_token = str(payload.get('offer_token') or '').strip()
    if not offer_token:
        return jsonify({'error': 'offer_token is required'}), 400

    offer = WasteRemovalDispatchOffer.query.filter_by(
        waste_removal_request_id=booking.id,
        offer_token=offer_token,
    ).first()
    if not offer:
        return jsonify({'error': 'Dispatch offer not found'}), 404

    driver_user_id = _current_jwt_user_id()
    if driver_user_id is None:
        return jsonify({'error': 'Token missing valid user id claim'}), 401

    match_row, outcome = _accept_dispatch_offer(
        booking,
        offer,
        assigned_driver_user_id=driver_user_id,
    )
    if outcome == 'accepted':
        _publish_waste_request_event(
            booking.id,
            'dispatch_offer_accepted',
            payload=_serialize_waste_request_snapshot(booking),
            metadata={
                'accepted_offer_id': offer.id,
                'accepted_offer_rank': offer.offer_rank,
                'assigned_driver_user_id': booking.assigned_driver_user_id,
            },
        )
        _notify_mobile_push_for_waste_event(
            booking,
            'dispatch_offer_accepted',
            metadata={
                'accepted_offer_id': offer.id,
                'accepted_offer_rank': offer.offer_rank,
            },
        )
        return jsonify(
            {
                'request': _serialize_waste_request(booking),
                'match': _serialize_waste_match(match_row),
                'accepted_offer': _serialize_dispatch_offer(offer),
                'dispatch': _dispatch_summary_for_request(booking.id),
            }
        )
    if outcome == 'already_matched':
        return (
            jsonify(
                {
                    'error': 'Request already matched',
                    'match': _serialize_waste_match(match_row),
                    'dispatch': _dispatch_summary_for_request(booking.id),
                }
            ),
            409,
        )
    if outcome == 'driver_mismatch':
        return jsonify({'error': 'Request is assigned to a different driver'}), 409
    if outcome == 'offer_unavailable':
        return (
            jsonify(
                {
                    'error': 'Dispatch offer is no longer available',
                    'offer': _serialize_dispatch_offer(offer),
                }
            ),
            409,
        )
    return jsonify({'error': 'Invalid dispatch offer'}), 400


@app.route('/api/v1/waste-requests/<int:request_id>', methods=['GET'])
@jwt_required(roles={'customer', 'driver', 'admin'})
def api_get_waste_request(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_access_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403

    return jsonify(_serialize_waste_request_snapshot(booking))


@app.route('/api/v1/waste-requests/<int:request_id>/events', methods=['GET'])
@jwt_required(roles={'customer', 'driver', 'admin'})
def api_stream_waste_request_events(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_access_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403

    heartbeat_seconds = int(app.config.get('WASTE_REQUEST_STREAM_HEARTBEAT_SECONDS') or 20)
    heartbeat_seconds = max(5, heartbeat_seconds)
    channel = _subscribe_waste_request_events(request_id)
    last_event_id = _parse_waste_request_last_event_id(
        request.args.get('last_event_id') or request.headers.get('Last-Event-ID')
    )
    replay_events = _waste_request_replay_events_since(request_id, last_event_id)
    initial_event = {
        'event': 'snapshot',
        'request_id': request_id,
        'occurred_at': datetime.utcnow().isoformat() + 'Z',
        'payload': _serialize_waste_request_snapshot(booking),
        'metadata': {},
    }

    @stream_with_context
    def _event_stream():
        try:
            yield _format_sse_event('waste_request', initial_event)
            for replay_event in replay_events:
                replay_event_id = _parse_waste_request_last_event_id(replay_event.get('event_id'))
                yield _format_sse_event('waste_request', replay_event, event_id=replay_event_id)
            while True:
                try:
                    event_payload = channel.get(timeout=heartbeat_seconds)
                    event_id = _parse_waste_request_last_event_id(event_payload.get('event_id'))
                    yield _format_sse_event('waste_request', event_payload, event_id=event_id)
                except queue.Empty:
                    yield ': keepalive\n\n'
        except GeneratorExit:
            pass
        finally:
            _unsubscribe_waste_request_events(request_id, channel)

    response = Response(_event_stream(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Connection'] = 'keep-alive'
    response.headers['X-Accel-Buffering'] = 'no'
    return response


@app.route('/api/v1/waste-requests/<int:request_id>/status', methods=['POST'])
@jwt_required(roles={'driver', 'admin'})
def api_update_waste_request_status(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_access_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403

    payload = request.get_json(silent=True) or {}
    new_status = str(payload.get('status') or '').strip().lower()
    allowed_statuses = {
        'pending_match',
        'matched',
        'accepted',
        'rejected',
        'en_route',
        'arrived',
        'collected',
        'completed',
        'cancelled',
    }
    if new_status not in allowed_statuses:
        return jsonify({'error': 'Invalid status', 'allowed_statuses': sorted(allowed_statuses)}), 400

    requires_match_statuses = {'matched', 'accepted', 'en_route', 'arrived', 'collected', 'completed'}
    if new_status in requires_match_statuses:
        match_row = _get_latest_match_for_request(booking.id)
        if not match_row:
            return jsonify({'error': 'No provider has accepted this request yet'}), 409

    previous_status = booking.status
    booking.status = new_status
    db.session.commit()
    _publish_waste_request_event(
        booking.id,
        'status_updated',
        payload=_serialize_waste_request_snapshot(booking),
        metadata={
            'previous_status': previous_status,
            'new_status': new_status,
        },
    )
    _notify_mobile_push_for_waste_event(
        booking,
        'status_updated',
        metadata={
            'previous_status': previous_status,
            'new_status': new_status,
        },
    )
    return jsonify({'request': _serialize_waste_request(booking)})


@app.route('/api/v1/waste-requests/<int:request_id>/location', methods=['POST'])
@jwt_required(roles={'driver', 'admin'})
def api_create_vehicle_location(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_access_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403

    payload = request.get_json(silent=True) or {}
    latitude = _to_float_or_none(payload.get('latitude'))
    longitude = _to_float_or_none(payload.get('longitude'))
    if latitude is None or longitude is None:
        return jsonify({'error': 'latitude and longitude are required numeric values'}), 400

    recorded_raw = payload.get('recorded_at')
    if recorded_raw:
        try:
            recorded_at = _parse_datetime_or_error(recorded_raw, 'recorded_at')
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
    else:
        recorded_at = datetime.utcnow()

    location_row = WasteRemovalVehicleLocation(
        waste_removal_request_id=booking.id,
        driver_id=(str(_current_jwt_user_id() or '').strip()[:120] or None),
        vehicle_id=(str(payload.get('vehicle_id') or '').strip()[:120] or None),
        latitude=latitude,
        longitude=longitude,
        recorded_at=recorded_at,
        source=(str(payload.get('source') or 'mobile').strip()[:32] or 'mobile'),
    )
    db.session.add(location_row)
    db.session.commit()
    _publish_waste_request_event(
        booking.id,
        'location_updated',
        payload=_serialize_waste_request_snapshot(booking),
        metadata={
            'location_id': location_row.id,
            'latitude': location_row.latitude,
            'longitude': location_row.longitude,
        },
    )
    return jsonify({'location': _serialize_vehicle_location(location_row)}), 201


@app.route('/api/v1/waste-requests/<int:request_id>/location/latest', methods=['GET'])
@jwt_required(roles={'customer', 'driver', 'admin'})
def api_get_latest_vehicle_location(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_access_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403

    location_row = (
        WasteRemovalVehicleLocation.query.filter_by(waste_removal_request_id=booking.id)
        .order_by(WasteRemovalVehicleLocation.recorded_at.desc(), WasteRemovalVehicleLocation.id.desc())
        .first()
    )
    if not location_row:
        return jsonify({'error': 'No location updates for this request yet'}), 404

    return jsonify(
        {
            'request_id': booking.id,
            'request_status': booking.status,
            'latest_location': _serialize_vehicle_location(location_row),
        }
    )

#  Error Handling and Initializing
#  ----------------------------------------------------------------
@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def server_error(error):
    return render_template('errors/500.html'), 500


if not app.debug:
    file_handler = FileHandler('error.log')
    file_handler.setFormatter(
        Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')
    )
    app.logger.setLevel(logging.INFO)
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.info('errors')


# Default port:
if __name__ == '__main__':
    app.run()

# Or specify port manually:
'''
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
'''
