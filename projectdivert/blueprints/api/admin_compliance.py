"""Admin compliance routes."""

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from projectdivert.extensions import db
from projectdivert.models.compliance import CarrierCompany, CompanyComplianceDocument, DriverComplianceDocument, WasteComplianceDocument
from projectdivert.models.user import User
from projectdivert.models.waste import WasteRemovalRequest
from projectdivert.services.audit import record_audit_event
from projectdivert.services.auth import jwt_required
from projectdivert.services.compliance import COMPANY_COMPLIANCE_DOCUMENT_TYPES, COMPLIANCE_DOCUMENT_STATUSES, COMPLIANCE_DOCUMENT_TYPES, DRIVER_COMPLIANCE_DOCUMENT_TYPES, _build_company_compliance_document, _build_driver_compliance_document, _company_compliance_documents_for_company, _company_compliance_summary_for_documents, _compliance_documents_for_request, _compliance_summary_for_documents, _driver_compliance_documents_for_driver, _driver_compliance_summary_for_documents, _normalize_compliance_document_type, _serialize_carrier_company, _serialize_company_compliance_document, _serialize_compliance_document, _serialize_driver_compliance_document
from projectdivert.services.dispatch import _serialize_dispatch_driver, _serialize_waste_request
from projectdivert.services.utils import _current_jwt_user_id, _parse_datetime_or_error, _parse_optional_bool_query, _parse_optional_int_query, _to_int_or_none, utcnow

bp = Blueprint('api_admin_compliance', __name__)



@bp.route('/api/v1/admin/drivers', methods=['GET'])
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
        current_app.logger.exception('Failed to query driver list for admin.')
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



