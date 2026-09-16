"""Offline billing workflow, follow-ups and customer communications."""

from datetime import datetime
from flask import current_app
from sqlalchemy import func, or_
from projectdivert.extensions import db
from projectdivert.models.waste import WasteRemovalRequest, WasteRequestCommunicationLog
from projectdivert.services.billing_core import BILLING_FOLLOWUP_STATES, _effective_billing_followup_state, _serialize_request_billing_followup_workflow, _serialize_request_communication_log
from projectdivert.services.dispatch import _serialize_waste_request, _serialize_waste_request_snapshot
from projectdivert.services.events import _publish_waste_request_event
from projectdivert.services.notifications import _notify_mobile_push_for_waste_event
from projectdivert.services.utils import _hours_since


def _offline_billing_followup_limit(value=None):
    if value is None:
        value = current_app.config.get('OFFLINE_BILLING_FOLLOWUP_LIMIT', 200)
    try:
        return max(1, min(5000, int(value)))
    except (TypeError, ValueError):
        return 200


def _offline_billing_followup_after_hours(value=None):
    if value is None:
        value = current_app.config.get('OFFLINE_BILLING_FOLLOWUP_AFTER_HOURS', 72)
    try:
        return max(0, min(24 * 365, int(value)))
    except (TypeError, ValueError):
        return 72


def _offline_billing_followup_repeat_hours(value=None):
    if value is None:
        value = current_app.config.get('OFFLINE_BILLING_FOLLOWUP_REPEAT_HOURS', 72)
    try:
        return max(1, min(24 * 365, int(value)))
    except (TypeError, ValueError):
        return 72


OFFLINE_BILLING_STATES = {
    'pending_offline_invoice',
    'invoice_sent',
    'paid_offline',
    'payout_recorded',
    'cancelled',
}


COMMUNICATION_DIRECTIONS = {'outbound', 'inbound', 'internal'}


COMMUNICATION_CHANNELS = {'email', 'phone', 'sms', 'manual', 'other'}


COMMUNICATION_TEMPLATE_DEFINITIONS = (
    {
        'key': 'invoice_sent',
        'label': 'Invoice Sent',
        'direction': 'outbound',
        'channel': 'email',
        'customer_visible': True,
        'subject_template': 'Invoice for waste collection request #{request_id}',
        'message_template': (
            'Hi {requester_name}, your booking for request #{request_id} has been invoiced offline'
            '{reference_clause}. Please use the invoice details sent separately to arrange payment.'
        ),
        'outcome': 'invoice_sent',
    },
    {
        'key': 'payment_reminder',
        'label': 'Payment Reminder',
        'direction': 'outbound',
        'channel': 'email',
        'customer_visible': True,
        'subject_template': 'Payment reminder for request #{request_id}',
        'message_template': (
            'Hi {requester_name}, this is a reminder that request #{request_id} remains outstanding in'
            ' the offline billing workflow{reference_clause}. Please reply if you need invoice details re-sent.'
        ),
        'outcome': 'payment_reminder_sent',
    },
    {
        'key': 'payout_recorded',
        'label': 'Payout Recorded',
        'direction': 'internal',
        'channel': 'manual',
        'customer_visible': False,
        'subject_template': 'Carrier payout recorded for request #{request_id}',
        'message_template': (
            'Carrier payout has been recorded offline for request #{request_id}{reference_clause}.'
            ' Billing workflow can now be marked complete.'
        ),
        'outcome': 'payout_recorded',
    },
)


def _find_communication_template(key):
    normalized_key = str(key or '').strip().lower()
    if not normalized_key:
        return None
    for template in COMMUNICATION_TEMPLATE_DEFINITIONS:
        if str(template.get('key') or '').strip().lower() == normalized_key:
            return template
    return None


def _normalize_offline_billing_state(value, default=None):
    normalized = str(value or '').strip().lower().replace('-', '_').replace(' ', '_')
    if not normalized:
        return default
    return normalized


