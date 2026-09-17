"""Authentication and application-wide audit trails."""

import json
import uuid
from flask import g, has_request_context, request
from sqlalchemy import func
from flask_login import current_user
from projectdivert.extensions import db
from projectdivert.models.audit import AuditEvent, AuthAuditEvent
from projectdivert.services.utils import _current_jwt_claims, _current_jwt_email, _current_jwt_role, _current_jwt_user_id, _json_safe, _normalize_email, _parse_optional_bool_query, _parse_optional_int_query, _parse_query_datetime_utc, _request_client_ip, _to_int_or_none, utcnow
import logging

logger = logging.getLogger(__name__)


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
                    occurred_at=occurred_at or utcnow(),
                )
            )
    except Exception:
        # Audit persistence should never break auth endpoints.
        logger.exception('Failed to persist auth audit event.')


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


def _serialize_audit_event(row):
    if not row:
        return None
    return {
        'id': row.id,
        'occurred_at': row.occurred_at.isoformat() + 'Z' if row.occurred_at else None,
        'action': row.action,
        'entity_type': row.entity_type,
        'entity_id': row.entity_id,
        'actor': {
            'user_id': row.actor_user_id,
            'role': row.actor_role,
            'email': row.actor_email,
            'ip': row.actor_ip,
        },
        'source': row.source,
        'http_method': row.http_method,
        'path': row.path,
        'status_code': row.status_code,
        'request_id': row.request_id,
        'summary': row.summary,
        'changes': row.changes or {},
    }


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
        'is_active': bool((row.revoked_at is None) and (row.expires_at is None or row.expires_at > utcnow())),
    }


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
    occurred_at = utcnow()
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
        logger.info('auth_audit %s', json.dumps(payload, separators=(',', ':')))
    except Exception:
        logger.info(
            'auth_audit event=%s success=%s status=%s email=%s user_id=%s',
            payload['event'],
            payload['success'],
            payload['status_code'],
            payload['email'],
            payload['user_id'],
        )
    _persist_auth_audit_event(payload, occurred_at=occurred_at)


_AUDIT_JSON_MAX_CHARS = 8000


# Paths that must never generate a generic audit row even though they can be
# non-GET. Authentication flows are already covered by AuthAuditEvent.
_AUDIT_SKIP_PREFIXES = ('/static/', '/health', '/healthz', '/favicon', '/api/v1/auth/')


_AUDIT_SKIP_EXACT = {'/api/v1/health', '/api/v1/ping', '/login', '/register'}


# request.url_rule.rule -> (action, entity_type). Rules not listed here still get
# a generic row ("<method> <rule>") so nothing slips through unaudited.
_AUDIT_ROUTE_REGISTRY = {
    '/api/v1/waste-requests': ('waste_request.create', 'waste_request'),
    '/api/v1/waste-requests/<int:request_id>/status': ('waste_request.status_change', 'waste_request'),
    '/api/v1/waste-requests/<int:request_id>/location': ('waste_request.location_update', 'waste_request'),
    '/api/v1/waste-requests/<int:request_id>/dispatch/accept': ('dispatch_offer.accept', 'waste_request'),
    '/api/v1/push-subscriptions': ('push_subscription.register', 'push_subscription'),
    '/admin/dispatch/override': ('dispatch.override', 'waste_request'),
    '/admin/dispatch/incident': ('dispatch.incident_create', 'waste_request'),
    '/admin/dispatch/incident-owner': ('dispatch.incident_owner', 'waste_request'),
    '/output': ('diversion_estimate.create', 'diversion_estimate'),
    '/material_input': ('material.create', 'material'),
    '/material/<int:mat_id>/request': ('material_request.create', 'material_request'),
    '/submit_details1': ('charity.create', 'charity'),
    '/submit_details2': ('charity.create', 'charity'),
    '/submit_details3': ('charity.create', 'charity'),
    '/logout': ('auth.logout', 'user'),
}


def _audit_actor():
    """Resolve who is acting on the current request.

    Returns a dict with user_id / role / email / source. API requests carry a
    verified JWT (``g.jwt_claims``); web requests use the Flask-Login session.
    """
    claims = _current_jwt_claims()
    if claims:
        return {
            'user_id': _current_jwt_user_id(),
            'role': _current_jwt_role() or None,
            'email': _current_jwt_email() or None,
            'source': 'api',
        }
    try:
        if current_user and current_user.is_authenticated:
            role = str(getattr(current_user, 'role', '') or '').strip().lower() or None
            return {
                'user_id': getattr(current_user, 'id', None),
                'role': role,
                'email': getattr(current_user, 'email', None),
                'source': 'admin' if role == 'admin' else 'web',
            }
    except Exception:
        pass
    # Unauthenticated request inside a request context is still a web action.
    source = 'web' if has_request_context() else 'system'
    return {'user_id': None, 'role': None, 'email': None, 'source': source}


