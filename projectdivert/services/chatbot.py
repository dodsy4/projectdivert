"""Claude-powered conversational interface over the dispatch domain.

A site manager or driver messages in plain English; Claude drives an agentic
loop over a small set of tools, each of which is a thin wrapper over the same
service functions the JSON API uses. Nothing here reimplements domain rules --
completing a job runs the same compliance gate as ``POST /waste-requests/{id}
/status``, and claiming one goes through ``_accept_dispatch_offer`` -- so the
conversational path cannot drift away from the API path.

Every state change the assistant makes is written to the audit trail with
``source='whatsapp_bot'``, so an action taken by the assistant is as traceable
as one taken through the app.

Both the Anthropic SDK and a configured API key are optional: without either,
:func:`generate_reply` returns ``None`` and the caller falls back.
"""

import json
import logging
import time
from datetime import datetime

from flask import current_app

from projectdivert.extensions import db
from projectdivert.models.catalog import Material
from projectdivert.models.user import User
from projectdivert.models.waste import WasteRemovalRequest, WasteRemovalDispatchOffer
from projectdivert.services.audit import record_audit_event
from projectdivert.services.compliance import (
    COMPLIANCE_COMPLETION_REQUIRED_TYPES,
    _compliance_documents_for_request,
    _compliance_missing_required_document_types,
    _compliance_summary_for_documents,
)
from projectdivert.services.dispatch import (
    _accept_dispatch_offer,
    _create_dispatch_offers_for_request,
    _get_latest_match_for_request,
)
from projectdivert.services.geo import _postcode_coordinates
from projectdivert.services.utils import _is_truthy, _to_float_or_none, _to_int_or_none

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    import anthropic as _anthropic
except Exception:  # pragma: no cover
    _anthropic = None

DEFAULT_MODEL = 'claude-haiku-4-5-20251001'
MAX_TOOL_ROUNDS = 6
MAX_HISTORY_TURNS = 20
DEFAULT_HISTORY_TTL_SECONDS = 3600

# ---------------------------------------------------------------------------
# Conversation store
#
# Redis when configured, an in-process dict otherwise -- the same fallback the
# auth rate limiter uses. The upstream implementation kept history in a plain
# module dict, which silently splits a conversation across gunicorn workers.
# ---------------------------------------------------------------------------

_memory_history = {}
_redis_client = None
_redis_disabled = False


def _history_ttl():
    return _to_int_or_none(current_app.config.get('CHATBOT_HISTORY_TTL_SECONDS')) \
        or DEFAULT_HISTORY_TTL_SECONDS


def _history_key(conversation_id):
    prefix = str(current_app.config.get('CHATBOT_REDIS_PREFIX') or 'projectdivert:chat')
    return '{}:{}'.format(prefix, conversation_id)


def _get_redis():
    global _redis_client, _redis_disabled
    if _redis_disabled:
        return None
    if _redis_client is not None:
        return _redis_client
    url = str(
        current_app.config.get('CHATBOT_REDIS_URL')
        or current_app.config.get('RQ_REDIS_URL')
        or current_app.config.get('REDIS_URL')
        or ''
    ).strip()
    if not url:
        _redis_disabled = True
        return None
    try:
        from redis import Redis

        client = Redis.from_url(url)
        client.ping()
        _redis_client = client
        return client
    except Exception:
        logger.warning('Chatbot history falling back to in-process storage.', exc_info=True)
        _redis_disabled = True
        return None


def load_history(conversation_id):
    """Return the stored message list for a conversation, or []."""
    client = _get_redis()
    if client is not None:
        try:
            raw = client.get(_history_key(conversation_id))
            return json.loads(raw) if raw else []
        except Exception:
            logger.exception('Reading chatbot history failed; starting a fresh conversation.')
            return []

    entry = _memory_history.get(conversation_id)
    if entry and (time.time() - entry['last_active']) < _history_ttl():
        return entry['messages']
    _memory_history.pop(conversation_id, None)
    return []


def save_history(conversation_id, messages):
    """Persist the last MAX_HISTORY_TURNS messages, bounding token cost."""
    trimmed = messages[-MAX_HISTORY_TURNS:]
    client = _get_redis()
    if client is not None:
        try:
            client.setex(_history_key(conversation_id), _history_ttl(), json.dumps(trimmed, default=str))
            return
        except Exception:
            logger.exception('Writing chatbot history failed.')
            return
    _memory_history[conversation_id] = {'messages': trimmed, 'last_active': time.time()}


