#!/usr/bin/env python
"""Generate docs/openapi.json from the application itself.

The spec is derived from the code rather than hand-maintained, so it cannot
drift: paths and methods come from the Flask URL map, auth and required roles
from the ``jwt_required`` decorator, request fields from the ``payload.get``
and ``request.args.get`` calls in each view, and response codes from the
literal status codes each view returns.

Run ``python scripts/generate_openapi.py`` after changing the API surface.
``tests/api/test_openapi_contract.py`` fails if the committed spec is stale.
"""

import ast
import json
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('SQLALCHEMY_DATABASE_URI', 'sqlite:///:memory:')
os.environ.setdefault('SECRET_KEY', 'openapi-generation')
os.environ.setdefault('SESSION_COOKIE_SECURE', '0')

BLUEPRINT_DIR = ROOT / 'projectdivert' / 'blueprints'

TAGS = {
    'api_auth': ('Authentication', 'Login, signup, token refresh, email verification and password reset.'),
    'api_admin_security': ('Admin / Security', 'Auth audit trail, token revocation and the abuse blocklist.'),
    'api_admin_ops': ('Admin / Ops', 'Operational health snapshot.'),
    'api_admin_billing': ('Admin / Billing', 'Offline billing workflow, follow-ups and customer communications.'),
    'api_admin_dispatch': ('Admin / Dispatch', 'Dispatch queue, incidents, telemetry and manual override.'),
    'api_admin_compliance': ('Admin / Compliance', 'Driver and carrier-company compliance review.'),
    'api_drivers': ('Drivers', 'Driver self-service: own compliance and carrier company.'),
    'api_compliance': ('Compliance', 'Waste transfer notes and compliance uploads for a request.'),
    'api_payments': ('Payments', 'Stripe charges, refunds, driver payouts and webhooks.'),
    'api_push': ('Push', 'Expo push subscription registration.'),
    'api_whatsapp': ('WhatsApp', 'Inbound WhatsApp webhook for the conversational assistant.'),
    'api_waste_requests': ('Waste requests', 'Request lifecycle, dispatch acceptance, status and live location.'),
}

WORDS = {
    'api': None, 'admin': None,
    'lca': 'LCA', 'sse': 'SSE', 'id': 'ID', 'url': 'URL',
}


def summarise(func_name, methods, rule):
    """Turn api_admin_list_billing_requests into 'List billing requests'."""
    parts = [p for p in func_name.split('_') if p]
    if parts and parts[0] == 'api':
        parts = parts[1:]
    is_admin = parts and parts[0] == 'admin'
    if is_admin:
        parts = parts[1:]
    parts = [WORDS.get(p, p) for p in parts]
    parts = [p for p in parts if p]
    if not parts:
        parts = ['endpoint']
    text = ' '.join(parts)
    text = text[0].upper() + text[1:]
    text = text.replace('-', ' ')
    return text + (' (admin)' if is_admin else '')


def load_view_sources():
    """Map view function name -> (module stem, ast.FunctionDef, source)."""
    out = {}
    for path in sorted(BLUEPRINT_DIR.rglob('*.py')):
        source = path.read_text()
        tree = ast.parse(source)
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            decorators = [ast.get_source_segment(source, d) or '' for d in node.decorator_list]
            if any(d.startswith('bp.route') for d in decorators):
                out[node.name] = (path.stem, node, source, decorators)
    return out


def required_roles(decorators):
    for d in decorators:
        m = re.search(r"jwt_required\(\s*roles\s*=\s*\{([^}]*)\}", d)
        if m:
            return sorted(re.findall(r"'([^']+)'", m.group(1)))
        if d.startswith('jwt_required'):
            return []
    return None


def json_body_fields(node):
    """Field names read off the parsed JSON body of a view or service.

    A view assigns the body from get_json(); a service is handed it as a
    parameter, so its parameters count as body sources too -- otherwise the
    optional fields a service reads never reach the spec.
    """
    body_vars = {arg.arg for arg in node.args.args}
    body_vars.update(arg.arg for arg in getattr(node.args, 'kwonlyargs', []))
    # A view's own parameters are path arguments, not a body.
    if any(getattr(d, 'id', '') == 'bp' or 'bp.route' in ast.dump(d)
           for d in node.decorator_list):
        body_vars = set()
    for x in ast.walk(node):
        if isinstance(x, ast.Assign) and isinstance(x.value, (ast.Call, ast.BoolOp)):
            seg = ast.dump(x.value)
            if 'get_json' in seg:
                body_vars.update(t.id for t in x.targets if isinstance(t, ast.Name))
    fields = set()
    for x in ast.walk(node):
        if (isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
                and x.func.attr in ('get', 'getlist')
                and isinstance(x.func.value, ast.Name)
                and x.func.value.id in body_vars
                and x.args and isinstance(x.args[0], ast.Constant)
                and isinstance(x.args[0].value, str)):
            fields.add(x.args[0].value)
    return sorted(fields)


