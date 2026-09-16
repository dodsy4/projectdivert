"""Drivers routes."""

from flask import Blueprint, current_app, jsonify, request
from projectdivert.extensions import db
from projectdivert.models.compliance import CarrierCompany
from projectdivert.models.user import User
from projectdivert.services.auth import jwt_required
from projectdivert.services.compliance import COMPLIANCE_DOCUMENT_STATUSES, DRIVER_COMPLIANCE_DOCUMENT_TYPES, _build_driver_compliance_document, _company_compliance_documents_for_company, _company_compliance_summary_for_documents, _driver_compliance_documents_for_driver, _driver_compliance_summary_for_documents, _serialize_carrier_company, _serialize_company_compliance_document, _serialize_driver_compliance_document
from projectdivert.services.dispatch import _serialize_dispatch_driver
from projectdivert.services.utils import _current_jwt_user_id

bp = Blueprint('api_drivers', __name__)



@bp.route('/api/v1/drivers/me/compliance', methods=['GET'])
@jwt_required(roles={'driver'})
def api_driver_get_own_compliance():
    driver_user_id = _current_jwt_user_id()
    driver = db.session.get(User, driver_user_id)
    if not driver or (driver.role or '').strip().lower() != 'driver':
        return jsonify({'error': 'Driver not found'}), 404

    documents = _driver_compliance_documents_for_driver(driver.id)
    summary = _driver_compliance_summary_for_documents(documents)
    return jsonify(
        {
            'driver': _serialize_dispatch_driver(driver),
            'documents': [_serialize_driver_compliance_document(row) for row in documents],
            'summary': summary,
        }
    )



@bp.route('/api/v1/drivers/me/compliance/documents', methods=['POST'])
@jwt_required(roles={'driver'})
def api_driver_create_own_compliance_document():
    driver_user_id = _current_jwt_user_id()
    driver = db.session.get(User, driver_user_id)
    if not driver or (driver.role or '').strip().lower() != 'driver':
        return jsonify({'error': 'Driver not found'}), 404

    payload = request.get_json(silent=True) or {}
    try:
        document = _build_driver_compliance_document(
            driver.id,
            payload,
            actor_user_id=driver.id,
            actor_role='driver',
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
        current_app.logger.exception('Failed creating driver compliance document for user %s.', driver.id)
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



@bp.route('/api/v1/drivers/me/carrier-company', methods=['GET'])
@jwt_required(roles={'driver'})
def api_driver_get_own_carrier_company():
    driver_user_id = _current_jwt_user_id()
    driver = db.session.get(User, driver_user_id)
    if not driver or (driver.role or '').strip().lower() != 'driver':
        return jsonify({'error': 'Driver not found'}), 404

    company = db.session.get(CarrierCompany, driver.carrier_company_id) if driver.carrier_company_id else None
    documents = _company_compliance_documents_for_company(company.id) if company else []
    summary = _company_compliance_summary_for_documents(documents) if company else None
    return jsonify(
        {
            'driver': _serialize_dispatch_driver(driver),
            'carrier_company': _serialize_carrier_company(company, include_compliance=False),
            'documents': [_serialize_company_compliance_document(row) for row in documents],
            'summary': summary,
        }
    )
