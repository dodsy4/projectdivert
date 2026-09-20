"""Waste carrier registration numbers are checked for shape before they are stored.

A carrier licence recorded with a typo'd number is worse than one with no
number: it looks verifiable, so the admin reviewing it has no reason to doubt
it. The old mobile client validated this on the way in; this repository tracks
the licence as an uploaded document and never looked at the number.
"""

import pytest

from projectdivert.services.compliance import (
    _checked_carrier_reference,
    normalize_waste_carrier_reference,
    waste_carrier_reference_looks_valid,
)


@pytest.mark.parametrize('reference', [
    'CBDU123456',      # upper tier, the common shape
    'CBDL999999',      # lower tier
    'CBTU12345',       # transfer
    'ABWU12345',       # pre-dates the current scheme
    'CBD1234',         # no tier suffix
])
def test_real_registration_shapes_are_accepted(reference):
    assert waste_carrier_reference_looks_valid(reference) is True


@pytest.mark.parametrize('reference', [
    '',
    'NOTALICENCE',
    'CBDU12',          # too few digits to be a registration
    '123456',          # no prefix
    'CBDU',            # no digits
    'XYZU123456',      # not an Environment Agency prefix
])
def test_things_that_are_not_registrations_are_rejected(reference):
    assert waste_carrier_reference_looks_valid(reference) is False


@pytest.mark.parametrize('typed, stored', [
    ('cbdu123456', 'CBDU123456'),
    ('CBDU 123 456', 'CBDU123456'),
    ('cbdu-123456', 'CBDU123456'),
    ('  CBDU123456  ', 'CBDU123456'),
])
def test_the_number_is_stored_the_same_way_however_it_is_typed(typed, stored):
    assert normalize_waste_carrier_reference(typed) == stored


def test_a_valid_reference_is_tidied_on_the_way_in():
    assert _checked_carrier_reference('carrier_license', 'cbdu 123456', {}) == 'CBDU123456'


def test_a_malformed_reference_is_refused_with_the_expected_shape():
    with pytest.raises(ValueError) as excinfo:
        _checked_carrier_reference('carrier_license', 'probably-a-typo', {})
    assert 'CBDU123456' in str(excinfo.value), 'the error should show the shape expected'


def test_an_unrecognised_reference_can_still_be_recorded_deliberately():
    """The agency has changed this format before, so the check cannot be final."""
    kept = _checked_carrier_reference(
        'carrier_license', 'SOME-NEW-FORMAT-2031', {'allow_unrecognised_reference': True},
    )
    assert kept == 'SOME-NEW-FORMAT-2031', 'an overridden value is stored as typed'


@pytest.mark.parametrize('document_type', [
    'insurance_certificate', 'waste_transfer_note', 'proof_of_collection_photo',
])
def test_other_document_types_keep_whatever_reference_they_were_given(document_type):
    assert _checked_carrier_reference(document_type, 'anything at all', {}) == 'anything at all'


def test_a_missing_reference_is_still_allowed():
    """The number is optional; only a wrong one is a problem."""
    assert _checked_carrier_reference('carrier_license', None, {}) is None
    assert _checked_carrier_reference('carrier_license', '', {}) == ''


def test_the_api_refuses_a_malformed_carrier_number(client, app_context):
    from tests.helpers import _auth_header, _create_user

    _create_user(app_context, 'ea-admin@example.com', 'Password123!', role='admin', name='A')
    _create_user(app_context, 'ea-driver@example.com', 'Password123!', role='driver', name='D')
    with app_context.app.app_context():
        driver_id = app_context.User.query.filter_by(email='ea-driver@example.com').first().id
    headers = _auth_header(client, 'ea-admin@example.com', 'Password123!')

    def _post(reference, **extra):
        payload = {
            'document_type': 'carrier_license',
            'file_url': 'https://example.com/licence.pdf',
            'document_reference': reference,
        }
        payload.update(extra)
        return client.post(
            f'/api/v1/admin/drivers/{driver_id}/compliance/documents',
            json=payload, headers=headers,
        )

    refused = _post('not-a-licence')
    assert refused.status_code == 400
    assert 'waste carrier registration' in refused.get_json()['error']

    accepted = _post('cbdu 123456')
    assert accepted.status_code in {200, 201}, accepted.get_json()
    assert accepted.get_json()['document']['document_reference'] == 'CBDU123456'

    overridden = _post('SOME-NEW-FORMAT-2031', allow_unrecognised_reference=True)
    assert overridden.status_code in {200, 201}, overridden.get_json()
