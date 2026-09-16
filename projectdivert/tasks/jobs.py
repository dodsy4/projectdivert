"""The jobs that can be queued.

Each one is a thin wrapper over a service entry point: it runs inside an
application context supplied by the worker, returns a JSON-serialisable summary
so the result is readable in RQ, and logs a one-line outcome.
"""

import logging

from projectdivert.services.auth import run_auth_token_cleanup
from projectdivert.services.billing import _run_offline_billing_followup_maintenance
from projectdivert.services.dispatch import _run_dispatch_incident_maintenance
from projectdivert.services.ops import run_ops_health_digest

logger = logging.getLogger(__name__)


def ops_health_digest(**kwargs):
    """Collect the ops health snapshot and deliver it to the configured channels."""
    result = run_ops_health_digest(**kwargs)
    logger.info('ops-health-digest status=%s webhook=%s email=%s',
                result['status'], result['webhook'], result['email'])
    return {k: v for k, v in result.items() if k != 'snapshot'}


def auth_token_cleanup(**kwargs):
    """Delete auth lifecycle tokens that expired or were revoked before the cutoff."""
    summary = run_auth_token_cleanup(**kwargs)
    logger.info('auth-token-cleanup candidates=%s deleted=%s',
                summary['candidates'], summary['deleted'])
    return summary


def dispatch_incident_maintenance(**kwargs):
    """Assign owners and resolve stale dispatch incidents."""
    kwargs.setdefault('actor_email', 'dispatch-incident-maintenance@system.local')
    kwargs.setdefault('source', 'job_dispatch_incident_maintenance')
    result = _run_dispatch_incident_maintenance(**kwargs)
    logger.info('dispatch-incident-maintenance %s', _summarise(result))
    return result


def offline_billing_followups(**kwargs):
    """Review invoice-sent requests and log any due payment reminders."""
    kwargs.setdefault('actor_email', 'offline-billing-followups@system.local')
    kwargs.setdefault('source', 'job_offline_billing_followups')
    result = _run_offline_billing_followup_maintenance(**kwargs)
    logger.info('offline-billing-followups %s', _summarise(result))
    return result


def _summarise(result):
    if not isinstance(result, dict):
        return repr(result)[:200]
    return ' '.join('%s=%s' % (k, v) for k, v in sorted(result.items())
                    if isinstance(v, (int, float, str, bool)))


#: Job name -> callable, for the CLI and for scheduled triggers.
REGISTRY = {
    'ops-health-digest': ops_health_digest,
    'auth-token-cleanup': auth_token_cleanup,
    'dispatch-incident-maintenance': dispatch_incident_maintenance,
    'offline-billing-followups': offline_billing_followups,
}
