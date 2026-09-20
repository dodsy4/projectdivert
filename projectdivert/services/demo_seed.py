"""Populate the application with a demo scenario.

Demonstrating the product from an empty database means clicking through every
stage before you can show anything, and a collection cannot be shown reaching a
carbon certificate at all without one that has already completed. This builds a
scenario that is already part-way through: a site manager with collections at
each stage, and a driver who is compliant enough to be dispatched.

The accounts it creates have a known password, so it refuses to run unless the
environment says that is acceptable. See :func:`seeding_allowed`.
"""

import logging
from datetime import timedelta

from flask import current_app
from werkzeug.security import generate_password_hash

from projectdivert.extensions import db
from projectdivert.models.compliance import (
    CarrierCompany,
    CompanyComplianceDocument,
    DriverComplianceDocument,
    WasteComplianceDocument,
)
from projectdivert.models.audit import AuditEvent, AuthAuditEvent
from projectdivert.models.auth import AuthLifecycleToken, AuthSecurityBlocklist
from projectdivert.models.mobile import MobilePushSubscription
from projectdivert.models.payments import (
    WasteDriverPayout,
    WastePaymentCharge,
    WastePaymentRefund,
)
from projectdivert.models.user import User
from projectdivert.models.waste import (
    DispatchIncidentEvent,
    WasteRemovalDispatchOffer,
    WasteRemovalMatch,
    WasteRemovalRequest,
    WasteRemovalVehicleLocation,
    WasteRequestCommunicationLog,
)
from projectdivert.services.utils import _is_truthy, utcnow

logger = logging.getLogger(__name__)

#: .test is reserved by RFC 2606 and can never be a real domain, so these
#: addresses cannot collide with a real person's and cannot receive mail.
DEMO_EMAIL_DOMAIN = 'demo.projectdivert.test'

DEMO_CUSTOMER_EMAIL = 'site.manager@{}'.format(DEMO_EMAIL_DOMAIN)
DEMO_DRIVER_EMAIL = 'driver@{}'.format(DEMO_EMAIL_DOMAIN)
DEMO_ADMIN_EMAIL = 'admin@{}'.format(DEMO_EMAIL_DOMAIN)

DEMO_ACCOUNTS = (
    (DEMO_CUSTOMER_EMAIL, 'customer', 'Sam Okonkwo (site manager)'),
    (DEMO_DRIVER_EMAIL, 'driver', 'Ali Rahman (driver)'),
    (DEMO_ADMIN_EMAIL, 'admin', 'Demo Administrator'),
)

DEMO_CARRIER_COMPANY = 'Demo Carriers Ltd'

#: Materials chosen because the LCA engine has factors for all of them, so the
#: completed collection reaches a real carbon figure rather than the
#: certificate's "not available" path.
DEMO_COLLECTIONS = (
    {
        'status': 'pending_match',
        'material_type': 'Timber',
        'waste_amount': 3.2,
        'pickup_address': 'Plot 4, Riverside Development',
        'pickup_city': 'Bristol',
        'pickup_postcode': 'BS1 4ST',
        'latitude': 51.4488, 'longitude': -2.5972,
        'days_ahead': 2,
        'notes': 'Offcuts from first fix. Awaiting a driver.',
        'with_open_offer': True,
    },
    {
        'status': 'matched',
        'material_type': 'Plasterboard',
        'waste_amount': 1.8,
        'pickup_address': 'Unit 7, Eastgate Industrial Estate',
        'pickup_city': 'Bristol',
        'pickup_postcode': 'BS5 6XX',
        'latitude': 51.4633, 'longitude': -2.5539,
        'days_ahead': 1,
        'notes': 'Driver assigned, not yet collected.',
        'with_match': True,
        'assign_driver': True,
    },
    {
        'status': 'en_route',
        'material_type': 'Glass',
        'waste_amount': 0.9,
        'pickup_address': '12 Harbour Way',
        'pickup_city': 'Bristol',
        'pickup_postcode': 'BS1 5TY',
        'latitude': 51.4495, 'longitude': -2.5966,
        'days_ahead': 0,
        'notes': 'Driver is on the way now.',
        'with_match': True,
        'assign_driver': True,
    },
    {
        'status': 'completed',
        'material_type': 'Aggregate',
        'waste_amount': 12.5,
        'pickup_address': 'Northfield Demolition Site',
        'pickup_city': 'Bristol',
        'pickup_postcode': 'BS7 9LL',
        'latitude': 51.4832, 'longitude': -2.5825,
        'days_ahead': -3,
        'notes': 'Collected and diverted. Carbon certificate available.',
        'with_match': True,
        'assign_driver': True,
        'with_completion_documents': True,
    },
)


