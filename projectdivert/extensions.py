"""Flask extension instances.

Created unbound at import time and attached to an application by the app
factory, so that models and services can import ``db`` without importing the
application itself. This is what keeps the package free of circular imports.
"""

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_moment import Moment
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
moment = Moment()


def init_extensions(app):
    """Bind every extension instance to ``app``."""
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    moment.init_app(app)
    login_manager.login_view = 'web.login_page'
    login_manager.login_message = 'Please log in to continue.'
