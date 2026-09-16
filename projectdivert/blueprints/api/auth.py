"""Auth routes."""

from datetime import datetime
import jwt
from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash
from projectdivert.extensions import db
from projectdivert.models.user import User
from projectdivert.services.audit import _audit_auth_event
from projectdivert.services.auth import _auth_password_reset_request_cooldown_seconds, _auth_require_email_verification, _auth_return_tokens_in_response, _auth_suspicious_activity_revoke_min_lockout_level, _auth_suspicious_activity_revoke_sessions_enabled, _auth_verify_request_cooldown_seconds, _consume_one_time_lifecycle_token, _decode_access_token, _encode_lifecycle_token_from_row, _extract_bearer_token, _issue_auth_payload, _issue_email_verification_token, _issue_password_reset_token, _parse_lifecycle_token, _password_reset_url_for_token, _recent_valid_one_time_token, _refresh_row_from_claims, _revoke_access_token_jti, _revoke_all_access_tokens_for_user, _revoke_all_refresh_tokens_for_user, _revoke_sessions_for_suspicious_activity, _rotate_refresh_token, _serialize_auth_user, _validate_password_strength, _verification_url_for_token
from projectdivert.services.notifications import _send_account_email
from projectdivert.services.rate_limit import _auth_blocklist_response, _auth_login_lockout_identifiers, _auth_login_lockout_level, _auth_login_lockout_response, _auth_rate_limit_response, _clear_auth_login_failure, _record_auth_login_failure
from projectdivert.services.utils import _is_valid_email, _normalize_email, _to_int_or_none

bp = Blueprint('api_auth', __name__)



@bp.route('/api/v1/auth/login', methods=['POST'])
def api_auth_login():
    payload = request.get_json(silent=True) or {}
    email = _normalize_email(payload.get('email'))
    password = str(payload.get('password') or '').strip()
    block_response = _auth_blocklist_response(email=email)
    if block_response:
        _audit_auth_event(
            'login',
            success=False,
            status_code=403,
            email=email,
            details={'reason': 'blocklist'},
        )
        return block_response
    lockout_response = _auth_login_lockout_response(email=email)
    if lockout_response:
        _audit_auth_event(
            'login',
            success=False,
            status_code=429,
            email=email,
            details={'reason': 'lockout_active'},
        )
        return lockout_response
    rate_limited = _auth_rate_limit_response('login', email=email)
    if rate_limited:
        _audit_auth_event(
            'login',
            success=False,
            status_code=429,
            email=email,
            details={'reason': 'rate_limited'},
        )
        return rate_limited
    if not email or not password:
        _audit_auth_event(
            'login',
            success=False,
            status_code=400,
            email=email,
            details={'reason': 'missing_credentials'},
        )
        return jsonify({'error': 'email and password are required'}), 400

    user = User.query.filter(func.lower(User.email) == email).first()
    if not user or not user.is_active or not check_password_hash(user.password_hash, password):
        lockout_retry_after = 0
        lockout_level = 0
        lockout_identifiers = _auth_login_lockout_identifiers(email=email)
        for identifier in lockout_identifiers:
            lockout_retry_after = max(lockout_retry_after, _record_auth_login_failure(identifier))
            lockout_level = max(lockout_level, _auth_login_lockout_level(identifier))
        if lockout_retry_after > 0:
            sessions_revoked = False
            suspicious_revocation_enabled = (
                user is not None
                and _auth_suspicious_activity_revoke_sessions_enabled()
                and lockout_level >= _auth_suspicious_activity_revoke_min_lockout_level()
            )
            if suspicious_revocation_enabled:
                try:
                    sessions_revoked = _revoke_sessions_for_suspicious_activity(
                        user.id,
                        reason='suspicious_login_lockout',
                    )
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    sessions_revoked = False
                    current_app.logger.exception(
                        'Failed revoking sessions for suspicious login lockout user_id=%s.',
                        user.id,
                    )

            response = jsonify({'error': 'Too many failed login attempts. Please try again later.'})
            response.status_code = 429
            response.headers['Retry-After'] = str(lockout_retry_after)
            _audit_auth_event(
                'login',
                success=False,
                status_code=429,
                email=email,
                user_id=user.id if user else None,
                details={
                    'reason': 'lockout_triggered',
                    'retry_after_seconds': lockout_retry_after,
                    'lockout_level': lockout_level,
                    'sessions_revoked': sessions_revoked,
                },
            )
            return response

        _audit_auth_event(
            'login',
            success=False,
            status_code=401,
            email=email,
            user_id=user.id if user else None,
            details={'reason': 'invalid_credentials'},
        )
        return jsonify({'error': 'Invalid email or password'}), 401

    if _auth_require_email_verification() and not user.email_verified_at:
        _audit_auth_event(
            'login',
            success=False,
            status_code=403,
            email=email,
            user_id=user.id,
            details={'reason': 'email_unverified'},
        )
        return jsonify({'error': 'Email verification required'}), 403

    try:
        for identifier in _auth_login_lockout_identifiers(email=email):
            _clear_auth_login_failure(identifier)
        auth_payload = _issue_auth_payload(user)
        db.session.commit()
        _audit_auth_event(
            'login',
            success=True,
            status_code=200,
            email=email,
            user_id=user.id,
        )
        return jsonify(auth_payload)
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed issuing auth tokens for login.')
        _audit_auth_event(
            'login',
            success=False,
            status_code=500,
            email=email,
            user_id=user.id,
            details={'reason': 'server_error'},
        )
        return jsonify({'error': 'Failed to create session'}), 500



