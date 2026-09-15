"""Flask CLI commands for seeding, cleanup and scheduled maintenance."""

import json
from datetime import datetime, timedelta
import requests
import click
from flask import current_app
from sqlalchemy import and_, func, or_
from flask.cli import with_appcontext
from projectdivert.extensions import db
from projectdivert.models.auth import AuthLifecycleToken
from projectdivert.services.auth import _auth_token_cleanup_query, _auth_token_cleanup_retention_days
from projectdivert.services.billing import _run_offline_billing_followup_maintenance
from projectdivert.services.dispatch import _dispatch_incident_auto_assign_enabled, _dispatch_incident_auto_resolve_test_enabled, _run_dispatch_incident_maintenance
from projectdivert.services.notifications import _send_account_email
from projectdivert.services.ops import _collect_ops_health_snapshot, _format_ops_health_digest_text
from projectdivert.services.reference_data import _refresh_reference_dataframes_from_db, _seed_reference_data_from_files
from projectdivert.services.utils import _is_truthy



@click.command('seed-reference-data')
@click.option('--force', is_flag=True, help='Replace existing reference rows with file data.')
@with_appcontext
def seed_reference_data(force):
    """Load CSV/XLSX reference data into SQL tables."""
    summary = _seed_reference_data_from_files(force=force)
    loaded_from_db = _refresh_reference_dataframes_from_db()
    click.echo('Reference data seed complete.')
    click.echo('Loaded from DB: {}'.format('yes' if loaded_from_db else 'no'))
    for table_name in sorted(summary.keys()):
        table_summary = summary[table_name]
        click.echo(
            '{} -> inserted={}, existing_before={}, skipped={}'.format(
                table_name,
                table_summary['inserted'],
                table_summary['existing'],
                table_summary['skipped'],
            )
        )



@click.command('auth-token-cleanup')
@click.option(
    '--retention-days',
    type=int,
    default=None,
    help='Delete tokens expired/revoked before now - retention-days (default from AUTH_TOKEN_CLEANUP_RETENTION_DAYS).',
)
@click.option('--batch-size', type=int, default=500, show_default=True)
@click.option('--dry-run', is_flag=True, help='Show candidate rows without deleting.')
@with_appcontext
def auth_token_cleanup(retention_days, batch_size, dry_run):
    """Delete stale auth lifecycle token rows."""
    if retention_days is None:
        retention_days = _auth_token_cleanup_retention_days()
    if retention_days < 0:
        raise click.BadParameter('retention-days must be >= 0')
    if batch_size < 1:
        raise click.BadParameter('batch-size must be >= 1')

    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    query = _auth_token_cleanup_query(cutoff)
    total = query.count()
    type_counts = dict(
        db.session.query(
            AuthLifecycleToken.token_type,
            func.count(AuthLifecycleToken.id),
        )
        .filter(
            or_(
                AuthLifecycleToken.expires_at <= cutoff,
                and_(
                    AuthLifecycleToken.revoked_at.isnot(None),
                    AuthLifecycleToken.revoked_at <= cutoff,
                ),
            )
        )
        .group_by(AuthLifecycleToken.token_type)
        .all()
    )

    click.echo('Auth token cleanup cutoff: {}'.format(cutoff.isoformat() + 'Z'))
    click.echo('Candidates: {}'.format(total))
    if type_counts:
        for token_type in sorted(type_counts.keys()):
            click.echo('  {} -> {}'.format(token_type, type_counts[token_type]))

    if dry_run or total == 0:
        click.echo('Dry run: no rows deleted.' if dry_run else 'No rows to delete.')
        return

    deleted = 0
    while True:
        ids = [row.id for row in _auth_token_cleanup_query(cutoff).order_by(AuthLifecycleToken.id.asc()).limit(batch_size).all()]
        if not ids:
            break
        deleted += (
            AuthLifecycleToken.query.filter(AuthLifecycleToken.id.in_(ids)).delete(synchronize_session=False)
            or 0
        )
        db.session.commit()

    click.echo('Deleted rows: {}'.format(deleted))



