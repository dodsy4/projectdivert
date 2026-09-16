"""JWT issuing and verification, lifecycle tokens, request authorisation."""

import logging
import uuid
from datetime import datetime, timedelta
from functools import wraps
import jwt
from flask import current_app, g, jsonify, request
from sqlalchemy import and_, func, or_
from flask_login import current_user
from projectdivert.extensions import db, login_manager
from projectdivert.models.auth import AuthLifecycleToken
from projectdivert.models.user import User
from projectdivert.services.audit import _audit_auth_event
from projectdivert.services.rate_limit import _auth_rate_limit_admin_enabled, _auth_rate_limit_enabled, _check_auth_rate_limit
from projectdivert.services.utils import _current_jwt_email, _current_jwt_role, _current_jwt_user_id, _is_truthy, _normalize_email, _request_client_ip, _to_int_or_none, _token_expired

logger = logging.getLogger(__name__)



@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def _jwt_secret():
    return current_app.config.get('JWT_SECRET_KEY') or current_app.config.get('SECRET_KEY')


def _jwt_exp_hours():
    value = current_app.config.get('JWT_EXP_HOURS', 24)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 24


def _jwt_refresh_exp_days():
    value = current_app.config.get('JWT_REFRESH_EXP_DAYS', 30)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 30


def _email_verification_token_exp_hours():
    value = current_app.config.get('EMAIL_VERIFICATION_TOKEN_EXP_HOURS', 24)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 24


def _password_reset_token_exp_minutes():
    value = current_app.config.get('PASSWORD_RESET_TOKEN_EXP_MINUTES', 30)
    try:
        return max(5, int(value))
    except (TypeError, ValueError):
        return 30


def _auth_verify_request_cooldown_seconds():
    value = current_app.config.get('AUTH_VERIFY_REQUEST_COOLDOWN_SECONDS', 60)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 60


def _auth_password_reset_request_cooldown_seconds():
    value = current_app.config.get('AUTH_PASSWORD_RESET_REQUEST_COOLDOWN_SECONDS', 60)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 60


def _auth_max_active_refresh_tokens():
    value = current_app.config.get('AUTH_MAX_ACTIVE_REFRESH_TOKENS', 10)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 10


def _auth_require_email_verification():
    return _is_truthy(current_app.config.get('AUTH_REQUIRE_EMAIL_VERIFICATION', False))


def _auth_return_tokens_in_response():
    return _is_truthy(current_app.config.get('AUTH_RETURN_TOKENS_IN_RESPONSE', False))


def _auth_suspicious_activity_revoke_sessions_enabled():
    return _is_truthy(current_app.config.get('AUTH_SUSPICIOUS_ACTIVITY_REVOKE_SESSIONS', True))


def _auth_suspicious_activity_revoke_min_lockout_level():
    value = current_app.config.get('AUTH_SUSPICIOUS_ACTIVITY_REVOKE_MIN_LOCKOUT_LEVEL', 1)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


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


def _validate_password_strength(password):
    value = str(password or '')
    if len(value) < 8:
        return 'Password must be at least 8 characters.'
    if not any(ch.isalpha() for ch in value):
        return 'Password must include at least one letter.'
    if not any(ch.isdigit() for ch in value):
        return 'Password must include at least one number.'
    return None


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


def _verification_url_for_token(token):
    base_url = (current_app.config.get('APP_BASE_URL') or '').strip().rstrip('/')
    if not base_url:
        return ''
    return '{}/verify-email?token={}'.format(base_url, token)


def _password_reset_url_for_token(token):
    base_url = (current_app.config.get('APP_BASE_URL') or '').strip().rstrip('/')
    if not base_url:
        return ''
    return '{}/reset-password?token={}'.format(base_url, token)


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
        return _request_assigned_driver_matches_current_user(booking)
    if role == 'customer':
        return (booking.requester_email or '').strip().lower() == _current_jwt_email()
    return False


def _request_assigned_driver_matches_current_user(booking):
    if not booking:
        return False
    assigned_driver_user_id = _to_int_or_none(getattr(booking, 'assigned_driver_user_id', None))
    current_user_id = _to_int_or_none(_current_jwt_user_id())
    return bool(assigned_driver_user_id and current_user_id and assigned_driver_user_id == current_user_id)


def _request_driver_mutation_allowed(booking):
    role = _current_jwt_role()
    if role == 'admin':
        return True
    if role == 'driver':
        return _request_assigned_driver_matches_current_user(booking)
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


def _auth_token_cleanup_retention_days():
    value = current_app.config.get('AUTH_TOKEN_CLEANUP_RETENTION_DAYS', 30)
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


def _current_user_is_admin():
    return bool(
        current_user.is_authenticated
        and str(getattr(current_user, 'role', '') or '').strip().lower() == 'admin'
    )


def run_auth_token_cleanup(retention_days=None, batch_size=500, dry_run=False):
    """Delete auth lifecycle tokens that expired or were revoked before the cutoff.

    Shared by the ``auth-token-cleanup`` CLI command and the background job, so
    a scheduled run and a manual run cannot drift apart. Returns a summary dict.
    """
    if retention_days is None:
        retention_days = _auth_token_cleanup_retention_days()
    retention_days = int(retention_days)
    batch_size = int(batch_size)
    if retention_days < 0:
        raise ValueError('retention_days must be >= 0')
    if batch_size < 1:
        raise ValueError('batch_size must be >= 1')

    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    candidates = _auth_token_cleanup_query(cutoff).count()
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

    summary = {
        'cutoff': cutoff.isoformat() + 'Z',
        'retention_days': retention_days,
        'candidates': candidates,
        'by_token_type': {str(k): int(v) for k, v in type_counts.items()},
        'deleted': 0,
        'dry_run': bool(dry_run),
    }
    if dry_run or candidates == 0:
        return summary

    deleted = 0
    while True:
        ids = [
            row.id for row in _auth_token_cleanup_query(cutoff)
            .order_by(AuthLifecycleToken.id.asc())
            .limit(batch_size)
            .all()
        ]
        if not ids:
            break
        deleted += (
            AuthLifecycleToken.query
            .filter(AuthLifecycleToken.id.in_(ids))
            .delete(synchronize_session=False)
            or 0
        )
        db.session.commit()

    summary['deleted'] = deleted
    logger.info('Auth token cleanup deleted %s rows before %s', deleted, summary['cutoff'])
    return summary
