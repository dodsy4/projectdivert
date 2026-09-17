"""Project Divert application package.

The application is built by :func:`create_app` rather than at import time, so
that tests, CLI commands, RQ workers and the WSGI server can each construct an
instance with their own configuration.

Layering, strictly one-directional::

    services/utils -> extensions -> models -> services -> blueprints -> app
"""

import logging
import os
import sys
from logging import FileHandler, Formatter, StreamHandler

from flask import Flask

from projectdivert.extensions import init_extensions

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

__all__ = ['create_app', 'BASE_DIR']


def _register_blueprints(app):
    from projectdivert.blueprints import admin, certificates, web
    from projectdivert.blueprints.api import (
        admin_billing, admin_compliance, admin_dispatch, admin_ops,
        admin_security, auth, compliance, docs, drivers, payments, push,
        waste_requests, whatsapp,
    )
    from projectdivert.extensions import csrf

    for module in (
        web, admin,
        auth, admin_security, admin_ops, admin_billing, admin_dispatch,
        admin_compliance, drivers, compliance, payments, push, waste_requests,
        docs, whatsapp, certificates,
    ):
        app.register_blueprint(module.bp)

    # web, admin and certificates are cookie-authenticated: a cross-site POST
    # would carry the session, so they need CSRF tokens. Everything under
    # /api/v1 is authenticated by a Bearer token or a provider signature and
    # never by a cookie, so a forged cross-site request has nothing to borrow --
    # and requiring a token there would be unobtainable for the mobile app and
    # would break Stripe's and Twilio's webhook posts outright.
    for module in (
        auth, admin_security, admin_ops, admin_billing, admin_dispatch,
        admin_compliance, drivers, compliance, payments, push, waste_requests,
        docs, whatsapp,
    ):
        csrf.exempt(module.bp)


def _register_template_filters(app):
    from projectdivert.services.uploads import normalize_image_filename
    from projectdivert.services.utils import format_datetime

    app.jinja_env.filters['datetime'] = format_datetime
    app.jinja_env.filters['image_file'] = normalize_image_filename


def _configure_logging(app):
    """Send application logs to error.log and to stdout.

    Idempotent: create_app may run more than once in a process (tests, a worker
    that also builds an app), and app.logger is the same logger object as this
    package's logger, so handlers would otherwise be attached repeatedly and
    every line would appear two or more times.
    """
    if app.debug or app.config.get('TESTING'):
        return

    package_logger = logging.getLogger(__name__)
    targets = [app.logger]
    if package_logger is not app.logger:
        targets.append(package_logger)

    formatter = Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    )
    for logger in targets:
        if any(getattr(h, '_projectdivert', False) for h in logger.handlers):
            continue
        # stdout as well as the file: on a container platform the file handler
        # writes to a disk nobody reads and that vanishes on redeploy, so a
        # production traceback would be invisible in the platform's log stream.
        for handler in (FileHandler('error.log'), StreamHandler(sys.stdout)):
            handler.setFormatter(formatter)
            handler.setLevel(logging.INFO)
            handler._projectdivert = True
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)


#: The placeholder in config.py, kept here so the guard below is self-contained.
DEV_SECRET_KEY = 'dev-only-change-me'


def _verify_secrets(app):
    """Refuse to serve with the placeholder secret key.

    SECRET_KEY signs session cookies and, unless JWT_SECRET_KEY is set
    separately, every API access and refresh token. Left at its default, all of
    those are forgeable by anyone who has read config.py -- so this is a boot
    failure rather than a warning. scripts/production_preflight.sh checks the
    same thing before a deploy; this catches the case where nobody ran it.

    Debug and testing runs are exempt, so the local quickstart still works
    without any environment set up.
    """
    if app.debug or app.config.get('TESTING'):
        return

    insecure = [
        name for name in ('SECRET_KEY', 'JWT_SECRET_KEY')
        if not str(app.config.get(name) or '').strip()
        or str(app.config.get(name)).strip() == DEV_SECRET_KEY
    ]
    if insecure:
        raise RuntimeError(
            '{} must be set to a strong random value before serving traffic '
            '(currently unset or using the development default). Set it in the '
            'environment, or run with FLASK_DEBUG=1 for local development.'
            .format(' and '.join(insecure))
        )


def create_app(config_object='config'):
    """Build and configure a Project Divert application instance."""
    # root_path is pinned to the repository root, not the package directory:
    # config, templates, static assets and seed data all live alongside the
    # package, and code reads them via app.root_path / app.static_folder.
    app = Flask(
        __name__,
        root_path=BASE_DIR,
        template_folder=os.path.join(BASE_DIR, 'templates'),
        static_folder=os.path.join(BASE_DIR, 'static'),
    )
    app.config.from_object(config_object)
    _verify_secrets(app)

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
