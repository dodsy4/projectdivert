"""The gunicorn boot hook that migrates before workers fork.

Render's pre-deploy command is a paid feature and its free tier has no shell,
so on that plan there is nowhere to run `flask db upgrade` except a laptop --
which gets forgotten, and the application then serves against a schema that
does not match the code.
"""

import runpy

import pytest


@pytest.fixture(scope='module')
def gunicorn_config():
    return runpy.run_path('gunicorn.conf.py')


class _FakeLog:
    def __init__(self):
        self.messages = []

    def info(self, message, *args):
        self.messages.append(message % args if args else message)


class _FakeServer:
    def __init__(self):
        self.log = _FakeLog()


def test_the_hook_does_nothing_unless_it_is_switched_on(gunicorn_config, monkeypatch):
    """Off by default: on a platform that can migrate before release, a deploy
    should be refused rather than half-applied."""
    monkeypatch.delenv('MIGRATE_ON_BOOT', raising=False)
    ran = []
    monkeypatch.setattr('subprocess.run', lambda *a, **k: ran.append(a))

    server = _FakeServer()
    gunicorn_config['on_starting'](server)

    assert ran == []
    assert server.log.messages == []


@pytest.mark.parametrize('value', ['1', 'true', 'yes', 'on', 'TRUE'])
def test_the_hook_runs_the_migration_chain_when_switched_on(
    gunicorn_config, monkeypatch, value,
):
    monkeypatch.setenv('MIGRATE_ON_BOOT', value)
    monkeypatch.setenv('SEED_ON_BOOT', '0')
    calls = []

    class _Ok:
        returncode = 0

    def _fake_run(args, **kwargs):
        calls.append(args)
        return _Ok()

    monkeypatch.setattr('subprocess.run', _fake_run)
    gunicorn_config['on_starting'](_FakeServer())

    assert len(calls) == 1
    # It runs Alembic, not create_all: the schema keeps one owner.
    assert calls[0][-2:] == ['db', 'upgrade']


def test_seeding_runs_alongside_the_migration_by_default(gunicorn_config, monkeypatch):
    monkeypatch.setenv('MIGRATE_ON_BOOT', '1')
    monkeypatch.delenv('SEED_ON_BOOT', raising=False)
    calls = []

    class _Ok:
        returncode = 0

    monkeypatch.setattr('subprocess.run', lambda args, **k: calls.append(args) or _Ok())
    gunicorn_config['on_starting'](_FakeServer())

    assert [c[-1] for c in calls] == ['upgrade', 'seed-materials']


def test_a_failed_migration_refuses_to_start(gunicorn_config, monkeypatch):
    """Serving against a mismatched schema is worse than not serving."""
    monkeypatch.setenv('MIGRATE_ON_BOOT', '1')

    class _Failed:
        returncode = 2

    monkeypatch.setattr('subprocess.run', lambda *a, **k: _Failed())

    with pytest.raises(RuntimeError, match='refusing to start'):
        gunicorn_config['on_starting'](_FakeServer())