def reset_history(conversation_id):
    client = _get_redis()
    if client is not None:
        try:
            client.delete(_history_key(conversation_id))
        except Exception:
            logger.exception('Clearing chatbot history failed.')
    _memory_history.pop(conversation_id, None)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

TOOLS = [
    {
        'name': 'search_jobs',
        'description': 'Search waste collection requests that are still awaiting a driver.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'material': {'type': 'string', 'description': 'Material keyword, e.g. "timber", "plasterboard".'},
                'postcode': {'type': 'string', 'description': 'UK postcode or prefix, e.g. "EC2M".'},
                'limit': {'type': 'integer', 'description': 'Maximum results, default 5.'},
            },
        },
    },
    {
        'name': 'get_job_status',
        'description': 'Get the current status and details of one request by its numeric id.',
        'input_schema': {
            'type': 'object',
            'properties': {'request_id': {'type': 'integer'}},
            'required': ['request_id'],
        },
    },
    {
        'name': 'get_my_requests',
        'description': 'List collection requests the current user raised as a customer.',
        'input_schema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'get_my_jobs',
        'description': 'List jobs assigned to the current user as a driver.',
        'input_schema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'claim_job',
        'description': 'Claim an available job for the current driver. Confirm with the user first.',
        'input_schema': {
            'type': 'object',
            'properties': {'request_id': {'type': 'integer'}},
            'required': ['request_id'],
        },
    },
    {
        'name': 'complete_job',
        'description': (
            'Mark a job the current driver is assigned to as completed. Fails if the '
            'required compliance documents have not been verified.'
        ),
        'input_schema': {
            'type': 'object',
            'properties': {'request_id': {'type': 'integer'}},
            'required': ['request_id'],
        },
    },
    {
        'name': 'create_request',
        'description': (
            'Raise a waste collection request for the current user. Confirm every '
            'detail with the user before calling this.'
        ),
        'input_schema': {
            'type': 'object',
            'properties': {
                'material_type': {'type': 'string'},
                'waste_amount': {'type': 'number'},
                'waste_unit': {'type': 'string', 'description': 'tonnes, kg, per item or square metres.'},
                'pickup_address': {'type': 'string'},
                'pickup_postcode': {'type': 'string'},
                'scheduled_pickup_at': {'type': 'string', 'description': 'ISO 8601 date/time in the future.'},
                'notes': {'type': 'string'},
            },
            'required': [
                'material_type', 'waste_amount', 'waste_unit',
                'pickup_address', 'pickup_postcode', 'scheduled_pickup_at',
            ],
        },
    },
    {
        'name': 'list_reuse_material',
        'description': (
            'List a material on the reuse marketplace instead of sending it for '
            'disposal. Confirm the details with the user before calling this.'
        ),
        'input_schema': {
            'type': 'object',
            'properties': {
                'waste_stream': {'type': 'string'},
                'amount': {'type': 'integer'},
                'address': {'type': 'string'},
                'postcode': {'type': 'string'},
                'condition': {'type': 'string'},
                'dimensions': {'type': 'string'},
            },
            'required': ['waste_stream', 'postcode'],
        },
    },
]


def _summarise_request(booking):
    return {
        'request_id': booking.id,
        'reference': 'PD-{:05d}'.format(booking.id),
        'material_type': booking.material_type,
        'waste_amount': booking.waste_amount,
        'waste_unit': booking.waste_unit,
        'pickup_address': booking.pickup_address,
        'pickup_postcode': booking.pickup_postcode,
        'scheduled_pickup_at': booking.scheduled_pickup_at.isoformat() if booking.scheduled_pickup_at else None,
        'status': booking.status,
        'assigned': bool(booking.assigned_driver_user_id),
    }


