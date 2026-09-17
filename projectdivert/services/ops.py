"""Operational health snapshots and digests."""

import logging
from datetime import timedelta
import requests
from flask import current_app
from projectdivert.models.audit import AuthAuditEvent
from projectdivert.models.waste import WasteRemovalRequest, WasteRemovalVehicleLocation
from projectdivert.services.billing import _collect_admin_billing_followups, _offline_billing_followup_limit
from projectdivert.services.dispatch import _serialize_dispatch_queue_item
from projectdivert.services.notifications import _send_account_email
from projectdivert.services.utils import _is_truthy, utcnow

logger = logging.getLogger(__name__)


def _ops_health_auth_window_minutes(value=None):
    if value is None:
        value = current_app.config.get('OPS_HEALTH_AUTH_WINDOW_MINUTES', 60)
    try:
        return max(5, min(10080, int(value)))
    except (TypeError, ValueError):
        return 60


def _ops_health_dispatch_limit(value=None):
    if value is None:
        value = current_app.config.get('OPS_HEALTH_DISPATCH_LIMIT', 500)
    try:
        return max(1, min(5000, int(value)))
    except (TypeError, ValueError):
        return 500


def _ops_health_thresholds():
    def _int_threshold(key, default, min_value=0, max_value=100000):
        value = current_app.config.get(key, default)
        try:
            return max(min_value, min(max_value, int(value)))
        except (TypeError, ValueError):
            return default

    return {
        'dispatch_backlog_warn': _int_threshold('OPS_HEALTH_DISPATCH_BACKLOG_WARN', 25, min_value=1),
        'dispatch_backlog_critical': _int_threshold('OPS_HEALTH_DISPATCH_BACKLOG_CRITICAL', 60, min_value=1),
        'incident_critical_breach_warn': _int_threshold('OPS_HEALTH_INCIDENT_CRITICAL_BREACH_WARN', 1, min_value=1),
        'incident_total_breach_warn': _int_threshold('OPS_HEALTH_INCIDENT_TOTAL_BREACH_WARN', 5, min_value=1),
        'lockout_events_warn': _int_threshold('OPS_HEALTH_LOCKOUT_EVENTS_WARN', 5, min_value=1),
        'admin_rate_limit_events_warn': _int_threshold('OPS_HEALTH_ADMIN_RATE_LIMIT_EVENTS_WARN', 5, min_value=1),
        'audit_5xx_events_warn': _int_threshold('OPS_HEALTH_AUDIT_5XX_EVENTS_WARN', 1, min_value=1),
        'billing_followups_warn': _int_threshold('OPS_HEALTH_BILLING_FOLLOWUPS_WARN', 3, min_value=1),
        'billing_followups_critical': _int_threshold(
            'OPS_HEALTH_BILLING_FOLLOWUPS_CRITICAL',
            10,
            min_value=1,
        ),
    }