@bp.route('/api/v1/auth/signup', methods=['POST'])
def api_auth_signup():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get('name') or '').strip()
    email = _normalize_email(payload.get('email'))
    password = str(payload.get('password') or '')
    role = 'customer'

    rate_limited = _auth_rate_limit_response('signup', email=email)
    if rate_limited:
        _audit_auth_event(
            'signup',
            success=False,
            status_code=429,
            email=email,
            details={'reason': 'rate_limited'},
        )
        return rate_limited

    if not name:
        _audit_auth_event(
            'signup',
            success=False,
            status_code=400,
            email=email,
            details={'reason': 'missing_name'},
        )
        return jsonify({'error': 'name is required'}), 400
    if not _is_valid_email(email):
        _audit_auth_event(
            'signup',
            success=False,
            status_code=400,
            email=email,
            details={'reason': 'invalid_email'},
        )
        return jsonify({'error': 'A valid email is required'}), 400
    password_error = _validate_password_strength(password)
    if password_error:
        _audit_auth_event(
            'signup',
            success=False,
            status_code=400,
            email=email,
            details={'reason': 'weak_password'},
        )
        return jsonify({'error': password_error}), 400

    if User.query.filter(func.lower(User.email) == email).first():
        _audit_auth_event(
            'signup',
            success=False,
            status_code=409,
            email=email,
            details={'reason': 'email_exists'},
        )
        return jsonify({'error': 'An account with this email already exists'}), 409

    try:
        user = User(
            name=name[:120],
            email=email,
            password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
            role=role,
            is_active_user=True,
            email_verified_at=None if _auth_require_email_verification() else datetime.utcnow(),
        )
        db.session.add(user)
        db.session.flush()

        if user.email_verified_at:
            auth_payload = _issue_auth_payload(user)
            db.session.commit()
            auth_payload['created'] = True
            _audit_auth_event(
                'signup',
                success=True,
                status_code=201,
                email=email,
                user_id=user.id,
                details={'verification_required': False},
            )
            return jsonify(auth_payload), 201

        verification_token = _issue_email_verification_token(user)
        verify_url = _verification_url_for_token(verification_token)
        message_lines = [
            'Verify your Project Divert account by using this token:',
            verification_token,
        ]
        if verify_url:
            message_lines.extend(['', 'Or open:', verify_url])
        verification_email_sent = _send_account_email(
            user.email,
            'Verify your Project Divert account',
            '\n'.join(message_lines),
        )
        db.session.commit()

        response_payload = {
            'created': True,
            'verification_required': True,
            'verification_email_sent': bool(verification_email_sent),
            'user': _serialize_auth_user(user),
        }
        if _auth_return_tokens_in_response():
            response_payload['verification_token'] = verification_token
        _audit_auth_event(
            'signup',
            success=True,
            status_code=201,
            email=email,
            user_id=user.id,
            details={
                'verification_required': True,
                'verification_email_sent': bool(verification_email_sent),
            },
        )
        return jsonify(response_payload), 201
    except Exception:
        db.session.rollback()
        current_app.logger.exception('API signup failed.')
        _audit_auth_event(
            'signup',
            success=False,
            status_code=500,
            email=email,
            details={'reason': 'server_error'},
        )
        return jsonify({'error': 'Failed to create account'}), 500



