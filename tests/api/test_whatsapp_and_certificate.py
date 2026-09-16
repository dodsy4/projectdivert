"""Tests for the WhatsApp assistant and the diversion certificate.

Neither the Anthropic nor the Twilio SDK is required to run these: the feature
is flag-gated and both integrations degrade, so the tests exercise the degraded
paths as first-class behaviour rather than skipping them.

The webhook tests matter most. The implementation this was ported from trusted
Twilio's ``From`` field without verifying the request signature, which let
anyone who learned the URL act as a linked user, so the rejection path is
pinned here.
"""

from datetime import datetime, timedelta

import pytest

import project_divert_lca
from projectdivert.services import chatbot, whatsapp

WEBHOOK = '/api/v1/whatsapp/inbound'
PHONE = '+447700900123'


def _enable(app, **overrides):
    app.config.update(WHATSAPP_ENABLED=True, CHATBOT_ENABLED=False, **overrides)


def _make_user(app_context, role='customer', phone=PHONE, email='sam@example.com'):
    with app_context.app.app_context():
        user = app_context.User(
            email=email, password_hash='x', name='Sam', role=role,
            is_active_user=True, phone=phone,
        )
        app_context.db.session.add(user)
        app_context.db.session.commit()
        return user.id


def _make_request(app_context, email='sam@example.com', status='pending',
                  material='Timber', amount=2.0, unit='tonnes'):
    with app_context.app.app_context():
        booking = app_context.WasteRemovalRequest(
            requester_name='Sam', requester_email=email,
            material_type=material, waste_amount=amount, waste_unit=unit,
            pickup_address='1 Site Road', pickup_postcode='SW1A1AA',
            scheduled_pickup_at=datetime.utcnow() + timedelta(days=2),
            status=status,
        )
        app_context.db.session.add(booking)
        app_context.db.session.commit()
        return booking.id


# ---------------------------------------------------------------------------
# Webhook security
# ---------------------------------------------------------------------------

def test_webhook_is_absent_when_the_feature_is_disabled(client, app_context):
    app_context.app.config['WHATSAPP_ENABLED'] = False
    response = client.post(WEBHOOK, data={'From': 'whatsapp:' + PHONE, 'Body': 'hello'})
    assert response.status_code == 404


def test_webhook_rejects_an_unsigned_request(client, app_context):
    """Without a valid Twilio signature the sender is not who they claim."""
    _enable(app_context.app)
    _make_user(app_context)
    response = client.post(WEBHOOK, data={'From': 'whatsapp:' + PHONE, 'Body': 'hello'})
    assert response.status_code == 403
    assert b'Signature' in response.data


def test_verification_fails_closed_without_the_twilio_sdk(app_context, monkeypatch):
    monkeypatch.setattr(whatsapp, '_RequestValidator', None)
    with app_context.app.app_context():
        app_context.app.config['TWILIO_AUTH_TOKEN'] = 'token'
        ok, reason = whatsapp.verify_request('https://x/y', {}, 'sig')
    assert ok is False
    assert 'not installed' in reason


def test_verification_fails_closed_without_an_auth_token(app_context, monkeypatch):
    monkeypatch.setattr(whatsapp, '_RequestValidator', object)
    with app_context.app.app_context():
        app_context.app.config['TWILIO_AUTH_TOKEN'] = ''
        ok, reason = whatsapp.verify_request('https://x/y', {}, 'sig')
    assert ok is False
    assert 'TWILIO_AUTH_TOKEN' in reason


def test_a_rejected_webhook_is_audited(client, app_context):
    _enable(app_context.app)
    client.post(WEBHOOK, data={'From': 'whatsapp:' + PHONE, 'Body': 'hi'})
    with app_context.app.app_context():
        rows = app_context.AuditEvent.query.filter(
            app_context.AuditEvent.action == 'whatsapp.webhook_rejected').all()
    assert rows, 'a rejected webhook should leave an audit trail'


# ---------------------------------------------------------------------------
# Webhook behaviour, with verification stubbed to pass
# ---------------------------------------------------------------------------

@pytest.fixture
def signed(monkeypatch):
    monkeypatch.setattr(whatsapp, 'verify_request', lambda *a, **k: (True, ''))


def test_an_unlinked_number_is_told_how_to_link(client, app_context, signed):
    _enable(app_context.app)
    response = client.post(WEBHOOK, data={'From': 'whatsapp:+447000000000', 'Body': 'hello'})
    assert response.status_code == 200
    assert response.mimetype == 'application/xml'
    assert 'Link WhatsApp' in response.get_data(as_text=True)


def test_reply_is_well_formed_twiml(client, app_context, signed):
    """Message text must not be able to break out of the XML."""
    import xml.etree.ElementTree as ET

    _enable(app_context.app)
    _make_user(app_context)
    response = client.post(WEBHOOK, data={'From': 'whatsapp:' + PHONE, 'Body': '</Message><script>'})
    root = ET.fromstring(response.get_data(as_text=True))
    assert root.tag == 'Response'
    assert root.find('Message') is not None


def test_falls_back_to_keywords_when_the_assistant_is_unavailable(client, app_context, signed):
    _enable(app_context.app)
    _make_user(app_context)
    _make_request(app_context)
    response = client.post(WEBHOOK, data={'From': 'whatsapp:' + PHONE, 'Body': 'status'})
    body = response.get_data(as_text=True)
    assert 'PD-' in body and 'pending' in body


def test_reset_clears_the_conversation(client, app_context, signed):
    _enable(app_context.app)
    _make_user(app_context)
    with app_context.app.app_context():
        chatbot.save_history(PHONE, [{'role': 'user', 'content': 'earlier'}])
    client.post(WEBHOOK, data={'From': 'whatsapp:' + PHONE, 'Body': 'reset'})
    with app_context.app.app_context():
        assert chatbot.load_history(PHONE) == []