def _tool_search_jobs(user, material=None, postcode=None, limit=5):
    limit = max(1, min(int(limit or 5), 20))
    query = WasteRemovalRequest.query.filter(
        WasteRemovalRequest.status == 'pending',
        WasteRemovalRequest.assigned_driver_user_id.is_(None),
    )
    if material:
        query = query.filter(WasteRemovalRequest.material_type.ilike('%{}%'.format(str(material).strip())))
    if postcode:
        query = query.filter(
            WasteRemovalRequest.pickup_postcode.ilike('{}%'.format(str(postcode).strip().replace(' ', '')))
        )
    rows = query.order_by(WasteRemovalRequest.scheduled_pickup_at.asc()).limit(limit).all()
    return {'count': len(rows), 'jobs': [_summarise_request(r) for r in rows]}


def _tool_get_job_status(user, request_id):
    booking = db.session.get(WasteRemovalRequest, _to_int_or_none(request_id))
    if not booking:
        return {'error': 'No request found with id {}.'.format(request_id)}
    return _summarise_request(booking)


def _tool_get_my_requests(user):
    rows = (
        WasteRemovalRequest.query
        .filter(WasteRemovalRequest.requester_email == (user.email or '').lower())
        .order_by(WasteRemovalRequest.id.desc())
        .limit(10)
        .all()
    )
    return {'count': len(rows), 'requests': [_summarise_request(r) for r in rows]}


def _tool_get_my_jobs(user):
    rows = (
        WasteRemovalRequest.query
        .filter(WasteRemovalRequest.assigned_driver_user_id == user.id)
        .order_by(WasteRemovalRequest.id.desc())
        .limit(10)
        .all()
    )
    return {'count': len(rows), 'jobs': [_summarise_request(r) for r in rows]}


_CLAIM_OUTCOME_ERRORS = {
    'already_matched': 'Someone else has already been matched to that job.',
    'driver_mismatch': 'That job is assigned to a different driver.',
    'offer_unavailable': 'That dispatch offer is no longer available.',
    'invalid_offer': 'That dispatch offer is not valid for this job.',
}


def _tool_claim_job(user, request_id):
    if user.role not in ('driver', 'admin'):
        return {'error': 'Only a driver can claim a job.'}
    booking = db.session.get(WasteRemovalRequest, _to_int_or_none(request_id))
    if not booking:
        return {'error': 'No request found with id {}.'.format(request_id)}

    offer = (
        WasteRemovalDispatchOffer.query
        .filter(
            WasteRemovalDispatchOffer.waste_removal_request_id == booking.id,
            WasteRemovalDispatchOffer.status == 'offered',
        )
        .order_by(WasteRemovalDispatchOffer.offer_rank.asc())
        .first()
    )
    if not offer:
        return {'error': 'That job has no open dispatch offer left to claim.'}

    # The second value is an outcome, not an error flag: only 'accepted' is a
    # claim. The others are mapped to the same messages the JSON API gives.
    _match, outcome = _accept_dispatch_offer(booking, offer, assigned_driver_user_id=user.id)
    if outcome != 'accepted':
        return {'error': _CLAIM_OUTCOME_ERRORS.get(
            outcome, 'Could not claim that job ({}).'.format(outcome))}

    record_audit_event(
        action='dispatch_offer.accept',
        entity_type='waste_request',
        entity_id=booking.id,
        summary='Claimed via the WhatsApp assistant',
        source='whatsapp_bot',
    )
    db.session.commit()
    return {'claimed': True, 'request': _summarise_request(booking)}


def _tool_complete_job(user, request_id):
    booking = db.session.get(WasteRemovalRequest, _to_int_or_none(request_id))
    if not booking:
        return {'error': 'No request found with id {}.'.format(request_id)}
    if user.role != 'admin' and booking.assigned_driver_user_id != user.id:
        return {'error': 'That job is not assigned to you.'}
    if not _get_latest_match_for_request(booking.id):
        return {'error': 'No provider has accepted this request yet.'}

    # The same gate the JSON API applies, so the two paths cannot diverge.
    documents = _compliance_documents_for_request(booking.id)
    summary = _compliance_summary_for_documents(documents)
    missing = _compliance_missing_required_document_types(summary, COMPLIANCE_COMPLETION_REQUIRED_TYPES)
    if missing:
        return {
            'error': 'Compliance review is incomplete, so this job cannot be completed yet.',
            'missing_document_types': missing,
        }

    previous = booking.status
    booking.status = 'completed'
    db.session.commit()
    record_audit_event(
        action='waste_request.status_change',
        entity_type='waste_request',
        entity_id=booking.id,
        summary='Status {} -> completed via the WhatsApp assistant'.format(previous),
        changes={'status': [previous, 'completed']},
        source='whatsapp_bot',
    )
    db.session.commit()
    return {'completed': True, 'request': _summarise_request(booking)}