@bp.route('/api/v1/auth/refresh', methods=['POST'])
def api_auth_refresh():
    rate_limited = _auth_rate_limit_response('refresh')
    if rate_limited:
        _audit_auth_event(
            'refresh',
            success=False,
            status_code=429,
            details={'reason': 'rate_limited'},
        )
        return rate_limited

    payload = request.get_json(silent=True) or {}
    refresh_token = str(payload.get('refresh_token') or '').strip()
    if not refresh_token:
        refresh_token = _extract_bearer_token()
    if not refresh_token:
        _audit_auth_event(
            'refresh',
            success=False,
            status_code=400,
            details={'reason': 'missing_refresh_token'},
        )
        return jsonify({'error': 'refresh_token is required'}), 400

    try:
        user = _rotate_refresh_token(refresh_token)
        auth_payload = _issue_auth_payload(user)
        db.session.commit()
        _audit_auth_event(
            'refresh',
            success=True,
            status_code=200,
            email=user.email,
            user_id=user.id,
        )
        return jsonify(auth_payload)
    except ValueError as exc:
        db.session.rollback()
        message = str(exc)
        status = 403 if message == 'Email verification required' else 401
        _audit_auth_event(
            'refresh',
            success=False,
            status_code=status,
            details={'reason': message},
        )
        return jsonify({'error': message}), status
    except Exception:
        db.session.rollback()
        current_app.logger.exception('API refresh token failed.')
        _audit_auth_event(
            'refresh',
            success=False,
            status_code=500,
            details={'reason': 'server_error'},
        )
        return jsonify({'error': 'Failed to refresh session'}), 500



@bp.route('/api/v1/auth/logout', methods=['POST'])
def api_auth_logout():
    rate_limited = _auth_rate_limit_response('logout')
    if rate_limited:
        _audit_auth_event(
            'logout',
            success=False,
            status_code=429,
            details={'reason': 'rate_limited'},
        )
        return rate_limited

    payload = request.get_json(silent=True) or {}
    refresh_token = str(payload.get('refresh_token') or '').strip()
    if not refresh_token:
        refresh_token = _extract_bearer_token()
    if not refresh_token:
        _audit_auth_event(
            'logout',
            success=False,
            status_code=400,
            details={'reason': 'missing_refresh_token'},
        )
        return jsonify({'error': 'refresh_token is required'}), 400

    try:
        claims, user_id = _parse_lifecycle_token(refresh_token, 'refresh')
        token_row = _refresh_row_from_claims(claims)
        now = datetime.utcnow()
        if token_row and token_row.user_id == user_id:
            if not token_row.revoked_at:
                token_row.revoked_at = now
            if not token_row.used_at:
                token_row.used_at = now

        _revoke_all_access_tokens_for_user(user_id, reason='logout')

        raw_access_token = _extract_bearer_token()
        if raw_access_token:
            try:
                access_claims = _decode_access_token(raw_access_token)
                token_type = str(access_claims.get('token_type') or '').strip().lower()
                access_user_id = _to_int_or_none(access_claims.get('sub'))
                if token_type == 'access' and access_user_id == user_id:
                    _revoke_access_token_jti(access_claims, reason='logout')
            except jwt.InvalidTokenError:
                pass

        db.session.commit()
        user = db.session.get(User, user_id)
        _audit_auth_event(
            'logout',
            success=True,
            status_code=200,
            email=user.email if user else '',
            user_id=user_id,
        )
        return jsonify({'revoked': True})
    except ValueError as exc:
        db.session.rollback()
        _audit_auth_event(
            'logout',
            success=False,
            status_code=200,
            details={'reason': str(exc)},
        )
        return jsonify({'revoked': False, 'message': str(exc)})
    except Exception:
        db.session.rollback()
        current_app.logger.exception('API logout failed.')
        _audit_auth_event(
            'logout',
            success=False,
            status_code=500,
            details={'reason': 'server_error'},
        )
        return jsonify({'error': 'Failed to revoke session'}), 500



