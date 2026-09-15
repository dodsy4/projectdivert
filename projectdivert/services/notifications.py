"""Outbound email and Expo push notifications."""

import json
import requests
from flask import current_app
from sqlalchemy import func
from projectdivert.models.mobile import MobilePushSubscription
from projectdivert.models.user import User
from projectdivert.services.utils import _is_truthy
import logging

logger = logging.getLogger(__name__)


def _send_account_email(to_email, subject, text_body):
    return _send_material_request_email(to_email, subject, text_body)


def _notify_dispatch_offers(booking, offer_rows, base_url):
    success_count = 0
    for offer in offer_rows:
        to_email = (offer.provider_email or '').strip()
        if not to_email:
            continue

        subject = 'New waste collection job offer #{}'.format(booking.id)
        text_body = (
            'A new waste collection job is available.\n\n'
            'Request ID: {request_id}\n'
            'Material: {material}\n'
            'Waste Amount: {amount} {unit}\n'
            'Pickup Postcode: {postcode}\n'
            'Scheduled Pickup: {scheduled_pickup}\n'
            'Distance to pickup: {distance} miles\n'
            'Offer rank: {rank}\n\n'
            'To accept this job, POST to:\n'
            '{base_url}/api/v1/waste-requests/{request_id}/dispatch/accept\n'
            'with Authorization header:\n'
            'Bearer <driver access token>\n'
            'with JSON body:\n'
            '{{"offer_token":"{offer_token}"}}\n'
        ).format(
            request_id=booking.id,
            material=booking.material_type,
            amount=booking.waste_amount,
            unit=booking.waste_unit,
            postcode=booking.pickup_postcode,
            scheduled_pickup=booking.scheduled_pickup_at.strftime('%Y-%m-%d %H:%M'),
            distance=offer.distance_miles,
            rank=offer.offer_rank,
            base_url=base_url.rstrip('/'),
            offer_token=offer.offer_token,
        )
        if _send_material_request_email(to_email, subject, text_body):
            success_count += 1
    return success_count


def _expo_push_is_enabled():
    return _is_truthy(current_app.config.get('EXPO_PUSH_ENABLED', True))


def _requester_user_id_for_booking(booking):
    if not booking:
        return None
    email = (booking.requester_email or '').strip().lower()
    if not email:
        return None
    user = User.query.filter(func.lower(User.email) == email).first()
    return user.id if user else None


def _active_push_tokens_for_users(user_ids):
    if not user_ids:
        return []
    rows = (
        MobilePushSubscription.query.filter(
            MobilePushSubscription.user_id.in_(list(user_ids)),
            MobilePushSubscription.is_active.is_(True),
            MobilePushSubscription.provider == 'expo',
        )
        .order_by(MobilePushSubscription.updated_at.desc(), MobilePushSubscription.id.desc())
        .all()
    )
    tokens = []
    seen = set()
    for row in rows:
        token = (row.token or '').strip()
        if not token or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _send_expo_push_messages(messages):
    if not messages or not _expo_push_is_enabled():
        return 0

    endpoint = (
        current_app.config.get('EXPO_PUSH_API_URL')
        or 'https://exp.host/--/api/v2/push/send'
    )
    access_token = (current_app.config.get('EXPO_PUSH_ACCESS_TOKEN') or '').strip()
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }
    if access_token:
        headers['Authorization'] = 'Bearer {}'.format(access_token)

    delivered = 0
    chunk_size = 100
    for start in range(0, len(messages), chunk_size):
        chunk = messages[start:start + chunk_size]
        try:
            response = requests.post(endpoint, json=chunk, headers=headers, timeout=8)
            if response.status_code >= 400:
                logger.warning(
                    'Expo push request failed status=%s body=%s',
                    response.status_code,
                    response.text[:400],
                )
                continue
            delivered += len(chunk)
        except Exception:
            logger.exception('Expo push delivery failed.')
    return delivered


