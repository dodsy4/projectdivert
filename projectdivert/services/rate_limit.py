"""Auth rate limiting, login lockout and the security blocklist."""

import uuid
import threading
from datetime import datetime, timedelta
try:
    import redis
except Exception:  # pragma: no cover - optional dependency
    redis = None
from flask import current_app, jsonify
from sqlalchemy import or_
from projectdivert.models.auth import AuthSecurityBlocklist
from projectdivert.services.utils import _is_truthy, _normalize_email, _request_client_ip, _to_int_or_none
import logging

logger = logging.getLogger(__name__)


def _auth_blocklist_enabled():
    return _is_truthy(current_app.config.get('AUTH_BLOCKLIST_ENABLED', True))


def _auth_blocklist_default_duration_seconds():
    value = current_app.config.get('AUTH_BLOCKLIST_DEFAULT_DURATION_SECONDS', 86400)
    try:
        return max(60, int(value))
    except (TypeError, ValueError):
        return 86400


def _auth_rate_limit_enabled():
    return _is_truthy(current_app.config.get('AUTH_RATE_LIMIT_ENABLED', True))


def _auth_rate_limit_admin_enabled():
    return _is_truthy(current_app.config.get('AUTH_RATE_LIMIT_ADMIN_ENABLED', True))


def _auth_rate_limit_window_seconds(action=''):
    value = current_app.config.get('AUTH_RATE_LIMIT_WINDOW_SECONDS', 300)
    try:
        return max(10, int(value))
    except (TypeError, ValueError):
        return 300


def _auth_rate_limit_redis_url():
    return str(current_app.config.get('AUTH_RATE_LIMIT_REDIS_URL') or '').strip()


def _auth_rate_limit_redis_prefix():
    value = str(current_app.config.get('AUTH_RATE_LIMIT_REDIS_PREFIX') or '').strip()
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
    value = current_app.config.get(config_key, 10)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 10


def _auth_login_lockout_enabled():
    return _is_truthy(current_app.config.get('AUTH_LOGIN_LOCKOUT_ENABLED', True))


def _auth_login_lockout_window_seconds():
    value = current_app.config.get('AUTH_LOGIN_LOCKOUT_WINDOW_SECONDS', 900)
    try:
        return max(60, int(value))
    except (TypeError, ValueError):
        return 900


def _auth_login_lockout_max_attempts():
    value = current_app.config.get('AUTH_LOGIN_LOCKOUT_MAX_ATTEMPTS', 5)
    try:
        return max(2, int(value))
    except (TypeError, ValueError):
        return 5


def _auth_login_lockout_duration_seconds():
    value = current_app.config.get('AUTH_LOGIN_LOCKOUT_DURATION_SECONDS', 900)
    try:
        return max(60, int(value))
    except (TypeError, ValueError):
        return 900


def _auth_login_lockout_escalation_enabled():
    return _is_truthy(current_app.config.get('AUTH_LOGIN_LOCKOUT_ESCALATION_ENABLED', True))


def _auth_login_lockout_escalation_factor():
    value = current_app.config.get('AUTH_LOGIN_LOCKOUT_ESCALATION_FACTOR', 2)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 2


def _auth_login_lockout_escalation_reset_seconds():
    value = current_app.config.get('AUTH_LOGIN_LOCKOUT_ESCALATION_RESET_SECONDS', 86400)
    try:
        return max(60, int(value))
    except (TypeError, ValueError):
        return 86400


def _auth_login_lockout_max_duration_seconds():
    value = current_app.config.get('AUTH_LOGIN_LOCKOUT_MAX_DURATION_SECONDS', 86400)
    try:
        return max(60, int(value))
    except (TypeError, ValueError):
        return 86400


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
            logger.warning(
                'AUTH_RATE_LIMIT_REDIS_URL is set but redis package is unavailable; using in-memory rate limits.',
            )
        _auth_rate_limit_redis_disabled = True
        return None

    try:
        client = redis.Redis.from_url(redis_url, decode_responses=True)
        client.ping()
        _auth_rate_limit_redis_client = client
        logger.info('Auth rate limiting using Redis backend.')
        return _auth_rate_limit_redis_client
    except Exception:
        _auth_rate_limit_redis_disabled = True
        logger.exception('Failed to initialize Redis auth rate limiter; using in-memory fallback.')
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
        logger.exception(
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


def _normalize_auth_block_identifier(identifier_type, identifier_value):
    id_type = str(identifier_type or '').strip().lower()
    raw_value = str(identifier_value or '').strip()
    if id_type == 'email':
        return id_type, _normalize_email(raw_value)
    if id_type == 'ip':
        return id_type, raw_value[:64]
    return id_type, raw_value


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
