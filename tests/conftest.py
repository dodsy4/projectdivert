import os

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/projectdivert_pytest.db'
os.environ['SESSION_COOKIE_SECURE'] = '0'
os.environ['SECRET_KEY'] = 'pytest-secret-key'

import pytest

import app as app_module


@pytest.fixture
def app_context():
    app = app_module.app
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        AUTH_RATE_LIMIT_ENABLED=False,
        AUTH_LOGIN_LOCKOUT_ENABLED=False,
    )

    with app_module._auth_rate_limit_lock:
        app_module._auth_rate_limit_events.clear()
    with app_module._auth_login_lockout_lock:
        app_module._auth_login_lockouts.clear()
    app_module._auth_rate_limit_redis_client = None
    app_module._auth_rate_limit_redis_disabled = False

    with app.app_context():
        app_module.db.session.remove()
        app_module.db.drop_all()
        app_module.db.create_all()

    yield app_module

    with app_module._auth_rate_limit_lock:
        app_module._auth_rate_limit_events.clear()
    with app_module._auth_login_lockout_lock:
        app_module._auth_login_lockouts.clear()
    app_module._auth_rate_limit_redis_client = None
    app_module._auth_rate_limit_redis_disabled = False

    with app.app_context():
        app_module.db.session.remove()
        app_module.db.drop_all()


@pytest.fixture
def client(app_context):
    return app_context.app.test_client()