def _send_push_notification_to_users(user_ids, title, body, data=None):
    tokens = _active_push_tokens_for_users(user_ids)
    if not tokens:
        return 0
    messages = []
    for token in tokens:
        messages.append(
            {
                'to': token,
                'title': title,
                'body': body,
                'sound': 'default',
                'priority': 'high',
                'data': data or {},
            }
        )
    return _send_expo_push_messages(messages)


def _notify_mobile_push_for_waste_event(booking, event_name, metadata=None):
    if not booking:
        return 0

    requester_user_id = _requester_user_id_for_booking(booking)
    recipients = set()
    if requester_user_id:
        recipients.add(requester_user_id)
    if booking.assigned_driver_user_id:
        recipients.add(booking.assigned_driver_user_id)
    if not recipients:
        return 0

    metadata = metadata or {}
    status = (booking.status or '').strip().lower() or 'unknown'
    if event_name == 'request_created':
        title = 'Request submitted'
        body = 'Request #{} is now live.'.format(booking.id)
    elif event_name == 'dispatch_offer_accepted':
        title = 'Driver matched'
        body = 'Request #{} has been matched.'.format(booking.id)
    elif event_name == 'status_updated':
        title = 'Status update'
        body = 'Request #{} is now {}.'.format(
            booking.id,
            status.replace('_', ' '),
        )
    elif event_name == 'payment_succeeded':
        title = 'Payment received'
        body = 'Payment succeeded for request #{}.'.format(booking.id)
    elif event_name == 'refund_processed':
        title = 'Refund processed'
        body = 'Refund issued for request #{}.'.format(booking.id)
    elif event_name == 'payout_processed':
        title = 'Driver payout sent'
        body = 'Driver payout was processed for request #{}.'.format(booking.id)
    elif event_name == 'admin_dispatch_override':
        title = 'Dispatch assignment updated'
        if booking.assigned_driver_user_id:
            body = 'Driver assignment updated for request #{}.'.format(booking.id)
        else:
            body = 'Driver assignment removed for request #{}.'.format(booking.id)
    else:
        return 0

    return _send_push_notification_to_users(
        recipients,
        title,
        body,
        data={
            'event': event_name,
            'request_id': booking.id,
            'status': status,
            'metadata': metadata,
        },
    )


def _send_material_request_email(to_email, subject, text_body, html_body=None):
    provider = (current_app.config.get('MAIL_PROVIDER') or 'console').strip().lower()

    if provider == 'console':
        logger.info('MAIL(console) to=%s subject=%s body=%s', to_email, subject, text_body)
        return True

    if provider == 'sendgrid':
        api_key = current_app.config.get('SENDGRID_API_KEY', '')
        from_email = current_app.config.get('MAIL_FROM_EMAIL', 'noreply@example.com')
        if not api_key:
            logger.error('SENDGRID_API_KEY missing; email not sent.')
            return False

        payload = {
            'personalizations': [{'to': [{'email': to_email}], 'subject': subject}],
            'from': {'email': from_email},
            'content': [{'type': 'text/plain', 'value': text_body}],
        }
        if html_body:
            payload['content'].append({'type': 'text/html', 'value': html_body})

        try:
            response = requests.post(
                'https://api.sendgrid.com/v3/mail/send',
                headers={
                    'Authorization': 'Bearer {}'.format(api_key),
                    'Content-Type': 'application/json',
                },
                data=json.dumps(payload),
                timeout=15,
            )
            if 200 <= response.status_code < 300:
                return True
            logger.error('SendGrid email failed status=%s body=%s', response.status_code, response.text[:500])
            return False
        except Exception:
            logger.exception('SendGrid email request failed.')
            return False

    logger.error('Unknown MAIL_PROVIDER=%s', provider)
    return False


def _serialize_push_subscription(subscription):
    if not subscription:
        return None
    return {
        'id': subscription.id,
        'user_id': subscription.user_id,
        'provider': subscription.provider,
        'platform': subscription.platform,
        'token': subscription.token,
        'is_active': subscription.is_active,
        'last_seen_at': subscription.last_seen_at.isoformat() if subscription.last_seen_at else None,
        'created_at': subscription.created_at.isoformat() if subscription.created_at else None,
        'updated_at': subscription.updated_at.isoformat() if subscription.updated_at else None,
    }
