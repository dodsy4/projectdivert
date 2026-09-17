"""Stripe charges, refunds and driver payouts."""

import hmac
import hashlib
import requests
from flask import current_app
from sqlalchemy import func
from projectdivert.extensions import db
from projectdivert.models.payments import WasteDriverPayout, WastePaymentCharge, WastePaymentRefund
from projectdivert.services.compliance import _serialize_driver_payout
from projectdivert.services.utils import _is_truthy, utcnow


def _serialize_payment_charge(charge):
    if not charge:
        return None
    return {
        'id': charge.id,
        'waste_removal_request_id': charge.waste_removal_request_id,
        'customer_user_id': charge.customer_user_id,
        'processor': charge.processor,
        'payment_intent_id': charge.payment_intent_id,
        'charge_id': charge.charge_id,
        'amount_minor': charge.amount_minor,
        'currency': charge.currency,
        'platform_fee_minor': charge.platform_fee_minor,
        'driver_payout_minor': charge.driver_payout_minor,
        'status': charge.status,
        'client_secret': charge.client_secret,
        'last_error': charge.last_error,
        'paid_at': charge.paid_at.isoformat() if charge.paid_at else None,
        'refunded_at': charge.refunded_at.isoformat() if charge.refunded_at else None,
        'metadata': charge.metadata_json or {},
        'created_at': charge.created_at.isoformat() if charge.created_at else None,
        'updated_at': charge.updated_at.isoformat() if charge.updated_at else None,
    }


def _serialize_payment_refund(refund):
    if not refund:
        return None
    return {
        'id': refund.id,
        'waste_removal_request_id': refund.waste_removal_request_id,
        'payment_charge_id': refund.payment_charge_id,
        'processor': refund.processor,
        'refund_id': refund.refund_id,
        'amount_minor': refund.amount_minor,
        'currency': refund.currency,
        'status': refund.status,
        'reason': refund.reason,
        'created_at': refund.created_at.isoformat() if refund.created_at else None,
        'updated_at': refund.updated_at.isoformat() if refund.updated_at else None,
    }


def _financial_summary_for_request(request_id):
    charges = (
        WastePaymentCharge.query.filter_by(waste_removal_request_id=request_id)
        .order_by(WastePaymentCharge.created_at.desc(), WastePaymentCharge.id.desc())
        .all()
    )
    refunds = (
        WastePaymentRefund.query.filter_by(waste_removal_request_id=request_id)
        .order_by(WastePaymentRefund.created_at.desc(), WastePaymentRefund.id.desc())
        .all()
    )
    payouts = (
        WasteDriverPayout.query.filter_by(waste_removal_request_id=request_id)
        .order_by(WasteDriverPayout.created_at.desc(), WasteDriverPayout.id.desc())
        .all()
    )
    total_charged_minor = sum(
        charge.amount_minor
        for charge in charges
        if (charge.status or '').lower() in {'succeeded', 'requires_capture', 'partially_refunded', 'refunded'}
    )
    total_refunded_minor = sum(refund.amount_minor for refund in refunds if (refund.status or '').lower() != 'failed')
    total_payout_minor = sum(payout.amount_minor for payout in payouts if (payout.status or '').lower() in {'paid', 'completed'})
    return {
        'charges': [_serialize_payment_charge(charge) for charge in charges],
        'refunds': [_serialize_payment_refund(refund) for refund in refunds],
        'payouts': [_serialize_driver_payout(payout) for payout in payouts],
        'totals': {
            'charged_minor': total_charged_minor,
            'refunded_minor': total_refunded_minor,
            'paid_out_minor': total_payout_minor,
            'platform_net_minor': total_charged_minor - total_refunded_minor - total_payout_minor,
        },
    }


def _platform_fee_bps():
    raw = current_app.config.get('PLATFORM_FEE_BPS', 1500)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 1500
    return max(0, min(9500, value))


def _platform_currency():
    return (current_app.config.get('PLATFORM_CURRENCY') or 'gbp').strip().lower() or 'gbp'


def _payments_enabled():
    return _is_truthy(current_app.config.get('PAYMENTS_ENABLED', False))


def _compute_fee_split(amount_minor, platform_fee_bps=None):
    fee_bps = _platform_fee_bps() if platform_fee_bps is None else int(platform_fee_bps)
    fee_bps = max(0, min(9500, fee_bps))
    platform_fee_minor = int(round((amount_minor * fee_bps) / 10000.0))
    driver_payout_minor = max(0, amount_minor - platform_fee_minor)
    return platform_fee_minor, driver_payout_minor


def _stripe_secret_key():
    return (current_app.config.get('STRIPE_SECRET_KEY') or '').strip()


def _stripe_webhook_secret():
    return (current_app.config.get('STRIPE_WEBHOOK_SECRET') or '').strip()


def _stripe_api_base():
    return (current_app.config.get('STRIPE_API_BASE_URL') or 'https://api.stripe.com').strip().rstrip('/')


def _stripe_is_configured():
    return bool(_stripe_secret_key())


