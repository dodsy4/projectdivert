"""Shared fixtures for the Project Divert test suite.

Tests reach the application through the ``app_context`` namespace, which
exposes the app, the models and the service modules. Monkeypatch the module
that *owns* a dependency rather than this namespace -- for example
``monkeypatch.setattr(app_context.reference_data, 'suppliers', frame)`` -- so
that the patch is visible to every caller of that dependency.
"""

import os

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/projectdivert_pytest.db'
os.environ['SESSION_COOKIE_SECURE'] = '0'
os.environ['SECRET_KEY'] = 'pytest-secret-key'

import pytest
import requests
from werkzeug.security import generate_password_hash

from projectdivert import create_app
from projectdivert.extensions import db
from projectdivert.models import (
    AuditEvent, AuthAuditEvent, AuthLifecycleToken, CarrierCompany,
    CompanyComplianceDocument, DispatchIncidentEvent, DiversionEstimate,
    DriverComplianceDocument, Material, SupplierReference, User,
    WasteRemovalDispatchOffer, WasteRemovalMatch, WasteRemovalRequest,
)
from projectdivert.services import (
    audit, auth, dispatch, events, geo, lca_glue, notifications, rate_limit,
    reference_data, uploads,
)


class AppUnderTest:
    """Test-facing view of the application and the pieces tests exercise."""

    def __init__(self, app):
        self.app = app
        self.db = db
        self.requests = requests
        self.generate_password_hash = generate_password_hash

        # Service modules: patch attributes on these.
        self.audit = audit
        self.auth = auth
        self.dispatch = dispatch
        self.events = events
        self.geo = geo
        self.lca_glue = lca_glue
        self.notifications = notifications
        self.rate_limit = rate_limit
        self.reference_data = reference_data
        self.uploads = uploads

        # Models.
        self.AuditEvent = AuditEvent
        self.AuthAuditEvent = AuthAuditEvent
        self.AuthLifecycleToken = AuthLifecycleToken
        self.CarrierCompany = CarrierCompany
        self.CompanyComplianceDocument = CompanyComplianceDocument
        self.DispatchIncidentEvent = DispatchIncidentEvent
        self.DiversionEstimate = DiversionEstimate
        self.DriverComplianceDocument = DriverComplianceDocument
        self.Material = Material
        self.SupplierReference = SupplierReference
        self.User = User
        self.WasteRemovalDispatchOffer = WasteRemovalDispatchOffer
        self.WasteRemovalMatch = WasteRemovalMatch
        self.WasteRemovalRequest = WasteRemovalRequest

        # Helpers called directly by tests.
        self._audit_diff = audit._audit_diff
        self.record_audit_event = audit.record_audit_event
        self._publish_waste_request_event = events._publish_waste_request_event
        self._waste_request_replay_events_since = events._waste_request_replay_events_since
        self._waste_request_event_history = events._waste_request_event_history
        self._waste_request_event_lock = events._waste_request_event_lock
        self._waste_request_event_subscribers = events._waste_request_event_subscribers
        self._refresh_reference_dataframes_from_db = reference_data._refresh_reference_dataframes_from_db
        self._select_best_provider_within_radius = dispatch._select_best_provider_within_radius
        self._select_provider_candidates_within_radius = dispatch._select_provider_candidates_within_radius
        self.assess_diversion_estimate = lca_glue.assess_diversion_estimate

        # Mutable auth state shared with services.rate_limit.
        self._auth_rate_limit_lock = rate_limit._auth_rate_limit_lock
        self._auth_rate_limit_events = rate_limit._auth_rate_limit_events
        self._auth_login_lockout_lock = rate_limit._auth_login_lockout_lock
        self._auth_login_lockouts = rate_limit._auth_login_lockouts


def _reset_postcode_cache():
    geo.clear_postcode_cache()


def _reset_auth_state():
    with rate_limit._auth_rate_limit_lock:
        rate_limit._auth_rate_limit_events.clear()
    with rate_limit._auth_login_lockout_lock:
        rate_limit._auth_login_lockouts.clear()
    rate_limit._auth_rate_limit_redis_client = None
    rate_limit._auth_rate_limit_redis_disabled = False


@pytest.fixture(scope='session')
def flask_app():
    """One application instance for the whole session."""
    return create_app()


@pytest.fixture
def app_context(flask_app):
    flask_app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        AUTH_RATE_LIMIT_ENABLED=False,
        AUTH_LOGIN_LOCKOUT_ENABLED=False,
    )
    _reset_auth_state()
    _reset_postcode_cache()

    with flask_app.app_context():
        db.session.remove()
        db.drop_all()
        db.create_all()

    yield AppUnderTest(flask_app)

    _reset_auth_state()
    with flask_app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app_context):
    return app_context.app.test_client()