@bp.route('/api/v1/admin/carrier-companies', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_list_carrier_companies():
    active = request.args.get('active')
    search = str(request.args.get('search') or '').strip().lower()
    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=200)
        offset = _parse_optional_int_query(request.args.get('offset'), 'offset', min_value=0, max_value=100000)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    limit = limit or 50
    offset = offset or 0

    query = CarrierCompany.query
    if active is not None and active != '':
        parsed_active = _parse_optional_bool_query(active, 'active')
        query = query.filter(CarrierCompany.is_active.is_(bool(parsed_active)))
    if search:
        pattern = '%{}%'.format(search.lower())
        query = query.filter(
            or_(
                func.lower(CarrierCompany.name).like(pattern),
                func.lower(func.coalesce(CarrierCompany.contact_email, '')).like(pattern),
            )
        )

    total = query.count()
    rows = (
        query.order_by(func.lower(CarrierCompany.name).asc(), CarrierCompany.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return jsonify(
        {
            'items': [_serialize_carrier_company(row, include_compliance=True) for row in rows],
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



@bp.route('/api/v1/admin/carrier-companies', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_create_carrier_company():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400
    if len(name) > 255:
        return jsonify({'error': 'name is too long'}), 400

    existing = CarrierCompany.query.filter(func.lower(CarrierCompany.name) == name.lower()).first()
    if existing:
        return jsonify({'error': 'Carrier company already exists', 'company': _serialize_carrier_company(existing, include_compliance=True)}), 409

    company = CarrierCompany(
        name=name,
        contact_email=(str(payload.get('contact_email') or '').strip()[:255] or None),
        contact_phone=(str(payload.get('contact_phone') or '').strip()[:120] or None),
        is_active=bool(payload.get('is_active', True)),
    )
    try:
        db.session.add(company)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to create carrier company %s.', name)
        return jsonify({'error': 'Failed to create carrier company'}), 500

    return jsonify({'company': _serialize_carrier_company(company, include_compliance=True)}), 201



@bp.route('/api/v1/admin/drivers/<int:driver_user_id>/carrier-company', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_assign_driver_carrier_company(driver_user_id):
    driver = db.session.get(User, driver_user_id)
    if not driver or (driver.role or '').strip().lower() != 'driver':
        return jsonify({'error': 'Driver not found'}), 404

    payload = request.get_json(silent=True) or {}
    raw_company_id = payload.get('carrier_company_id')
    if raw_company_id in (None, ''):
        company = None
        next_company_id = None
    else:
        next_company_id = _to_int_or_none(raw_company_id)
        if next_company_id is None:
            return jsonify({'error': 'carrier_company_id must be an integer or null'}), 400
        company = db.session.get(CarrierCompany, next_company_id)
        if not company:
            return jsonify({'error': 'Carrier company not found'}), 404

    previous_company_id = driver.carrier_company_id
    driver.carrier_company_id = next_company_id
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed assigning carrier company %s to driver %s.', next_company_id, driver_user_id)
        return jsonify({'error': 'Failed to assign carrier company'}), 500

    return jsonify(
        {
            'updated': previous_company_id != next_company_id,
            'previous_carrier_company_id': previous_company_id,
            'carrier_company_id': driver.carrier_company_id,
            'driver': _serialize_dispatch_driver(driver),
            'carrier_company': _serialize_carrier_company(company, include_compliance=True),
        }
    )



@bp.route('/api/v1/admin/drivers/<int:driver_user_id>/compliance', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_get_driver_compliance(driver_user_id):
    driver = db.session.get(User, driver_user_id)
    if not driver or (driver.role or '').strip().lower() != 'driver':
        return jsonify({'error': 'Driver not found'}), 404

    documents = _driver_compliance_documents_for_driver(driver.id)
    return jsonify(
        {
            'driver': _serialize_dispatch_driver(driver),
            'documents': [_serialize_driver_compliance_document(row) for row in documents],
            'summary': _driver_compliance_summary_for_documents(documents),
        }
    )



@bp.route('/api/v1/admin/drivers/<int:driver_user_id>/compliance/documents', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_create_driver_compliance_document(driver_user_id):
    driver = db.session.get(User, driver_user_id)
    if not driver or (driver.role or '').strip().lower() != 'driver':
        return jsonify({'error': 'Driver not found'}), 404

    payload = request.get_json(silent=True) or {}
    try:
        document = _build_driver_compliance_document(
            driver.id,
            payload,
            actor_user_id=_current_jwt_user_id(),
            actor_role='admin',
        )
    except PermissionError as exc:
        return jsonify({'error': str(exc)}), 403
    except ValueError as exc:
        message = str(exc)
        if message == 'Invalid document_type':
            return jsonify(
                {
                    'error': message,
                    'allowed_document_types': sorted(DRIVER_COMPLIANCE_DOCUMENT_TYPES),
                }
            ), 400
        if message == 'Invalid status':
            return jsonify(
                {
                    'error': message,
                    'allowed_statuses': sorted(COMPLIANCE_DOCUMENT_STATUSES),
                }
            ), 400
        return jsonify({'error': message}), 400

    try:
        db.session.add(document)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed admin driver compliance create for user %s.', driver.id)
        return jsonify({'error': 'Failed to create driver compliance document'}), 500

    documents = _driver_compliance_documents_for_driver(driver.id)
    return (
        jsonify(
            {
                'driver': _serialize_dispatch_driver(driver),
                'document': _serialize_driver_compliance_document(document),
                'summary': _driver_compliance_summary_for_documents(documents),
            }
        ),
        201,
    )



@bp.route('/api/v1/admin/carrier-companies/<int:carrier_company_id>/compliance', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_get_carrier_company_compliance(carrier_company_id):
    company = db.session.get(CarrierCompany, carrier_company_id)
    if not company:
        return jsonify({'error': 'Carrier company not found'}), 404

    documents = _company_compliance_documents_for_company(company.id)
    summary = _company_compliance_summary_for_documents(documents)
    return jsonify(
        {
            'carrier_company': _serialize_carrier_company(company, include_compliance=False),
            'documents': [_serialize_company_compliance_document(row) for row in documents],
            'summary': summary,
        }
    )



@bp.route('/api/v1/admin/carrier-companies/<int:carrier_company_id>/compliance/documents', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_create_carrier_company_compliance_document(carrier_company_id):
    company = db.session.get(CarrierCompany, carrier_company_id)
    if not company:
        return jsonify({'error': 'Carrier company not found'}), 404

    payload = request.get_json(silent=True) or {}
    try:
        document = _build_company_compliance_document(
            company.id,
            payload,
            actor_user_id=_current_jwt_user_id(),
        )
    except ValueError as exc:
        message = str(exc)
        if message == 'Invalid document_type':
            return jsonify(
                {
                    'error': message,
                    'allowed_document_types': sorted(COMPANY_COMPLIANCE_DOCUMENT_TYPES),
                }
            ), 400
        if message == 'Invalid status':
            return jsonify(
                {
                    'error': message,
                    'allowed_statuses': sorted(COMPLIANCE_DOCUMENT_STATUSES),
                }
            ), 400
        return jsonify({'error': message}), 400

    try:
        db.session.add(document)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed creating company compliance document for company %s.', company.id)
        return jsonify({'error': 'Failed to create company compliance document'}), 500

    documents = _company_compliance_documents_for_company(company.id)
    return (
        jsonify(
            {
                'carrier_company': _serialize_carrier_company(company, include_compliance=False),
                'document': _serialize_company_compliance_document(document),
                'summary': _company_compliance_summary_for_documents(documents),
            }
        ),
        201,
    )



@bp.route('/api/v1/admin/carrier-companies/<int:carrier_company_id>/compliance/documents/<int:document_id>/verify', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_verify_carrier_company_compliance_document(carrier_company_id, document_id):
    company = db.session.get(CarrierCompany, carrier_company_id)
    if not company:
        return jsonify({'error': 'Carrier company not found'}), 404

    document = db.session.get(CompanyComplianceDocument, document_id)
    if not document or document.carrier_company_id != company.id:
        return jsonify({'error': 'Company compliance document not found'}), 404

    payload = request.get_json(silent=True) or {}
    status = str(payload.get('status') or '').strip().lower().replace('-', '_').replace(' ', '_')
    if status not in COMPLIANCE_DOCUMENT_STATUSES:
        return jsonify(
            {
                'error': 'Invalid status',
                'allowed_statuses': sorted(COMPLIANCE_DOCUMENT_STATUSES),
            }
        ), 400

    previous_status = document.status
    updated = False
    if document.status != status:
        document.status = status
        updated = True

    notes = str(payload.get('notes') or '').strip()
    next_notes = notes[:2000] if notes else None
    if document.notes != next_notes:
        document.notes = next_notes
        updated = True

    expires_at = document.expires_at
    if payload.get('expires_at') not in (None, ''):
        try:
            expires_at = _parse_datetime_or_error(payload.get('expires_at'), 'expires_at')
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
    if document.expires_at != expires_at:
        document.expires_at = expires_at
        updated = True

    metadata = payload.get('metadata') if 'metadata' in payload else document.metadata_json
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        return jsonify({'error': 'metadata must be an object'}), 400
    if document.metadata_json != metadata:
        document.metadata_json = metadata
        updated = True

    if status in {'verified', 'rejected', 'expired'}:
        document.verified_by_user_id = _current_jwt_user_id()
        document.verified_at = utcnow()
        updated = True

    if not updated:
        documents = _company_compliance_documents_for_company(company.id)
        return jsonify(
            {
                'updated': False,
                'previous_status': previous_status,
                'carrier_company': _serialize_carrier_company(company, include_compliance=False),
                'document': _serialize_company_compliance_document(document),
                'summary': _company_compliance_summary_for_documents(documents),
            }
        )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed admin company compliance verify for company %s doc %s.', company.id, document.id)
        return jsonify({'error': 'Failed to update company compliance document'}), 500

    record_audit_event(
        action='compliance.company_document_review',
        entity_type='company_compliance_document',
        entity_id=document.id,
        summary='Carrier company #{} document {} -> {}'.format(company.id, document.document_type, document.status),
        changes={'status': [previous_status, document.status]},
        status_code=200,
    )
    documents = _company_compliance_documents_for_company(company.id)
    return jsonify(
        {
            'updated': True,
            'previous_status': previous_status,
            'carrier_company': _serialize_carrier_company(company, include_compliance=False),
            'document': _serialize_company_compliance_document(document),
            'summary': _company_compliance_summary_for_documents(documents),
        }
    )



@bp.route('/api/v1/admin/drivers/<int:driver_user_id>/compliance/documents/<int:document_id>/verify', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_verify_driver_compliance_document(driver_user_id, document_id):
    driver = db.session.get(User, driver_user_id)
    if not driver or (driver.role or '').strip().lower() != 'driver':
        return jsonify({'error': 'Driver not found'}), 404

    document = db.session.get(DriverComplianceDocument, document_id)
    if not document or document.driver_user_id != driver.id:
        return jsonify({'error': 'Driver compliance document not found'}), 404

    payload = request.get_json(silent=True) or {}
    status = str(payload.get('status') or '').strip().lower().replace('-', '_').replace(' ', '_')
    if status not in COMPLIANCE_DOCUMENT_STATUSES:
        return jsonify(
            {
                'error': 'Invalid status',
                'allowed_statuses': sorted(COMPLIANCE_DOCUMENT_STATUSES),
            }
        ), 400

    previous_status = document.status
    updated = False
    if document.status != status:
        document.status = status
        updated = True

    notes = str(payload.get('notes') or '').strip()
    next_notes = notes[:2000] if notes else None
    if document.notes != next_notes:
        document.notes = next_notes
        updated = True

    expires_at = document.expires_at
    if payload.get('expires_at') not in (None, ''):
        try:
            expires_at = _parse_datetime_or_error(payload.get('expires_at'), 'expires_at')
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
    if document.expires_at != expires_at:
        document.expires_at = expires_at
        updated = True

    metadata = payload.get('metadata') if 'metadata' in payload else document.metadata_json
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        return jsonify({'error': 'metadata must be an object'}), 400
    if document.metadata_json != metadata:
        document.metadata_json = metadata
        updated = True

    if status in {'verified', 'rejected', 'expired'}:
        document.verified_by_user_id = _current_jwt_user_id()
        document.verified_at = utcnow()
        updated = True

    if not updated:
        documents = _driver_compliance_documents_for_driver(driver.id)
        return jsonify(
            {
                'updated': False,
                'previous_status': previous_status,
                'driver': _serialize_dispatch_driver(driver),
                'document': _serialize_driver_compliance_document(document),
                'summary': _driver_compliance_summary_for_documents(documents),
            }
        )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed admin driver compliance verify for user %s doc %s.', driver.id, document.id)
        return jsonify({'error': 'Failed to update driver compliance document'}), 500

    record_audit_event(
        action='compliance.driver_document_review',
        entity_type='driver_compliance_document',
        entity_id=document.id,
        summary='Driver #{} document {} -> {}'.format(driver.id, document.document_type, document.status),
        changes={'status': [previous_status, document.status]},
        status_code=200,
    )
    documents = _driver_compliance_documents_for_driver(driver.id)
    return jsonify(
        {
            'updated': True,
            'previous_status': previous_status,
            'driver': _serialize_dispatch_driver(driver),
            'document': _serialize_driver_compliance_document(document),
            'summary': _driver_compliance_summary_for_documents(documents),
        }
    )



@bp.route('/api/v1/admin/compliance/review-queue', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_compliance_review_queue():
    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=500)
        offset = _parse_optional_int_query(request.args.get('offset'), 'offset', min_value=0)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    limit = limit or 50
    offset = offset or 0

    status = (str(request.args.get('status') or '').strip().lower().replace('-', '_').replace(' ', '_') or 'submitted')
    if status != 'all' and status not in COMPLIANCE_DOCUMENT_STATUSES:
        return jsonify(
            {
                'error': 'Invalid status filter',
                'allowed_statuses': ['all'] + sorted(COMPLIANCE_DOCUMENT_STATUSES),
            }
        ), 400

    document_type = _normalize_compliance_document_type(request.args.get('document_type'))
    if document_type and document_type not in COMPLIANCE_DOCUMENT_TYPES:
        return jsonify(
            {
                'error': 'Invalid document_type filter',
                'allowed_document_types': sorted(COMPLIANCE_DOCUMENT_TYPES),
            }
        ), 400

    try:
        query = WasteComplianceDocument.query
        if status != 'all':
            query = query.filter(WasteComplianceDocument.status == status)
        if document_type:
            query = query.filter(WasteComplianceDocument.document_type == document_type)

        total = query.count()
        rows = (
            query.order_by(
                WasteComplianceDocument.created_at.asc(),
                WasteComplianceDocument.id.asc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
    except SQLAlchemyError:
        current_app.logger.exception('Failed to query compliance review queue.')
        return jsonify({'error': 'Failed to query compliance review queue'}), 500

    items = []
    status_counts = {}
    type_counts = {}
    for row in rows:
        status_key = (row.status or '').strip().lower() or 'unknown'
        type_key = _normalize_compliance_document_type(row.document_type) or 'unknown'
        status_counts[status_key] = status_counts.get(status_key, 0) + 1
        type_counts[type_key] = type_counts.get(type_key, 0) + 1

        booking = db.session.get(WasteRemovalRequest, row.waste_removal_request_id)
        items.append(
            {
                'document': _serialize_compliance_document(row),
                'request': _serialize_waste_request(booking) if booking else None,
                'summary': _compliance_summary_for_documents(
                    _compliance_documents_for_request(row.waste_removal_request_id)
                ) if booking else None,
            }
        )

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
                'status': status,
                'document_type': document_type or '',
            },
            'summary': {
                'status_counts': status_counts,
                'document_type_counts': type_counts,
            },
        }
    )
