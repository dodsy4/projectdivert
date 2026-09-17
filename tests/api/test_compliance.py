"""Tests for waste, driver and carrier-company compliance documents."""

import io
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from tests.helpers import _auth_header, _create_user, _fake_postcode_lookup, _provider_frame


def test_waste_request_compliance_document_flow_and_permissions(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())

    _create_user(app_context, 'complianceadmin@example.com', 'Password123!', role='admin', name='Compliance Admin')
    _create_user(app_context, 'compliancecustomer@example.com', 'Password123!', role='customer', name='Compliance Customer')
    _create_user(app_context, 'compliancedriver1@example.com', 'Password123!', role='driver', name='Compliance Driver 1')
    _create_user(app_context, 'compliancedriver2@example.com', 'Password123!', role='driver', name='Compliance Driver 2')

    admin_headers = _auth_header(client, 'complianceadmin@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'compliancecustomer@example.com', 'Password123!')
    driver_one_headers = _auth_header(client, 'compliancedriver1@example.com', 'Password123!')
    driver_two_headers = _auth_header(client, 'compliancedriver2@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'Compliance Customer',
            'requester_email': 'compliancecustomer@example.com',
            'material_type': 'Glass',
            'waste_amount': 1.0,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '1 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': scheduled_time,
        },
        headers=customer_headers,
    )
    assert create_response.status_code == 201
    request_id = create_response.get_json()['request']['id']

    with app_context.app.app_context():
        booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
        assigned_driver = app_context.User.query.filter_by(email='compliancedriver1@example.com').first()
        booking.assigned_driver_user_id = assigned_driver.id
        app_context.db.session.commit()

    forbidden_create = client.post(
        f'/api/v1/waste-requests/{request_id}/compliance/documents',
        json={
            'document_type': 'waste_transfer_note',
            'file_url': 'https://example.com/docs/wtn-unauthorized.pdf',
        },
        headers=driver_two_headers,
    )
    assert forbidden_create.status_code == 403

    create_doc = client.post(
        f'/api/v1/waste-requests/{request_id}/compliance/documents',
        json={
            'document_type': 'waste_transfer_note',
            'file_url': 'https://example.com/docs/wtn-123.pdf',
            'document_reference': 'WTN-123',
            'notes': 'Captured at pickup',
            'metadata': {'vehicle_registration': 'AB12CDE'},
        },
        headers=driver_one_headers,
    )
    assert create_doc.status_code == 201
    create_payload = create_doc.get_json()
    document_id = create_payload['document']['id']
    assert create_payload['document']['status'] == 'submitted'
    assert create_payload['summary']['by_type']['waste_transfer_note']['present'] is True

    customer_list = client.get(
        f'/api/v1/waste-requests/{request_id}/compliance',
        headers=customer_headers,
    )
    assert customer_list.status_code == 200
    list_payload = customer_list.get_json()
    assert len(list_payload['documents']) == 1
    assert list_payload['documents'][0]['document_type'] == 'waste_transfer_note'

    verify = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/compliance/documents/{document_id}/verify',
        json={
            'status': 'verified',
            'notes': 'Validated against carrier paperwork',
            'metadata': {'validated_by': 'ops'},
        },
        headers=admin_headers,
    )
    assert verify.status_code == 200
    verify_payload = verify.get_json()
    assert verify_payload['updated'] is True
    assert verify_payload['previous_status'] == 'submitted'
    assert verify_payload['document']['status'] == 'verified'
    assert verify_payload['summary']['by_type']['waste_transfer_note']['verified'] is True

    customer_verify = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/compliance/documents/{document_id}/verify',
        json={'status': 'verified'},
        headers=customer_headers,
    )
    assert customer_verify.status_code == 403

    driver_license_upload = client.post(
        f'/api/v1/waste-requests/{request_id}/compliance/documents',
        json={
            'document_type': 'carrier_license',
            'file_url': 'https://example.com/docs/carrier-license.pdf',
        },
        headers=driver_one_headers,
    )
    assert driver_license_upload.status_code == 403


