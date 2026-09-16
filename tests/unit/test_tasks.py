"""Tests for the background job queue.

The queue is optional: with no Redis URL configured the application must still
work and jobs must still run, just inline. These tests cover both paths, using
fakeredis to exercise the real RQ machinery without needing a Redis server.
"""

import json

import pytest
from fakeredis import FakeStrictRedis
from rq import Queue

from projectdivert import tasks
from projectdivert.tasks import jobs


def test_queue_is_disabled_when_no_url_is_configured(app_context):
    with app_context.app.app_context():
        app_context.app.config.pop('RQ_REDIS_URL', None)
        app_context.app.config.pop('REDIS_URL', None)
        assert tasks.queue_url() == ''
        assert tasks.queue_enabled() is False
        assert tasks.get_queue() is None


def test_enqueue_runs_inline_without_a_queue(app_context):
    calls = []

    def job(**kwargs):
        calls.append(kwargs)
        return {'ran': True}

    with app_context.app.app_context():
        app_context.app.config.pop('RQ_REDIS_URL', None)
        app_context.app.config.pop('REDIS_URL', None)
        job_id, result = tasks.enqueue(job, dry_run=True)

    assert job_id is None
    assert result == {'ran': True}
    assert calls == [{'dry_run': True}]


def test_enqueue_uses_the_queue_when_one_is_available(app_context, monkeypatch):
    queue = Queue('projectdivert', connection=FakeStrictRedis(), is_async=False)
    monkeypatch.setattr(tasks, 'get_queue', lambda: queue)

    with app_context.app.app_context():
        job_id, result = tasks.enqueue(jobs.auth_token_cleanup, dry_run=True)

    assert job_id is not None, 'a queued job should report an id'
    assert result is None, 'a queued job has no inline result'
    finished = queue.fetch_job(job_id)
    assert finished.return_value()['dry_run'] is True
    assert finished.return_value()['deleted'] == 0


def test_a_bad_queue_url_degrades_to_inline_rather_than_failing(app_context):
    with app_context.app.app_context():
        app_context.app.config['RQ_REDIS_URL'] = 'redis://127.0.0.1:1/0'
        assert tasks.queue_enabled() is True
        job_id, result = tasks.enqueue(jobs.auth_token_cleanup, dry_run=True)
    assert job_id is None
    assert result['dry_run'] is True


@pytest.mark.parametrize('name', sorted(jobs.REGISTRY))
def test_every_job_returns_a_json_serialisable_summary(app_context, name):
    with app_context.app.app_context():
        result = jobs.REGISTRY[name](dry_run=True)
    json.dumps(result, default=str)
    assert isinstance(result, dict)


def test_registry_matches_the_cli_choices():
    from projectdivert.cli import enqueue_job

    choices = next(p for p in enqueue_job.params if p.name == 'job_name')
    assert sorted(choices.type.choices) == sorted(jobs.REGISTRY)


def test_worker_refuses_to_start_without_a_queue(app_context):
    from projectdivert.tasks import worker

    with app_context.app.app_context():
        app_context.app.config.pop('RQ_REDIS_URL', None)
        app_context.app.config.pop('REDIS_URL', None)
        with pytest.raises(RuntimeError, match='No job queue configured'):
            worker.build_worker(app_context.app)


def test_worker_runs_jobs_inside_an_application_context(app_context, monkeypatch):
    """The worker must push a context: jobs read config and hit the database."""
    import inspect

    import redis

    from projectdivert.tasks import worker

    monkeypatch.setattr(redis.Redis, 'from_url', classmethod(lambda cls, url: FakeStrictRedis()))
    with app_context.app.app_context():
        app_context.app.config['RQ_REDIS_URL'] = 'redis://localhost:6379/0'
        built = worker.build_worker(app_context.app)

    assert type(built).__name__ == 'AppContextWorker'
    assert 'with app.app_context():' in inspect.getsource(type(built).perform_job)
