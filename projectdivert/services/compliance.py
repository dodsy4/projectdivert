"""Waste, driver and carrier-company compliance documents."""

import re

from projectdivert.extensions import db
from projectdivert.models.compliance import CarrierCompany, CompanyComplianceDocument, DriverComplianceDocument, WasteComplianceDocument
from projectdivert.models.user import User
from projectdivert.services.utils import _is_truthy, _parse_datetime_or_error, _to_int_or_none, utcnow


def _driver_dispatch_eligibility_error(driver_user_id):
    normalized_driver_user_id = _to_int_or_none(driver_user_id)
    if normalized_driver_user_id is None:
        return 'driver_user_id is required', []

    status = _driver_dispatch_compliance_status(normalized_driver_user_id)
    if status['eligible']:
        return '', []

    return 'Driver compliance review incomplete for dispatch', status['missing_document_types']


#: Environment Agency waste carrier registration numbers. Upper and lower tier
#: registrations carry a letter suffix (CBDU / CBDL); the older ABW and ABT
#: series appear on registrations predating the current scheme.
#:
#: The agency has changed this format before and may again, which is why an
#: unrecognised number can still be recorded deliberately rather than refused --
#: a real licence the pattern has not caught up with must not block a driver
#: from being onboarded.
WASTE_CARRIER_REFERENCE_PATTERN = re.compile(r'^(CBD|CBT|ABW|ABT)[UL]?\d{4,10}$')

WASTE_CARRIER_REFERENCE_HINT = (
    'Environment Agency waste carrier numbers look like CBDU123456. '
    'Send allow_unrecognised_reference to record it anyway.'
)


def normalize_waste_carrier_reference(value):
    """Upper-case, and strip the spaces and dashes people type into the field."""
    return re.sub(r'[\s-]+', '', str(value or '')).upper()


def waste_carrier_reference_looks_valid(value):
    """Whether a reference matches the Environment Agency registration format."""
    return bool(WASTE_CARRIER_REFERENCE_PATTERN.match(
        normalize_waste_carrier_reference(value),
    ))


def _checked_carrier_reference(document_type, document_reference, payload):
    """Validate and tidy a waste carrier number, for the document type that is one.

    A carrier licence whose number is a typo is worse than one with no number at
    all: it looks verifiable, so the admin reviewing it has no reason to doubt
    it. Other document types keep whatever reference they were given.
    """
    if document_type != 'carrier_license' or not document_reference:
        return document_reference

    if waste_carrier_reference_looks_valid(document_reference):
        return normalize_waste_carrier_reference(document_reference)[:120]

    if _is_truthy(payload.get('allow_unrecognised_reference')):
        return document_reference

    raise ValueError(
        'document_reference does not look like a waste carrier registration. '
        + WASTE_CARRIER_REFERENCE_HINT
    )


COMPLIANCE_DOCUMENT_TYPES = {
    'carrier_license',
    'insurance_certificate',
    'waste_transfer_note',
    'proof_of_collection_photo',
}


COMPLIANCE_DRIVER_UPLOAD_TYPES = {
    'waste_transfer_note',
    'proof_of_collection_photo',
}


DRIVER_COMPLIANCE_DOCUMENT_TYPES = {
    'carrier_license',
    'insurance_certificate',
}


DRIVER_DISPATCH_REQUIRED_TYPES = {
    'carrier_license',
    'insurance_certificate',
}


COMPANY_COMPLIANCE_DOCUMENT_TYPES = {
    'operator_license',
    'insurance_certificate',
}


COMPANY_DISPATCH_REQUIRED_TYPES = {
    'operator_license',
    'insurance_certificate',
}


COMPLIANCE_COMPLETION_REQUIRED_TYPES = {
    'waste_transfer_note',
    'proof_of_collection_photo',
}


COMPLIANCE_DOCUMENT_STATUSES = {
    'submitted',
    'verified',
    'rejected',
    'expired',
}