def test_admin_compliance_review_queue_lists_pending_documents(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())

    _create_user(app_context, 'reviewadmin@example.com', 'Password123!', role='admin', name='Review Admin')
    _create_user(app_context, 'reviewcustomer@example.com', 'Password123!', role='customer', name='Review Customer')
    _create_user(app_context, 'reviewdriver@example.com', 'Password123!', role='driver', name='Review Driver')

    admin_headers = _auth_header(client, 'reviewadmin@example.com', 'Password123!')
    customer_headers = _auth_header(client, 'reviewcustomer@example.com', 'Password123!')
    driver_headers = _auth_header(client, 'reviewdriver@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'Review Customer',
            'requester_email': 'reviewcustomer@example.com',
            'material_type': 'Glass',
            'waste_amount': 1.0,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '1 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': scheduled_time,
        },
        headers=customer_headers,
    )
    assert create_response.status_code == 201
    request_id = create_response.get_json()['request']['id']

    with app_context.app.app_context():
        booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
        driver_user = app_context.User.query.filter_by(email='reviewdriver@example.com').first()
        booking.assigned_driver_user_id = driver_user.id
        app_context.db.session.commit()

    create_doc = client.post(
        f'/api/v1/waste-requests/{request_id}/compliance/documents',
        json={
            'document_type': 'proof_of_collection_photo',
            'file_url': 'https://example.com/docs/proof-photo.jpg',
        },
        headers=driver_headers,
    )
    assert create_doc.status_code == 201
    document_id = create_doc.get_json()['document']['id']

    pending_queue = client.get(
        '/api/v1/admin/compliance/review-queue?status=submitted&limit=50',
        headers=admin_headers,
    )
    assert pending_queue.status_code == 200
    pending_payload = pending_queue.get_json()
    document_ids = [item['document']['id'] for item in pending_payload['items']]
    assert document_id in document_ids

    verify = client.post(
        f'/api/v1/admin/waste-requests/{request_id}/compliance/documents/{document_id}/verify',
        json={'status': 'verified'},
        headers=admin_headers,
    )
    assert verify.status_code == 200

    pending_queue_after = client.get(
        '/api/v1/admin/compliance/review-queue?status=submitted&limit=50',
        headers=admin_headers,
    )
    assert pending_queue_after.status_code == 200
    pending_after_ids = [item['document']['id'] for item in pending_queue_after.get_json()['items']]
    assert document_id not in pending_after_ids


def test_driver_can_upload_compliance_file_and_receive_served_url(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())

    _create_user(app_context, 'uploadadmin@example.com', 'Password123!', role='admin', name='Upload Admin')
    _create_user(app_context, 'uploadcustomer@example.com', 'Password123!', role='customer', name='Upload Customer')
    _create_user(app_context, 'uploaddriver@example.com', 'Password123!', role='driver', name='Upload Driver')

    customer_headers = _auth_header(client, 'uploadcustomer@example.com', 'Password123!')
    driver_headers = _auth_header(client, 'uploaddriver@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'Upload Customer',
            'requester_email': 'uploadcustomer@example.com',
            'material_type': 'Glass',
            'waste_amount': 1.0,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '1 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': scheduled_time,
        },
        headers=customer_headers,
    )
    assert create_response.status_code == 201
    request_id = create_response.get_json()['request']['id']

    with app_context.app.app_context():
        booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
        driver_user = app_context.User.query.filter_by(email='uploaddriver@example.com').first()
        booking.assigned_driver_user_id = driver_user.id
        app_context.db.session.commit()

    upload_response = client.post(
        f'/api/v1/waste-requests/{request_id}/compliance/uploads',
        data={
            'document_type': 'proof_of_collection_photo',
            'file': (io.BytesIO(b'fake-image-binary'), 'proof-photo.jpg'),
        },
        content_type='multipart/form-data',
        headers=driver_headers,
    )
    assert upload_response.status_code == 201
    upload_payload = upload_response.get_json()
    file_url = upload_payload['upload']['file_url']
    assert '/static/uploads/compliance/request-{}'.format(request_id) in file_url
    assert upload_payload['upload']['original_filename'] == 'proof-photo.jpg'

    served_asset = client.get(urlsplit(file_url).path)
    assert served_asset.status_code == 200
    assert served_asset.data == b'fake-image-binary'


def test_driver_compliance_upload_can_use_s3_storage_backend(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())

    _create_user(app_context, 's3customer@example.com', 'Password123!', role='customer', name='S3 Customer')
    _create_user(app_context, 's3driver@example.com', 'Password123!', role='driver', name='S3 Driver')

    customer_headers = _auth_header(client, 's3customer@example.com', 'Password123!')
    driver_headers = _auth_header(client, 's3driver@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'S3 Customer',
            'requester_email': 's3customer@example.com',
            'material_type': 'Glass',
            'waste_amount': 1.0,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '1 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': scheduled_time,
        },
        headers=customer_headers,
    )
    assert create_response.status_code == 201
    request_id = create_response.get_json()['request']['id']

    with app_context.app.app_context():
        booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
        driver_user = app_context.User.query.filter_by(email='s3driver@example.com').first()
        booking.assigned_driver_user_id = driver_user.id
        app_context.db.session.commit()

    class FakeS3Client:
        def __init__(self):
            self.calls = []

        def put_object(self, **kwargs):
            self.calls.append(kwargs)

    fake_s3 = FakeS3Client()
    monkeypatch.setattr(app_context.uploads, '_compliance_s3_client', lambda: fake_s3)

    monkeypatch.setitem(app_context.app.config, 'COMPLIANCE_STORAGE_BACKEND', 's3')
    monkeypatch.setitem(app_context.app.config, 'COMPLIANCE_S3_BUCKET', 'projectdivert-compliance')
    monkeypatch.setitem(
        app_context.app.config,
        'COMPLIANCE_S3_PUBLIC_BASE_URL',
        'https://cdn.example.com/projectdivert',
    )

    upload_response = client.post(
        f'/api/v1/waste-requests/{request_id}/compliance/uploads',
        data={
            'document_type': 'waste_transfer_note',
            'file': (io.BytesIO(b'fake-pdf-binary'), 'wtn.pdf'),
        },
        content_type='multipart/form-data',
        headers=driver_headers,
    )
    assert upload_response.status_code == 201
    upload_payload = upload_response.get_json()
    assert upload_payload['upload']['backend'] == 's3'
    assert upload_payload['upload']['file_url'].startswith(
        'https://cdn.example.com/projectdivert/compliance/request-{}'.format(request_id)
    )
    assert upload_payload['upload']['storage_key'].endswith('.pdf')

    assert len(fake_s3.calls) == 1
    put_call = fake_s3.calls[0]
    assert put_call['Bucket'] == 'projectdivert-compliance'
    assert put_call['ContentType'] == 'application/pdf'
    assert put_call['Metadata']['request-id'] == str(request_id)
    assert put_call['Metadata']['document-type'] == 'waste_transfer_note'