def seeding_allowed():
    """Whether it is acceptable to create accounts with a known password here.

    Allowed while debugging or under test, and otherwise only when the
    environment says so explicitly. A demo account on a real deployment is a
    published username and password against live data.
    """
    if current_app.debug or current_app.config.get('TESTING'):
        return True
    return _is_truthy(current_app.config.get('ALLOW_DEMO_SEED'))


def _upsert_user(email, role, name, password):
    user = User.query.filter_by(email=email).first()
    created = user is None
    if created:
        user = User(email=email)
        db.session.add(user)
    user.name = name
    user.role = role
    user.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    user.is_active_user = True
    if hasattr(user, 'email_verified_at'):
        user.email_verified_at = utcnow()
    return user, created


def _verified_document(model, **fields):
    """A compliance document already signed off, so the demo starts usable."""
    now = utcnow()
    return model(
        status='verified',
        verified_at=now,
        issued_at=now - timedelta(days=90),
        expires_at=now + timedelta(days=275),
        metadata_json={'seeded': 'demo'},
        **fields
    )


def _seed_driver_compliance(driver, admin):
    """Make the demo driver dispatch-eligible: company, then both licences."""
    company = CarrierCompany.query.filter_by(name=DEMO_CARRIER_COMPANY).first()
    if company is None:
        company = CarrierCompany(
            name=DEMO_CARRIER_COMPANY,
            contact_email='ops@{}'.format(DEMO_EMAIL_DOMAIN),
            is_active=True,
        )
        db.session.add(company)
        db.session.flush()
    driver.carrier_company_id = company.id

    DriverComplianceDocument.query.filter_by(driver_user_id=driver.id).delete()
    CompanyComplianceDocument.query.filter_by(carrier_company_id=company.id).delete()

    for document_type, reference in (
        # A real-shaped Environment Agency number: carrier licences are
        # validated on the way in, and the demo should model valid data.
        ('carrier_license', 'CBDU483921'),
        ('insurance_certificate', 'INS-DEMO-84213'),
    ):
        db.session.add(_verified_document(
            DriverComplianceDocument,
            driver_user_id=driver.id,
            uploaded_by_user_id=driver.id,
            verified_by_user_id=admin.id,
            document_type=document_type,
            document_reference=reference,
            file_url='https://example.invalid/demo/{}.pdf'.format(document_type),
        ))

    for document_type, reference in (
        ('operator_license', 'EPR-DEMO-55120'),
        ('insurance_certificate', 'INS-DEMO-CO-99811'),
    ):
        db.session.add(_verified_document(
            CompanyComplianceDocument,
            carrier_company_id=company.id,
            uploaded_by_user_id=admin.id,
            verified_by_user_id=admin.id,
            document_type=document_type,
            document_reference=reference,
            file_url='https://example.invalid/demo/company-{}.pdf'.format(document_type),
        ))

    return company