@bp.route('/api/v1/auth/verify/request', methods=['POST'])
def api_auth_verify_request():
    payload = request.get_json(silent=True) or {}
    email = _normalize_email(payload.get('email'))

    rate_limited = _auth_rate_limit_response('verify_request', email=email)
    if rate_limited:
        _audit_auth_event(
            'verify_request',
            success=False,
            status_code=429,
            email=email,
            details={'reason': 'rate_limited'},
        )
        return rate_limited

    if not _is_valid_email(email):
        _audit_auth_event(
            'verify_request',
            success=False,
            status_code=400,
            email=email,
            details={'reason': 'invalid_email'},
        )
        return jsonify({'error': 'A valid email is required'}), 400

    response_payload = {
        'message': 'If an account exists, a verification message has been sent.',
    }
    try:
        user = User.query.filter(func.lower(User.email) == email).first()
        if user and user.is_active and not user.email_verified_at:
            existing_token_row, retry_after = _recent_valid_one_time_token(
                user.id,
                'email_verify',
                _auth_verify_request_cooldown_seconds(),
            )
            if existing_token_row:
                response_payload['verification_email_sent'] = False
                response_payload['retry_after_seconds'] = retry_after
                if _auth_return_tokens_in_response():
                    response_payload['verification_token'] = _encode_lifecycle_token_from_row(
                        user,
                        existing_token_row,
                    )
            else:
                verification_token = _issue_email_verification_token(user)
                verify_url = _verification_url_for_token(verification_token)
                lines = [
                    'Verify your Project Divert account by using this token:',
                    verification_token,
                ]
                if verify_url:
                    lines.extend(['', 'Or open:', verify_url])
                response_payload['verification_email_sent'] = bool(
                    _send_account_email(
                        user.email,
                        'Verify your Project Divert account',
                        '\n'.join(lines),
                    )
                )
                if _auth_return_tokens_in_response():
                    response_payload['verification_token'] = verification_token
                db.session.commit()

            _audit_auth_event(
                'verify_request',
                success=True,
                status_code=200,
                email=email,
                user_id=user.id,
                details={
                    'verification_email_sent': bool(response_payload.get('verification_email_sent')),
                    'retry_after_seconds': _to_int_or_none(response_payload.get('retry_after_seconds')),
                },
            )
        else:
            response_payload['verification_email_sent'] = False
            _audit_auth_event(
                'verify_request',
                success=True,
                status_code=200,
                email=email,
                user_id=user.id if user else None,
                details={'verification_email_sent': False},
            )
    except Exception:
        db.session.rollback()
        current_app.logger.exception('API verify request failed.')
        _audit_auth_event(
            'verify_request',
            success=False,
            status_code=500,
            email=email,
            details={'reason': 'server_error'},
        )
        # Intentionally keep a generic response to avoid account enumeration.
    return jsonify(response_payload)



@bp.route('/api/v1/auth/verify/confirm', methods=['POST'])
def api_auth_verify_confirm():
    rate_limited = _auth_rate_limit_response('verify_confirm')
    if rate_limited:
        _audit_auth_event(
            'verify_confirm',
            success=False,
            status_code=429,
            details={'reason': 'rate_limited'},
        )
        return rate_limited

    payload = request.get_json(silent=True) or {}
    raw_token = payload.get('token')

    try:
        user, _token_row = _consume_one_time_lifecycle_token(raw_token, 'email_verify')
        user.email_verified_at = user.email_verified_at or datetime.utcnow()
        auth_payload = _issue_auth_payload(user)
        db.session.commit()
        auth_payload['email_verified'] = True
        _audit_auth_event(
            'verify_confirm',
            success=True,
            status_code=200,
            email=user.email,
            user_id=user.id,
        )
        return jsonify(auth_payload)
    except ValueError as exc:
        db.session.rollback()
        _audit_auth_event(
            'verify_confirm',
            success=False,
            status_code=400,
            details={'reason': str(exc)},
        )
        return jsonify({'error': str(exc)}), 400
    except Exception:
        db.session.rollback()
        current_app.logger.exception('API verify confirm failed.')
        _audit_auth_event(
            'verify_confirm',
            success=False,
            status_code=500,
            details={'reason': 'server_error'},
        )
        return jsonify({'error': 'Failed to verify email'}), 500