def listed_fields(node):
    """Body fields declared as a list literal and then read in a loop.

    Views commonly do ``required_fields = ['a', 'b']`` followed by
    ``for field in required_fields: data.get(field)``, which the direct
    ``payload.get('literal')`` scan cannot see.
    """
    required, optional = set(), set()
    for x in ast.walk(node):
        if not isinstance(x, ast.Assign) or not isinstance(x.value, ast.List):
            continue
        names = [t.id for t in x.targets if isinstance(t, ast.Name)]
        if not names or not names[0].endswith(('field', 'fields')):
            continue
        values = [e.value for e in x.value.elts
                  if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if not values:
            continue
        (required if 'required' in names[0] else optional).update(values)
    return sorted(required), sorted(optional)


def request_attr_fields(node, attr):
    """Field names read from request.args / request.form / request.files."""
    fields = set()
    for x in ast.walk(node):
        if (isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
                and x.func.attr in ('get', 'getlist')
                and isinstance(x.func.value, ast.Attribute)
                and x.func.value.attr == attr
                and isinstance(x.func.value.value, ast.Name)
                and x.func.value.value.id == 'request'
                and x.args and isinstance(x.args[0], ast.Constant)
                and isinstance(x.args[0].value, str)):
            fields.add(x.args[0].value)
    return sorted(fields)


def status_codes(node):
    codes = set()
    for x in ast.walk(node):
        if not isinstance(x, ast.Return) or x.value is None:
            continue
        v = x.value
        if isinstance(v, ast.Tuple) and len(v.elts) >= 2 and isinstance(v.elts[1], ast.Constant) \
                and isinstance(v.elts[1].value, int):
            codes.add(v.elts[1].value)
        else:
            codes.add(200)
    return sorted(codes)


def error_messages(node):
    out = set()
    for x in ast.walk(node):
        if isinstance(x, ast.Dict):
            for k, v in zip(x.keys, x.values):
                if (isinstance(k, ast.Constant) and k.value == 'error'
                        and isinstance(v, ast.Constant) and isinstance(v.value, str)):
                    out.add(v.value)
    return sorted(out)


SERVICE_DIR = ROOT / 'projectdivert' / 'services'


def load_service_functions():
    """Map service function name -> (its ast.FunctionDef, its module's tree).

    A view that hands the work to a service still has to document what that
    service accepts and what it can refuse, so the analysis has to follow the
    call rather than stop at the view body.
    """
    out = {}
    for path in sorted(SERVICE_DIR.rglob('*.py')):
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                out.setdefault(node.name, (node, tree))
    return out


def analysed_nodes(view_node, service_functions, depth=2):
    """The view, the services it calls, and the helpers those call.

    Bounded depth on purpose: it reaches a service and the helper it validates
    with, without dragging in the whole call graph beneath.
    """
    def body_calls(fn):
        # Walk the body only. ast.walk on a FunctionDef also covers its
        # decorator_list, which would follow jwt_required into the auth service
        # and attach its 401/403 errors to every endpoint in the API.
        for statement in fn.body:
            for x in ast.walk(statement):
                yield x

    nodes, trees, seen = [view_node], [], set()
    frontier, remaining = [view_node], depth
    while frontier and remaining > 0:
        next_frontier = []
        for current in frontier:
            for x in body_calls(current):
                if not (isinstance(x, ast.Call) and isinstance(x.func, ast.Name)):
                    continue
                found = service_functions.get(x.func.id)
                if found is None or x.func.id in seen:
                    continue
                seen.add(x.func.id)
                node, tree = found
                nodes.append(node)
                trees.append(tree)
                next_frontier.append(node)
        frontier, remaining = next_frontier, remaining - 1
    return nodes, trees


def constant_string_sequence_fields(tree, wanted='required'):
    """Field names from a module-level FIELDS constant, list or tuple.

    A service declares REQUIRED_FIELDS at module level rather than rebuilding
    the list inside the function, which the in-function scan cannot see.
    """
    found = set()
    for node in getattr(tree, 'body', []):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, (ast.Tuple, ast.List)):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if not names or not names[0].lower().endswith(('field', 'fields')):
            continue
        if wanted not in names[0].lower():
            continue
        found.update(e.value for e in node.value.elts
                     if isinstance(e, ast.Constant) and isinstance(e.value, str))
    return sorted(found)


