#!/usr/bin/env python
"""Check the demo page's JavaScript LCA port against the Python engine.

docs/lca-demo.html carries a JavaScript translation of project_divert_lca so the
model can run in a browser. A translation that silently disagrees with the
engine would publish wrong carbon numbers under the project's name, so this
script extracts the engine block from the built page, runs it under Node across
every material, both pathways and a spread of masses and distances, and compares
each total and stage against Python.

Requires Node. Exits non-zero on any mismatch.
"""

import json
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PAGE = ROOT / 'docs' / 'lca-demo.html'
TOLERANCE = 1e-9

MASSES = (1.0, 2.5, 0.25, 17.0)
DISTANCES = ((25.0, 15.0), (80.0, 40.0), (5.0, 60.0), (0.0, 0.0))


def engine_source():
    """The first <script> block of the page: the dataset plus the engine port."""
    html = PAGE.read_text(encoding='utf-8')
    blocks = re.findall(r'<script>(.*?)</script>', html, re.S)
    for block in blocks:
        if 'function assessDiversion' in block:
            return block
    raise SystemExit('Could not find the engine <script> block in {}'.format(PAGE))


def run_node(cases):
    script = engine_source() + """
const cases = JSON.parse(process.argv[2]);
const out = cases.map(function (c) {
  try {
    const r = assessDiversion(c.material, c.mass, c.collection, c.landfill, c.pathway);
    const stages = {};
    for (const s of r.stages) stages[s.stage] = s.kg_co2e;
    return {
      baseline: r.baseline_kg, diversion: r.diversion_kg, net: r.net_avoided_kg,
      stages: stages, warnings: r.warnings.length
    };
  } catch (err) {
    return { error: String(err.message) };
  }
});
process.stdout.write(JSON.stringify(out));
"""
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as handle:
        handle.write(script)
        path = handle.name
    try:
        proc = subprocess.run([ 'node', path, json.dumps(cases)],
                              capture_output=True, text=True, check=False)
    finally:
        pathlib.Path(path).unlink(missing_ok=True)
    if proc.returncode != 0:
        raise SystemExit('node failed:\n{}'.format(proc.stderr[:2000]))
    return json.loads(proc.stdout)


def main():
    import project_divert_lca as lca

    cases = []
    for material in lca.available_materials():
        for pathway in ('recycle', 'reuse'):
            for mass in MASSES:
                for collection, landfill in DISTANCES:
                    cases.append({'material': material, 'pathway': pathway, 'mass': mass,
                                  'collection': collection, 'landfill': landfill})

    js_results = run_node(cases)
    if len(js_results) != len(cases):
        raise SystemExit('expected {} results, got {}'.format(len(cases), len(js_results)))

    failures = []
    for case, js in zip(cases, js_results):
        py = lca.assess_diversion(
            case['material'], case['mass'],
            collection_distance_km=case['collection'],
            landfill_distance_km=case['landfill'],
            pathway=case['pathway'],
        )
        label = '{material} / {pathway} / {mass} t / {collection} km / {landfill} km'.format(**case)
        if 'error' in js:
            failures.append('{}: JS raised {!r}, Python did not'.format(label, js['error']))
            continue
        for field, py_value in (('baseline', py.baseline_kg),
                                ('diversion', py.diversion_kg),
                                ('net', py.net_avoided_kg)):
            if abs(js[field] - py_value) > TOLERANCE * max(1.0, abs(py_value)):
                failures.append('{}: {} JS={!r} PY={!r}'.format(label, field, js[field], py_value))
        py_stages = {s['stage']: s['kg_co2e'] for s in py.stages}
        if set(py_stages) != set(js['stages']):
            failures.append('{}: stage set differs JS={} PY={}'.format(
                label, sorted(js['stages']), sorted(py_stages)))
        else:
            for stage, py_value in py_stages.items():
                if abs(js['stages'][stage] - py_value) > TOLERANCE * max(1.0, abs(py_value)):
                    failures.append('{}: stage {} JS={!r} PY={!r}'.format(
                        label, stage, js['stages'][stage], py_value))
        if js['warnings'] != len(py.warnings):
            failures.append('{}: warning count JS={} PY={}'.format(
                label, js['warnings'], len(py.warnings)))

    if failures:
        print('MISMATCH in {} of {} cases:'.format(len(failures), len(cases)))
        for line in failures[:25]:
            print('  ' + line)
        return 1
    print('OK: {} cases agree between the JavaScript port and project_divert_lca'.format(len(cases)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
