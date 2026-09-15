"""Tests for how the application is assembled.

The package lives one directory below the repository root, so anything that
resolves a path from the application must still resolve against the repository
root. Getting that wrong silently breaks seed data and uploads rather than
raising, which is why it is pinned here.
"""

import os

from projectdivert import BASE_DIR, create_app


def test_root_path_is_the_repository_root(app_context):
    assert app_context.app.root_path == BASE_DIR
    assert os.path.isfile(os.path.join(app_context.app.root_path, 'config.py'))


def test_seed_data_and_templates_resolve_from_the_app(app_context):
    app = app_context.app
    assert os.path.isfile(os.path.join(app.root_path, 'material_sheet.csv'))
    assert os.path.isdir(app.static_folder)
    assert os.path.isfile(os.path.join(app.template_folder, 'layouts', 'main.html'))


def test_material_seeding_finds_its_csv(app_context):
    from projectdivert.models import Material
    from projectdivert.services.reference_data import _seed_materials_if_empty

    with app_context.app.app_context():
        _seed_materials_if_empty()
        assert Material.query.count() > 0


def test_factory_builds_independent_instances():
    first, second = create_app(), create_app()
    assert first is not second
    assert len(list(first.url_map.iter_rules())) == len(list(second.url_map.iter_rules()))


def test_each_rule_and_method_pair_is_registered_once(app_context):
    # HEAD and OPTIONS are added automatically and legitimately repeat across
    # a GET rule and a POST rule that share a path.
    pairs = [(str(r.rule), m)
             for r in app_context.app.url_map.iter_rules()
             for m in sorted(r.methods)
             if m not in ('HEAD', 'OPTIONS')]
    assert len(pairs) == len(set(pairs))


def test_endpoints_with_several_rules_are_only_spelling_aliases(app_context):
    """A view may answer on more than one URL, but only as a spelling alias.

    Three legacy routes are reachable with both hyphens and underscores. Any
    other duplicate endpoint would mean two genuinely different URLs share a
    view, which is worth noticing.
    """
    by_endpoint = {}
    for rule in app_context.app.url_map.iter_rules():
        by_endpoint.setdefault(rule.endpoint, set()).add(str(rule.rule))

    for endpoint, rules in by_endpoint.items():
        if len(rules) == 1:
            continue
        normalised = {r.replace('-', '').replace('_', '') for r in rules}
        assert len(normalised) == 1, (
            '%s serves genuinely different URLs: %s' % (endpoint, sorted(rules)))


def test_blueprints_cover_the_whole_surface(app_context):
    non_blueprint = [
        r.endpoint for r in app_context.app.url_map.iter_rules()
        if '.' not in r.endpoint and r.endpoint != 'static'
    ]
    assert not non_blueprint, 'routes registered outside a blueprint: %s' % non_blueprint
