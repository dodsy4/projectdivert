"""`flask seed-reference-data` must work from a checkout of the repository.

sites.xlsx holds real client site records and is gitignored, so it never
exists in a fresh clone or a deploy. The seed used to read it unconditionally
and stopped with FileNotFoundError before seeding anything, which also blocked
the supplier and carbon-offset tables the app does use. The seed now skips the
site table when that one file is missing, and still fails loudly if a file that
ships with the repository is missing.
"""

import pandas as pd
import pytest

from projectdivert.cli import seed_reference_data
from projectdivert.models.reference import (
    CarbonEquivalencyReference,
    SiteReference,
    SupplierReference,
)


@pytest.fixture
def no_sites_file(app_context, monkeypatch, tmp_path):
    monkeypatch.setattr(
        app_context.reference_data,
        'SITES_REFERENCE_FILE',
        str(tmp_path / 'sites.xlsx'),
    )
    return app_context


def test_seed_completes_without_sites_file(no_sites_file):
    with no_sites_file.app.app_context():
        summary = no_sites_file.reference_data._seed_reference_data_from_files()

        assert summary['site_reference']['skipped'] is True
        assert summary['site_reference']['inserted'] == 0
        assert summary['site_reference']['missing_file'].endswith('sites.xlsx')

        assert summary['supplier_reference']['inserted'] > 0
        assert summary['carbon_equivalency_reference']['inserted'] > 0
        assert SupplierReference.query.count() > 0
        assert CarbonEquivalencyReference.query.count() > 0


def test_force_does_not_wipe_site_rows_it_cannot_replace(no_sites_file):
    with no_sites_file.app.app_context():
        no_sites_file.db.session.add(SiteReference(source_row_index=0, row_data={'site': 'kept'}))
        no_sites_file.db.session.commit()

        summary = no_sites_file.reference_data._seed_reference_data_from_files(force=True)

        assert summary['site_reference']['existing'] == 1
        assert SiteReference.query.count() == 1
        assert SiteReference.query.one().row_data == {'site': 'kept'}


def test_sites_file_is_still_seeded_when_present(app_context, monkeypatch, tmp_path):
    sites_path = tmp_path / 'sites.xlsx'
    pd.DataFrame({'site': ['Depot A', 'Depot B']}).to_excel(sites_path, index=False)
    monkeypatch.setattr(app_context.reference_data, 'SITES_REFERENCE_FILE', str(sites_path))

    with app_context.app.app_context():
        summary = app_context.reference_data._seed_reference_data_from_files()

        assert summary['site_reference']['inserted'] == 2
        assert 'missing_file' not in summary['site_reference']
        assert SiteReference.query.count() == 2


def test_missing_bundled_file_still_stops_the_seed(app_context, monkeypatch, tmp_path):
    # Run from an empty directory: data/df3.csv and the other bundled files are
    # gone, which is a broken checkout rather than an expected absence.
    monkeypatch.chdir(tmp_path)

    with app_context.app.app_context():
        with pytest.raises(FileNotFoundError):
            app_context.reference_data._seed_reference_data_from_files()


def test_cli_command_succeeds_and_explains_the_skip(no_sites_file):
    result = no_sites_file.app.test_cli_runner().invoke(seed_reference_data)

    assert result.exit_code == 0, result.output
    assert 'Reference data seed complete.' in result.output
    assert 'site_reference -> inserted=0' in result.output
    assert 'sites.xlsx not found' in result.output
