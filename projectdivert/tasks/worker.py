"""RQ worker entry point: ``python -m projectdivert.tasks.worker``.

The worker builds one application and pushes a context around each job, so
jobs get the same configuration, database session and logging as a request
without paying to construct an app per job.
"""

import logging
import sys

from projectdivert import create_app
from projectdivert.tasks import QUEUE_NAME, queue_url

logger = logging.getLogger(__name__)


def build_worker(app):
    from redis import Redis
    from rq import Queue, Worker

    url = queue_url()
    if not url:
        raise RuntimeError(
            'No job queue configured. Set RQ_REDIS_URL (or REDIS_URL) to run a worker.')
    connection = Redis.from_url(url)

    class AppContextWorker(Worker):
        """Runs each job inside a Flask application context."""

        def perform_job(self, job, queue):
            with app.app_context():
                return super().perform_job(job, queue)

    return AppContextWorker([Queue(QUEUE_NAME, connection=connection)], connection=connection)


def main():
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    app = create_app()
    with app.app_context():
        try:
            worker = build_worker(app)
        except RuntimeError as exc:
            logger.error('%s', exc)
            return 1
    logger.info('Worker listening on queue %r', QUEUE_NAME)
    worker.work(with_scheduler=False)
    return 0


if __name__ == '__main__':
    sys.exit(main())
