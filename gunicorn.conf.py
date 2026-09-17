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
