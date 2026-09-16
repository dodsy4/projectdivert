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
    app.register_error_handler(404, not_found_error)
    app.register_error_handler(500, server_error)