def _seed_collection(spec, customer, driver, admin, company):
    now = utcnow()
    booking = WasteRemovalRequest(
        requester_name=customer.name,
        requester_email=customer.email,
        material_type=spec['material_type'],
        waste_amount=spec['waste_amount'],
        waste_unit='Tonnes',
        pickup_address=spec['pickup_address'],
        pickup_city=spec['pickup_city'],
        pickup_county='Bristol',
        pickup_postcode=spec['pickup_postcode'],
        pickup_latitude=spec['latitude'],
        pickup_longitude=spec['longitude'],
        scheduled_pickup_at=now + timedelta(days=spec['days_ahead']),
        notes=spec['notes'],
        status=spec['status'],
    )
    if spec.get('assign_driver'):
        booking.assigned_driver_user_id = driver.id
    db.session.add(booking)
    db.session.flush()

    provider = {
        'provider_name': DEMO_CARRIER_COMPANY,
        'provider_type': 'Waste Carrier',
        'provider_city': 'Bristol',
        'provider_postcode': 'BS2 8QN',
        'provider_latitude': 51.4584,
        'provider_longitude': -2.5836,
        'distance_miles': 4.2,
        'match_radius_miles': 25.0,
    }

    if spec.get('with_open_offer'):
        # An offer a driver can actually claim during the demo.
        db.session.add(WasteRemovalDispatchOffer(
            waste_removal_request_id=booking.id,
            offer_rank=1,
            offer_token='demo-offer-{}'.format(booking.id),
            status='offered',
            provider_email='ops@{}'.format(DEMO_EMAIL_DOMAIN),
            **provider
        ))

    if spec.get('with_match'):
        # distance_miles is what lets the certificate report a measured
        # collection distance rather than assuming the landfill haul.
        db.session.add(WasteRemovalMatch(
            waste_removal_request_id=booking.id, **provider
        ))

    if spec.get('with_completion_documents'):
        for document_type in ('waste_transfer_note', 'proof_of_collection_photo'):
            db.session.add(_verified_document(
                WasteComplianceDocument,
                waste_removal_request_id=booking.id,
                uploaded_by_user_id=driver.id,
                verified_by_user_id=admin.id,
                document_type=document_type,
                document_reference='WTN-DEMO-{}'.format(booking.id),
                file_url='https://example.invalid/demo/{}.pdf'.format(document_type),
            ))

    return booking


#: Everything that hangs off a waste request, as (model, foreign key column).
#: A row here belongs to the request, so clearing a demo request clears it too.
_REQUEST_CHILDREN = (
    (WasteComplianceDocument, 'waste_removal_request_id'),
    (WasteRequestCommunicationLog, 'waste_removal_request_id'),
    (WasteRemovalDispatchOffer, 'waste_removal_request_id'),
    (WasteRemovalMatch, 'waste_removal_request_id'),
    (WasteRemovalVehicleLocation, 'waste_removal_request_id'),
    (DispatchIncidentEvent, 'waste_removal_request_id'),
    (WastePaymentRefund, 'waste_removal_request_id'),
    (WastePaymentCharge, 'waste_removal_request_id'),
    (WasteDriverPayout, 'waste_removal_request_id'),
)

#: Rows that belong to a demo account rather than merely mentioning one: the
#: account's own sessions, devices and documents. These go with the account.
_USER_OWNED = (
    (AuthLifecycleToken, 'user_id'),
    (AuthAuditEvent, 'user_id'),
    (MobilePushSubscription, 'user_id'),
    (DriverComplianceDocument, 'driver_user_id'),
)

#: Columns that only record who did something. The row may belong to real data
#: -- a genuine collection the demo driver was assigned to, an audit entry
#: naming the demo admin -- so the reference is cleared and the row is kept.
#: Every one of these columns is nullable; that is what makes this safe.
_USER_REFERENCES = (
    (WasteRemovalRequest, 'assigned_driver_user_id'),
    (WasteRemovalRequest, 'incident_owner_admin_user_id'),
    (WasteRemovalRequest, 'billing_updated_by_user_id'),
    (WasteRemovalRequest, 'billing_followup_updated_by_user_id'),
    (WasteComplianceDocument, 'uploaded_by_user_id'),
    (WasteComplianceDocument, 'verified_by_user_id'),
    (CompanyComplianceDocument, 'uploaded_by_user_id'),
    (CompanyComplianceDocument, 'verified_by_user_id'),
    (DriverComplianceDocument, 'verified_by_user_id'),
    (DriverComplianceDocument, 'uploaded_by_user_id'),
    (WasteRequestCommunicationLog, 'created_by_user_id'),
    (DispatchIncidentEvent, 'actor_user_id'),
    (AuditEvent, 'actor_user_id'),
    (AuthSecurityBlocklist, 'created_by_user_id'),
    (WastePaymentCharge, 'customer_user_id'),
)