def _create_request_communication_log(
    booking,
    *,
    direction,
    channel,
    message,
    subject=None,
    outcome=None,
    contact_name=None,
    contact_email=None,
    contact_phone=None,
    customer_visible=False,
    created_by_user_id=None,
    occurred_at=None,
):
    if not booking:
        raise ValueError('booking is required')
    if str(direction or '').strip().lower() not in COMMUNICATION_DIRECTIONS:
        raise ValueError('direction must be a supported communication direction')
    if str(channel or '').strip().lower() not in COMMUNICATION_CHANNELS:
        raise ValueError('channel must be a supported communication channel')
    normalized_message = str(message or '').strip()
    if not normalized_message:
        raise ValueError('message is required')

    return WasteRequestCommunicationLog(
        waste_removal_request_id=booking.id,
        created_by_user_id=created_by_user_id,
        direction=str(direction).strip().lower(),
        channel=str(channel).strip().lower(),
        subject=(str(subject or '').strip()[:255] or None),
        message=normalized_message[:4000],
        outcome=(str(outcome or '').strip()[:120] or None),
        contact_name=(str(contact_name or '').strip()[:120] or None),
        contact_email=(str(contact_email or '').strip()[:255] or None),
        contact_phone=(str(contact_phone or '').strip()[:120] or None),
        customer_visible=bool(customer_visible),
        occurred_at=occurred_at or datetime.utcnow(),
    )


def _publish_request_communication_log_event(booking, entry, metadata=None):
    if not booking or not entry:
        return
    event_metadata = {
        'communication_log_id': entry.id,
        'direction': entry.direction,
        'channel': entry.channel,
        'customer_visible': bool(entry.customer_visible),
        'created_by_user_id': entry.created_by_user_id,
    }
    if metadata:
        event_metadata.update(metadata)

    _publish_waste_request_event(
        booking.id,
        'admin_communication_logged',
        payload=_serialize_waste_request_snapshot(booking),
        metadata=event_metadata,
    )


def _communication_template_context(booking):
    reference = (booking.billing_reference or '').strip()
    return {
        'request_id': booking.id,
        'requester_name': booking.requester_name or 'Customer',
        'requester_email': booking.requester_email or '',
        'billing_state': (booking.billing_state or '').strip().lower() or 'pending_offline_invoice',
        'billing_reference': reference,
        'reference_clause': f' under reference {reference}' if reference else '',
    }


def _serialize_communication_template(template, booking):
    context = _communication_template_context(booking)
    return {
        'key': template['key'],
        'label': template['label'],
        'direction': template['direction'],
        'channel': template['channel'],
        'customer_visible': bool(template.get('customer_visible')),
        'outcome': template.get('outcome'),
        'subject': (template.get('subject_template') or '').format(**context),
        'message': (template.get('message_template') or '').format(**context),
    }


def _build_admin_billing_followups_query(search=None):
    query = WasteRemovalRequest.query.filter(
        func.coalesce(func.lower(WasteRemovalRequest.billing_state), 'pending_offline_invoice') == 'invoice_sent'
    )
    if search:
        pattern = '%{}%'.format(str(search).strip().lower())
        query = query.filter(
            or_(
                func.lower(func.coalesce(WasteRemovalRequest.requester_name, '')).like(pattern),
                func.lower(func.coalesce(WasteRemovalRequest.requester_email, '')).like(pattern),
                func.lower(func.coalesce(WasteRemovalRequest.pickup_postcode, '')).like(pattern),
                func.lower(func.coalesce(WasteRemovalRequest.billing_reference, '')).like(pattern),
            )
        )
    return query


def _latest_billing_communication(booking, *, outcomes=None, customer_visible=None, directions=None):
    if not booking:
        return None
    query = WasteRequestCommunicationLog.query.filter(
        WasteRequestCommunicationLog.waste_removal_request_id == booking.id
    )
    if outcomes:
        lowered = [str(value).strip().lower() for value in outcomes if str(value).strip()]
        if lowered:
            query = query.filter(func.lower(func.coalesce(WasteRequestCommunicationLog.outcome, '')).in_(lowered))
    if customer_visible is not None:
        query = query.filter(WasteRequestCommunicationLog.customer_visible.is_(bool(customer_visible)))
    if directions:
        lowered = [str(value).strip().lower() for value in directions if str(value).strip()]
        if lowered:
            query = query.filter(func.lower(func.coalesce(WasteRequestCommunicationLog.direction, '')).in_(lowered))
    return (
        query.order_by(
            WasteRequestCommunicationLog.occurred_at.desc(),
            WasteRequestCommunicationLog.id.desc(),
        )
        .first()
    )


