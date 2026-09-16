"""WhatsApp transport (Twilio).

Sending and inbound-request verification are kept here so the webhook blueprint
stays thin and the chatbot never talks to Twilio directly.

Twilio is an optional dependency, like redis and boto3 elsewhere in this
package: the module imports and the application starts without it, and every
entry point degrades to a no-op that says why.
"""

import logging

from flask import current_app

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    from twilio.rest import Client as _TwilioClient
except Exception:  # pragma: no cover
    _TwilioClient = None

try:  # pragma: no cover - optional dependency
    from twilio.request_validator import RequestValidator as _RequestValidator
except Exception:  # pragma: no cover
    _RequestValidator = None


def _config(name, default=''):
    return str(current_app.config.get(name) or default).strip()


def account_sid():
    return _config('TWILIO_ACCOUNT_SID')


def auth_token():
    return _config('TWILIO_AUTH_TOKEN')


def whatsapp_from():
    return _config('TWILIO_WHATSAPP_FROM')


def is_configured():
    """True when Twilio credentials and a sending number are all present."""
    return bool(account_sid() and auth_token() and whatsapp_from())


def is_enabled():
    """The feature flag gating every WhatsApp entry point."""
    from projectdivert.services.utils import _is_truthy

    return bool(_is_truthy(current_app.config.get('WHATSAPP_ENABLED', False)))


def sdk_available():
    return _TwilioClient is not None


def normalise_number(value):
    """Strip the whatsapp: prefix and surrounding whitespace from a number."""
    number = str(value or '').strip()
    if number.lower().startswith('whatsapp:'):
        number = number[len('whatsapp:'):]
    return number.strip()


def verify_request(url, form, signature):
    """Verify an inbound Twilio webhook signature.

    The upstream implementation this was ported from trusted the ``From`` field
    unverified, which let anyone who knew the URL impersonate a linked user and
    act on their account. A request is accepted only when Twilio's HMAC over the
    exact URL and form fields matches.

    Returns (ok, reason). Fails closed whenever it cannot check properly.
    """
    if _RequestValidator is None:
        return False, 'twilio is not installed, so the signature cannot be verified'
    token = auth_token()
    if not token:
        return False, 'TWILIO_AUTH_TOKEN is not set, so the signature cannot be verified'
    if not signature:
        return False, 'request carried no X-Twilio-Signature header'
    try:
        valid = _RequestValidator(token).validate(url, form, signature)
    except Exception:
        logger.exception('Twilio signature validation raised.')
        return False, 'signature validation failed'
    if not valid:
        return False, 'signature did not match'
    return True, ''


def send_message(to_number, body):
    """Send a WhatsApp message. Returns the message SID, or None if not sent.

    Never raises: a notification that cannot be delivered must not fail the
    operation that triggered it.
    """
    if not is_enabled():
        logger.info('WhatsApp is disabled; not sending to %s', to_number)
        return None
    if _TwilioClient is None:
        logger.warning('twilio is not installed; cannot send WhatsApp message.')
        return None
    if not is_configured():
        logger.warning('Twilio is not fully configured; cannot send WhatsApp message.')
        return None

    number = normalise_number(to_number)
    if not number:
        return None

    try:
        client = _TwilioClient(account_sid(), auth_token())
        message = client.messages.create(
            body=str(body or '')[:1600],
            from_='whatsapp:{}'.format(normalise_number(whatsapp_from())),
            to='whatsapp:{}'.format(number),
        )
        logger.info('Sent WhatsApp message %s', message.sid)
        return message.sid
    except Exception:
        logger.exception('Sending a WhatsApp message failed.')
        return None
