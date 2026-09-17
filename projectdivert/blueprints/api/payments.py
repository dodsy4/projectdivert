"""Payments routes."""

import uuid
from flask import Blueprint, current_app, jsonify, request
from projectdivert.extensions import db
from projectdivert.models.payments import WasteDriverPayout, WastePaymentCharge, WastePaymentRefund
from projectdivert.models.waste import WasteRemovalRequest
from projectdivert.services.audit import record_audit_event
from projectdivert.services.auth import _request_access_allowed, jwt_required
from projectdivert.services.billing_core import _billing_summary
from projectdivert.services.compliance import _serialize_driver_payout
from projectdivert.services.dispatch import _serialize_waste_request_snapshot
from projectdivert.services.events import _publish_waste_request_event
from projectdivert.services.notifications import _notify_mobile_push_for_waste_event
from projectdivert.services.payments import _compute_fee_split, _financial_summary_for_request, _payments_enabled, _payout_status_from_stripe, _platform_currency, _platform_fee_bps, _refund_status_from_stripe, _remaining_driver_payout_minor, _remaining_refundable_minor, _serialize_payment_charge, _serialize_payment_refund, _stripe_is_configured, _stripe_request, _stripe_webhook_secret, _sync_charge_from_payment_intent, _verify_stripe_webhook_signature
from projectdivert.services.utils import _current_jwt_user_id, _is_truthy, _to_float_or_none, _to_int_or_none, utcnow

bp = Blueprint('api_payments', __name__)