def _serialize_billing_followup_item(booking, reminder_after_hours=None, repeat_hours=None, now=None):
    if not booking:
        return None

    now = now or datetime.utcnow()
    reminder_after_hours = _offline_billing_followup_after_hours(reminder_after_hours)
    repeat_hours = _offline_billing_followup_repeat_hours(repeat_hours)
    workflow = _serialize_request_billing_followup_workflow(booking) or {
        'state': _effective_billing_followup_state(booking),
        'notes': None,
        'updated_at': None,
        'updated_by_user_id': None,
        'active': (booking.billing_state or '').strip().lower() == 'invoice_sent',
    }
    workflow_state = str(workflow.get('state') or 'open').strip().lower()
    invoice_anchor = booking.billing_updated_at or booking.created_at
    invoice_age_hours = _hours_since(invoice_anchor, now=now) or 0.0
    last_customer_touch = _latest_billing_communication(
        booking,
        customer_visible=True,
        directions={'outbound', 'inbound'},
    )
    last_reminder = _latest_billing_communication(
        booking,
        outcomes={'payment_reminder_sent'},
    )
    hours_since_last_customer_touch = _hours_since(
        getattr(last_customer_touch, 'occurred_at', None),
        now=now,
    )
    hours_since_last_reminder = _hours_since(
        getattr(last_reminder, 'occurred_at', None),
        now=now,
    )

    due_now = False
    due_reason = None
    suppressed_reason = None
    if workflow_state == 'acknowledged':
        suppressed_reason = 'acknowledged'
    elif workflow_state == 'closed':
        suppressed_reason = 'closed'
    elif invoice_age_hours >= reminder_after_hours:
        if last_reminder is None:
            due_now = True
            due_reason = 'invoice_age_exceeded'
        elif (hours_since_last_reminder or 0.0) >= repeat_hours:
            due_now = True
            due_reason = 'reminder_repeat_due'

    payment_reminder_template = _find_communication_template('payment_reminder')
    return {
        'request': _serialize_waste_request(booking),
        'followup': {
            'workflow': workflow,
            'due_now': due_now,
            'due_reason': due_reason,
            'suppressed_reason': suppressed_reason,
            'reminder_after_hours': reminder_after_hours,
            'repeat_hours': repeat_hours,
            'invoice_age_hours': invoice_age_hours,
            'hours_since_last_customer_touch': hours_since_last_customer_touch,
            'hours_since_last_reminder': hours_since_last_reminder,
            'last_customer_touch': _serialize_request_communication_log(last_customer_touch),
            'last_reminder': _serialize_request_communication_log(last_reminder),
            'recommended_template': (
                _serialize_communication_template(payment_reminder_template, booking)
                if payment_reminder_template
                else None
            ),
        },
    }


