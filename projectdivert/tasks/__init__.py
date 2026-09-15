"""Background job queue.

Jobs are plain functions in :mod:`projectdivert.tasks.jobs`. They call the same
service entry points the CLI commands call, so a scheduled run and a manual run
cannot drift apart.

Scheduling is deliberately kept outside the application: a platform cron
enqueues a job and the worker executes it. That keeps one process responsible
for running work, with RQ's retry and failure visibility, instead of cron
shelling directly into the app on the web instance.

When no Redis URL is configured -- local development, CI, the test suite --
:func:`enqueue` runs the job inline and says so, so nothing silently stops
happening just because a queue is absent.
"""

import logging

from flask import current_app

logger = logging.getLogger(__name__)

QUEUE_NAME = 'projectdivert'
DEFAULT_JOB_TIMEOUT = 600


def queue_url():
    """Redis URL for the job queue, falling back to the shared REDIS_URL."""
    config = current_app.config
    return str(config.get('RQ_REDIS_URL') or config.get('REDIS_URL') or '').strip()


def queue_enabled():
    return bool(queue_url())


def get_queue():
    """Return the RQ queue, or ``None`` when no queue is configured."""
    url = queue_url()
    if not url:
        return None
    try:
        from redis import Redis
        from rq import Queue
    except ImportError:
        logger.warning('RQ_REDIS_URL is set but rq/redis are not installed; '
                       'jobs will run inline.')
        return None
    try:
        connection = Redis.from_url(url)
        # from_url is lazy, so ping here: the caller needs to know now whether
        # the queue is usable, not halfway through enqueueing.
        connection.ping()
        return Queue(
            QUEUE_NAME,
            connection=connection,
            default_timeout=current_app.config.get('RQ_JOB_TIMEOUT', DEFAULT_JOB_TIMEOUT),
        )
    except Exception:
        logger.exception('Job queue is unreachable; falling back to inline execution.')
        return None


def enqueue(func, **kwargs):
    """Enqueue ``func``; run it inline if no queue is available.

    Returns ``(job_id, result)``. Exactly one of the two is ever set: a queued
    job has an id and no result yet, an inline run has a result and no id.
    """
    queue = get_queue()
    if queue is None:
        logger.info('No job queue configured; running %s inline.', func.__name__)
        return None, func(**kwargs)
    try:
        job = queue.enqueue(func, **kwargs)
    except Exception:
        # The queue answered a ping and then failed. Getting the work done
        # matters more than getting it done on the queue, so run it here and
        # log loudly enough that the outage is visible.
        logger.exception('Enqueueing %s failed; running it inline instead.', func.__name__)
        return None, func(**kwargs)
    logger.info('Enqueued %s as job %s', func.__name__, job.id)
    return job.id, None
