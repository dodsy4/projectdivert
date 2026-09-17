"""Compliance routes."""

from flask import Blueprint, current_app, jsonify, request
from projectdivert.extensions import db
from projectdivert.models.compliance import WasteComplianceDocument
from projectdivert.models.waste import WasteRemovalRequest
from projectdivert.services.audit import record_audit_event
from projectdivert.services.auth import _request_access_allowed, _request_driver_mutation_allowed, jwt_required
from projectdivert.services.compliance import COMPLIANCE_DOCUMENT_STATUSES, COMPLIANCE_DOCUMENT_TYPES, COMPLIANCE_DRIVER_UPLOAD_TYPES, _compliance_documents_for_request, _compliance_summary_for_documents, _normalize_compliance_document_type, _serialize_compliance_document
from projectdivert.services.dispatch import _serialize_waste_request_snapshot
from projectdivert.services.events import _publish_waste_request_event
from projectdivert.services.uploads import _build_compliance_signed_upload, _compliance_storage_backend, _save_compliance_upload
from projectdivert.services.utils import _current_jwt_role, _current_jwt_user_id, _parse_datetime_or_error, utcnow

bp = Blueprint('api_compliance', __name__)



@bp.route('/api/v1/waste-requests/<int:request_id>/compliance', methods=['GET'])
@jwt_required(roles={'customer', 'driver', 'admin'})
def api_get_waste_request_compliance(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_access_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403

    documents = _compliance_documents_for_request(booking.id)
    return jsonify(
        {
            'request_id': booking.id,
            'request_status': booking.status,
            'documents': [_serialize_compliance_document(row) for row in documents],
            'summary': _compliance_summary_for_documents(documents),
        }
    )



@bp.route('/api/v1/waste-requests/<int:request_id>/compliance/uploads', methods=['POST'])
@jwt_required(roles={'driver', 'admin'})
def api_upload_waste_request_compliance_file(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_driver_mutation_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403

    document_type = _normalize_compliance_document_type(
        request.form.get('document_type') or request.args.get('document_type')
    )
    if document_type not in COMPLIANCE_DOCUMENT_TYPES:
        return jsonify(
            {
                'error': 'Invalid document_type',
                'allowed_document_types': sorted(COMPLIANCE_DOCUMENT_TYPES),
            }
        ), 400

    role = _current_jwt_role()
    if role == 'driver' and document_type not in COMPLIANCE_DRIVER_UPLOAD_TYPES:
        return jsonify(
            {
                'error': 'Drivers can only upload collection evidence documents',
                'allowed_document_types': sorted(COMPLIANCE_DRIVER_UPLOAD_TYPES),
            }
        ), 403

    uploaded_file = request.files.get('file')
    if not uploaded_file or not uploaded_file.filename:
        return jsonify({'error': 'file is required'}), 400

    try:
        upload_info = _save_compliance_upload(uploaded_file, booking.id, document_type)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception:
        current_app.logger.exception('Failed saving compliance upload for request %s.', request_id)
        return jsonify({'error': 'Failed to save compliance upload'}), 500

    return (
        jsonify(
            {
                'request_id': booking.id,
                'document_type': document_type,
                'upload': upload_info,
            }
        ),
        201,
    )



@bp.route('/api/v1/waste-requests/<int:request_id>/compliance/uploads/sign', methods=['POST'])
@jwt_required(roles={'driver', 'admin'})
def api_sign_waste_request_compliance_upload(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_driver_mutation_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403
    if _compliance_storage_backend() != 's3':
        return jsonify({'error': 'Signed uploads require S3 storage backend'}), 409

    payload = request.get_json(silent=True) or {}
    document_type = _normalize_compliance_document_type(payload.get('document_type'))
    if document_type not in COMPLIANCE_DOCUMENT_TYPES:
        return jsonify(
            {
                'error': 'Invalid document_type',
                'allowed_document_types': sorted(COMPLIANCE_DOCUMENT_TYPES),
            }
        ), 400

    role = _current_jwt_role()
    if role == 'driver' and document_type not in COMPLIANCE_DRIVER_UPLOAD_TYPES:
        return jsonify(
            {
                'error': 'Drivers can only upload collection evidence documents',
                'allowed_document_types': sorted(COMPLIANCE_DRIVER_UPLOAD_TYPES),
            }
        ), 403

    file_name = str(payload.get('file_name') or '').strip()
    if not file_name:
        return jsonify({'error': 'file_name is required'}), 400

    mime_type = str(payload.get('mime_type') or '').strip()
    if not mime_type:
        return jsonify({'error': 'mime_type is required'}), 400

    try:
        signed_upload = _build_compliance_signed_upload(
            booking.id,
            document_type,
            file_name,
            mime_type,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception:
        current_app.logger.exception('Failed generating signed compliance upload for request %s.', request_id)
        return jsonify({'error': 'Failed to create signed upload'}), 500

    return jsonify(
        {
            'request_id': booking.id,
            'document_type': document_type,
            **signed_upload,
        }
    )



@bp.route('/api/v1/waste-requests/<int:request_id>/compliance/documents', methods=['POST'])
@jwt_required(roles={'driver', 'admin'})
def api_create_waste_request_compliance_document(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_driver_mutation_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403

    payload = request.get_json(silent=True) or {}
    document_type = _normalize_compliance_document_type(payload.get('document_type'))
    if document_type not in COMPLIANCE_DOCUMENT_TYPES:
        return jsonify(
            {
                'error': 'Invalid document_type',
                'allowed_document_types': sorted(COMPLIANCE_DOCUMENT_TYPES),
            }
        ), 400

    file_url = str(payload.get('file_url') or '').strip()
    if not file_url:
        return jsonify({'error': 'file_url is required'}), 400
    if len(file_url) > 500:
        return jsonify({'error': 'file_url is too long'}), 400

    status = str(payload.get('status') or 'submitted').strip().lower().replace('-', '_').replace(' ', '_')
    if status not in COMPLIANCE_DOCUMENT_STATUSES:
        return jsonify(
            {
                'error': 'Invalid status',
                'allowed_statuses': sorted(COMPLIANCE_DOCUMENT_STATUSES),
            }
        ), 400

    role = _current_jwt_role()
    if role != 'admin' and status != 'submitted':
        return jsonify({'error': 'Only admins can set non-submitted status'}), 403
    if role == 'driver' and document_type not in COMPLIANCE_DRIVER_UPLOAD_TYPES:
        return jsonify(
            {
                'error': 'Drivers can only upload collection evidence documents',
                'allowed_document_types': sorted(COMPLIANCE_DRIVER_UPLOAD_TYPES),
            }
        ), 403

    metadata = payload.get('metadata') if 'metadata' in payload else {}
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        return jsonify({'error': 'metadata must be an object'}), 400

    notes = str(payload.get('notes') or '').strip()
    notes = notes[:2000] if notes else None
    document_reference = str(payload.get('document_reference') or '').strip()
    document_reference = document_reference[:120] if document_reference else None

    issued_at = None
    expires_at = None
    if payload.get('issued_at') not in (None, ''):
        try:
            issued_at = _parse_datetime_or_error(payload.get('issued_at'), 'issued_at')
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
    if payload.get('expires_at') not in (None, ''):
        try:
            expires_at = _parse_datetime_or_error(payload.get('expires_at'), 'expires_at')
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
    if issued_at and expires_at and expires_at <= issued_at:
        return jsonify({'error': 'expires_at must be later than issued_at'}), 400

    now = utcnow()
    current_user_id = _current_jwt_user_id()
    document = WasteComplianceDocument(
        waste_removal_request_id=booking.id,
        uploaded_by_user_id=current_user_id,
        document_type=document_type,
        status=status,
        file_url=file_url,
        document_reference=document_reference,
        issued_at=issued_at,
        expires_at=expires_at,
        notes=notes,
        metadata_json=metadata,
    )
    if role == 'admin' and status in {'verified', 'rejected', 'expired'}:
        document.verified_by_user_id = current_user_id
        document.verified_at = now

    db.session.add(document)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to create compliance document for request %s.', request_id)
        return jsonify({'error': 'Failed to create compliance document'}), 500

    _publish_waste_request_event(
        booking.id,
        'compliance_document_created',
        payload=_serialize_waste_request_snapshot(booking),
        metadata={
            'compliance_document_id': document.id,
            'document_type': document.document_type,
            'status': document.status,
        },
    )
    documents = _compliance_documents_for_request(booking.id)
    return (
        jsonify(
            {
                'request_id': booking.id,
                'document': _serialize_compliance_document(document),
                'summary': _compliance_summary_for_documents(documents),
            }
        ),
        201,
    )



@bp.route('/api/v1/admin/waste-requests/<int:request_id>/compliance/documents/<int:document_id>/verify', methods=['POST'])
@jwt_required(roles={'admin'})
def api_admin_verify_waste_request_compliance_document(request_id, document_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404

    document = WasteComplianceDocument.query.filter_by(
        id=document_id,
        waste_removal_request_id=booking.id,
    ).first()
    if not document:
        return jsonify({'error': 'Compliance document not found'}), 404

    payload = request.get_json(silent=True) or {}
    status = str(payload.get('status') or 'verified').strip().lower().replace('-', '_').replace(' ', '_')
    allowed_review_statuses = {'verified', 'rejected', 'expired'}
    if status not in allowed_review_statuses:
        return jsonify({'error': 'status must be verified, rejected, or expired'}), 400

    metadata = payload.get('metadata') if 'metadata' in payload else None
    if metadata is not None and not isinstance(metadata, dict):
        return jsonify({'error': 'metadata must be an object'}), 400

    notes = None
    if 'notes' in payload:
        notes = str(payload.get('notes') or '').strip()
        notes = notes[:2000] if notes else None

    expires_at = document.expires_at
    if 'expires_at' in payload:
        if payload.get('expires_at') in (None, ''):
            expires_at = None
        else:
            try:
                expires_at = _parse_datetime_or_error(payload.get('expires_at'), 'expires_at')
            except ValueError as exc:
                return jsonify({'error': str(exc)}), 400
    if document.issued_at and expires_at and expires_at <= document.issued_at:
        return jsonify({'error': 'expires_at must be later than issued_at'}), 400

    previous_status = document.status
    document.status = status
    document.verified_by_user_id = _current_jwt_user_id()
    document.verified_at = utcnow()
    document.expires_at = expires_at
    if notes is not None:
        document.notes = notes
    if metadata is not None:
        merged = dict(document.metadata_json or {})
        merged.update(metadata)
        document.metadata_json = merged

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            'Failed to review compliance document %s for request %s.',
            document_id,
            request_id,
        )
        return jsonify({'error': 'Failed to update compliance document'}), 500

    record_audit_event(
        action='compliance.waste_document_review',
        entity_type='waste_compliance_document',
        entity_id=document.id,
        summary='Request #{} document {} -> {}'.format(booking.id, document.document_type, document.status),
        changes={'status': [previous_status, document.status]},
        status_code=200,
    )
    _publish_waste_request_event(
        booking.id,
        'compliance_document_reviewed',
        payload=_serialize_waste_request_snapshot(booking),
        metadata={
            'compliance_document_id': document.id,
            'previous_status': previous_status,
            'status': document.status,
        },
    )
    documents = _compliance_documents_for_request(booking.id)
    return jsonify(
        {
            'updated': True,
            'request_id': booking.id,
            'document': _serialize_compliance_document(document),
            'previous_status': previous_status,
            'summary': _compliance_summary_for_documents(documents),
        }
    )
