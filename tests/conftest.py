import os

os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/projectdivert_pytest.db'
os.environ['SESSION_COOKIE_SECURE'] = '0'
os.environ['SECRET_KEY'] = 'pytest-secret-key'

import pytest

import app as app_module


@pytest.fixture
def app_context():
    app = app_module.app
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)

    with app.app_context():
        app_module.db.session.remove()
        app_module.db.drop_all()
        app_module.db.create_all()

    yield app_module

    with app.app_context():
        app_module.db.session.remove()
        app_module.db.drop_all()


@pytest.fixture
def client(app_context):
    return app_context.app.test_client()
