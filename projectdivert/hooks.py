"""Request lifecycle hooks and error handlers."""

import uuid
from flask import current_app, g, render_template, request
from projectdivert.extensions import db
from projectdivert.services.audit import _AUDIT_ROUTE_REGISTRY, _audit_should_capture, record_audit_event
from projectdivert.services.reference_data import _seed_materials_if_empty



def ensure_core_tables():
    # Create core tables on first request if missing.
    if getattr(current_app, '_core_tables_checked', False):
        return
    try:
        db.create_all()
        _seed_materials_if_empty()
        current_app._core_tables_checked = True
    except Exception:
        current_app.logger.exception('Failed creating core tables on startup.')



def _assign_request_id():
    g.request_id = uuid.uuid4().hex
    g.audit_explicitly_recorded = False



#: Content-Security-Policy. The server-rendered pages are Bootstrap 3 and jQuery
#: inherited from the project's first version, with 11 inline <script> blocks, 13
#: <style> blocks, 31 inline style attributes and 2 on* handlers, so
#: 'unsafe-inline' is required for now. That weakens the XSS protection a CSP
#: normally gives -- what this still buys is that script can only be loaded from
#: this origin and the few listed hosts, the page cannot be framed, and form
#: submissions cannot be redirected off-origin. Tightening it means moving those
#: inline blocks into files under /static and then switching to nonces.
DEFAULT_CONTENT_SECURITY_POLICY = '; '.join([
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' https://maps.googleapis.com "
    "https://kit.fontawesome.com https://*.fontawesome.com",
    "style-src 'self' 'unsafe-inline' https://*.fontawesome.com",
    # Google Maps serves tiles from several hosts and rotates them.
    "img-src 'self' data: https:",
    "font-src 'self' data: https://*.fontawesome.com",
    "connect-src 'self' https://maps.googleapis.com https://*.fontawesome.com",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
])


def _set_security_headers(response):
    """Add the response headers a browser uses to constrain the page.

    Referrer-Policy is deliberately 'same-origin' rather than 'no-referrer':
    Flask-WTF's CSRF protection checks the Referer on secure requests and
    rejects a POST that has none, so suppressing it entirely would reject every
    form submission over HTTPS.
    """
    config = current_app.config

    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'same-origin')

    # The config key always exists and is None when unset, so a two-argument
    # get() would return None rather than the default and send no CSP at all.
    # Unset means the default; an empty string means deliberately no CSP.
    policy = config.get('CONTENT_SECURITY_POLICY')
    if policy is None:
        policy = DEFAULT_CONTENT_SECURITY_POLICY
    if policy:
        response.headers.setdefault('Content-Security-Policy', policy)

    # Only meaningful over HTTPS, and actively harmful if a browser pins it from
    # a plain-HTTP local development server.
    max_age = config.get('HSTS_MAX_AGE_SECONDS') or 0
    if max_age and request.is_secure:
        response.headers.setdefault(
            'Strict-Transport-Security',
            'max-age={}; includeSubDomains'.format(int(max_age)),
        )

    return response


def _audit_state_changes(response):
    try:
        if _audit_should_capture(response):
            rule = request.url_rule.rule if request.url_rule else request.path
            action, entity_type = _AUDIT_ROUTE_REGISTRY.get(
                rule,
                ('{}.{}'.format(request.method.lower(), rule), None),
            )
            entity_id = None
            for candidate in ('request_id', 'material_id', 'mat_id', 'document_id', 'id'):
                if request.view_args and candidate in request.view_args:
                    entity_id = request.view_args[candidate]
                    break
            record_audit_event(
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                status_code=response.status_code,
            )
    except Exception:
        current_app.logger.exception('after_request audit capture failed.')
    return response


#  Error Handling and Initializing
#  ----------------------------------------------------------------
def not_found_error(error):
    return render_template('errors/404.html'), 404



def server_error(error):
    return render_template('errors/500.html'), 500


def register_hooks(app):
    """Wire request hooks and error handlers onto an application instance."""
    app.before_request(ensure_core_tables)
    app.before_request(_assign_request_id)
    app.after_request(_audit_state_changes)
    app.after_request(_set_security_headers)
    app.register_error_handler(404, not_found_error)
    app.register_error_handler(500, server_error)