def _normalize_compliance_document_type(value):
    normalized = str(value or '').strip().lower().replace('-', '_').replace(' ', '_')
    aliases = {
        'carrier_licence': 'carrier_license',
        'carrier_license': 'carrier_license',
        'operator_licence': 'operator_license',
        'operator_license': 'operator_license',
        'insurance': 'insurance_certificate',
        'insurance_certificate': 'insurance_certificate',
        'wtn': 'waste_transfer_note',
        'waste_transfer_note': 'waste_transfer_note',
        'proof_photo': 'proof_of_collection_photo',
        'proof_of_collection_photo': 'proof_of_collection_photo',
    }
    return aliases.get(normalized, normalized)


def _serialize_compliance_document(document):
    if not document:
        return None
    return {
        'id': document.id,
        'waste_removal_request_id': document.waste_removal_request_id,
        'uploaded_by_user_id': document.uploaded_by_user_id,
        'verified_by_user_id': document.verified_by_user_id,
        'document_type': document.document_type,
        'status': document.status,
        'file_url': document.file_url,
        'document_reference': document.document_reference,
        'issued_at': document.issued_at.isoformat() if document.issued_at else None,
        'expires_at': document.expires_at.isoformat() if document.expires_at else None,
        'verified_at': document.verified_at.isoformat() if document.verified_at else None,
        'notes': document.notes,
        'metadata': document.metadata_json or {},
        'created_at': document.created_at.isoformat() if document.created_at else None,
        'updated_at': document.updated_at.isoformat() if document.updated_at else None,
    }


def _serialize_driver_compliance_document(document):
    if not document:
        return None
    return {
        'id': document.id,
        'driver_user_id': document.driver_user_id,
        'uploaded_by_user_id': document.uploaded_by_user_id,
        'verified_by_user_id': document.verified_by_user_id,
        'document_type': document.document_type,
        'status': document.status,
        'file_url': document.file_url,
        'document_reference': document.document_reference,
        'issued_at': document.issued_at.isoformat() if document.issued_at else None,
        'expires_at': document.expires_at.isoformat() if document.expires_at else None,
        'verified_at': document.verified_at.isoformat() if document.verified_at else None,
        'notes': document.notes,
        'metadata': document.metadata_json or {},
        'created_at': document.created_at.isoformat() if document.created_at else None,
        'updated_at': document.updated_at.isoformat() if document.updated_at else None,
    }


def _serialize_company_compliance_document(document):
    if not document:
        return None
    return {
        'id': document.id,
        'carrier_company_id': document.carrier_company_id,
        'uploaded_by_user_id': document.uploaded_by_user_id,
        'verified_by_user_id': document.verified_by_user_id,
        'document_type': document.document_type,
        'status': document.status,
        'file_url': document.file_url,
        'document_reference': document.document_reference,
        'issued_at': document.issued_at.isoformat() if document.issued_at else None,
        'expires_at': document.expires_at.isoformat() if document.expires_at else None,
        'verified_at': document.verified_at.isoformat() if document.verified_at else None,
        'notes': document.notes,
        'metadata': document.metadata_json or {},
        'created_at': document.created_at.isoformat() if document.created_at else None,
        'updated_at': document.updated_at.isoformat() if document.updated_at else None,
    }


def _compliance_document_is_effectively_verified(document, now=None):
    if not document:
        return False
    now = now or utcnow()
    status = str(document.status or '').strip().lower()
    if status != 'verified':
        return False
    if document.expires_at and document.expires_at <= now:
        return False
    return True


def _driver_compliance_documents_for_driver(driver_user_id):
    if not driver_user_id:
        return []
    return (
        DriverComplianceDocument.query.filter_by(driver_user_id=driver_user_id)
        .order_by(
            DriverComplianceDocument.created_at.desc(),
            DriverComplianceDocument.id.desc(),
        )
        .all()
    )


def _company_compliance_documents_for_company(carrier_company_id):
    if not carrier_company_id:
        return []
    return (
        CompanyComplianceDocument.query.filter_by(carrier_company_id=carrier_company_id)
        .order_by(
            CompanyComplianceDocument.created_at.desc(),
            CompanyComplianceDocument.id.desc(),
        )
        .all()
    )