def _stripe_request(method, path, data=None, idempotency_key=None):
    secret_key = _stripe_secret_key()
    if not secret_key:
        raise ValueError('Stripe is not configured. Set STRIPE_SECRET_KEY.')

    url = '{}{}'.format(_stripe_api_base(), path)
    headers = {
        'Authorization': 'Bearer {}'.format(secret_key),
        'Accept': 'application/json',
    }
    if idempotency_key:
        headers['Idempotency-Key'] = str(idempotency_key).strip()

    request_data = {}
    for key, value in (data or {}).items():
        if value is None:
            continue
        request_data[key] = str(value)

    try:
        response = requests.request(
            method.upper(),
            url,
            data=request_data,
            headers=headers,
            timeout=20,
        )
    except Exception as exc:
        raise ValueError('Stripe request failed: {}'.format(exc))

    try:
        payload = response.json()
    except Exception:
        payload = {'raw': response.text}

    if response.status_code >= 400:
        error_info = payload.get('error') if isinstance(payload, dict) else None
        if isinstance(error_info, dict):
            message = error_info.get('message') or 'Stripe request failed'
        else:
            message = 'Stripe request failed'
        raise ValueError('{} (HTTP {})'.format(message, response.status_code))

    if not isinstance(payload, dict):
        raise ValueError('Stripe response was invalid.')
    return payload


def _payment_status_from_stripe_intent(intent_status):
    status = (intent_status or '').strip().lower()
    if status == 'succeeded':
        return 'succeeded'
    if status in {'requires_payment_method', 'requires_confirmation', 'requires_action'}:
        return 'requires_payment_method'
    if status in {'requires_capture'}:
        return 'requires_capture'
    if status in {'processing'}:
        return 'processing'
    if status in {'canceled'}:
        return 'cancelled'
    return status or 'pending'


def _stripe_charge_id_from_payment_intent(payment_intent_payload):
    if not isinstance(payment_intent_payload, dict):
        return None
    latest_charge = payment_intent_payload.get('latest_charge')
    if isinstance(latest_charge, str):
        return latest_charge.strip() or None
    charges = ((payment_intent_payload.get('charges') or {}).get('data') or [])
    if charges and isinstance(charges[0], dict):
        return (charges[0].get('id') or '').strip() or None
    return None


def _sync_charge_from_payment_intent(charge_row, payment_intent_payload):
    mapped_status = _payment_status_from_stripe_intent(payment_intent_payload.get('status'))
    charge_row.status = mapped_status
    charge_row.payment_intent_id = (payment_intent_payload.get('id') or '').strip() or charge_row.payment_intent_id
    charge_row.client_secret = (payment_intent_payload.get('client_secret') or '').strip() or charge_row.client_secret
    charge_row.charge_id = _stripe_charge_id_from_payment_intent(payment_intent_payload)
    charge_row.processor_response = payment_intent_payload
    if mapped_status == 'succeeded':
        charge_row.paid_at = utcnow()
        charge_row.last_error = None
    return charge_row


def _parse_stripe_signature_header(signature_header):
    parts = {}
    for raw_part in str(signature_header or '').split(','):
        segment = raw_part.strip()
        if '=' not in segment:
            continue
        key, value = segment.split('=', 1)
        parts.setdefault(key.strip(), []).append(value.strip())
    return parts


def _verify_stripe_webhook_signature(payload_raw, signature_header):
    webhook_secret = _stripe_webhook_secret()
    if not webhook_secret:
        return False
    parsed = _parse_stripe_signature_header(signature_header)
    timestamp = (parsed.get('t') or [None])[0]
    v1_signatures = parsed.get('v1') or []
    if not timestamp or not v1_signatures:
        return False

    signed_payload = '{}.{}'.format(timestamp, payload_raw.decode('utf-8'))
    expected = hmac.new(
        webhook_secret.encode('utf-8'),
        signed_payload.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    for candidate in v1_signatures:
        if hmac.compare_digest(expected, candidate):
            return True
    return False


def _refund_status_from_stripe(refund_status):
    status = (refund_status or '').strip().lower()
    if status in {'succeeded'}:
        return 'succeeded'
    if status in {'pending', 'requires_action'}:
        return 'pending'
    if status in {'failed', 'canceled'}:
        return 'failed'
    return status or 'pending'


def _payout_status_from_stripe(payload):
    if not isinstance(payload, dict):
        return 'unknown'

    status = (payload.get('status') or '').strip().lower()
    if status in {'paid', 'completed'}:
        return 'paid'
    if status in {'pending', 'in_transit'}:
        return 'processing'
    if status in {'failed', 'canceled'}:
        return 'failed'

    try:
        amount_reversed = int(payload.get('amount_reversed') or 0)
    except (TypeError, ValueError):
        amount_reversed = 0
    if amount_reversed > 0:
        return 'reversed'

    # Stripe transfer objects often have no status field; success means accepted.
    return 'paid'


def _remaining_refundable_minor(charge_row):
    if not charge_row:
        return 0
    refunded_minor = (
        db.session.query(func.coalesce(func.sum(WastePaymentRefund.amount_minor), 0))
        .filter(
            WastePaymentRefund.payment_charge_id == charge_row.id,
            WastePaymentRefund.status.notin_(['failed']),
        )
        .scalar()
    ) or 0
    return max(0, int(charge_row.amount_minor or 0) - int(refunded_minor))


def _remaining_driver_payout_minor(charge_row):
    if not charge_row:
        return 0
    paid_out_minor = (
        db.session.query(func.coalesce(func.sum(WasteDriverPayout.amount_minor), 0))
        .filter(
            WasteDriverPayout.payment_charge_id == charge_row.id,
            WasteDriverPayout.status.notin_(['failed', 'cancelled', 'reversed']),
        )
        .scalar()
    ) or 0
    return max(0, int(charge_row.driver_payout_minor or 0) - int(paid_out_minor))
