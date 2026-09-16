"""Inbound WhatsApp webhook.

Twilio POSTs an inbound message here; the reply goes back as TwiML in the
response body. The blueprint does three things and delegates everything else:
verify the request really came from Twilio, resolve the sender to a linked
user, and hand the message to the chatbot service.

The TwiML is built here rather than with ``twilio.twiml`` so that replying
works whether or not the SDK is installed. Signature verification does need the
SDK, and fails closed without it -- an unverified webhook would let anyone who
learned the URL act as a linked user.
"""

import logging
from xml.sax.saxutils import escape

from flask import Blueprint, Response, request

from projectdivert.models.user import User
from projectdivert.services import chatbot, whatsapp
from projectdivert.services.audit import record_audit_event

logger = logging.getLogger(__name__)

bp = Blueprint('api_whatsapp', __name__)

UNLINKED_REPLY = (
    "This number isn't linked to a Project Divert account yet. "
    "Open the app, go to Profile, and choose Link WhatsApp. "
    "Once it's linked you can book collections, claim jobs and check status here."
)

UNAVAILABLE_REPLY = (
    "The assistant is offline at the moment. You can still do everything in the "
    "Project Divert app, and we'll pick this up here once it's back."
)


def _twiml(message):
    """A minimal TwiML response. Escaped, so message text cannot break the XML."""
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response><Message>{}</Message></Response>'
    ).format(escape(str(message or '')))
    return Response(body, status=200, mimetype='application/xml')


def _fallback_reply(user, text):
    """Keyword replies for when the assistant is unavailable.

    Deliberately narrow: it answers what it is certain about and points at the
    app for anything else, rather than guessing at intent without a model.
    """
    lowered = (text or '').strip().lower()
    if lowered in ('help', 'hi', 'hello', 'start'):
        return (
            "Hi {}. The assistant is offline right now, but you can reply STATUS "
            "for your latest request, or JOBS if you're a driver."
        ).format(user.name or 'there')
    if lowered.startswith('status'):
        result = chatbot._tool_get_my_requests(user)
        if not result['count']:
            return "You have no collection requests on the system yet."
        latest = result['requests'][0]
        return "{} - {} at {} is currently {}.".format(
            latest['reference'], latest['material_type'],
            latest['pickup_postcode'], latest['status'])
    if lowered.startswith('jobs'):
        result = chatbot._tool_search_jobs(user, limit=5)
        if not result['count']:
            return "There are no open jobs right now."
        return "Open jobs:\n" + "\n".join(
            "{} {} at {}".format(j['reference'], j['material_type'], j['pickup_postcode'])
            for j in result['jobs']
        )
    return UNAVAILABLE_REPLY


@bp.route('/api/v1/whatsapp/inbound', methods=['POST'])
def api_whatsapp_inbound():
    if not whatsapp.is_enabled():
        logger.info('WhatsApp webhook called while the feature is disabled.')
        return Response('WhatsApp is not enabled', status=404, mimetype='text/plain')

    ok, reason = whatsapp.verify_request(
        request.url,
        request.form.to_dict(),
        request.headers.get('X-Twilio-Signature', ''),
    )
    if not ok:
        logger.warning('Rejected an inbound WhatsApp webhook: %s', reason)
        record_audit_event(
            action='whatsapp.webhook_rejected',
            entity_type='whatsapp',
            summary='Rejected inbound webhook: {}'.format(reason),
            status_code=403,
        )
        return Response('Signature verification failed', status=403, mimetype='text/plain')

    phone = whatsapp.normalise_number(request.form.get('From'))
    body = (request.form.get('Body') or '').strip()
    if not phone:
        return _twiml("Sorry, I couldn't tell which number that came from.")

    user = User.query.filter(User.phone == phone).first()
    if not user or not user.is_active_user:
        return _twiml(UNLINKED_REPLY)

    if body.lower() in ('reset', 'restart', 'forget'):
        chatbot.reset_history(phone)
        return _twiml("Cleared. What can I help with?")

    try:
        reply = chatbot.handle_message(user, phone, body)
    except Exception:
        logger.exception('The WhatsApp assistant failed for user %s', user.id)
        reply = None

    if reply is None:
        reply = _fallback_reply(user, body)

    return _twiml(reply)