@bp.route('/api/v1/auth/password-reset/request', methods=['POST'])
def api_auth_password_reset_request():
    payload = request.get_json(silent=True) or {}
    email = _normalize_email(payload.get('email'))

    rate_limited = _auth_rate_limit_response('password_reset_request', email=email)
    if rate_limited:
        _audit_auth_event(
            'password_reset_request',
            success=False,
            status_code=429,
            email=email,
            details={'reason': 'rate_limited'},
        )
        return rate_limited

    if not _is_valid_email(email):
        _audit_auth_event(
            'password_reset_request',
            success=False,
            status_code=400,
            email=email,
            details={'reason': 'invalid_email'},
        )
        return jsonify({'error': 'A valid email is required'}), 400

    response_payload = {
        'message': 'If an account exists, a password reset message has been sent.',
    }
    try:
        user = User.query.filter(func.lower(User.email) == email).first()
        if user and user.is_active:
            existing_token_row, retry_after = _recent_valid_one_time_token(
                user.id,
                'password_reset',
                _auth_password_reset_request_cooldown_seconds(),
            )
            if existing_token_row:
                response_payload['reset_email_sent'] = False
                response_payload['retry_after_seconds'] = retry_after
                if _auth_return_tokens_in_response():
                    response_payload['reset_token'] = _encode_lifecycle_token_from_row(
                        user,
                        existing_token_row,
                    )
            else:
                reset_token = _issue_password_reset_token(user)
                reset_url = _password_reset_url_for_token(reset_token)
                lines = [
                    'Reset your Project Divert password with this token:',
                    reset_token,
                ]
                if reset_url:
                    lines.extend(['', 'Or open:', reset_url])
                response_payload['reset_email_sent'] = bool(
                    _send_account_email(
                        user.email,
                        'Reset your Project Divert password',
                        '\n'.join(lines),
                    )
                )
                if _auth_return_tokens_in_response():
                    response_payload['reset_token'] = reset_token
                db.session.commit()

            _audit_auth_event(
                'password_reset_request',
                success=True,
                status_code=200,
                email=email,
                user_id=user.id,
                details={
                    'reset_email_sent': bool(response_payload.get('reset_email_sent')),
                    'retry_after_seconds': _to_int_or_none(response_payload.get('retry_after_seconds')),
                },
            )
        else:
            response_payload['reset_email_sent'] = False
            _audit_auth_event(
                'password_reset_request',
                success=True,
                status_code=200,
                email=email,
                user_id=user.id if user else None,
                details={'reset_email_sent': False},
            )
    except Exception:
        db.session.rollback()
        current_app.logger.exception('API password reset request failed.')
        _audit_auth_event(
            'password_reset_request',
            success=False,
            status_code=500,
            email=email,
            details={'reason': 'server_error'},
        )
        # Intentionally keep a generic response to avoid account enumeration.
    return jsonify(response_payload)



@bp.route('/api/v1/auth/password-reset/confirm', methods=['POST'])
def api_auth_password_reset_confirm():
    rate_limited = _auth_rate_limit_response('password_reset_confirm')
    if rate_limited:
        _audit_auth_event(
            'password_reset_confirm',
            success=False,
            status_code=429,
            details={'reason': 'rate_limited'},
        )
        return rate_limited

    payload = request.get_json(silent=True) or {}
    raw_token = payload.get('token')
    new_password = str(payload.get('new_password') or '')
    password_error = _validate_password_strength(new_password)
    if password_error:
        _audit_auth_event(
            'password_reset_confirm',
            success=False,
            status_code=400,
            details={'reason': 'weak_password'},
        )
        return jsonify({'error': password_error}), 400

    try:
        user, _token_row = _consume_one_time_lifecycle_token(raw_token, 'password_reset')
        user.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
        _revoke_all_refresh_tokens_for_user(user.id)
        _revoke_all_access_tokens_for_user(user.id, reason='password_reset')
        auth_payload = _issue_auth_payload(user)
        db.session.commit()
        auth_payload['password_reset'] = True
        _audit_auth_event(
            'password_reset_confirm',
            success=True,
            status_code=200,
            email=user.email,
            user_id=user.id,
        )
        return jsonify(auth_payload)
    except ValueError as exc:
        db.session.rollback()
        _audit_auth_event(
            'password_reset_confirm',
            success=False,
            status_code=400,
            details={'reason': str(exc)},
        )
        return jsonify({'error': str(exc)}), 400
    except Exception:
        db.session.rollback()
        current_app.logger.exception('API password reset confirm failed.')
        _audit_auth_event(
            'password_reset_confirm',
            success=False,
            status_code=500,
            details={'reason': 'server_error'},
        )
        return jsonify({'error': 'Failed to reset password'}), 500
