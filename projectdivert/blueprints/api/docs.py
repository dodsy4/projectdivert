"""API documentation routes: the OpenAPI document and a rendered reference."""

import json
import os

from flask import Blueprint, Response, jsonify, render_template_string

bp = Blueprint('api_docs', __name__)

_SPEC_CACHE = {}

_REDOC_PAGE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Project Divert API reference</title>
    <style>body { margin: 0; padding: 0; }</style>
  </head>
  <body>
    <redoc spec-url="{{ spec_url }}"></redoc>
    <script src="https://cdn.jsdelivr.net/npm/redoc@2.1.3/bundles/redoc.standalone.js"></script>
  </body>
</html>
"""


def _spec_path():
    from projectdivert import BASE_DIR
    return os.path.join(BASE_DIR, 'docs', 'openapi.json')


def load_spec():
    """Read the generated OpenAPI document, caching on file mtime."""
    path = _spec_path()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    if _SPEC_CACHE.get('mtime') != mtime:
        with open(path, encoding='utf-8') as handle:
            _SPEC_CACHE['spec'] = json.load(handle)
        _SPEC_CACHE['mtime'] = mtime
    return _SPEC_CACHE['spec']


@bp.route('/api/v1/openapi.json', methods=['GET'])
def api_openapi_spec():
    spec = load_spec()
    if spec is None:
        return jsonify({'error': 'OpenAPI document has not been generated'}), 404
    return jsonify(spec)


@bp.route('/api/docs', methods=['GET'])
def api_docs_page():
    return Response(
        render_template_string(_REDOC_PAGE, spec_url='/api/v1/openapi.json'),
        mimetype='text/html',
    )