def raised_error_messages(node):
    """Messages from ``raise SomeError('...')`` inside a service.

    Views report errors by returning a dict; a service raises instead, so the
    dict scan alone would document none of them.
    """
    out = set()
    for x in ast.walk(node):
        if not isinstance(x, ast.Raise) or not isinstance(x.exc, ast.Call):
            continue
        for arg in x.exc.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                out.add(arg.value)
    return sorted(out)


def load_serializer_keys():
    """Map serializer function name -> the keys of the dict it returns."""
    out = {}
    for path in sorted(SERVICE_DIR.rglob('*.py')):
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith('_serialize'):
                continue
            keys = set()
            for x in ast.walk(node):
                target = None
                if isinstance(x, ast.Return) and isinstance(x.value, ast.Dict):
                    target = x.value
                elif isinstance(x, ast.Assign) and isinstance(x.value, ast.Dict):
                    target = x.value
                if target is not None:
                    for k in target.keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            keys.add(k.value)
                if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) \
                        and x.func.attr in ('setdefault', '__setitem__') and x.args \
                        and isinstance(x.args[0], ast.Constant) and isinstance(x.args[0].value, str):
                    keys.add(x.args[0].value)
                if isinstance(x, ast.Subscript) and isinstance(x.ctx, ast.Store) \
                        and isinstance(x.slice, ast.Constant) and isinstance(x.slice.value, str):
                    keys.add(x.slice.value)
            if keys:
                out[node.name] = sorted(keys)
    return out


def response_properties(node, serializer_keys):
    """Best-effort key set of the JSON body a view returns on success."""
    keys = set()
    for x in ast.walk(node):
        if not (isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id == 'jsonify'):
            continue
        for arg in x.args:
            if isinstance(arg, ast.Dict):
                literal = [k.value for k in arg.keys
                           if isinstance(k, ast.Constant) and isinstance(k.value, str)]
                if 'error' in literal:      # an error envelope, not a success body
                    continue
                keys.update(literal)
            elif isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name):
                keys.update(serializer_keys.get(arg.func.id, []))
        for kw in x.keywords:
            if kw.arg:
                keys.add(kw.arg)
    return sorted(keys)


PATH_PARAM_TYPES = {'integer': 'integer', 'float': 'number', 'number': 'number',
                    'path': 'string', 'unicodestring': 'string', 'string': 'string',
                    'uuid': 'string', 'any': 'string'}