def _delete_where_in(model, column_name, ids):
    if not ids:
        return 0
    column = getattr(model, column_name)
    return (
        model.query.filter(column.in_(ids))
        .delete(synchronize_session=False)
    )


def clear_demo_data():
    """Remove everything a previous seed created. Touches nothing else.

    Demo rows are recognised by the reserved .test email domain, so this cannot
    reach a real customer's collections even if it is pointed at a database
    holding them.

    A demo leaves more behind than the seed created. Signing in writes session
    and audit rows, driving writes locations, and every one of those has a
    foreign key to the account. Deleting the accounts without clearing them
    first fails on the constraint -- which is exactly when reset is wanted, so
    this walks the references rather than only the rows the seed wrote.

    References are treated by what they mean. A row that belongs to a demo
    request or a demo account is deleted with it. A column that merely records
    who acted is set to NULL, because the row it sits on may be real data the
    demo driver happened to touch, and deleting that would be destroying
    something this promised not to reach.
    """
    removed = {'requests': 0, 'users': 0}

    request_ids = [
        row.id for row in WasteRemovalRequest.query
        .filter_by(requester_email=DEMO_CUSTOMER_EMAIL)
        .with_entities(WasteRemovalRequest.id)
        .all()
    ]
    user_ids = [
        row.id for row in User.query
        .filter(User.email.in_([email for email, _role, _name in DEMO_ACCOUNTS]))
        .with_entities(User.id)
        .all()
    ]

    for model, column_name in _REQUEST_CHILDREN:
        _delete_where_in(model, column_name, request_ids)

    removed['requests'] = _delete_where_in(
        WasteRemovalRequest, 'id', request_ids,
    )

    company = CarrierCompany.query.filter_by(name=DEMO_CARRIER_COMPANY).first()
    if company is not None:
        CompanyComplianceDocument.query.filter_by(
            carrier_company_id=company.id).delete(synchronize_session=False)

    for model, column_name in _USER_OWNED:
        _delete_where_in(model, column_name, user_ids)

    # Clear the pointers before the accounts go, so nothing is left referring
    # to a user id that no longer exists.
    for model, column_name in _USER_REFERENCES:
        if not user_ids:
            break
        column = getattr(model, column_name)
        (model.query.filter(column.in_(user_ids))
         .update({column_name: None}, synchronize_session=False))

    removed['users'] = _delete_where_in(User, 'id', user_ids)

    if company is not None:
        db.session.delete(company)

    db.session.commit()
    return removed


def seed_demo(password, reset=False):
    """Create the demo accounts and a scenario part-way through.

    Returns a summary for the caller to print. Raises PermissionError when the
    environment has not said that demo accounts are acceptable here.
    """
    if not seeding_allowed():
        raise PermissionError(
            'Refusing to create demo accounts with a known password. '
            'Set ALLOW_DEMO_SEED=1 if this is really what you want here.'
        )

    if reset:
        clear_demo_data()

    accounts = []
    for email, role, name in DEMO_ACCOUNTS:
        user, created = _upsert_user(email, role, name, password)
        accounts.append({'email': email, 'role': role, 'created': created})
    db.session.flush()

    customer = User.query.filter_by(email=DEMO_CUSTOMER_EMAIL).first()
    driver = User.query.filter_by(email=DEMO_DRIVER_EMAIL).first()
    admin = User.query.filter_by(email=DEMO_ADMIN_EMAIL).first()

    company = _seed_driver_compliance(driver, admin)

    existing = WasteRemovalRequest.query.filter_by(
        requester_email=DEMO_CUSTOMER_EMAIL,
    ).count()
    collections = []
    if existing:
        logger.info('Demo collections already present; leaving them alone.')
    else:
        for spec in DEMO_COLLECTIONS:
            booking = _seed_collection(spec, customer, driver, admin, company)
            collections.append({
                'id': booking.id,
                'status': booking.status,
                'material_type': booking.material_type,
            })

    db.session.commit()
    return {
        'accounts': accounts,
        'password': password,
        'collections': collections,
        'existing_collections': existing,
        'carrier_company': DEMO_CARRIER_COMPANY,
    }
