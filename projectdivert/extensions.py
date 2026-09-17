"""Flask extension instances.

Created unbound at import time and attached to an application by the app
factory, so that models and services can import ``db`` without importing the
application itself. This is what keeps the package free of circular imports.
"""

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_moment import Moment
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
moment = Moment()
csrf = CSRFProtect()


def init_extensions(app):
    """Bind every extension instance to ``app``."""
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    moment.init_app(app)
    # WTF_CSRF_ENABLED alone only covers forms that are validated through a
    # FlaskForm. The session-authenticated admin and account routes read
    # request.form directly, so protection has to be enforced app-wide here;
    # the token-authenticated blueprints are exempted in the app factory.
    csrf.init_app(app)
    login_manager.login_view = 'web.login_page'
    login_manager.login_message = 'Please log in to continue.'