# ---------------------------------------------------------------------------
# Chatbot tools
# ---------------------------------------------------------------------------

def test_tools_are_unavailable_without_a_key(app_context):
    with app_context.app.app_context():
        app_context.app.config.update(CHATBOT_ENABLED=True, ANTHROPIC_API_KEY='')
        assert chatbot.is_available() is False
        assert chatbot.generate_reply(object(), [], 'hello') is None


def test_history_round_trips_and_is_bounded(app_context):
    with app_context.app.app_context():
        chatbot.reset_history('conv')
        chatbot.save_history('conv', [{'role': 'user', 'content': str(i)} for i in range(40)])
        stored = chatbot.load_history('conv')
    assert len(stored) == chatbot.MAX_HISTORY_TURNS
    assert stored[-1]['content'] == '39'


def test_search_and_status_tools_read_real_rows(app_context):
    user_id = _make_user(app_context)
    request_id = _make_request(app_context)
    with app_context.app.app_context():
        user = app_context.db.session.get(app_context.User, user_id)
        found = chatbot._tool_search_jobs(user, material='timber')
        assert found['count'] == 1
        assert found['jobs'][0]['request_id'] == request_id
        assert chatbot._tool_get_job_status(user, request_id)['status'] == 'pending'
        assert chatbot._tool_get_job_status(user, 999999)['error']


def test_completing_a_job_requires_the_assignment(app_context):
    user_id = _make_user(app_context, role='driver', email='driver@example.com')
    request_id = _make_request(app_context)
    with app_context.app.app_context():
        user = app_context.db.session.get(app_context.User, user_id)
        result = chatbot._tool_complete_job(user, request_id)
    assert 'not assigned to you' in result['error']


def test_claiming_requires_a_driver_role(app_context):
    user_id = _make_user(app_context)
    request_id = _make_request(app_context)
    with app_context.app.app_context():
        user = app_context.db.session.get(app_context.User, user_id)
        result = chatbot._tool_claim_job(user, request_id)
    assert 'Only a driver' in result['error']


def test_creating_a_request_rejects_a_past_date(app_context):
    user_id = _make_user(app_context)
    with app_context.app.app_context():
        user = app_context.db.session.get(app_context.User, user_id)
        result = chatbot._tool_create_request(
            user, material_type='Timber', waste_amount=1, waste_unit='tonnes',
            pickup_address='1 Site Road', pickup_postcode='SW1A1AA',
            scheduled_pickup_at='2020-01-01T09:00:00',
        )
    assert 'future' in result['error']


def test_a_failing_tool_reports_rather_than_raising(app_context):
    user_id = _make_user(app_context)
    with app_context.app.app_context():
        user = app_context.db.session.get(app_context.User, user_id)
        assert chatbot.run_tool('no_such_tool', {}, user)['error']


def test_listing_material_for_reuse_records_an_audit_event(app_context):
    user_id = _make_user(app_context)
    with app_context.app.app_context():
        user = app_context.db.session.get(app_context.User, user_id)
        result = chatbot._tool_list_reuse_material(
            user, waste_stream='Bricks', postcode='SW1A1AA', amount=40)
        assert result['listed'] is True
        rows = app_context.AuditEvent.query.filter(
            app_context.AuditEvent.action == 'material.create').all()
        assert rows and rows[-1].source == 'whatsapp_bot'


# ---------------------------------------------------------------------------
# Certificate
# ---------------------------------------------------------------------------

def test_certificate_is_not_public_until_the_job_is_complete(client, app_context):
    request_id = _make_request(app_context, status='pending')
    assert client.get('/certificate/{}'.format(request_id)).status_code == 404


def test_certificate_404s_for_an_unknown_request(client, app_context):
    assert client.get('/certificate/999999').status_code == 404


def test_certificate_renders_with_a_carbon_figure(client, app_context):
    request_id = _make_request(app_context, status='completed', material='Timber',
                               amount=2.0, unit='tonnes')
    response = client.get('/certificate/{}'.format(request_id))
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'Timber' in body
    assert 'PD-' in body
    assert 'CO<sub>2</sub>e avoided' in body


def test_certificate_figure_matches_the_lca_engine(client, app_context):
    """The page must not invent a number: it has to equal the engine's."""
    request_id = _make_request(app_context, status='completed', material='Timber',
                               amount=2.0, unit='tonnes')
    with app_context.app.app_context():
        from projectdivert.blueprints.certificates import _assess

        booking = app_context.db.session.get(app_context.WasteRemovalRequest, request_id)
        result, context = _assess(booking)
        expected = project_divert_lca.assess_diversion(
            'Timber', 2.0,
            collection_distance_km=context['collection_km'],
            landfill_distance_km=context['landfill_km'],
            pathway=context['pathway'],
        )
    assert result.net_avoided_kg == pytest.approx(expected.net_avoided_kg)


def test_certificate_does_not_claim_to_be_a_statutory_record(client, app_context):
    """It must not read as a waste transfer note or a DWT record."""
    request_id = _make_request(app_context, status='completed')
    body = client.get('/certificate/{}'.format(request_id)).get_data(as_text=True)
    assert 'not a waste transfer note' in body
    assert 'DWT-' not in body


def test_certificate_states_its_transport_assumption(client, app_context):
    request_id = _make_request(app_context, status='completed')
    body = client.get('/certificate/{}'.format(request_id)).get_data(as_text=True)
    assert 'landfill haul is assumed' in body
