"""Push routes."""

from datetime import datetime
from flask import Blueprint, jsonify, request
from projectdivert.extensions import db
from projectdivert.models.mobile import MobilePushSubscription
from projectdivert.services.auth import jwt_required
from projectdivert.services.notifications import _serialize_push_subscription
from projectdivert.services.utils import _current_jwt_user_id

bp = Blueprint('api_push', __name__)



@bp.route('/api/v1/push-subscriptions', methods=['POST'])
@jwt_required(roles={'customer', 'driver', 'admin'})
def api_upsert_push_subscription():
    payload = request.get_json(silent=True) or {}
    token = str(payload.get('token') or '').strip()
    if not token:
        return jsonify({'error': 'token is required'}), 400
    if len(token) > 255:
        return jsonify({'error': 'token is too long'}), 400

    user_id = _current_jwt_user_id()
    if user_id is None:
        return jsonify({'error': 'Token missing valid user id claim'}), 401

    provider = (str(payload.get('provider') or 'expo').strip().lower() or 'expo')[:32]
    platform = (str(payload.get('platform') or '').strip().lower() or None)
    if platform:
        platform = platform[:32]

    subscription = MobilePushSubscription.query.filter_by(token=token).first()
    if not subscription:
        subscription = MobilePushSubscription(
            user_id=user_id,
            provider=provider,
            token=token,
            platform=platform,
            is_active=True,
            last_seen_at=datetime.utcnow(),
        )
        db.session.add(subscription)
    else:
        subscription.user_id = user_id
        subscription.provider = provider
        subscription.platform = platform
        subscription.is_active = True
        subscription.last_seen_at = datetime.utcnow()

    db.session.commit()
    return jsonify({'subscription': _serialize_push_subscription(subscription)})



@bp.route('/api/v1/push-subscriptions', methods=['DELETE'])
@jwt_required(roles={'customer', 'driver', 'admin'})
def api_deactivate_push_subscription():
    payload = request.get_json(silent=True) or {}
    token = str(payload.get('token') or '').strip()
    if not token:
        return jsonify({'error': 'token is required'}), 400

    user_id = _current_jwt_user_id()
    if user_id is None:
        return jsonify({'error': 'Token missing valid user id claim'}), 401

    subscription = MobilePushSubscription.query.filter_by(
        token=token,
        user_id=user_id,
    ).first()
    if not subscription:
        return jsonify({'deactivated': False}), 200

    subscription.is_active = False
    subscription.last_seen_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'deactivated': True})