@click.command('ops-health-digest')
@click.option('--auth-window-minutes', type=int, default=None, help='Auth/audit lookback window.')
@click.option('--dispatch-limit', type=int, default=None, help='Max active dispatch rows to inspect.')
@click.option('--include-ok', is_flag=True, help='Send notifications even when status is ok.')
@click.option('--webhook-url', default=None, help='Override OPS_HEALTH_DIGEST_WEBHOOK_URL.')
@click.option('--email-to', default=None, help='Override OPS_HEALTH_DIGEST_EMAIL_TO.')
@click.option('--dry-run', is_flag=True, help='Compute and print digest without sending.')
@click.option('--fail-on-critical', is_flag=True, help='Return non-zero if status is critical.')
@with_appcontext
def ops_health_digest(
    auth_window_minutes,
    dispatch_limit,
    include_ok,
    webhook_url,
    email_to,
    dry_run,
    fail_on_critical,
):
    """Generate and optionally send an ops health digest."""
    if auth_window_minutes is not None and auth_window_minutes < 5:
        raise click.BadParameter('auth-window-minutes must be >= 5')
    if dispatch_limit is not None and dispatch_limit < 1:
        raise click.BadParameter('dispatch-limit must be >= 1')

    snapshot = _collect_ops_health_snapshot(
        auth_window_minutes=auth_window_minutes,
        dispatch_limit=dispatch_limit,
    )
    digest_text = _format_ops_health_digest_text(snapshot)
    click.echo(json.dumps(snapshot, indent=2, sort_keys=True))

    should_include_ok = bool(include_ok or _is_truthy(current_app.config.get('OPS_HEALTH_DIGEST_INCLUDE_OK', False)))
    should_notify = should_include_ok or snapshot.get('status') != 'ok'
    if not should_notify:
        click.echo('Status is ok and include-ok is disabled; no notifications sent.')
        return

    if dry_run:
        click.echo('Dry run: notifications not sent.')
        click.echo(digest_text)
        if fail_on_critical and snapshot.get('status') == 'critical':
            raise click.ClickException('Ops health is critical.')
        return

    final_webhook_url = str(webhook_url or current_app.config.get('OPS_HEALTH_DIGEST_WEBHOOK_URL') or '').strip()
    final_email_to = str(email_to or current_app.config.get('OPS_HEALTH_DIGEST_EMAIL_TO') or '').strip()

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
            if response.status_code >= 400:
                click.echo('Webhook send failed status={} body={}'.format(response.status_code, response.text[:500]))
            else:
                click.echo('Webhook digest sent.')
        except Exception:
            current_app.logger.exception('Ops health digest webhook send failed.')
            click.echo('Webhook digest send failed.')

    if final_email_to:
        email_subject = '[Project Divert] Ops Health {}'.format(str(snapshot.get('status') or 'unknown').upper())
        email_sent = _send_account_email(final_email_to, email_subject, digest_text)
        click.echo('Email digest {}.'.format('sent' if email_sent else 'failed'))

    if fail_on_critical and snapshot.get('status') == 'critical':
        raise click.ClickException('Ops health is critical.')