@bp.route('/api/v1/waste-requests/<int:request_id>/payments', methods=['GET'])
@jwt_required(roles={'customer', 'driver', 'admin'})
def api_get_waste_request_financials(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_access_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403

    return jsonify(
        {
            'request_id': booking.id,
            'request_status': booking.status,
            'payments_enabled': _payments_enabled(),
            'billing': _billing_summary(),
            'financials': _financial_summary_for_request(booking.id),
        }
    )



@bp.route('/api/v1/waste-requests/<int:request_id>/payments/charge', methods=['POST'])
@jwt_required(roles={'customer', 'admin'})
def api_create_payment_charge(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_access_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403
    if not _payments_enabled():
        return jsonify({'error': 'Payments are disabled by feature flag'}), 503
    if not _stripe_is_configured():
        return jsonify({'error': 'Payments are not configured. Set STRIPE_SECRET_KEY.'}), 503

    payload = request.get_json(silent=True) or {}
    amount_minor = _to_int_or_none(payload.get('amount_minor'))
    if amount_minor is None:
        amount_major = _to_float_or_none(payload.get('amount'))
        if amount_major is not None:
            amount_minor = int(round(amount_major * 100))
    if amount_minor is None or amount_minor <= 0:
        return jsonify({'error': 'amount_minor (or amount) must be a positive value'}), 400

    currency = (str(payload.get('currency') or _platform_currency()).strip().lower() or _platform_currency())
    if len(currency) != 3:
        return jsonify({'error': 'currency must be a 3-letter code'}), 400

    platform_fee_bps = _to_int_or_none(payload.get('platform_fee_bps'))
    if platform_fee_bps is None:
        platform_fee_bps = _platform_fee_bps()
    platform_fee_minor, driver_payout_minor = _compute_fee_split(amount_minor, platform_fee_bps)
    customer_user_id = _current_jwt_user_id()

    idempotency_key = str(payload.get('idempotency_key') or '').strip() or uuid.uuid4().hex
    payment_method_id = str(payload.get('payment_method_id') or '').strip() or None
    stripe_customer_id = str(payload.get('stripe_customer_id') or '').strip() or None
    return_url = str(payload.get('return_url') or '').strip() or None
    description = (
        str(payload.get('description') or '').strip()
        or 'Waste removal request #{}'.format(booking.id)
    )[:255]

    charge_row = WastePaymentCharge(
        waste_removal_request_id=booking.id,
        customer_user_id=customer_user_id,
        processor='stripe',
        amount_minor=amount_minor,
        currency=currency,
        platform_fee_minor=platform_fee_minor,
        driver_payout_minor=driver_payout_minor,
        status='initiated',
        metadata_json={
            'platform_fee_bps': platform_fee_bps,
            'request_id': booking.id,
            'assigned_driver_user_id': booking.assigned_driver_user_id,
        },
    )
    db.session.add(charge_row)

    try:
        db.session.flush()
        stripe_payload = {
            'amount': amount_minor,
            'currency': currency,
            'description': description,
            'automatic_payment_methods[enabled]': 'true',
            'metadata[request_id]': booking.id,
            'metadata[payment_charge_id]': charge_row.id,
            'metadata[platform_fee_bps]': platform_fee_bps,
        }
        if customer_user_id:
            stripe_payload['metadata[customer_user_id]'] = customer_user_id
        if booking.assigned_driver_user_id:
            stripe_payload['metadata[driver_user_id]'] = booking.assigned_driver_user_id
        if stripe_customer_id:
            stripe_payload['customer'] = stripe_customer_id
        if payment_method_id:
            stripe_payload['payment_method'] = payment_method_id
            stripe_payload['confirm'] = 'true'
        elif _is_truthy(payload.get('confirm')):
            stripe_payload['confirm'] = 'true'
            if return_url:
                stripe_payload['return_url'] = return_url

        payment_intent_payload = _stripe_request(
            'POST',
            '/v1/payment_intents',
            data=stripe_payload,
            idempotency_key=idempotency_key,
        )
        _sync_charge_from_payment_intent(charge_row, payment_intent_payload)
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to create payment charge for request %s.', booking.id)
        return jsonify({'error': 'Failed to create payment charge'}), 500

    record_audit_event(
        action='payment.charge_create',
        entity_type='payment_charge',
        entity_id=charge_row.id,
        summary='Charge of {} {} for request #{} ({})'.format(
            amount_minor, currency, booking.id, charge_row.status,
        ),
        changes={
            'amount_minor': [None, amount_minor],
            'currency': [None, currency],
            'status': [None, charge_row.status],
            'waste_removal_request_id': [None, booking.id],
        },
        status_code=201,
    )

    if (charge_row.status or '').lower() == 'succeeded':
        _publish_waste_request_event(
            booking.id,
            'payment_succeeded',
            payload=_serialize_waste_request_snapshot(booking),
            metadata={
                'payment_charge_id': charge_row.id,
                'payment_intent_id': charge_row.payment_intent_id,
            },
        )
        _notify_mobile_push_for_waste_event(
            booking,
            'payment_succeeded',
            metadata={
                'payment_charge_id': charge_row.id,
            },
        )

    return jsonify(
        {
            'charge': _serialize_payment_charge(charge_row),
            'financials': _financial_summary_for_request(booking.id),
        }
    ), 201



@bp.route('/api/v1/waste-requests/<int:request_id>/payments/<int:charge_id>/refund', methods=['POST'])
@jwt_required(roles={'customer', 'admin'})
def api_create_payment_refund(request_id, charge_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _request_access_allowed(booking):
        return jsonify({'error': 'Forbidden'}), 403
    if not _payments_enabled():
        return jsonify({'error': 'Payments are disabled by feature flag'}), 503
    if not _stripe_is_configured():
        return jsonify({'error': 'Payments are not configured. Set STRIPE_SECRET_KEY.'}), 503

    charge_row = WastePaymentCharge.query.filter_by(
        id=charge_id,
        waste_removal_request_id=booking.id,
    ).first()
    if not charge_row:
        return jsonify({'error': 'Payment charge not found'}), 404

    if not charge_row.payment_intent_id and not charge_row.charge_id:
        return jsonify({'error': 'Charge is missing processor references and cannot be refunded'}), 409

    payload = request.get_json(silent=True) or {}
    remaining_refundable_minor = _remaining_refundable_minor(charge_row)
    if remaining_refundable_minor <= 0:
        return jsonify({'error': 'Charge is already fully refunded'}), 409

    amount_minor = _to_int_or_none(payload.get('amount_minor'))
    if amount_minor is None:
        amount_minor = remaining_refundable_minor
    if amount_minor <= 0:
        return jsonify({'error': 'amount_minor must be positive'}), 400
    if amount_minor > remaining_refundable_minor:
        return jsonify(
            {
                'error': 'amount_minor exceeds refundable balance',
                'remaining_refundable_minor': remaining_refundable_minor,
            }
        ), 400

    reason_raw = str(payload.get('reason') or '').strip().lower()
    stripe_reason = reason_raw if reason_raw in {'duplicate', 'fraudulent', 'requested_by_customer'} else None
    refund_reason = reason_raw or 'requested_by_customer'
    idempotency_key = str(payload.get('idempotency_key') or '').strip() or uuid.uuid4().hex

    try:
        stripe_payload = {
            'amount': amount_minor,
        }
        if charge_row.payment_intent_id:
            stripe_payload['payment_intent'] = charge_row.payment_intent_id
        elif charge_row.charge_id:
            stripe_payload['charge'] = charge_row.charge_id
        if stripe_reason:
            stripe_payload['reason'] = stripe_reason

        stripe_refund_payload = _stripe_request(
            'POST',
            '/v1/refunds',
            data=stripe_payload,
            idempotency_key=idempotency_key,
        )
        refund_status = _refund_status_from_stripe(stripe_refund_payload.get('status'))
        refund_row = WastePaymentRefund(
            waste_removal_request_id=booking.id,
            payment_charge_id=charge_row.id,
            processor='stripe',
            refund_id=(stripe_refund_payload.get('id') or '').strip() or None,
            amount_minor=_to_int_or_none(stripe_refund_payload.get('amount')) or amount_minor,
            currency=(stripe_refund_payload.get('currency') or charge_row.currency or _platform_currency()).strip().lower(),
            status=refund_status,
            reason=refund_reason[:120],
            processor_response=stripe_refund_payload,
        )
        db.session.add(refund_row)
        db.session.flush()

        remaining_after_refund = _remaining_refundable_minor(charge_row)
        if refund_status == 'succeeded':
            charge_row.refunded_at = utcnow()
            charge_row.status = 'refunded' if remaining_after_refund <= 0 else 'partially_refunded'
            charge_row.last_error = None
        elif refund_status == 'failed':
            charge_row.last_error = 'Refund failed'
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to refund payment charge %s.', charge_row.id)
        return jsonify({'error': 'Failed to create refund'}), 500

    record_audit_event(
        action='payment.refund_create',
        entity_type='payment_refund',
        entity_id=refund_row.id,
        summary='Refund {} on charge #{} for request #{} ({})'.format(
            refund_row.amount_minor, charge_row.id, booking.id, refund_status,
        ),
        changes={
            'amount_minor': [None, refund_row.amount_minor],
            'refund_status': [None, refund_status],
            'charge_status': [None, charge_row.status],
            'payment_charge_id': [None, charge_row.id],
        },
        status_code=201,
    )
    _publish_waste_request_event(
        booking.id,
        'refund_processed',
        payload=_serialize_waste_request_snapshot(booking),
        metadata={
            'payment_charge_id': charge_row.id,
            'refund_id': refund_row.id,
        },
    )
    _notify_mobile_push_for_waste_event(
        booking,
        'refund_processed',
        metadata={
            'payment_charge_id': charge_row.id,
            'refund_id': refund_row.id,
        },
    )

    return jsonify(
        {
            'refund': _serialize_payment_refund(refund_row),
            'charge': _serialize_payment_charge(charge_row),
            'financials': _financial_summary_for_request(booking.id),
        }
    ), 201



@bp.route('/api/v1/waste-requests/<int:request_id>/payouts', methods=['POST'])
@jwt_required(roles={'admin'})
def api_create_driver_payout(request_id):
    booking = db.session.get(WasteRemovalRequest, request_id)
    if not booking:
        return jsonify({'error': 'Waste request not found'}), 404
    if not _payments_enabled():
        return jsonify({'error': 'Payments are disabled by feature flag'}), 503
    if not _stripe_is_configured():
        return jsonify({'error': 'Payments are not configured. Set STRIPE_SECRET_KEY.'}), 503

    payload = request.get_json(silent=True) or {}
    charge_id = _to_int_or_none(payload.get('payment_charge_id'))
    if charge_id is not None:
        charge_row = WastePaymentCharge.query.filter_by(
            id=charge_id,
            waste_removal_request_id=booking.id,
        ).first()
    else:
        charge_row = (
            WastePaymentCharge.query.filter(
                WastePaymentCharge.waste_removal_request_id == booking.id,
                WastePaymentCharge.status.in_(['succeeded', 'partially_refunded']),
            )
            .order_by(WastePaymentCharge.paid_at.desc(), WastePaymentCharge.id.desc())
            .first()
        )
    if not charge_row:
        return jsonify({'error': 'No eligible succeeded charge found for payout'}), 409

    driver_user_id = _to_int_or_none(payload.get('driver_user_id')) or booking.assigned_driver_user_id
    if not driver_user_id:
        return jsonify({'error': 'No assigned driver for payout'}), 409

    destination_account_id = str(payload.get('destination_account_id') or '').strip()
    if not destination_account_id:
        return jsonify({'error': 'destination_account_id is required (Stripe connected account id)'}), 400

    remaining_payout_minor = _remaining_driver_payout_minor(charge_row)
    if remaining_payout_minor <= 0:
        return jsonify({'error': 'No remaining driver payout balance'}), 409

    amount_minor = _to_int_or_none(payload.get('amount_minor'))
    if amount_minor is None:
        amount_minor = remaining_payout_minor
    if amount_minor <= 0:
        return jsonify({'error': 'amount_minor must be positive'}), 400
    if amount_minor > remaining_payout_minor:
        return jsonify(
            {
                'error': 'amount_minor exceeds driver payout balance',
                'remaining_driver_payout_minor': remaining_payout_minor,
            }
        ), 400

    idempotency_key = str(payload.get('idempotency_key') or '').strip() or uuid.uuid4().hex
    description = (
        str(payload.get('description') or '').strip()
        or 'Driver payout for request #{}'.format(booking.id)
    )[:255]

    try:
        stripe_transfer_payload = _stripe_request(
            'POST',
            '/v1/transfers',
            data={
                'amount': amount_minor,
                'currency': (charge_row.currency or _platform_currency()),
                'destination': destination_account_id,
                'description': description,
                'metadata[request_id]': booking.id,
                'metadata[payment_charge_id]': charge_row.id,
                'metadata[driver_user_id]': driver_user_id,
                'transfer_group': 'waste_request_{}'.format(booking.id),
            },
            idempotency_key=idempotency_key,
        )
        payout_status = _payout_status_from_stripe(stripe_transfer_payload)
        payout_row = WasteDriverPayout(
            waste_removal_request_id=booking.id,
            payment_charge_id=charge_row.id,
            driver_user_id=driver_user_id,
            processor='stripe',
            payout_id=(stripe_transfer_payload.get('id') or '').strip() or None,
            destination_account_id=destination_account_id[:120],
            amount_minor=amount_minor,
            currency=(stripe_transfer_payload.get('currency') or charge_row.currency or _platform_currency()).strip().lower(),
            status=payout_status,
            paid_out_at=utcnow() if payout_status == 'paid' else None,
            processor_response=stripe_transfer_payload,
        )
        db.session.add(payout_row)
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed to create driver payout for request %s.', booking.id)
        return jsonify({'error': 'Failed to create driver payout'}), 500

    record_audit_event(
        action='payment.driver_payout',
        entity_type='driver_payout',
        entity_id=payout_row.id,
        summary='Driver payout {} for request #{} ({})'.format(amount_minor, booking.id, payout_status),
        changes={
            'amount_minor': [None, amount_minor],
            'status': [None, payout_status],
            'payment_charge_id': [None, charge_row.id],
            'driver_user_id': [None, booking.assigned_driver_user_id],
        },
        status_code=201,
    )
    _publish_waste_request_event(
        booking.id,
        'payout_processed',
        payload=_serialize_waste_request_snapshot(booking),
        metadata={
            'payment_charge_id': charge_row.id,
            'payout_id': payout_row.id,
        },
    )
    _notify_mobile_push_for_waste_event(
        booking,
        'payout_processed',
        metadata={
            'payment_charge_id': charge_row.id,
            'payout_id': payout_row.id,
        },
    )
    return jsonify(
        {
            'payout': _serialize_driver_payout(payout_row),
            'financials': _financial_summary_for_request(booking.id),
        }
    ), 201



@bp.route('/api/v1/payments/stripe/webhook', methods=['POST'])
def api_stripe_webhook():
    if not _payments_enabled():
        return jsonify({'received': True, 'handled': False, 'disabled': True})

    raw_payload = request.get_data(cache=False, as_text=False) or b''
    signature_header = request.headers.get('Stripe-Signature', '')
    if _stripe_webhook_secret() and not _verify_stripe_webhook_signature(raw_payload, signature_header):
        return jsonify({'error': 'Invalid Stripe signature'}), 400

    event_payload = request.get_json(silent=True) or {}
    if not isinstance(event_payload, dict):
        return jsonify({'error': 'Invalid webhook payload'}), 400

    event_type = str(event_payload.get('type') or '').strip()
    stripe_object = ((event_payload.get('data') or {}).get('object') or {})
    handled = False

    try:
        if event_type.startswith('payment_intent.') and isinstance(stripe_object, dict):
            payment_intent_id = str(stripe_object.get('id') or '').strip()
            if payment_intent_id:
                charge_row = WastePaymentCharge.query.filter_by(payment_intent_id=payment_intent_id).first()
                if not charge_row:
                    metadata = stripe_object.get('metadata') or {}
                    metadata_charge_id = _to_int_or_none(metadata.get('payment_charge_id'))
                    if metadata_charge_id:
                        charge_row = db.session.get(WastePaymentCharge, metadata_charge_id)

                if charge_row:
                    previous_status = charge_row.status
                    _sync_charge_from_payment_intent(charge_row, stripe_object)
                    if event_type == 'payment_intent.payment_failed':
                        charge_row.status = 'failed'
                        payment_error = stripe_object.get('last_payment_error') or {}
                        if isinstance(payment_error, dict):
                            charge_row.last_error = (payment_error.get('message') or 'Payment failed')[:2000]
                        else:
                            charge_row.last_error = 'Payment failed'
                    db.session.commit()
                    handled = True

                    booking = db.session.get(WasteRemovalRequest, charge_row.waste_removal_request_id)
                    if (
                        booking
                        and (charge_row.status or '').lower() == 'succeeded'
                        and (previous_status or '').lower() != 'succeeded'
                    ):
                        _publish_waste_request_event(
                            booking.id,
                            'payment_succeeded',
                            payload=_serialize_waste_request_snapshot(booking),
                            metadata={
                                'payment_charge_id': charge_row.id,
                                'payment_intent_id': charge_row.payment_intent_id,
                                'source': 'stripe_webhook',
                            },
                        )
                        _notify_mobile_push_for_waste_event(
                            booking,
                            'payment_succeeded',
                            metadata={
                                'payment_charge_id': charge_row.id,
                                'source': 'stripe_webhook',
                            },
                        )

        if event_type in {'refund.created', 'refund.updated'} and isinstance(stripe_object, dict):
            payment_intent_id = str(stripe_object.get('payment_intent') or '').strip()
            charge_id = str(stripe_object.get('charge') or '').strip()
            charge_row = None
            if payment_intent_id:
                charge_row = WastePaymentCharge.query.filter_by(payment_intent_id=payment_intent_id).first()
            if not charge_row and charge_id:
                charge_row = WastePaymentCharge.query.filter_by(charge_id=charge_id).first()

            if charge_row:
                stripe_refund_id = str(stripe_object.get('id') or '').strip()
                refund_row = WastePaymentRefund.query.filter_by(refund_id=stripe_refund_id).first()
                if not refund_row:
                    refund_row = WastePaymentRefund(
                        waste_removal_request_id=charge_row.waste_removal_request_id,
                        payment_charge_id=charge_row.id,
                        processor='stripe',
                        refund_id=stripe_refund_id or None,
                        amount_minor=_to_int_or_none(stripe_object.get('amount')) or 0,
                        currency=(stripe_object.get('currency') or charge_row.currency or _platform_currency()).strip().lower(),
                        status=_refund_status_from_stripe(stripe_object.get('status')),
                        reason=(str(stripe_object.get('reason') or '').strip() or None),
                        processor_response=stripe_object,
                    )
                    db.session.add(refund_row)
                else:
                    refund_row.amount_minor = _to_int_or_none(stripe_object.get('amount')) or refund_row.amount_minor
                    refund_row.currency = (stripe_object.get('currency') or refund_row.currency or _platform_currency()).strip().lower()
                    refund_row.status = _refund_status_from_stripe(stripe_object.get('status'))
                    refund_row.reason = (str(stripe_object.get('reason') or '').strip() or refund_row.reason)
                    refund_row.processor_response = stripe_object

                if (refund_row.status or '').lower() != 'failed':
                    remaining_refundable_minor = _remaining_refundable_minor(charge_row)
                    if remaining_refundable_minor <= 0:
                        charge_row.status = 'refunded'
                        charge_row.refunded_at = utcnow()
                    else:
                        charge_row.status = 'partially_refunded'

                db.session.commit()
                handled = True

                booking = db.session.get(WasteRemovalRequest, charge_row.waste_removal_request_id)
                if booking:
                    _publish_waste_request_event(
                        booking.id,
                        'refund_processed',
                        payload=_serialize_waste_request_snapshot(booking),
                        metadata={
                            'payment_charge_id': charge_row.id,
                            'stripe_refund_id': stripe_refund_id,
                            'source': 'stripe_webhook',
                        },
                    )
                    _notify_mobile_push_for_waste_event(
                        booking,
                        'refund_processed',
                        metadata={
                            'payment_charge_id': charge_row.id,
                            'stripe_refund_id': stripe_refund_id,
                            'source': 'stripe_webhook',
                        },
                    )

        if event_type.startswith('transfer.') and isinstance(stripe_object, dict):
            transfer_id = str(stripe_object.get('id') or '').strip()
            if transfer_id:
                payout_row = WasteDriverPayout.query.filter_by(payout_id=transfer_id).first()
                if payout_row:
                    payout_row.status = _payout_status_from_stripe(stripe_object)
                    if event_type == 'transfer.failed':
                        payout_row.status = 'failed'
                    elif event_type in {'transfer.reversed', 'transfer.updated'}:
                        try:
                            amount_reversed = int(stripe_object.get('amount_reversed') or 0)
                        except (TypeError, ValueError):
                            amount_reversed = 0
                        if amount_reversed > 0:
                            payout_row.status = 'reversed'
                    if payout_row.status == 'paid':
                        payout_row.paid_out_at = payout_row.paid_out_at or utcnow()
                    payout_row.processor_response = stripe_object
                    db.session.commit()
                    handled = True

                    booking = db.session.get(WasteRemovalRequest, payout_row.waste_removal_request_id)
                    if booking and payout_row.status == 'paid':
                        _publish_waste_request_event(
                            booking.id,
                            'payout_processed',
                            payload=_serialize_waste_request_snapshot(booking),
                            metadata={
                                'payment_charge_id': payout_row.payment_charge_id,
                                'payout_id': payout_row.id,
                                'source': 'stripe_webhook',
                            },
                        )
                        _notify_mobile_push_for_waste_event(
                            booking,
                            'payout_processed',
                            metadata={
                                'payment_charge_id': payout_row.payment_charge_id,
                                'payout_id': payout_row.id,
                                'source': 'stripe_webhook',
                            },
                        )
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Failed processing Stripe webhook event %s.', event_type)
        return jsonify({'error': 'Webhook processing failed'}), 500

    return jsonify({'received': True, 'handled': handled, 'type': event_type})
