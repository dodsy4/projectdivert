"""Every url_for() target must be a registered endpoint.

Moving the routes into blueprints renamed every endpoint (`index` became
`web.index`), and a `url_for` that names the old one raises BuildError at render
time rather than at import or start-up. The error templates were the worst case:
a failing request rendered an error page that itself failed, hiding the original
exception.

Nothing here needs the routes to be exercised, so this catches call sites no
functional test happens to reach.
"""

import pathlib
import re

import pytest

from projectdivert import BASE_DIR

# url_for('literal'  /  url_for("literal"  — dynamic endpoints are skipped.
URL_FOR = re.compile(r"""url_for\(\s*['"]([A-Za-z_][A-Za-z0-9_.]*)['"]""")

SEARCH_ROOTS = (
    (pathlib.Path(BASE_DIR) / 'templates', '*.html'),
    (pathlib.Path(BASE_DIR) / 'projectdivert', '*.py'),
)


def _call_sites():
    found = []
    for root, glob in SEARCH_ROOTS:
        for path in sorted(root.rglob(glob)):
            text = path.read_text(encoding='utf-8', errors='replace')
            for match in URL_FOR.finditer(text):
                line = text.count('\n', 0, match.start()) + 1
                found.append((path.relative_to(BASE_DIR), line, match.group(1)))
    return found


CALL_SITES = _call_sites()


def test_there_are_call_sites_to_check():
    """Guard against the regex silently matching nothing."""
    assert CALL_SITES, 'found no url_for call sites; the scan is broken'


@pytest.mark.parametrize(
    'path,line,endpoint', CALL_SITES,
    ids=['%s:%s:%s' % (p, l, e) for p, l, e in CALL_SITES],
)
def test_url_for_target_exists(app_context, path, line, endpoint):
    endpoints = {rule.endpoint for rule in app_context.app.url_map.iter_rules()}
    assert endpoint in endpoints, (
        "%s:%s builds a URL for '%s', which is not a registered endpoint. "
        "Blueprint endpoints are prefixed - did you mean one of %s?"
        % (path, line, endpoint,
           sorted(e for e in endpoints if e.split('.')[-1] == endpoint.split('.')[-1]))
    )


def test_error_templates_render(app_context):
    """Both error templates must build their Back link.

    These are the last line of defence: an error page that raises hides the
    exception that caused it.
    """
    from flask import render_template

    with app_context.app.test_request_context('/'):
        for template in ('errors/404.html', 'errors/500.html'):
            html = render_template(template)
            assert 'href="/"' in html, '%s did not build its Back link' % template


def test_404_page_is_served(client):
    response = client.get('/no-such-page-exists-here')
    assert response.status_code == 404
    assert 'href="/"' in response.get_data(as_text=True)
