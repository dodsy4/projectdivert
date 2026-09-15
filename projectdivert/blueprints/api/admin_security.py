"""Admin security routes."""

import json
import io
import csv
from datetime import datetime, timedelta
from flask import Blueprint, Response, current_app, jsonify, request
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from projectdivert.extensions import db
from projectdivert.models.audit import AuditEvent, AuthAuditEvent
from projectdivert.models.auth import AuthLifecycleToken, AuthSecurityBlocklist
from projectdivert.models.user import User
from projectdivert.services.audit import _audit_auth_event, _build_admin_auth_audit_query, _build_audit_events_query, _parse_admin_auth_audit_filters, _serialize_audit_event, _serialize_auth_audit_event, _serialize_auth_blocklist_entry, _serialize_auth_lifecycle_token
from projectdivert.services.auth import _revoke_all_access_tokens_for_user, _revoke_all_refresh_tokens_for_user, _serialize_auth_user, jwt_required
from projectdivert.services.rate_limit import _auth_blocklist_default_duration_seconds, _normalize_auth_block_identifier
from projectdivert.services.utils import _current_jwt_user_id, _parse_optional_bool_query, _parse_optional_int_query, _parse_query_datetime_utc

bp = Blueprint('api_admin_security', __name__)



@bp.route('/api/v1/admin/auth-audit', methods=['GET'])
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
        current_app.logger.exception('Failed to query auth audit events.')
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



@bp.route('/api/v1/admin/auth-audit/export', methods=['GET'])
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
        current_app.logger.exception('Failed to export auth audit events.')
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

    csv_bytes = buffer.getvalue()
    filename = 'auth_audit_export_{}.csv'.format(datetime.utcnow().strftime('%Y%m%d_%H%M%S'))
    response = Response(csv_bytes, mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename={}'.format(filename)
    return response



@bp.route('/api/v1/admin/audit-events', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_audit_events():
    try:
        limit = _parse_optional_int_query(request.args.get('limit'), 'limit', min_value=1, max_value=500)
        offset = _parse_optional_int_query(request.args.get('offset'), 'offset', min_value=0)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    limit = limit or 50
    offset = offset or 0

    try:
        query = _build_audit_events_query(request.args)
        total = query.count()
        rows = (
            query.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
    except SQLAlchemyError:
        current_app.logger.exception('Failed to query audit events.')
        return jsonify({'error': 'Failed to query audit events'}), 500

    return jsonify(
        {
            'items': [_serialize_audit_event(row) for row in rows],
            'pagination': {
                'limit': limit,
                'offset': offset,
                'returned': len(rows),
                'total': total,
                'has_more': (offset + len(rows)) < total,
            },
        }
    )



@bp.route('/api/v1/admin/auth-security/blocks', methods=['GET'])
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
        current_app.logger.exception('Failed to query auth security blocks.')
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



@bp.route('/api/v1/admin/auth-security/blocks', methods=['POST'])
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
        current_app.logger.exception('Failed to create auth security block.')
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



@bp.route('/api/v1/admin/auth-security/blocks/<int:block_id>/unblock', methods=['POST'])
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
        current_app.logger.exception('Failed to unblock auth security block %s.', block_id)
        return jsonify({'error': 'Failed to unblock auth security block'}), 500

    _audit_auth_event(
        'admin_security_block_unblock',
        success=True,
        status_code=200,
        user_id=_current_jwt_user_id(),
        details={'block_id': row.id},
    )
    return jsonify({'revoked': True, 'block': _serialize_auth_blocklist_entry(row)})



@bp.route('/api/v1/admin/auth-security/telemetry', methods=['GET'])
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
        current_app.logger.exception('Failed to generate auth security telemetry.')
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



@bp.route('/api/v1/admin/auth-tokens', methods=['GET'])
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
        current_app.logger.exception('Failed to query auth lifecycle tokens.')
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



@bp.route('/api/v1/admin/auth-tokens/<int:token_row_id>/revoke', methods=['POST'])
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
        current_app.logger.exception('Failed to revoke auth token %s.', token_row_id)
        return jsonify({'error': 'Failed to revoke auth token'}), 500

    _audit_auth_event(
        'admin_token_revoke',
        success=True,
        status_code=200,
        user_id=token_row.user_id,
        details={'token_row_id': token_row_id, 'token_type': token_row.token_type},
    )
    return jsonify({'revoked': True, 'token': _serialize_auth_lifecycle_token(token_row)})



@bp.route('/api/v1/admin/users/<int:user_id>/sessions/revoke', methods=['POST'])
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
        current_app.logger.exception('Failed to revoke sessions for user %s.', user_id)
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