def _driver_compliance_summary_for_documents(documents):
    now = utcnow()
    by_type = {}
    for doc_type in sorted(DRIVER_COMPLIANCE_DOCUMENT_TYPES):
        typed_docs = [row for row in documents if row.document_type == doc_type]
        latest = typed_docs[0] if typed_docs else None
        by_type[doc_type] = {
            'present': bool(typed_docs),
            'count': len(typed_docs),
            'latest_status': latest.status if latest else None,
            'latest_document_id': latest.id if latest else None,
            'latest_expires_at': latest.expires_at.isoformat() if latest and latest.expires_at else None,
            'verified': any(_compliance_document_is_effectively_verified(row, now=now) for row in typed_docs),
            'expired': bool(
                latest and latest.expires_at and latest.expires_at <= now and str(latest.status or '').lower() == 'verified'
            ),
        }

    dispatch_missing_types = []
    for doc_type in sorted(DRIVER_DISPATCH_REQUIRED_TYPES):
        if not by_type.get(doc_type, {}).get('verified'):
            dispatch_missing_types.append(doc_type)

    return {
        'required_document_types': sorted(DRIVER_COMPLIANCE_DOCUMENT_TYPES),
        'dispatch_required_document_types': sorted(DRIVER_DISPATCH_REQUIRED_TYPES),
        'dispatch_eligible': len(dispatch_missing_types) == 0,
        'dispatch_missing_document_types': dispatch_missing_types,
        'by_type': by_type,
        'total_documents': len(documents),
    }


def _company_compliance_summary_for_documents(documents):
    now = utcnow()
    by_type = {}
    for doc_type in sorted(COMPANY_COMPLIANCE_DOCUMENT_TYPES):
        typed_docs = [row for row in documents if row.document_type == doc_type]
        latest = typed_docs[0] if typed_docs else None
        by_type[doc_type] = {
            'present': bool(typed_docs),
            'count': len(typed_docs),
            'latest_status': latest.status if latest else None,
            'latest_document_id': latest.id if latest else None,
            'latest_expires_at': latest.expires_at.isoformat() if latest and latest.expires_at else None,
            'verified': any(_compliance_document_is_effectively_verified(row, now=now) for row in typed_docs),
            'expired': bool(
                latest and latest.expires_at and latest.expires_at <= now and str(latest.status or '').lower() == 'verified'
            ),
        }

    dispatch_missing_types = []
    for doc_type in sorted(COMPANY_DISPATCH_REQUIRED_TYPES):
        if not by_type.get(doc_type, {}).get('verified'):
            dispatch_missing_types.append(doc_type)

    return {
        'required_document_types': sorted(COMPANY_COMPLIANCE_DOCUMENT_TYPES),
        'dispatch_required_document_types': sorted(COMPANY_DISPATCH_REQUIRED_TYPES),
        'dispatch_eligible': len(dispatch_missing_types) == 0,
        'dispatch_missing_document_types': dispatch_missing_types,
        'by_type': by_type,
        'total_documents': len(documents),
    }


def _driver_compliance_summary_for_user(driver_user_id):
    documents = _driver_compliance_documents_for_driver(driver_user_id)
    return _driver_compliance_summary_for_documents(documents)


def _company_compliance_summary_for_company(carrier_company_id):
    documents = _company_compliance_documents_for_company(carrier_company_id)
    return _company_compliance_summary_for_documents(documents)


def _serialize_carrier_company(company, include_compliance=False):
    if not company:
        return None
    payload = {
        'id': company.id,
        'name': company.name,
        'contact_email': company.contact_email,
        'contact_phone': company.contact_phone,
        'is_active': bool(company.is_active),
        'created_at': company.created_at.isoformat() if company.created_at else None,
        'updated_at': company.updated_at.isoformat() if company.updated_at else None,
    }
    if include_compliance:
        payload['compliance'] = _company_compliance_summary_for_company(company.id)
    return payload