def _collect_admin_billing_followups(search=None, reminder_after_hours=None, repeat_hours=None, limit=None, due_only=True, now=None):
    now = now or datetime.utcnow()
    reminder_after_hours = _offline_billing_followup_after_hours(reminder_after_hours)
    repeat_hours = _offline_billing_followup_repeat_hours(repeat_hours)
    limit = _offline_billing_followup_limit(limit)

    query = _build_admin_billing_followups_query(search=search)
    total_candidates = query.count()
    rows = (
        query.order_by(
            func.coalesce(WasteRemovalRequest.billing_updated_at, WasteRemovalRequest.created_at).asc(),
            WasteRemovalRequest.id.asc(),
        )
        .limit(limit)
        .all()
    )

    items = []
    due_count = 0
    oldest_due_hours = 0.0
    oldest_invoice_age_hours = 0.0
    state_counts = {state: 0 for state in sorted(BILLING_FOLLOWUP_STATES)}
    suppressed_count = 0

    for booking in rows:
        item = _serialize_billing_followup_item(
            booking,
            reminder_after_hours=reminder_after_hours,
            repeat_hours=repeat_hours,
            now=now,
        )
        followup = (item or {}).get('followup') or {}
        workflow = (followup.get('workflow') or {})
        workflow_state = str(workflow.get('state') or 'open').strip().lower()
        if workflow_state in state_counts:
            state_counts[workflow_state] += 1
        oldest_invoice_age_hours = max(oldest_invoice_age_hours, float(followup.get('invoice_age_hours') or 0.0))
        if followup.get('due_now'):
            due_count += 1
            oldest_due_hours = max(oldest_due_hours, float(followup.get('invoice_age_hours') or 0.0))
        elif followup.get('suppressed_reason'):
            suppressed_count += 1
        if due_only and not followup.get('due_now'):
            continue
        items.append(item)

    return {
        'items': items,
        'summary': {
            'scanned': len(rows),
            'invoice_sent_candidates': total_candidates,
            'due_now_count': due_count,
            'oldest_due_hours': oldest_due_hours,
            'oldest_invoice_age_hours': oldest_invoice_age_hours,
            'suppressed_count': suppressed_count,
            'state_counts': state_counts,
        },
        'filters': {
            'search': search or '',
            'due_only': bool(due_only),
            'reminder_after_hours': reminder_after_hours,
            'repeat_hours': repeat_hours,
            'limit': limit,
        },
    }


def _run_offline_billing_followup_maintenance(
    *,
    search=None,
    reminder_after_hours=None,
    repeat_hours=None,
    limit=None,
    dry_run=False,
    log_reminders=True,
    actor_user_id=None,
    actor_email=None,
    source='system_offline_billing_followup',
    now=None,
):
    now = now or datetime.utcnow()
    report = _collect_admin_billing_followups(
        search=search,
        reminder_after_hours=reminder_after_hours,
        repeat_hours=repeat_hours,
        limit=limit,
        due_only=True,
        now=now,
    )
    reminder_after_hours = report['filters']['reminder_after_hours']
    repeat_hours = report['filters']['repeat_hours']
    limit = report['filters']['limit']

    reminders_planned = 0
    reminders_logged = 0
    changed_request_ids = []
    publish_jobs = []
    items = []

    for row in report['items']:
        booking = db.session.get(WasteRemovalRequest, row['request']['id'])
        if not booking:
            continue

        followup = row.get('followup') or {}
        planned_actions = []
        applied_actions = []
        if log_reminders and followup.get('due_now'):
            planned_actions.append('log_payment_reminder')
            reminders_planned += 1

        item_summary = {
            'request_id': booking.id,
            'billing_reference': booking.billing_reference,
            'billing_state': (booking.billing_state or '').strip().lower() or 'pending_offline_invoice',
            'followup_state': str((followup.get('workflow') or {}).get('state') or 'open'),
            'invoice_age_hours': followup.get('invoice_age_hours'),
            'hours_since_last_customer_touch': followup.get('hours_since_last_customer_touch'),
            'hours_since_last_reminder': followup.get('hours_since_last_reminder'),
            'due_reason': followup.get('due_reason'),
            'suppressed_reason': followup.get('suppressed_reason'),
            'planned_actions': planned_actions,
            'applied_actions': applied_actions,
        }
        items.append(item_summary)

        if dry_run or not planned_actions:
            continue

        template = _find_communication_template('payment_reminder')
        payload = _serialize_communication_template(template, booking) if template else None
        if not payload:
            continue

        entry = _create_request_communication_log(
            booking,
            direction=payload['direction'],
            channel=payload['channel'],
            subject=payload['subject'],
            message=payload['message'],
            outcome=payload.get('outcome'),
            contact_name=booking.requester_name,
            contact_email=booking.requester_email,
            customer_visible=payload.get('customer_visible'),
            created_by_user_id=actor_user_id,
            occurred_at=now,
        )
        db.session.add(entry)
        db.session.flush()
        publish_jobs.append(
            {
                'request_id': booking.id,
                'entry_id': entry.id,
                'metadata': {
                    'automation': True,
                    'source': source,
                    'admin_user_id': actor_user_id,
                    'actor_email': actor_email,
                },
            }
        )
        applied_actions.append('log_payment_reminder')
        changed_request_ids.append(booking.id)
        reminders_logged += 1

    if not dry_run and changed_request_ids:
        db.session.commit()
        for job in publish_jobs:
            booking = db.session.get(WasteRemovalRequest, job['request_id'])
            entry = db.session.get(WasteRequestCommunicationLog, job['entry_id'])
            if not booking or not entry:
                continue
            _publish_request_communication_log_event(
                booking,
                entry,
                metadata=job['metadata'],
            )
            _notify_mobile_push_for_waste_event(
                booking,
                'admin_communication_logged',
                metadata=job['metadata'],
            )

    return {
        'executed_at': now.isoformat() + 'Z',
        'dry_run': bool(dry_run),
        'options': {
            'search': search or '',
            'reminder_after_hours': reminder_after_hours,
            'repeat_hours': repeat_hours,
            'limit': limit,
            'log_reminders': bool(log_reminders),
        },
        'summary': {
            'scanned': report['summary']['scanned'],
            'invoice_sent_candidates': report['summary']['invoice_sent_candidates'],
            'due_now_count': report['summary']['due_now_count'],
            'reminders_planned': reminders_planned,
            'reminders_logged': reminders_logged if not dry_run else 0,
            'changed_request_count': len(set(changed_request_ids)) if not dry_run else 0,
            'oldest_due_hours': report['summary']['oldest_due_hours'],
        },
        'items': items,
    }