def _collect_ops_health_snapshot(auth_window_minutes=None, dispatch_limit=None, now=None):
    now = now or utcnow()
    auth_window_minutes = _ops_health_auth_window_minutes(auth_window_minutes)
    dispatch_limit = _ops_health_dispatch_limit(dispatch_limit)
    thresholds = _ops_health_thresholds()

    since = now - timedelta(minutes=auth_window_minutes)
    auth_rows = (
        AuthAuditEvent.query.filter(AuthAuditEvent.occurred_at >= since)
        .order_by(AuthAuditEvent.occurred_at.desc(), AuthAuditEvent.id.desc())
        .limit(10000)
        .all()
    )

    failed_login_events = 0
    lockout_events = 0
    blocklist_events = 0
    rate_limited_events = 0
    admin_rate_limit_events = 0
    audit_5xx_events = 0
    failed_email_buckets = {}
    failed_ip_buckets = {}

    for row in auth_rows:
        event_name = str(row.event or '').strip().lower()
        details = row.details_json or {}
        reason = str(details.get('reason') or '').strip().lower()

        if row.status_code >= 500:
            audit_5xx_events += 1
        if event_name == 'admin_rate_limit' and row.status_code == 429:
            admin_rate_limit_events += 1

        if event_name == 'login' and not row.success:
            failed_login_events += 1
            if reason in {'lockout_triggered', 'lockout_active'}:
                lockout_events += 1
            if reason == 'blocklist':
                blocklist_events += 1
            if reason == 'rate_limited':
                rate_limited_events += 1

            if row.email:
                failed_email_buckets[row.email] = failed_email_buckets.get(row.email, 0) + 1
            if row.ip:
                failed_ip_buckets[row.ip] = failed_ip_buckets.get(row.ip, 0) + 1

    top_failed_emails = [
        {'email': email, 'failed_attempts': attempts}
        for email, attempts in sorted(
            failed_email_buckets.items(),
            key=lambda item: (-item[1], item[0]),
        )[:10]
    ]
    top_failed_ips = [
        {'ip': ip, 'failed_attempts': attempts}
        for ip, attempts in sorted(
            failed_ip_buckets.items(),
            key=lambda item: (-item[1], item[0]),
        )[:10]
    ]

    active_statuses = ['pending_match', 'matched', 'accepted', 'en_route', 'arrived', 'collected']
    dispatch_rows = (
        WasteRemovalRequest.query.filter(WasteRemovalRequest.status.in_(active_statuses))
        .order_by(WasteRemovalRequest.created_at.asc(), WasteRemovalRequest.id.asc())
        .limit(dispatch_limit)
        .all()
    )

    incident_total = 0
    incident_open = 0
    incident_acknowledged = 0
    incident_resolved = 0
    incident_breach_total = 0
    incident_breach_critical = 0
    incident_breach_ack_sla = 0
    incident_breach_resolve_sla = 0
    incident_status_counts = {}
    max_breach_minutes = 0
    oldest_pending_match_minutes = 0
    oldest_unassigned_match_minutes = 0
    billing_followups = _collect_admin_billing_followups(
        limit=_offline_billing_followup_limit(),
        due_only=True,
        now=now,
    )
    billing_due_count = int((billing_followups.get('summary') or {}).get('due_now_count') or 0)
    billing_invoice_sent_candidates = int(
        (billing_followups.get('summary') or {}).get('invoice_sent_candidates') or 0
    )
    billing_oldest_due_hours = float((billing_followups.get('summary') or {}).get('oldest_due_hours') or 0.0)
    billing_oldest_invoice_age_hours = float(
        (billing_followups.get('summary') or {}).get('oldest_invoice_age_hours') or 0.0
    )

    for booking in dispatch_rows:
        status_key = (booking.status or '').strip().lower() or 'unknown'
        incident_status_counts[status_key] = incident_status_counts.get(status_key, 0) + 1

        latest_location = (
            WasteRemovalVehicleLocation.query.filter_by(waste_removal_request_id=booking.id)
            .order_by(WasteRemovalVehicleLocation.recorded_at.desc(), WasteRemovalVehicleLocation.id.desc())
            .first()
        )
        queue_item = _serialize_dispatch_queue_item(
            booking,
            driver=None,
            latest_location=latest_location,
            now=now,
        )

        incident_flags = queue_item.get('incident_flags') or []
        incident_info = queue_item.get('incident') or {}
        if incident_flags:
            incident_total += 1

        incident_state = str(incident_info.get('state') or '').strip().lower()
        if incident_state == 'open':
            incident_open += 1
        elif incident_state == 'acknowledged':
            incident_acknowledged += 1
        elif incident_state == 'resolved':
            incident_resolved += 1

        breach_type = str(incident_info.get('breach_type') or '').strip().lower()
        breach_minutes = max(0, int(incident_info.get('breach_minutes') or 0))
        if breach_type:
            incident_breach_total += 1
            if breach_type == 'ack_sla':
                incident_breach_ack_sla += 1
            elif breach_type == 'resolve_sla':
                incident_breach_resolve_sla += 1
            if (str(incident_info.get('severity') or '').strip().lower()) == 'critical':
                incident_breach_critical += 1
            max_breach_minutes = max(max_breach_minutes, breach_minutes)

        age_minutes = int(queue_item.get('age_minutes') or 0)
        if status_key == 'pending_match':
            oldest_pending_match_minutes = max(oldest_pending_match_minutes, age_minutes)
        if status_key in {'matched', 'accepted'} and booking.assigned_driver_user_id is None:
            oldest_unassigned_match_minutes = max(oldest_unassigned_match_minutes, age_minutes)

    alerts = []

    def _add_alert(code, severity, message, current_value, threshold_value):
        alerts.append(
            {
                'code': str(code),
                'severity': str(severity),
                'message': str(message),
                'current': current_value,
                'threshold': threshold_value,
            }
        )

    backlog_count = len(dispatch_rows)
    if backlog_count >= thresholds['dispatch_backlog_critical']:
        _add_alert(
            'dispatch_backlog_critical',
            'critical',
            'Dispatch backlog exceeded critical threshold.',
            backlog_count,
            thresholds['dispatch_backlog_critical'],
        )
    elif backlog_count >= thresholds['dispatch_backlog_warn']:
        _add_alert(
            'dispatch_backlog_warn',
            'warning',
            'Dispatch backlog exceeded warning threshold.',
            backlog_count,
            thresholds['dispatch_backlog_warn'],
        )

    if incident_breach_critical >= thresholds['incident_critical_breach_warn']:
        _add_alert(
            'incident_critical_breach',
            'critical',
            'Critical incident SLA breaches detected.',
            incident_breach_critical,
            thresholds['incident_critical_breach_warn'],
        )

    if incident_breach_total >= thresholds['incident_total_breach_warn']:
        _add_alert(
            'incident_breach_total',
            'warning',
            'Total incident SLA breaches exceeded warning threshold.',
            incident_breach_total,
            thresholds['incident_total_breach_warn'],
        )

    if lockout_events >= thresholds['lockout_events_warn']:
        _add_alert(
            'auth_lockout_events',
            'warning',
            'Lockout events exceeded warning threshold.',
            lockout_events,
            thresholds['lockout_events_warn'],
        )

    if admin_rate_limit_events >= thresholds['admin_rate_limit_events_warn']:
        _add_alert(
            'auth_admin_rate_limit_events',
            'warning',
            'Admin API rate-limit events exceeded warning threshold.',
            admin_rate_limit_events,
            thresholds['admin_rate_limit_events_warn'],
        )

    if audit_5xx_events >= thresholds['audit_5xx_events_warn']:
        _add_alert(
            'auth_audit_5xx_events',
            'warning',
            'Auth/audit 5xx events exceeded warning threshold.',
            audit_5xx_events,
            thresholds['audit_5xx_events_warn'],
        )

    if billing_due_count >= thresholds['billing_followups_critical']:
        _add_alert(
            'billing_followups_critical',
            'critical',
            'Offline billing follow-ups exceeded critical threshold.',
            billing_due_count,
            thresholds['billing_followups_critical'],
        )
    elif billing_due_count >= thresholds['billing_followups_warn']:
        _add_alert(
            'billing_followups_warn',
            'warning',
            'Offline billing follow-ups exceeded warning threshold.',
            billing_due_count,
            thresholds['billing_followups_warn'],
        )

    status = 'ok'
    if any(alert['severity'] == 'critical' for alert in alerts):
        status = 'critical'
    elif alerts:
        status = 'warning'

    return {
        'status': status,
        'generated_at': now.isoformat() + 'Z',
        'window': {
            'auth_minutes': auth_window_minutes,
            'dispatch_rows_limit': dispatch_limit,
        },
        'alerts': alerts,
        'thresholds': thresholds,
        'metrics': {
            'auth': {
                'failed_login_events': failed_login_events,
                'lockout_events': lockout_events,
                'blocklist_events': blocklist_events,
                'rate_limited_events': rate_limited_events,
                'admin_rate_limit_events': admin_rate_limit_events,
                'audit_5xx_events': audit_5xx_events,
                'top_failed_emails': top_failed_emails,
                'top_failed_ips': top_failed_ips,
            },
            'dispatch': {
                'queue_rows_considered': backlog_count,
                'status_counts': incident_status_counts,
                'incident_rows': incident_total,
                'incident_open': incident_open,
                'incident_acknowledged': incident_acknowledged,
                'incident_resolved': incident_resolved,
                'incident_breach_total': incident_breach_total,
                'incident_breach_critical': incident_breach_critical,
                'incident_breach_ack_sla': incident_breach_ack_sla,
                'incident_breach_resolve_sla': incident_breach_resolve_sla,
                'max_breach_minutes': max_breach_minutes,
                'oldest_pending_match_minutes': oldest_pending_match_minutes,
                'oldest_unassigned_match_minutes': oldest_unassigned_match_minutes,
            },
            'billing': {
                'invoice_sent_candidates': billing_invoice_sent_candidates,
                'followups_due': billing_due_count,
                'oldest_due_hours': billing_oldest_due_hours,
                'oldest_invoice_age_hours': billing_oldest_invoice_age_hours,
            },
        },
    }