def _driver_dispatch_compliance_status(driver_user_id):
    driver_summary = _driver_compliance_summary_for_user(driver_user_id)
    driver = db.session.get(User, _to_int_or_none(driver_user_id)) if _to_int_or_none(driver_user_id) else None
    carrier_company = db.session.get(CarrierCompany, driver.carrier_company_id) if driver and driver.carrier_company_id else None
    company_summary = _company_compliance_summary_for_company(carrier_company.id) if carrier_company else None

    missing_types = []
    missing_types.extend(
        ['driver:{}'.format(doc_type) for doc_type in driver_summary.get('dispatch_missing_document_types') or []]
    )
    if not carrier_company:
        missing_types.append('company:assignment')
    elif not carrier_company.is_active:
        missing_types.append('company:inactive')
    else:
        missing_types.extend(
            ['company:{}'.format(doc_type) for doc_type in (company_summary or {}).get('dispatch_missing_document_types') or []]
        )

    eligible = (
        bool(driver_summary.get('dispatch_eligible'))
        and bool(carrier_company)
        and bool(carrier_company.is_active)
        and bool(company_summary and company_summary.get('dispatch_eligible'))
    )
    return {
        'eligible': eligible,
        'missing_document_types': missing_types,
        'summary': {
            'driver': driver_summary,
            'company': company_summary,
            'carrier_company_assigned': bool(carrier_company),
            'carrier_company_active': bool(carrier_company.is_active) if carrier_company else False,
            'carrier_company': _serialize_carrier_company(carrier_company, include_compliance=False),
        },
    }


def _build_driver_compliance_document(driver_user_id, payload, actor_user_id, actor_role):
    document_type = _normalize_compliance_document_type(payload.get('document_type'))
    if document_type not in DRIVER_COMPLIANCE_DOCUMENT_TYPES:
        raise ValueError('Invalid document_type')

    file_url = str(payload.get('file_url') or '').strip()
    if not file_url:
        raise ValueError('file_url is required')
    if len(file_url) > 500:
        raise ValueError('file_url is too long')

    status = str(payload.get('status') or 'submitted').strip().lower().replace('-', '_').replace(' ', '_')
    if status not in COMPLIANCE_DOCUMENT_STATUSES:
        raise ValueError('Invalid status')
    if actor_role != 'admin' and status != 'submitted':
        raise PermissionError('Only admins can set non-submitted status')

    metadata = payload.get('metadata') if 'metadata' in payload else {}
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError('metadata must be an object')

    notes = str(payload.get('notes') or '').strip()
    notes = notes[:2000] if notes else None
    document_reference = str(payload.get('document_reference') or '').strip()
    document_reference = document_reference[:120] if document_reference else None
    document_reference = _checked_carrier_reference(document_type, document_reference, payload)

    issued_at = None
    expires_at = None
    if payload.get('issued_at') not in (None, ''):
        issued_at = _parse_datetime_or_error(payload.get('issued_at'), 'issued_at')
    if payload.get('expires_at') not in (None, ''):
        expires_at = _parse_datetime_or_error(payload.get('expires_at'), 'expires_at')
    if issued_at and expires_at and expires_at <= issued_at:
        raise ValueError('expires_at must be later than issued_at')

    document = DriverComplianceDocument(
        driver_user_id=driver_user_id,
        uploaded_by_user_id=actor_user_id,
        document_type=document_type,
        status=status,
        file_url=file_url,
        document_reference=document_reference,
        issued_at=issued_at,
        expires_at=expires_at,
        notes=notes,
        metadata_json=metadata,
    )
    if actor_role == 'admin' and status in {'verified', 'rejected', 'expired'}:
        document.verified_by_user_id = actor_user_id
        document.verified_at = utcnow()
    return document


