"""Project Divert application package.

The application is built by :func:`create_app` rather than at import time, so
that tests, CLI commands, RQ workers and the WSGI server can each construct an
instance with their own configuration.

Layering, strictly one-directional::

    services/utils -> extensions -> models -> services -> blueprints -> app
"""

import logging
import os
from logging import FileHandler, Formatter

from flask import Flask

from projectdivert.extensions import init_extensions

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

__all__ = ['create_app', 'BASE_DIR']


def _register_blueprints(app):
    from projectdivert.blueprints import admin, web
    from projectdivert.blueprints.api import (
        admin_billing, admin_compliance, admin_dispatch, admin_ops,
        admin_security, auth, compliance, drivers, payments, push,
        waste_requests,
    )

    for module in (
        web, admin,
        auth, admin_security, admin_ops, admin_billing, admin_dispatch,
        admin_compliance, drivers, compliance, payments, push, waste_requests,
    ):
        app.register_blueprint(module.bp)


def _register_template_filters(app):
    from projectdivert.services.uploads import normalize_image_filename
    from projectdivert.services.utils import format_datetime

    app.jinja_env.filters['datetime'] = format_datetime
    app.jinja_env.filters['image_file'] = normalize_image_filename


def _configure_logging(app):
    if app.debug or app.config.get('TESTING'):
        return
    file_handler = FileHandler('error.log')
    file_handler.setFormatter(
        Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')
    )
    file_handler.setLevel(logging.INFO)
    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    # The service layer logs through module loggers under the package name.
    package_logger = logging.getLogger(__name__)
    package_logger.setLevel(logging.INFO)
    package_logger.addHandler(file_handler)


def create_app(config_object='config'):
    """Build and configure a Project Divert application instance."""
    app = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, 'templates'),
        static_folder=os.path.join(BASE_DIR, 'static'),
    )
    app.config.from_object(config_object)

    init_extensions(app)

    # Imported for their side effects: model registration on the metadata and
    # the Flask-Login user loader.
    from projectdivert import models  # noqa: F401
    from projectdivert.services import auth as _auth  # noqa: F401

    _register_blueprints(app)
    _register_template_filters(app)

    from projectdivert.cli import register_cli
    from projectdivert.hooks import register_hooks

    register_hooks(app)
    register_cli(app)
    _configure_logging(app)
    return app
