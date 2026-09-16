"""Billing state and communication serialisation shared with dispatch."""

from projectdivert.models.waste import WasteRequestCommunicationLog
from projectdivert.services.payments import _payments_enabled, _stripe_is_configured


BILLING_FOLLOWUP_STATES = {'open', 'acknowledged', 'closed'}


def _normalize_billing_followup_state(value, default=None):
    normalized = str(value or '').strip().lower().replace('-', '_').replace(' ', '_')
    if not normalized:
        return default
    return normalized


def _effective_billing_followup_state(booking, default='open'):
    if not booking:
        return default
    normalized = _normalize_billing_followup_state(getattr(booking, 'billing_followup_state', None))
    if normalized in BILLING_FOLLOWUP_STATES:
        return normalized
    billing_state = (booking.billing_state or '').strip().lower() or 'pending_offline_invoice'
    if billing_state != 'invoice_sent':
        return 'closed'
    return default


def _serialize_request_billing_followup_workflow(booking):
    if not booking:
        return None

    billing_state = (booking.billing_state or '').strip().lower() or 'pending_offline_invoice'
    has_explicit_tracking = any(
        [
            getattr(booking, 'billing_followup_state', None),
            getattr(booking, 'billing_followup_notes', None),
            getattr(booking, 'billing_followup_updated_at', None),
            getattr(booking, 'billing_followup_updated_by_user_id', None),
        ]
    )
    if billing_state != 'invoice_sent' and not has_explicit_tracking:
        return None

    return {
        'state': _effective_billing_followup_state(booking),
        'notes': booking.billing_followup_notes,
        'updated_at': (
            booking.billing_followup_updated_at.isoformat()
            if booking.billing_followup_updated_at
            else None
        ),
        'updated_by_user_id': booking.billing_followup_updated_by_user_id,
        'active': billing_state == 'invoice_sent',
    }


def _serialize_request_communication_log(entry):
    if not entry:
        return None
    return {
        'id': entry.id,
        'waste_removal_request_id': entry.waste_removal_request_id,
        'created_by_user_id': entry.created_by_user_id,
        'direction': entry.direction,
        'channel': entry.channel,
        'subject': entry.subject,
        'message': entry.message,
        'outcome': entry.outcome,
        'contact_name': entry.contact_name,
        'contact_email': entry.contact_email,
        'contact_phone': entry.contact_phone,
        'customer_visible': bool(entry.customer_visible),
        'occurred_at': entry.occurred_at.isoformat() if entry.occurred_at else None,
        'created_at': entry.created_at.isoformat() if entry.created_at else None,
    }


def _communication_logs_for_request(request_id, customer_visible_only=False, limit=50):
    query = WasteRequestCommunicationLog.query.filter(
        WasteRequestCommunicationLog.waste_removal_request_id == request_id
    )
    if customer_visible_only:
        query = query.filter(WasteRequestCommunicationLog.customer_visible.is_(True))
    return (
        query.order_by(
            WasteRequestCommunicationLog.occurred_at.desc(),
            WasteRequestCommunicationLog.id.desc(),
        )
        .limit(limit)
        .all()
    )


def _serialize_request_communication_summary(entries):
    direction_counts = {}
    channel_counts = {}
    customer_visible_count = 0
    for entry in entries:
        direction = (entry.direction or '').strip().lower() or 'unknown'
        channel = (entry.channel or '').strip().lower() or 'unknown'
        direction_counts[direction] = direction_counts.get(direction, 0) + 1
        channel_counts[channel] = channel_counts.get(channel, 0) + 1
        if entry.customer_visible:
            customer_visible_count += 1
    return {
        'total': len(entries),
        'customer_visible_count': customer_visible_count,
        'direction_counts': direction_counts,
        'channel_counts': channel_counts,
    }


def _billing_summary():
    payments_enabled = _payments_enabled()
    stripe_configured = _stripe_is_configured()

    if payments_enabled and stripe_configured:
        return {
            'mode': 'in_app',
            'payments_enabled': True,
            'stripe_configured': True,
            'launch_scope': 'in_app_payments',
            'offline_reason': None,
            'customer_message': 'Pay securely in app once your waste collection is confirmed.',
            'admin_message': 'Charges, refunds, and driver payouts are active in-app.',
            'actions_disabled': [],
        }

    offline_reason = 'feature_flag_disabled'
    if payments_enabled and not stripe_configured:
        offline_reason = 'processor_not_configured'

    return {
        'mode': 'offline',
        'payments_enabled': payments_enabled,
        'stripe_configured': stripe_configured,
        'launch_scope': 'offline_billing',
        'offline_reason': offline_reason,
        'customer_message': 'Billing is arranged offline after booking confirmation.',
        'admin_message': 'In-app payments are disabled; billing, refunds, and payouts are handled offline.',
        'actions_disabled': ['charge', 'refund', 'payout'],
    }