def _build_admin_communications_query(
    state=None,
    direction=None,
    channel=None,
    customer_visible=None,
    search=None,
):
    query = (
        WasteRequestCommunicationLog.query
        .join(
            WasteRemovalRequest,
            WasteRemovalRequest.id == WasteRequestCommunicationLog.waste_removal_request_id,
        )
    )
    if state and state != 'all':
        query = query.filter(
            func.coalesce(func.lower(WasteRemovalRequest.billing_state), 'pending_offline_invoice') == state
        )
    if direction and direction != 'all':
        query = query.filter(func.lower(WasteRequestCommunicationLog.direction) == direction)
    if channel and channel != 'all':
        query = query.filter(func.lower(WasteRequestCommunicationLog.channel) == channel)
    if customer_visible is True:
        query = query.filter(WasteRequestCommunicationLog.customer_visible.is_(True))
    elif customer_visible is False:
        query = query.filter(WasteRequestCommunicationLog.customer_visible.is_(False))
    if search:
        pattern = '%{}%'.format(search.lower())
        query = query.filter(
            or_(
                func.lower(func.coalesce(WasteRequestCommunicationLog.subject, '')).like(pattern),
                func.lower(func.coalesce(WasteRequestCommunicationLog.message, '')).like(pattern),
                func.lower(func.coalesce(WasteRemovalRequest.requester_email, '')).like(pattern),
                func.lower(func.coalesce(WasteRemovalRequest.billing_reference, '')).like(pattern),
            )
        )
    return query


def _build_admin_billing_requests_query(state=None, request_status=None, reference=None, search=None):
    query = WasteRemovalRequest.query
    if state and state != 'all':
        query = query.filter(
            func.coalesce(func.lower(WasteRemovalRequest.billing_state), 'pending_offline_invoice') == state
        )
    if request_status and request_status != 'all':
        query = query.filter(func.lower(WasteRemovalRequest.status) == request_status)
    if reference:
        pattern = '%{}%'.format(reference.lower())
        query = query.filter(func.lower(func.coalesce(WasteRemovalRequest.billing_reference, '')).like(pattern))
    if search:
        pattern = '%{}%'.format(search.lower())
        query = query.filter(
            or_(
                func.lower(func.coalesce(WasteRemovalRequest.billing_reference, '')).like(pattern),
                func.lower(func.coalesce(WasteRemovalRequest.requester_email, '')).like(pattern),
                func.lower(func.coalesce(WasteRemovalRequest.requester_name, '')).like(pattern),
                func.lower(func.coalesce(WasteRemovalRequest.pickup_postcode, '')).like(pattern),
            )
        )
    return query