def _audit_request_id():
    existing = getattr(g, 'request_id', None)
    if not existing:
        existing = uuid.uuid4().hex
        try:
            g.request_id = existing
        except Exception:
            pass
    return existing


def _audit_diff(before, after):
    """Return {field: [old, new]} for keys whose value changed."""
    before = before or {}
    after = after or {}
    changes = {}
    for key in set(before) | set(after):
        old = before.get(key)
        new = after.get(key)
        if old != new:
            changes[str(key)] = [_json_safe(old), _json_safe(new)]
    return changes


def _persist_audit_event(row_values):
    try:
        with db.engine.begin() as connection:
            connection.execute(AuditEvent.__table__.insert().values(**row_values))
    except Exception:
        # Audit persistence must never break the request it describes.
        logger.exception('Failed to persist audit event.')


def record_audit_event(
    action,
    entity_type=None,
    entity_id=None,
    summary=None,
    changes=None,
    status_code=None,
    source=None,
    actor=None,
    occurred_at=None,
):
    """Write one application audit row (DB + structured log).

    Safe to call from within a request handler: the DB write runs on its own
    connection so it is never rolled back with the request transaction, and any
    failure is swallowed after logging.
    """
    actor = actor or _audit_actor()
    occurred_at = occurred_at or utcnow()
    try:
        g.audit_explicitly_recorded = True
    except Exception:
        pass
    changes = changes or {}
    if not isinstance(changes, dict):
        changes = {'value': _json_safe(changes)}

    try:
        method = request.method
        path = request.path
        user_agent = str((request.user_agent.string or '')[:255])
        ip = _request_client_ip()
    except Exception:
        method = path = user_agent = ip = None

    # Round-trip through JSON so any non-serialisable value is coerced to a
    # string here rather than blowing up the DB write later.
    serialized_changes = json.dumps(changes, separators=(',', ':'), default=str)
    if len(serialized_changes) > _AUDIT_JSON_MAX_CHARS:
        changes = {'_truncated': True, 'field_count': len(changes)}
    else:
        changes = json.loads(serialized_changes)

    row_values = {
        'occurred_at': occurred_at,
        'action': str(action or 'unknown')[:80],
        'entity_type': (str(entity_type)[:64] if entity_type else None),
        'entity_id': (str(entity_id)[:64] if entity_id not in (None, '') else None),
        'actor_user_id': _to_int_or_none(actor.get('user_id')),
        'actor_role': (str(actor.get('role'))[:32] if actor.get('role') else None),
        'actor_email': (_normalize_email(actor.get('email')) or None),
        'actor_ip': (str(ip)[:64] if ip else None),
        'user_agent': (user_agent or None),
        'source': (str(source or actor.get('source') or 'web')[:16]),
        'http_method': (str(method)[:8] if method else None),
        'path': (str(path)[:255] if path else None),
        'status_code': _to_int_or_none(status_code),
        'request_id': _audit_request_id(),
        'summary': (str(summary)[:255] if summary else None),
        'changes': changes,
    }

    log_payload = {k: v for k, v in row_values.items() if k != 'changes'}
    log_payload['occurred_at'] = occurred_at.isoformat() + 'Z'
    log_payload['change_fields'] = sorted(changes.keys())
    try:
        logger.info('audit %s', json.dumps(log_payload, separators=(',', ':'), default=str))
    except Exception:
        logger.info('audit action=%s entity=%s:%s', action, entity_type, entity_id)

    _persist_audit_event(row_values)


def _audit_should_capture(response):
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return False
    path = request.path or ''
    if path in _AUDIT_SKIP_EXACT or path.startswith(_AUDIT_SKIP_PREFIXES):
        return False
    # Only successful mutations. Failed auth / validation noise is either handled
    # by _audit_auth_event or simply not interesting for the audit trail.
    if response.status_code >= 400:
        return False
    # A handler already wrote a richer, explicit row for this request.
    if getattr(g, 'audit_explicitly_recorded', False):
        return False
    return True


def _build_audit_events_query(args):
    query = AuditEvent.query
    action = str(args.get('action') or '').strip()
    if action:
        query = query.filter(AuditEvent.action.ilike('%{}%'.format(action)))
    entity_type = str(args.get('entity_type') or '').strip()
    if entity_type:
        query = query.filter(AuditEvent.entity_type == entity_type)
    entity_id = str(args.get('entity_id') or '').strip()
    if entity_id:
        query = query.filter(AuditEvent.entity_id == entity_id)
    actor_user_id = _to_int_or_none(args.get('actor_user_id'))
    if actor_user_id is not None:
        query = query.filter(AuditEvent.actor_user_id == actor_user_id)
    actor_email = _normalize_email(args.get('actor_email'))
    if actor_email:
        query = query.filter(AuditEvent.actor_email == actor_email)
    source = str(args.get('source') or '').strip()
    if source:
        query = query.filter(AuditEvent.source == source)
    return query
