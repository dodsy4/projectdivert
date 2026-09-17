"""Small, dependency-free helpers shared across the service layer."""

import json
from datetime import datetime, timezone
import dateutil.parser
import babel
from flask import g, request


def utcnow():
    """The application's only clock: the current time in UTC, without a tzinfo.

    Every stored timestamp is naive UTC, so a naive UTC "now" is what they can
    be compared against. Use this rather than :func:`datetime.datetime.utcnow`,
    which is deprecated, or :func:`datetime.datetime.now`, which returns the
    server's local time and silently disagrees with everything in the database
    whenever the server is not on UTC.

    The columns themselves are still naive; making them timezone-aware would
    need a migration and would change comparison semantics across the whole
    codebase, so the convention is enforced here instead.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_utc_naive(value):
    """Normalise a parsed datetime to the naive-UTC convention used for storage.

    An aware value is converted to UTC before its tzinfo is dropped, so an
    explicit offset from a client is honoured rather than discarded. A naive
    value is assumed to already be UTC, which is what the callers that parse
    bare ``YYYY-MM-DDTHH:MM`` strings have always effectively done.
    """
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _normalize_email(email):
    return str(email or '').strip().lower()


def _request_client_ip():
    forwarded = str(request.headers.get('X-Forwarded-For') or '').strip()
    if forwarded:
        return forwarded.split(',')[0].strip()
    real_ip = str(request.headers.get('X-Real-IP') or '').strip()
    if real_ip:
        return real_ip
    return str(request.remote_addr or '').strip() or 'unknown'


def _parse_optional_bool_query(value, label):
    raw = str(value or '').strip().lower()
    if not raw:
        return None
    if raw in {'1', 'true', 'yes', 'on'}:
        return True
    if raw in {'0', 'false', 'no', 'off'}:
        return False
    raise ValueError('Invalid {} filter. Use true or false.'.format(label))


def _parse_optional_int_query(value, label, min_value=None, max_value=None):
    raw = '' if value is None else str(value).strip()
    if not raw:
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        raise ValueError('Invalid {} filter. Use an integer.'.format(label))
    if min_value is not None and parsed < min_value:
        raise ValueError('{} must be at least {}.'.format(label, min_value))
    if max_value is not None and parsed > max_value:
        raise ValueError('{} must be at most {}.'.format(label, max_value))
    return parsed


def _parse_query_datetime_utc(value, label):
    raw = str(value or '').strip()
    if not raw:
        return None
    try:
        parsed = dateutil.parser.parse(raw)
    except (TypeError, ValueError, OverflowError):
        raise ValueError('Invalid {} datetime. Use ISO-8601 format.'.format(label))

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _json_safe(value):
    try:
        json.dumps(value, separators=(',', ':'), default=str)
        return value
    except Exception:
        return str(value)


def _snapshot(obj, fields):
    """Grab a plain-dict snapshot of model attributes for diffing."""
    if obj is None:
        return {}
    return {field: _json_safe(getattr(obj, field, None)) for field in fields}


def _is_valid_email(email):
    value = _normalize_email(email)
    if not value or len(value) > 255:
        return False
    if '@' not in value:
        return False
    local, _, domain = value.partition('@')
    if not local or not domain or '.' not in domain:
        return False
    return True


def _token_expired(expires_at):
    return bool(expires_at and expires_at <= utcnow())


def _current_jwt_claims():
    return getattr(g, 'jwt_claims', None)


def _current_jwt_role():
    claims = _current_jwt_claims() or {}
    return str(claims.get('role') or '').strip().lower()


def _current_jwt_email():
    claims = _current_jwt_claims() or {}
    return str(claims.get('email') or '').strip().lower()


def _current_jwt_user_id():
    claims = _current_jwt_claims() or {}
    raw = str(claims.get('sub') or '').strip()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _to_int_or_none(value):
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float_or_none(value):
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_yes_no_flag(value):
    normalized = str(value or '').strip().lower()
    if normalized in {'1', 'true', 'yes', 'y'}:
        return True
    if normalized in {'0', 'false', 'no', 'n'}:
        return False
    numeric = _to_float_or_none(normalized)
    if numeric is not None:
        if numeric == 1.0:
            return True
        if numeric == 0.0:
            return False
    return None


def _to_percent_or_none(value):
    parsed = _to_float_or_none(value)
    if parsed is None:
        return None
    return max(0.0, min(100.0, parsed))


def _require_form_fields(form_data, required_fields):
    """Return stripped field values and raise ValueError for missing required fields."""
    cleaned = {}
    missing = []
    for field in required_fields:
        value = (form_data.get(field) or '').strip()
        cleaned[field] = value
        if not value:
            missing.append(field)
    if missing:
        raise ValueError('Missing required field(s): {}.'.format(', '.join(missing)))
    return cleaned


def _require_positive_number(value, label, allow_zero=False):
    """Parse a user-supplied numeric field, raising ValueError with a friendly message."""
    try:
        number = float(str(value).strip().replace(',', ''))
    except (TypeError, ValueError):
        raise ValueError('Please enter a valid number for {}.'.format(label))
    if number < 0 or (number == 0 and not allow_zero):
        raise ValueError('Please enter a {} greater than {}.'.format(label, '0' if not allow_zero else 'or equal to 0'))
    return number


def _parse_datetime_or_error(value, label):
    try:
        parsed = dateutil.parser.parse(str(value).strip())
    except (TypeError, ValueError, OverflowError):
        raise ValueError('Please provide a valid {}.'.format(label))

    # astimezone() with no argument converts to the server's local zone, which
    # made a client's explicit offset land an hour out whenever the server was
    # not on UTC. Storage is UTC, so normalise to UTC.
    return to_utc_naive(parsed)


def _hours_since(timestamp, now=None):
    minutes = _minutes_since(timestamp, now=now)
    if minutes is None:
        return None
    return round(minutes / 60.0, 1)


def _minutes_since(timestamp, now=None):
    if not timestamp:
        return None
    now = now or utcnow()
    return max(0, int((now - timestamp).total_seconds() // 60))


def _is_truthy(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def format_datetime(value, format='medium'):
    date = dateutil.parser.parse(value)
    if format == 'full':
        format="EEEE MMMM, d, y 'at' h:mma"
    elif format == 'medium':
        format="EE MM, dd, y h:mma"
    return babel.dates.format_datetime(date, format)