@click.command('dispatch-incident-maintenance')
@click.option('--limit', type=int, default=None, help='Max active dispatch rows to inspect.')
@click.option('--auto-assign', is_flag=True, help='Auto-assign owner for unowned active incidents.')
@click.option('--auto-resolve-test', is_flag=True, help='Auto-resolve stale test incidents.')
@click.option('--owner-admin-email', default=None, help='Preferred admin email for owner assignment.')
@click.option(
    '--resolve-test-minutes',
    type=int,
    default=None,
    help='Minimum incident age (minutes) before auto-resolving test incidents.',
)
@click.option('--dry-run', is_flag=True, help='Compute actions without persisting changes.')
@with_appcontext
def dispatch_incident_maintenance(
    limit,
    auto_assign,
    auto_resolve_test,
    owner_admin_email,
    resolve_test_minutes,
    dry_run,
):
    """Auto-maintain dispatch incidents (owner assignment and stale test cleanup)."""
    if limit is not None and limit < 1:
        raise click.BadParameter('limit must be >= 1')
    if resolve_test_minutes is not None and resolve_test_minutes < 1:
        raise click.BadParameter('resolve-test-minutes must be >= 1')

    effective_auto_assign = bool(auto_assign or _dispatch_incident_auto_assign_enabled())
    effective_auto_resolve_test = bool(
        auto_resolve_test or _dispatch_incident_auto_resolve_test_enabled()
    )

    if not effective_auto_assign and not effective_auto_resolve_test:
        click.echo(
            'No maintenance actions enabled. '
            'Pass --auto-assign and/or --auto-resolve-test or enable related config flags.'
        )
        return

    result = _run_dispatch_incident_maintenance(
        auto_assign=effective_auto_assign,
        auto_resolve_test=effective_auto_resolve_test,
        resolve_test_minutes=resolve_test_minutes,
        owner_admin_email=owner_admin_email,
        limit=limit,
        dry_run=dry_run,
        actor_user_id=None,
        actor_email='dispatch-incident-maintenance@system.local',
        source='cli_dispatch_incident_maintenance',
    )
    click.echo(json.dumps(result, indent=2, sort_keys=True))



@click.command('offline-billing-followups')
@click.option('--limit', type=int, default=None, help='Max invoice-sent rows to inspect.')
@click.option('--search', default=None, help='Optional search across requester fields and billing reference.')
@click.option(
    '--reminder-after-hours',
    type=int,
    default=None,
    help='Hours after invoice_sent before a reminder is due.',
)
@click.option(
    '--repeat-hours',
    type=int,
    default=None,
    help='Minimum hours between reminder communications.',
)
@click.option('--log-reminders', is_flag=True, help='Create payment reminder communication entries.')
@click.option('--dry-run', is_flag=True, help='Compute due reminders without persisting changes.')
@with_appcontext
def offline_billing_followups(limit, search, reminder_after_hours, repeat_hours, log_reminders, dry_run):
    """Review and optionally log stale offline billing follow-ups."""
    if limit is not None and limit < 1:
        raise click.BadParameter('limit must be >= 1')
    if reminder_after_hours is not None and reminder_after_hours < 0:
        raise click.BadParameter('reminder-after-hours must be >= 0')
    if repeat_hours is not None and repeat_hours < 1:
        raise click.BadParameter('repeat-hours must be >= 1')

    effective_log_reminders = bool(
        log_reminders or _is_truthy(current_app.config.get('OFFLINE_BILLING_FOLLOWUP_AUTOMATION_ENABLED', False))
    )
    effective_dry_run = bool(dry_run or _is_truthy(current_app.config.get('OFFLINE_BILLING_FOLLOWUP_DRY_RUN', False)))

    result = _run_offline_billing_followup_maintenance(
        search=search,
        reminder_after_hours=reminder_after_hours,
        repeat_hours=repeat_hours,
        limit=limit,
        dry_run=effective_dry_run,
        log_reminders=effective_log_reminders,
        actor_user_id=None,
        actor_email='offline-billing-followups@system.local',
        source='cli_offline_billing_followups',
    )
    click.echo(json.dumps(result, indent=2, sort_keys=True))


COMMANDS = (
    seed_reference_data,
    auth_token_cleanup,
    ops_health_digest,
    dispatch_incident_maintenance,
    offline_billing_followups,
)


def register_cli(app):
    """Register the Flask CLI commands onto an application instance."""
    for command in COMMANDS:
        app.cli.add_command(command)