def _format_ops_health_digest_text(snapshot):
    generated_at = snapshot.get('generated_at') or ''
    status = str(snapshot.get('status') or 'unknown').upper()
    alerts = list(snapshot.get('alerts') or [])
    auth = (snapshot.get('metrics') or {}).get('auth') or {}
    dispatch = (snapshot.get('metrics') or {}).get('dispatch') or {}
    billing = (snapshot.get('metrics') or {}).get('billing') or {}
    lines = [
        '[Project Divert] Ops Health Digest',
        'Status: {}'.format(status),
        'Generated: {}'.format(generated_at),
        '',
        'Auth metrics:',
        '  failed_login_events={}'.format(auth.get('failed_login_events', 0)),
        '  lockout_events={}'.format(auth.get('lockout_events', 0)),
        '  admin_rate_limit_events={}'.format(auth.get('admin_rate_limit_events', 0)),
        '  audit_5xx_events={}'.format(auth.get('audit_5xx_events', 0)),
        '',
        'Dispatch metrics:',
        '  queue_rows_considered={}'.format(dispatch.get('queue_rows_considered', 0)),
        '  incident_rows={}'.format(dispatch.get('incident_rows', 0)),
        '  incident_breach_total={}'.format(dispatch.get('incident_breach_total', 0)),
        '  incident_breach_critical={}'.format(dispatch.get('incident_breach_critical', 0)),
        '  oldest_pending_match_minutes={}'.format(dispatch.get('oldest_pending_match_minutes', 0)),
        '',
        'Billing metrics:',
        '  invoice_sent_candidates={}'.format(billing.get('invoice_sent_candidates', 0)),
        '  followups_due={}'.format(billing.get('followups_due', 0)),
        '  oldest_due_hours={}'.format(billing.get('oldest_due_hours', 0)),
    ]
    if alerts:
        lines.extend(['', 'Active alerts:'])
        for alert in alerts:
            lines.append(
                '  - [{severity}] {code}: {message} (current={current}, threshold={threshold})'.format(
                    severity=str(alert.get('severity') or '').upper(),
                    code=alert.get('code'),
                    message=alert.get('message'),
                    current=alert.get('current'),
                    threshold=alert.get('threshold'),
                )
            )
    else:
        lines.extend(['', 'Active alerts: none'])
    return '\n'.join(lines)


