"""Flask CLI commands for seeding, cleanup and scheduled maintenance."""

import json
import click
from flask import current_app
from flask.cli import with_appcontext
from projectdivert.services.auth import run_auth_token_cleanup
from projectdivert.services.billing import _run_offline_billing_followup_maintenance
from projectdivert.services.dispatch import _dispatch_incident_auto_assign_enabled, _dispatch_incident_auto_resolve_test_enabled, _run_dispatch_incident_maintenance
from projectdivert.services.ops import run_ops_health_digest
from projectdivert.tasks import enqueue
from projectdivert.tasks.jobs import REGISTRY
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



@click.command('seed-materials')
@with_appcontext
def seed_materials():
    """Load the bundled material catalogue if the table is empty.

    Used to run on the first request of every process. That made the web
    workers responsible for populating the database, which is a deploy step, so
    it lives here and runs once per deploy instead.
    """
    from projectdivert.models.catalog import Material
    from projectdivert.services.reference_data import _seed_materials_if_empty

    before = Material.query.count()
    _seed_materials_if_empty()
    after = Material.query.count()
    click.echo('Materials: {} before, {} after ({} seeded).'.format(
        before, after, after - before,
    ))


@click.command('seed-demo')
@click.option('--password', default='DemoPassword123!', show_default=True,
              help='Password for every demo account.')
@click.option('--reset', is_flag=True,
              help='Remove the previous demo data first.')
@with_appcontext
def seed_demo_command(password, reset):
    """Create demo accounts and a scenario part-way through, for demonstrating."""
    from projectdivert.services.demo_seed import seed_demo

    try:
        summary = seed_demo(password=password, reset=reset)
    except PermissionError as exc:
        raise click.ClickException(str(exc))

    click.echo('Demo accounts (password: {}):'.format(summary['password']))
    for account in summary['accounts']:
        click.echo('  {:<40} {:<9} {}'.format(
            account['email'], account['role'],
            'created' if account['created'] else 'updated',
        ))

    if summary['collections']:
        click.echo('\nCollections seeded:')
        for row in summary['collections']:
            click.echo('  #{:<5} {:<14} {}'.format(
                row['id'], row['status'], row['material_type']))
        click.echo('\nThe completed one has a carbon certificate at '
                   '/certificate/<id>.')
    else:
        click.echo('\n{} demo collection(s) already present; left alone. '
                   'Use --reset to rebuild them.'.format(
                       summary['existing_collections']))


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
    try:
        summary = run_auth_token_cleanup(
            retention_days=retention_days,
            batch_size=batch_size,
            dry_run=dry_run,
        )
    except ValueError as exc:
        raise click.BadParameter(str(exc))

    click.echo('Auth token cleanup cutoff: {}'.format(summary['cutoff']))
    click.echo('Candidates: {}'.format(summary['candidates']))
    for token_type in sorted(summary['by_token_type']):
        click.echo('  {} -> {}'.format(token_type, summary['by_token_type'][token_type]))
    if summary['dry_run']:
        click.echo('Dry run: no rows deleted.')
    elif summary['candidates'] == 0:
        click.echo('No rows to delete.')
    else:
        click.echo('Deleted rows: {}'.format(summary['deleted']))


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
    try:
        result = run_ops_health_digest(
            auth_window_minutes=auth_window_minutes,
            dispatch_limit=dispatch_limit,
            include_ok=include_ok,
            webhook_url=webhook_url,
            email_to=email_to,
            dry_run=dry_run,
        )
    except ValueError as exc:
        raise click.BadParameter(str(exc))

    click.echo(json.dumps(result['snapshot'], indent=2, sort_keys=True))
    if not result['notified']:
        click.echo('Status is ok and include-ok is disabled; no notifications sent.')
    elif result['dry_run']:
        click.echo('Dry run: notifications not sent.')
        click.echo(result['digest_text'])
    else:
        click.echo('Webhook digest {}.'.format(result['webhook']))
        click.echo('Email digest {}.'.format(result['email']))

    if fail_on_critical and result['status'] == 'critical':
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


@click.command('enqueue')
@click.argument('job_name', type=click.Choice(sorted(REGISTRY)))
@click.option('--sync', is_flag=True, help='Run the job inline instead of queueing it.')
@click.option('--dry-run', is_flag=True, help='Pass dry-run through to the job.')
@with_appcontext
def enqueue_job(job_name, sync, dry_run):
    """Queue a background job by name.

    Intended for a platform scheduler: cron enqueues, the worker executes.
    Falls back to running inline when no queue is configured.
    """
    job = REGISTRY[job_name]
    kwargs = {'dry_run': True} if dry_run else {}
    if sync:
        click.echo(json.dumps(job(**kwargs), indent=2, sort_keys=True, default=str))
        return
    job_id, result = enqueue(job, **kwargs)
    if job_id:
        click.echo('Queued {} as job {}'.format(job_name, job_id))
    else:
        click.echo('No queue configured; ran {} inline.'.format(job_name))
        click.echo(json.dumps(result, indent=2, sort_keys=True, default=str))


COMMANDS = (
    seed_reference_data,
    seed_materials,
    seed_demo_command,
    auth_token_cleanup,
    ops_health_digest,
    dispatch_incident_maintenance,
    offline_billing_followups,
    enqueue_job,
)


def register_cli(app):
    """Register the Flask CLI commands onto an application instance."""
    for command in COMMANDS:
        app.cli.add_command(command)
