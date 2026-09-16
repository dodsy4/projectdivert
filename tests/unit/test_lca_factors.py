"""Integrity checks on the emission-factor dataset.

The factor CSV is read with csv.DictReader, which silently shifts every column
after an unquoted comma. That is how twenty of these rows ended up reporting a
geography string as their publication year and a URL as their year: the carbon
numbers stayed correct, because value sits before source, but the citation
metadata shown to customers did not. These tests make that failure loud.
"""

import csv
import pathlib
import re

import pytest

import project_divert_lca as lca

FACTORS_CSV = pathlib.Path(lca._DEFAULT_FACTORS_PATH)
EXPECTED_COLUMNS = [
    'material', 'stage', 'value', 'unit', 'gwp_basis', 'source',
    'source_year', 'source_url', 'geography', 'data_quality', 'notes',
]
KNOWN_QUALITY = {
    'secondary-published', 'secondary-estimate',
    'secondary-proxy', 'secondary-legacy',
}


def _rows():
    with open(FACTORS_CSV, newline='', encoding='utf-8-sig') as handle:
        return list(csv.DictReader(handle))


def test_header_is_exactly_the_expected_columns():
    with open(FACTORS_CSV, newline='', encoding='utf-8-sig') as handle:
        header = next(csv.reader(handle))
    assert header == EXPECTED_COLUMNS


def test_no_row_has_extra_fields():
    """An unquoted comma shows up as a None key from DictReader."""
    offenders = [(r['material'], r['stage']) for r in _rows() if None in r]
    assert not offenders, (
        'these rows have more fields than the header, so every column after '
        'the stray comma is shifted: %s' % offenders)


@pytest.mark.parametrize('row', _rows(), ids=lambda r: '%s/%s' % (r['material'], r['stage']))
def test_every_row_is_well_formed(row):
    assert row['material'] and row['stage']
    float(row['value'])
    assert row['unit'], 'unit is required for the factor to mean anything'
    assert re.fullmatch(r'\d{4}', (row['source_year'] or '').strip()), (
        'source_year should be a four-digit year, got %r' % row['source_year'])
    assert (row['source_url'] or '').strip().startswith('http'), (
        'source_url should be a URL, got %r' % row['source_url'])
    assert (row['data_quality'] or '').strip() in KNOWN_QUALITY, (
        'unexpected data_quality %r' % row['data_quality'])


def test_every_material_can_be_assessed():
    """Required stages must resolve for every material the dataset offers."""
    for material in lca.available_materials():
        result = lca.assess_diversion(
            material, 1.0, collection_distance_km=20.0,
            landfill_distance_km=10.0, pathway='recycle')
        assert result.stages
        for citation in result.factor_provenance:
            assert re.fullmatch(r'\d{4}', citation['source_year'])
            assert citation['source_url'].startswith('http')