def _build_company_compliance_document(carrier_company_id, payload, actor_user_id):
    document_type = _normalize_compliance_document_type(payload.get('document_type'))
    if document_type not in COMPANY_COMPLIANCE_DOCUMENT_TYPES:
        raise ValueError('Invalid document_type')

    file_url = str(payload.get('file_url') or '').strip()
    if not file_url:
        raise ValueError('file_url is required')
    if len(file_url) > 500:
        raise ValueError('file_url is too long')

    status = str(payload.get('status') or 'submitted').strip().lower().replace('-', '_').replace(' ', '_')
    if status not in COMPLIANCE_DOCUMENT_STATUSES:
        raise ValueError('Invalid status')

    metadata = payload.get('metadata') if 'metadata' in payload else {}
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError('metadata must be an object')

    notes = str(payload.get('notes') or '').strip()
    notes = notes[:2000] if notes else None
    document_reference = str(payload.get('document_reference') or '').strip()
    document_reference = document_reference[:120] if document_reference else None
    document_reference = _checked_carrier_reference(document_type, document_reference, payload)

    issued_at = None
    expires_at = None
    if payload.get('issued_at') not in (None, ''):
        issued_at = _parse_datetime_or_error(payload.get('issued_at'), 'issued_at')
    if payload.get('expires_at') not in (None, ''):
        expires_at = _parse_datetime_or_error(payload.get('expires_at'), 'expires_at')
    if issued_at and expires_at and expires_at <= issued_at:
        raise ValueError('expires_at must be later than issued_at')

    document = CompanyComplianceDocument(
        carrier_company_id=carrier_company_id,
        uploaded_by_user_id=actor_user_id,
        document_type=document_type,
        status=status,
        file_url=file_url,
        document_reference=document_reference,
        issued_at=issued_at,
        expires_at=expires_at,
        notes=notes,
        metadata_json=metadata,
    )
    if status in {'verified', 'rejected', 'expired'}:
        document.verified_by_user_id = actor_user_id
        document.verified_at = utcnow()
    return document


def _compliance_summary_for_documents(documents):
    now = utcnow()
    by_type = {}
    for doc_type in sorted(COMPLIANCE_DOCUMENT_TYPES):
        by_type[doc_type] = {
            'present': False,
            'count': 0,
            'latest_status': None,
            'latest_document_id': None,
            'latest_expires_at': None,
            'verified': False,
            'expired': False,
        }

    for document in documents:
        doc_type = _normalize_compliance_document_type(document.document_type)
        bucket = by_type.setdefault(
            doc_type,
            {
                'present': False,
                'count': 0,
                'latest_status': None,
                'latest_document_id': None,
                'latest_expires_at': None,
                'verified': False,
                'expired': False,
            },
        )
        bucket['present'] = True
        bucket['count'] += 1
        if bucket['latest_document_id'] is None:
            bucket['latest_document_id'] = document.id
            bucket['latest_status'] = document.status
            bucket['latest_expires_at'] = (
                document.expires_at.isoformat() if document.expires_at else None
            )
            bucket['verified'] = _compliance_document_is_effectively_verified(document, now=now)
            bucket['expired'] = bool(document.expires_at and document.expires_at <= now)

    required_types = sorted(COMPLIANCE_DOCUMENT_TYPES)
    completion_required_types = sorted(COMPLIANCE_COMPLETION_REQUIRED_TYPES)
    is_ready = all(by_type[doc_type]['verified'] for doc_type in required_types)
    can_complete_request = all(by_type[doc_type]['verified'] for doc_type in completion_required_types)
    return {
        'required_document_types': required_types,
        'completion_required_document_types': completion_required_types,
        'is_ready': is_ready,
        'can_complete_request': can_complete_request,
        'by_type': by_type,
        'total_documents': len(documents),
    }


def _compliance_documents_for_request(request_id):
    return (
        WasteComplianceDocument.query.filter_by(waste_removal_request_id=request_id)
        .order_by(WasteComplianceDocument.created_at.desc(), WasteComplianceDocument.id.desc())
        .all()
    )


def _compliance_documents_for_requests(request_ids):
    """Every request's compliance documents, in one query.

    Same ordering as :func:`_compliance_documents_for_request`, so a caller can
    swap a page of per-row lookups for this without changing what it renders.
    Returns a dict keyed by request id; ids with no documents are absent.
    """
    grouped = {}
    request_ids = [rid for rid in set(request_ids or ()) if rid is not None]
    if not request_ids:
        return grouped

    rows = (
        WasteComplianceDocument.query
        .filter(WasteComplianceDocument.waste_removal_request_id.in_(request_ids))
        .order_by(
            WasteComplianceDocument.created_at.desc(),
            WasteComplianceDocument.id.desc(),
        )
        .all()
    )
    for row in rows:
        grouped.setdefault(row.waste_removal_request_id, []).append(row)
    return grouped


def _compliance_missing_required_document_types(summary, required_types):
    summary = summary or {}
    by_type = summary.get('by_type') or {}
    missing = []
    for doc_type in sorted(required_types):
        if not (by_type.get(doc_type) or {}).get('verified'):
            missing.append(doc_type)
    return missing


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
