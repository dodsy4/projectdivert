#!/usr/bin/env python
"""Build docs/lca-demo.html, the standalone carbon-model demo page.

The page is a single self-contained HTML file: it embeds the emission-factor
dataset and a JavaScript port of the LCA engine, so anyone can try the model
without a database, API keys or a running backend.

Run ``python scripts/build_lca_demo.py`` after editing either the template or
``data/lca/emission_factors.csv``, then ``python scripts/verify_lca_demo.py``
to confirm the JavaScript port still agrees with the Python engine.
"""

import csv
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
FACTORS_CSV = ROOT / 'data' / 'lca' / 'emission_factors.csv'
TEMPLATE = ROOT / 'scripts' / 'lca_demo_template.html'
OUTPUT = ROOT / 'docs' / 'lca-demo.html'

PLACEHOLDER = '/*__FACTORS__*/[]'

# Only the fields the page actually uses, to keep the payload small.
FIELDS = ('material', 'stage', 'value', 'unit', 'gwp_basis', 'source',
          'source_year', 'source_url', 'data_quality')


def load_factors():
    rows = []
    with open(FACTORS_CSV, newline='', encoding='utf-8-sig') as handle:
        for row in csv.DictReader(handle):
            material = (row.get('material') or '').strip()
            stage = (row.get('stage') or '').strip()
            if not material or not stage:
                continue
            try:
                value = float(row.get('value'))
            except (TypeError, ValueError):
                continue
            record = {}
            for field in FIELDS:
                record[field] = value if field == 'value' else (row.get(field) or '').strip()
            rows.append(record)
    if not rows:
        raise SystemExit('No usable rows in {}'.format(FACTORS_CSV))
    return rows


def main():
    factors = load_factors()
    template = TEMPLATE.read_text(encoding='utf-8')
    if PLACEHOLDER not in template:
        raise SystemExit('Placeholder {} not found in {}'.format(PLACEHOLDER, TEMPLATE))

    payload = json.dumps(factors, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    html = template.replace(PLACEHOLDER, payload)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding='utf-8')

    materials = sorted({f['material'] for f in factors if f['material'] != '*'})
    print('wrote {} ({:,} bytes)'.format(OUTPUT.relative_to(ROOT), len(html)))
    print('  {} factors, {} materials'.format(len(factors), len(materials)))


if __name__ == '__main__':
    main()