def build_spec():
    from projectdivert import create_app

    app = create_app()
    views = load_view_sources()
    serializer_keys = load_serializer_keys()
    service_functions = load_service_functions()

    paths = {}
    used_tags = {}
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: str(r.rule)):
        path = str(rule.rule)
        if not path.startswith('/api/v1'):
            continue
        func_name = rule.endpoint.split('.')[-1]
        entry = views.get(func_name)
        if entry is None:
            continue
        module_stem, node, source, decorators = entry
        bp_name = rule.endpoint.split('.')[0]
        tag, tag_desc = TAGS.get(bp_name, (bp_name, ''))
        used_tags[tag] = tag_desc

        oas_path = re.sub(r'<(?:[^:<>]+:)?([^<>]+)>', r'{\1}', path)
        params = []
        for arg in sorted(rule.arguments):
            conv = rule._converters.get(arg)
            kind = type(conv).__name__.replace('Converter', '').lower() if conv else 'string'
            params.append({
                'name': arg, 'in': 'path', 'required': True,
                'schema': {'type': PATH_PARAM_TYPES.get(kind, 'string')},
            })
        for q in request_attr_fields(node, 'args'):
            params.append({'name': q, 'in': 'query', 'required': False,
                           'schema': {'type': 'string'}})

        roles = required_roles(decorators)

        # A view that delegates to a service is documented from both, or the
        # spec loses the request body and the errors the service raises.
        targets, target_trees = analysed_nodes(node, service_functions)
        req_listed, opt_listed = set(), set()
        body_fields, form_fields, codes, errors = set(), set(), set(), set()
        for target in targets:
            required_here, optional_here = listed_fields(target)
            req_listed.update(required_here)
            opt_listed.update(optional_here)
            body_fields.update(json_body_fields(target))
            form_fields.update(request_attr_fields(target, 'form'))
            codes.update(status_codes(target))
            errors.update(error_messages(target))
            errors.update(raised_error_messages(target))
        for tree in target_trees:
            req_listed.update(constant_string_sequence_fields(tree, 'required'))

        # The service reads optional fields straight off the payload mapping it
        # is handed, which the JSON-body scan sees once the service is followed.
        req_listed, opt_listed = sorted(req_listed), sorted(opt_listed)
        body_fields = sorted(set(body_fields) | set(req_listed) | set(opt_listed))
        form_fields, codes, errors = sorted(form_fields), sorted(codes), sorted(errors)
        props = response_properties(node, serializer_keys)

        for method in sorted(m for m in rule.methods if m not in ('HEAD', 'OPTIONS')):
            op = {
                'operationId': func_name,
                'summary': summarise(func_name, method, path),
                'tags': [tag],
                'responses': {},
            }
            desc = []
            if roles is None:
                desc.append('Public endpoint: no bearer token required.')
            else:
                op['security'] = [{'bearerAuth': []}]
                desc.append('Requires a bearer token with role: '
                            + (', '.join('`%s`' % r for r in roles) if roles else 'any authenticated role')
                            + '.')
            if errors:
                desc.append('Error messages returned by this endpoint: '
                            + '; '.join('"%s"' % e for e in errors[:12]) + '.')
            op['description'] = ' '.join(desc)
            if params:
                op['parameters'] = params
            if method in ('POST', 'PUT', 'PATCH'):
                if body_fields:
                    schema = {'type': 'object',
                              'properties': {f: {} for f in body_fields}}
                    if req_listed:
                        schema['required'] = req_listed
                    op['requestBody'] = {
                        'required': True,
                        'content': {'application/json': {'schema': schema}},
                    }
                elif form_fields:
                    op['requestBody'] = {
                        'required': True,
                        'content': {'multipart/form-data': {'schema': {
                            'type': 'object',
                            'properties': {f: {} for f in form_fields},
                        }}},
                    }
            for code in codes:
                if code >= 400:
                    op['responses'][str(code)] = {
                        'description': 'Error',
                        'content': {'application/json': {
                            'schema': {'$ref': '#/components/schemas/Error'}}},
                    }
                else:
                    schema = {'type': 'object'}
                    if props:
                        schema['properties'] = {p: {} for p in props}
                    op['responses'][str(code)] = {
                        'description': 'Success',
                        'content': {'application/json': {'schema': schema}},
                    }
            if not op['responses']:
                op['responses']['200'] = {'description': 'Success'}
            paths.setdefault(oas_path, {})[method.lower()] = op

    return {
        'openapi': '3.1.0',
        'info': {
            'title': 'Project Divert API',
            'version': '1.0.0',
            'description': (
                'JSON API behind the Project Divert mobile app and admin tooling.\n\n'
                'This document is generated from the application source by '
                '`scripts/generate_openapi.py`: paths and methods come from the Flask '
                'URL map, authentication and roles from the `jwt_required` decorator, '
                'request fields from the body and query reads in each view, and '
                'response codes from the status codes each view returns. '
                '`tests/api/test_openapi_contract.py` fails if it falls out of date.\n\n'
                'Response property lists are best-effort: they are read from the '
                'serialiser each endpoint uses, so they name the keys you can expect '
                'rather than constraining their types.'
            ),
            'license': {'name': 'MIT', 'url': 'https://github.com/dodsy4/projectdivert/blob/main/LICENSE'},
        },
        'servers': [{'url': '/', 'description': 'This deployment'}],
        'tags': [{'name': t, 'description': d} for t, d in sorted(used_tags.items())],
        'components': {
            'securitySchemes': {
                'bearerAuth': {'type': 'http', 'scheme': 'bearer', 'bearerFormat': 'JWT'},
            },
            'schemas': {
                'Error': {
                    'type': 'object',
                    'properties': {'error': {'type': 'string'}},
                    'required': ['error'],
                },
            },
        },
        'paths': paths,
    }


if __name__ == '__main__':
    spec = build_spec()
    out = ROOT / 'docs' / 'openapi.json'
    out.write_text(json.dumps(spec, indent=2, sort_keys=True) + '\n')
    ops = sum(len(v) for v in spec['paths'].values())
    print(f'wrote {out.relative_to(ROOT)}: {len(spec["paths"])} paths, {ops} operations')
