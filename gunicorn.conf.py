"""Gunicorn configuration, shared by the Procfile, the Dockerfile and render.yaml.

The defaults gunicorn ships with are one synchronous worker: every request is
served by a single process, one at a time. That does not work here, because
/api/v1/waste-requests/<id>/events is a Server-Sent Events stream that stays
open for as long as a client is watching a job. Under a sync worker one
connected mobile client occupies the whole application, and the 30s default
timeout kills the stream regardless.

Threaded workers fix both halves: a stream costs a thread rather than the
process, and the worker keeps reporting to the arbiter while a request is still
open, so a long-lived response is not mistaken for a hung worker.

Concurrent streams are bounded by workers * threads, so size threads for the
number of clients expected to be watching a job at once.
"""

import os


def _int_env(name, default):
    try:
        return max(1, int(os.getenv(name, '').strip()))
    except (AttributeError, ValueError):
        return default


bind = '0.0.0.0:{}'.format(os.getenv('PORT', '5000'))

worker_class = 'gthread'
workers = _int_env('WEB_CONCURRENCY', 2)
threads = _int_env('GUNICORN_THREADS', 8)

# Applies to the worker heartbeat, not to individual requests: an open SSE
# stream does not count against it, but a genuinely wedged worker is replaced.
timeout = _int_env('GUNICORN_TIMEOUT', 60)
graceful_timeout = _int_env('GUNICORN_GRACEFUL_TIMEOUT', 30)
keepalive = _int_env('GUNICORN_KEEPALIVE', 5)

# Recycle workers periodically so a slow leak cannot accumulate indefinitely.
max_requests = _int_env('GUNICORN_MAX_REQUESTS', 2000)
max_requests_jitter = _int_env('GUNICORN_MAX_REQUESTS_JITTER', 200)

# The platform collects stdout/stderr; writing to files would strand the logs
# on a disk that vanishes on redeploy.
accesslog = '-'
errorlog = '-'
loglevel = os.getenv('GUNICORN_LOG_LEVEL', 'info')


def _bool_env(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def on_starting(server):
    """Bring the database up to date once, before any worker is forked.

    Render's pre-deploy command is a paid feature, and its free tier has no
    shell, so on that plan there is nowhere to run `flask db upgrade` except a
    developer's laptop -- which means it gets forgotten, and the application
    then boots against a schema that does not match the code.

    This is the gunicorn arbiter, which runs once per deploy before forking, so
    the migration cannot race between workers the way the old db.create_all()
    hook could. Alembic stays the single source of truth: this runs the real
    migration chain, it does not create tables from the models.

    Off unless MIGRATE_ON_BOOT is set, because it is the wrong behaviour on any
    platform that can migrate before a release goes live -- there, a deploy
    should be refused rather than half-applied. It also assumes one instance:
    with several booting at once they would contend, and while Postgres makes
    that safe rather than corrupting, it is not something to rely on.
    """
    if not _bool_env('MIGRATE_ON_BOOT'):
        return

    import subprocess
    import sys

    steps = [['db', 'upgrade']]
    if _bool_env('SEED_ON_BOOT', True):
        steps.append(['seed-materials'])

    for step in steps:
        server.log.info('MIGRATE_ON_BOOT: flask %s', ' '.join(step))
        result = subprocess.run(
            [sys.executable, '-m', 'flask'] + step,
            env=dict(os.environ, FLASK_APP=os.getenv('FLASK_APP', 'wsgi.py')),
        )
        if result.returncode != 0:
            # Refuse to serve rather than answer requests against a schema the
            # code does not match. The platform will show this as a failed
            # deploy, which is the point.
            raise RuntimeError(
                'flask {} failed with exit code {}; refusing to start.'.format(
                    ' '.join(step), result.returncode,
                )
            )
    server.log.info('MIGRATE_ON_BOOT: database is up to date.')