def test_driver_can_request_signed_compliance_upload(client, app_context, monkeypatch):
    monkeypatch.setattr(app_context.requests, 'get', _fake_postcode_lookup)
    monkeypatch.setattr(app_context.reference_data, 'suppliers', _provider_frame())

    _create_user(app_context, 'signcustomer@example.com', 'Password123!', role='customer', name='Sign Customer')
    _create_user(app_context, 'signdriver@example.com', 'Password123!', role='driver', name='Sign Driver')

    customer_headers = _auth_header(client, 'signcustomer@example.com', 'Password123!')
    driver_headers = _auth_header(client, 'signdriver@example.com', 'Password123!')

    scheduled_time = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    create_response = client.post(
        '/api/v1/waste-requests',
        json={
            'requester_name': 'Sign Customer',
            'requester_email': 'signcustomer@example.com',
            'material_type': 'Glass',
            'waste_amount': 1.0,
            'waste_unit': 'Tonnes',
            'match_radius_miles': 25,
            'pickup_address': '1 Example Road',
            'pickup_postcode': 'SW1A1AA',
            'scheduled_pickup_at': scheduled_time,
        },
        headers=customer_headers,
    )
    assert create_response.status_code == 201
    request_id = create_response.get_json()['request']['id']

    with app_context.app.app_context():
        booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
        driver_user = app_context.User.query.filter_by(email='signdriver@example.com').first()
        booking.assigned_driver_user_id = driver_user.id
        app_context.db.session.commit()

    class FakeS3Client:
        def __init__(self):
            self.calls = []

        def generate_presigned_url(self, operation_name, Params=None, ExpiresIn=None, HttpMethod=None):
            self.calls.append(
                {
                    'operation_name': operation_name,
                    'params': Params,
                    'expires_in': ExpiresIn,
                    'http_method': HttpMethod,
                }
            )
            return 'https://signed-upload.example.com/put-object'

    fake_s3 = FakeS3Client()
    monkeypatch.setattr(app_context.uploads, '_compliance_s3_client', lambda: fake_s3)
    monkeypatch.setitem(app_context.app.config, 'COMPLIANCE_STORAGE_BACKEND', 's3')
    monkeypatch.setitem(app_context.app.config, 'COMPLIANCE_S3_BUCKET', 'projectdivert-compliance')
    monkeypatch.setitem(
        app_context.app.config,
        'COMPLIANCE_S3_PUBLIC_BASE_URL',
        'https://cdn.example.com/projectdivert',
    )
    monkeypatch.setitem(app_context.app.config, 'COMPLIANCE_S3_PRESIGN_EXP_SECONDS', 600)

    sign_response = client.post(
        f'/api/v1/waste-requests/{request_id}/compliance/uploads/sign',
        json={
            'document_type': 'proof_of_collection_photo',
            'file_name': 'proof-photo.jpg',
            'mime_type': 'image/jpeg',
        },
        headers=driver_headers,
    )
    assert sign_response.status_code == 200
    sign_payload = sign_response.get_json()
    assert sign_payload['method'] == 'PUT'
    assert sign_payload['upload_url'] == 'https://signed-upload.example.com/put-object'
    assert sign_payload['upload']['file_url'].startswith(
        'https://cdn.example.com/projectdivert/compliance/request-{}'.format(request_id)
    )
    assert sign_payload['headers']['Content-Type'] == 'image/jpeg'

    assert len(fake_s3.calls) == 1
    call = fake_s3.calls[0]
    assert call['operation_name'] == 'put_object'
    assert call['http_method'] == 'PUT'
    assert call['expires_in'] == 600
    assert call['params']['Bucket'] == 'projectdivert-compliance'
    assert call['params']['ContentType'] == 'image/jpeg'
