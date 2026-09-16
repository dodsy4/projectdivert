"""Admin ops routes."""

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import SQLAlchemyError
from projectdivert.services.auth import jwt_required
from projectdivert.services.ops import _collect_ops_health_snapshot
from projectdivert.services.utils import _parse_optional_int_query

bp = Blueprint('api_admin_ops', __name__)



@bp.route('/api/v1/admin/ops/health', methods=['GET'])
@jwt_required(roles={'admin'})
def api_admin_ops_health():
    try:
        auth_window_minutes = _parse_optional_int_query(
            request.args.get('auth_window_minutes'),
            'auth_window_minutes',
            min_value=5,
            max_value=10080,
        )
        dispatch_limit = _parse_optional_int_query(
            request.args.get('dispatch_limit'),
            'dispatch_limit',
            min_value=1,
            max_value=5000,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    try:
        snapshot = _collect_ops_health_snapshot(
            auth_window_minutes=auth_window_minutes,
            dispatch_limit=dispatch_limit,
        )
    except SQLAlchemyError:
        current_app.logger.exception('Failed to collect ops health snapshot.')
        return jsonify({'error': 'Failed to collect ops health'}), 500

    return jsonify(snapshot)