def run_ops_health_digest(auth_window_minutes=None, dispatch_limit=None, include_ok=False,
                          webhook_url=None, email_to=None, dry_run=False):
    """Collect the ops health snapshot and deliver it to the configured channels.

    Shared by the ``ops-health-digest`` CLI command and the background job.
    Returns the snapshot plus what was delivered, and never raises for a failed
    delivery: a digest that cannot be sent must not mask the health status.
    """
    if auth_window_minutes is not None and int(auth_window_minutes) < 5:
        raise ValueError('auth_window_minutes must be >= 5')
    if dispatch_limit is not None and int(dispatch_limit) < 1:
        raise ValueError('dispatch_limit must be >= 1')

    snapshot = _collect_ops_health_snapshot(
        auth_window_minutes=auth_window_minutes,
        dispatch_limit=dispatch_limit,
    )
    digest_text = _format_ops_health_digest_text(snapshot)
    status = snapshot.get('status')

    should_include_ok = bool(
        include_ok or _is_truthy(current_app.config.get('OPS_HEALTH_DIGEST_INCLUDE_OK', False)))
    result = {
        'status': status,
        'snapshot': snapshot,
        'digest_text': digest_text,
        'notified': False,
        'webhook': 'skipped',
        'email': 'skipped',
        'dry_run': bool(dry_run),
    }
    if not (should_include_ok or status != 'ok'):
        return result
    result['notified'] = True
    if dry_run:
        return result

    final_webhook_url = str(
        webhook_url or current_app.config.get('OPS_HEALTH_DIGEST_WEBHOOK_URL') or '').strip()
    final_email_to = str(
        email_to or current_app.config.get('OPS_HEALTH_DIGEST_EMAIL_TO') or '').strip()

    if final_webhook_url:
        timeout = current_app.config.get('OPS_HEALTH_DIGEST_WEBHOOK_TIMEOUT_SECONDS', 8)
        try:
            timeout = max(2, int(timeout))
        except (TypeError, ValueError):
            timeout = 8
        try:
            response = requests.post(
                final_webhook_url,
                json={'text': digest_text, 'ops_health': snapshot},
                timeout=timeout,
            )
            result['webhook'] = 'sent' if response.status_code < 400 else 'failed'
            if response.status_code >= 400:
                logger.warning('Ops health webhook failed status=%s body=%s',
                               response.status_code, response.text[:500])
        except Exception:
            logger.exception('Ops health digest webhook send failed.')
            result['webhook'] = 'failed'

    if final_email_to:
        subject = '[Project Divert] Ops Health {}'.format(str(status or 'unknown').upper())
        result['email'] = 'sent' if _send_account_email(final_email_to, subject, digest_text) else 'failed'

    return result