def _tool_create_request(user, **fields):
    amount = _to_float_or_none(fields.get('waste_amount'))
    if amount is None or amount <= 0:
        return {'error': 'The amount must be a positive number.'}

    raw_when = str(fields.get('scheduled_pickup_at') or '').strip()
    try:
        scheduled = datetime.fromisoformat(raw_when.replace('Z', '+00:00'))
        if scheduled.tzinfo is not None:
            scheduled = scheduled.replace(tzinfo=None)
    except ValueError:
        return {'error': 'I could not read that collection date. Ask for a date and time.'}
    if scheduled <= datetime.utcnow():
        return {'error': 'The collection date needs to be in the future.'}

    postcode = str(fields.get('pickup_postcode') or '').strip()
    try:
        latitude, longitude = _postcode_coordinates(postcode)
    except Exception:
        return {'error': 'That postcode did not look valid. Ask the user to check it.'}

    booking = WasteRemovalRequest(
        requester_name=(user.name or user.email or 'WhatsApp user')[:120],
        requester_email=(user.email or '')[:255].lower(),
        material_type=str(fields.get('material_type') or '')[:120],
        waste_amount=amount,
        waste_unit=str(fields.get('waste_unit') or 'tonnes')[:32],
        pickup_address=str(fields.get('pickup_address') or '')[:255],
        pickup_postcode=postcode[:32],
        scheduled_pickup_at=scheduled,
        notes=(str(fields.get('notes') or '').strip() or None),
        status='pending',
    )
    db.session.add(booking)
    db.session.commit()

    radius = _to_float_or_none(current_app.config.get('WHATSAPP_DEFAULT_MATCH_RADIUS_MILES')) or 25.0
    try:
        _create_dispatch_offers_for_request(booking, latitude, longitude, radius)
        db.session.commit()
    except Exception:
        logger.exception('Creating dispatch offers for request %s failed.', booking.id)

    record_audit_event(
        action='waste_request.create',
        entity_type='waste_request',
        entity_id=booking.id,
        summary='Raised via the WhatsApp assistant',
        source='whatsapp_bot',
    )
    db.session.commit()
    return {'created': True, 'request': _summarise_request(booking)}


def _tool_list_reuse_material(user, **fields):
    material = Material(
        waste_stream=str(fields.get('waste_stream') or '')[:120],
        amount=_to_int_or_none(fields.get('amount')),
        address=str(fields.get('address') or '')[:120] or None,
        postcode=str(fields.get('postcode') or '')[:120],
        condition=str(fields.get('condition') or '')[:120] or None,
        dimensions=str(fields.get('dimensions') or '')[:120] or None,
    )
    db.session.add(material)
    db.session.commit()
    record_audit_event(
        action='material.create',
        entity_type='material',
        entity_id=material.id,
        summary='Listed for reuse via the WhatsApp assistant',
        source='whatsapp_bot',
    )
    db.session.commit()
    return {
        'listed': True,
        'material_id': material.id,
        'waste_stream': material.waste_stream,
        'postcode': material.postcode,
    }


_TOOL_DISPATCH = {
    'search_jobs': lambda user, i: _tool_search_jobs(
        user, material=i.get('material'), postcode=i.get('postcode'), limit=i.get('limit', 5)),
    'get_job_status': lambda user, i: _tool_get_job_status(user, i.get('request_id')),
    'get_my_requests': lambda user, i: _tool_get_my_requests(user),
    'get_my_jobs': lambda user, i: _tool_get_my_jobs(user),
    'claim_job': lambda user, i: _tool_claim_job(user, i.get('request_id')),
    'complete_job': lambda user, i: _tool_complete_job(user, i.get('request_id')),
    'create_request': lambda user, i: _tool_create_request(user, **i),
    'list_reuse_material': lambda user, i: _tool_list_reuse_material(user, **i),
}


