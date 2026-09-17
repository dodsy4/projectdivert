"""Shared builders and fakes for the test suite."""

import json
from datetime import timedelta
import pandas as pd
from projectdivert.services.utils import utcnow


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def _fake_postcode_lookup(*args, **kwargs):
    return FakeResponse({'result': {'longitude': -0.1276, 'latitude': 51.5072}})


def _provider_frame():
    return pd.DataFrame(
        [
            {
                'name': 'Provider Alpha',
                'sup_type': 'Waste Carrier',
                'city': 'London',
                'postcode': 'SW1A1AA',
                'lat': 51.5074,
                'long': -0.1278,
            },
            {
                'name': 'Provider Far',
                'sup_type': 'Waste Carrier',
                'city': 'Leeds',
                'postcode': 'LS11AA',
                'lat': 53.8008,
                'long': -1.5491,
            },
        ]
    )


def _create_user(app_context, email, password, role='customer', name='Test User'):
    with app_context.app.app_context():
        user = app_context.User(
            email=email,
            name=name,
            role=role,
            password_hash=app_context.generate_password_hash(password, method='pbkdf2:sha256'),
        )
        app_context.db.session.add(user)
        app_context.db.session.commit()
        return user


def _auth_header(client, email, password):
    response = client.post(
        '/api/v1/auth/login',
        json={
            'email': email,
            'password': password,
        },
    )
    assert response.status_code == 200
    token = response.get_json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def _seed_driver_dispatch_compliance(app_context, driver_email, verifier_email=None):
    with app_context.app.app_context():
        driver = app_context.User.query.filter_by(email=driver_email).first()
        assert driver is not None
        verifier = app_context.User.query.filter_by(email=verifier_email).first() if verifier_email else None
        company_name = f'Seeded Carrier {driver.id}'
        company = app_context.CarrierCompany.query.filter_by(name=company_name).first()
        if not company:
            company = app_context.CarrierCompany(
                name=company_name,
                contact_email=f'carrier{driver.id}@example.com',
                is_active=True,
            )
            app_context.db.session.add(company)
            app_context.db.session.flush()
        driver.carrier_company_id = company.id
        app_context.DriverComplianceDocument.query.filter_by(driver_user_id=driver.id).delete()
        app_context.CompanyComplianceDocument.query.filter_by(carrier_company_id=company.id).delete()
        now = utcnow()
        expires_at = now + timedelta(days=365)
        for document_type in ['carrier_license', 'insurance_certificate']:
            app_context.db.session.add(
                app_context.DriverComplianceDocument(
                    driver_user_id=driver.id,
                    uploaded_by_user_id=driver.id,
                    verified_by_user_id=verifier.id if verifier else driver.id,
                    document_type=document_type,
                    status='verified',
                    file_url=f'https://example.com/driver-compliance/{driver.id}/{document_type}.pdf',
                    document_reference=f'{document_type.upper()}-{driver.id}',
                    verified_at=now,
                    expires_at=expires_at,
                    metadata_json={'seeded': True},
                )
            )
        for document_type in ['operator_license', 'insurance_certificate']:
            app_context.db.session.add(
                app_context.CompanyComplianceDocument(
                    carrier_company_id=company.id,
                    uploaded_by_user_id=verifier.id if verifier else driver.id,
                    verified_by_user_id=verifier.id if verifier else driver.id,
                    document_type=document_type,
                    status='verified',
                    file_url=f'https://example.com/company-compliance/{company.id}/{document_type}.pdf',
                    document_reference=f'{document_type.upper()}-{company.id}',
                    verified_at=now,
                    expires_at=expires_at,
                    metadata_json={'seeded': True},
                )
            )
        app_context.db.session.commit()


def _reset_auth_security_runtime_state(app_context):
    with app_context._auth_rate_limit_lock:
        app_context._auth_rate_limit_events.clear()
    with app_context._auth_login_lockout_lock:
        app_context._auth_login_lockouts.clear()
    app_context.rate_limit._auth_rate_limit_redis_client = None
    app_context.rate_limit._auth_rate_limit_redis_disabled = False