def run_tool(name, tool_input, user):
    """Execute one tool call, returning a JSON-serialisable result."""
    handler = _TOOL_DISPATCH.get(name)
    if handler is None:
        return {'error': 'Unknown tool {}.'.format(name)}
    try:
        return handler(user, dict(tool_input or {}))
    except Exception:
        logger.exception('Chatbot tool %s failed.', name)
        db.session.rollback()
        return {'error': 'That did not work. Tell the user to try again shortly.'}


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------

def is_enabled():
    return bool(_is_truthy(current_app.config.get('CHATBOT_ENABLED', False)))


def api_key():
    return str(current_app.config.get('ANTHROPIC_API_KEY') or '').strip()


def is_available():
    """True when the SDK is installed, a key is set and the feature is on."""
    return bool(_anthropic is not None and api_key() and is_enabled())


def build_system_prompt(user):
    live = _tool_search_jobs(user, limit=10)
    if live['jobs']:
        lines = '\n'.join(
            '  {} | {} | {} {} | {}'.format(
                j['reference'], j['material_type'], j['waste_amount'], j['waste_unit'], j['pickup_postcode'])
            for j in live['jobs']
        )
        live_context = 'Open jobs right now (authoritative, never invent others):\n{}\n'.format(lines)
    else:
        live_context = 'Open jobs right now: none.\n'

    return (
        'You are the Project Divert dispatcher, assisting over WhatsApp with UK '
        'construction and office waste diversion.\n\n'
        'Current user: {name} (role: {role}).\n\n'
        '{live}\n'
        'What the platform does: it connects site managers who have waste to remove '
        'with licensed carriers, quantifies the carbon avoided by diverting that '
        'material from landfill, and tracks the statutory paperwork for each '
        'collection. Managers can book a collection, or list material for reuse '
        'instead of disposal. Drivers claim open jobs and complete them once the '
        'compliance documents are in order.\n\n'
        'How to reply:\n'
        '1. Write like a person texting. Short: one to four sentences.\n'
        '2. Plain text only. No markdown, no bullet lists, no headers.\n'
        '3. Ask for one or two missing details at a time, never a long form.\n'
        '4. Only mention jobs from the list above. Never invent a job or a reference.\n'
        '5. Read every detail back and get a clear yes before calling create_request, '
        'list_reuse_material, claim_job or complete_job.\n'
        '6. Never state a carbon figure yourself; the certificate is the source of truth.\n'
        '7. No emoji unless the user uses one first.\n'
        '8. If a tool returns an error, say plainly what went wrong and what would fix it.'
    ).format(name=user.name or 'there', role=user.role, live=live_context)


def generate_reply(user, history, user_message):
    """Run the agentic loop. Returns (reply_text, messages) or None if unavailable."""
    if not is_available():
        return None

    client = _anthropic.Anthropic(api_key=api_key())
    model = str(current_app.config.get('ANTHROPIC_MODEL') or DEFAULT_MODEL)
    system = build_system_prompt(user)
    messages = list(history) + [{'role': 'user', 'content': user_message}]

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=model,
            max_tokens=512,
            system=system,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({'role': 'assistant', 'content': [b.to_dict() if hasattr(b, 'to_dict') else b
                                                          for b in response.content]})

        if response.stop_reason == 'tool_use':
            results = []
            for block in response.content:
                if getattr(block, 'type', None) != 'tool_use':
                    continue
                results.append({
                    'type': 'tool_result',
                    'tool_use_id': block.id,
                    'content': json.dumps(run_tool(block.name, block.input, user), default=str),
                })
            messages.append({'role': 'user', 'content': results})
            continue

        text = ' '.join(
            getattr(block, 'text', '') for block in response.content
            if getattr(block, 'type', None) == 'text'
        ).strip()
        return text, messages

    logger.warning('Chatbot hit the tool-round limit for user %s', user.id)
    return ('Sorry, I got stuck on that one. Try rephrasing, or use the app.', messages)


def handle_message(user, conversation_id, user_message):
    """Full turn: load history, answer, persist. Returns the reply text."""
    history = load_history(conversation_id)
    outcome = generate_reply(user, history, user_message)
    if outcome is None:
        return None
    reply, messages = outcome
    save_history(conversation_id, messages)
    return reply
