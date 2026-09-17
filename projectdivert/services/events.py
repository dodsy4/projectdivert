"""Server-sent event pub/sub for live waste-request updates.

Subscribers are necessarily per-process: an SSE stream is held open by one
worker, and the queue it reads from lives in that worker's memory. Publishing
is not -- a status change can come from any worker, from the RQ worker running
incident maintenance, or from the WhatsApp webhook. So the fan-out has to cross
process boundaries, or a customer watching a job never sees an update that
happened to be produced somewhere else.

With a Redis URL configured, a publish goes to a Redis channel and one relay
thread per process hands what it receives to that process's subscribers. Event
ids come from a Redis counter and history from a Redis list, so ids stay
monotonic across workers and a reconnect can be replayed by whichever worker
picks it up.

Without one -- local development, CI, the test suite -- everything stays in
process memory and behaves as a single-process application always did.
"""

import json
import queue
import threading
from collections import OrderedDict, deque
from datetime import datetime
try:
    import redis
except Exception:  # pragma: no cover - optional dependency
    redis = None
from flask import current_app
import logging

logger = logging.getLogger(__name__)


_waste_request_event_subscribers = {}


_waste_request_event_lock = threading.Lock()


_waste_request_event_queue_size = 100


#: Per-request event history for replay, keyed by request id. Only used when no
#: Redis URL is configured; bounded in both directions (deque per request, LRU
#: over request ids) because a long-lived process sees unboundedly many ids.
_waste_request_event_history = OrderedDict()


_waste_request_event_history_request_cap = 500


_waste_request_event_sequence = 0


_waste_request_event_redis_client = None


_waste_request_event_redis_disabled = False


_waste_request_event_relay_thread = None


_waste_request_event_relay_lock = threading.Lock()


def _waste_request_event_history_size():
    """Per-stream history depth.

    Read lazily: importing this module must not require an application context.
    """
    try:
        configured = current_app.config.get('WASTE_REQUEST_STREAM_HISTORY_SIZE')
    except RuntimeError:  # outside an application context
        configured = None
    return max(20, int(configured or 200))


def _waste_request_event_redis_url():
    """Redis URL for the event bus, falling back to the shared queue Redis."""
    try:
        config = current_app.config
    except RuntimeError:  # outside an application context
        return ''
    return str(
        config.get('WASTE_REQUEST_STREAM_REDIS_URL')
        or config.get('REDIS_URL')
        or config.get('RQ_REDIS_URL')
        or ''
    ).strip()


def _waste_request_event_redis_prefix():
    try:
        value = str(current_app.config.get('WASTE_REQUEST_STREAM_REDIS_PREFIX') or '').strip()
    except RuntimeError:  # outside an application context
        value = ''
    return value or 'projectdivert:waste-request-events'


def _waste_request_event_history_ttl_seconds():
    try:
        configured = current_app.config.get('WASTE_REQUEST_STREAM_HISTORY_TTL_SECONDS')
    except RuntimeError:  # outside an application context
        configured = None
    try:
        return max(60, int(configured or 3600))
    except (TypeError, ValueError):
        return 3600


def _waste_request_event_channel():
    return '{}:channel'.format(_waste_request_event_redis_prefix())


def _waste_request_event_sequence_key():
    return '{}:sequence'.format(_waste_request_event_redis_prefix())


def _waste_request_event_history_key(request_id):
    return '{}:history:{}'.format(_waste_request_event_redis_prefix(), request_id)


def _get_waste_request_event_redis_client():
    """Return a connected Redis client, or ``None`` to use in-process delivery."""
    global _waste_request_event_redis_client
    global _waste_request_event_redis_disabled

    if _waste_request_event_redis_disabled:
        return None
    if _waste_request_event_redis_client is not None:
        return _waste_request_event_redis_client

    redis_url = _waste_request_event_redis_url()
    if not redis_url or redis is None:
        if redis_url and redis is None:
            logger.warning(
                'A Redis URL is configured but the redis package is unavailable; '
                'waste request events will not cross worker processes.',
            )
        _waste_request_event_redis_disabled = True
        return None

    try:
        client = redis.Redis.from_url(redis_url, decode_responses=True)
        client.ping()
        _waste_request_event_redis_client = client
        logger.info('Waste request event stream using Redis backend.')
        return _waste_request_event_redis_client
    except Exception:
        _waste_request_event_redis_disabled = True
        logger.exception(
            'Failed to initialize Redis for the waste request event stream; '
            'falling back to in-process delivery.',
        )
        return None


def _deliver_to_local_subscribers(request_id, event_payload):
    """Hand an event to the SSE streams open in this process."""
    with _waste_request_event_lock:
        channels = list(_waste_request_event_subscribers.get(request_id, set()))

    for channel in channels:
        try:
            channel.put_nowait(event_payload)
        except queue.Full:
            # A stream that is not keeping up loses its oldest event rather
            # than blocking the publisher.
            try:
                channel.get_nowait()
                channel.put_nowait(event_payload)
            except Exception:
                _unsubscribe_waste_request_events(request_id, channel)
        except Exception:
            _unsubscribe_waste_request_events(request_id, channel)


def _relay_waste_request_events(client, channel_name):
    """Relay events published by any process to this process's subscribers."""
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(channel_name)
    for message in pubsub.listen():
        try:
            if message.get('type') != 'message':
                continue
            event_payload = json.loads(message.get('data') or '{}')
            request_id = event_payload.get('request_id')
            if request_id is None:
                continue
            _deliver_to_local_subscribers(request_id, event_payload)
        except Exception:
            logger.exception('Failed to relay a waste request event.')


def _ensure_waste_request_event_relay():
    """Start this process's relay thread once, if Redis is in use."""
    global _waste_request_event_relay_thread

    client = _get_waste_request_event_redis_client()
    if client is None:
        return

    with _waste_request_event_relay_lock:
        if _waste_request_event_relay_thread is not None and _waste_request_event_relay_thread.is_alive():
            return
        channel_name = _waste_request_event_channel()
        thread = threading.Thread(
            target=_relay_waste_request_events,
            args=(client, channel_name),
            name='waste-request-event-relay',
            daemon=True,
        )
        _waste_request_event_relay_thread = thread
        thread.start()
        logger.info('Waste request event relay listening on %s.', channel_name)


def _subscribe_waste_request_events(request_id):
    channel = queue.Queue(maxsize=_waste_request_event_queue_size)
    with _waste_request_event_lock:
        subscribers = _waste_request_event_subscribers.setdefault(request_id, set())
        subscribers.add(channel)
    # Only a process holding a stream open needs to listen for what other
    # processes publish.
    _ensure_waste_request_event_relay()
    return channel


def _unsubscribe_waste_request_events(request_id, channel):
    with _waste_request_event_lock:
        subscribers = _waste_request_event_subscribers.get(request_id)
        if not subscribers:
            return
        subscribers.discard(channel)
        if not subscribers:
            _waste_request_event_subscribers.pop(request_id, None)


def _parse_waste_request_last_event_id(value):
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def _record_waste_request_event_history_memory(request_id, event_payload):
    with _waste_request_event_lock:
        history = _waste_request_event_history.get(request_id)
        if history is None:
            history = deque(maxlen=_waste_request_event_history_size())
            _waste_request_event_history[request_id] = history
        history.append(event_payload)
        _waste_request_event_history.move_to_end(request_id)
        while len(_waste_request_event_history) > _waste_request_event_history_request_cap:
            _waste_request_event_history.popitem(last=False)


def _waste_request_replay_events_since(request_id, event_id):
    if event_id is None:
        return []

    client = _get_waste_request_event_redis_client()
    if client is not None:
        try:
            raw_rows = client.lrange(_waste_request_event_history_key(request_id), 0, -1)
            history = [json.loads(row) for row in raw_rows]
        except Exception:
            logger.exception(
                'Failed to read waste request event history from Redis for request_id=%s.',
                request_id,
            )
            history = []
    else:
        with _waste_request_event_lock:
            history = list(_waste_request_event_history.get(request_id, ()))

    return [
        row for row in history
        if _parse_waste_request_last_event_id(row.get('event_id')) is not None
        and int(row['event_id']) > event_id
    ]


def _next_waste_request_event_id(client):
    """Allocate a monotonic event id, shared across workers when Redis is used."""
    global _waste_request_event_sequence

    if client is not None:
        try:
            return int(client.incr(_waste_request_event_sequence_key()))
        except Exception:
            logger.exception('Failed to allocate a waste request event id from Redis.')

    with _waste_request_event_lock:
        _waste_request_event_sequence += 1
        return _waste_request_event_sequence


def _publish_waste_request_event(request_id, event_name, payload=None, metadata=None):
    client = _get_waste_request_event_redis_client()
    event_payload = {
        'event_id': _next_waste_request_event_id(client),
        'event': str(event_name or 'update').strip() or 'update',
        'request_id': request_id,
        'occurred_at': datetime.utcnow().isoformat() + 'Z',
        'payload': payload,
        'metadata': metadata or {},
    }

    if client is not None:
        try:
            serialized = json.dumps(event_payload, separators=(',', ':'), default=str)
            history_key = _waste_request_event_history_key(request_id)
            pipeline = client.pipeline()
            pipeline.rpush(history_key, serialized)
            pipeline.ltrim(history_key, -_waste_request_event_history_size(), -1)
            pipeline.expire(history_key, _waste_request_event_history_ttl_seconds())
            pipeline.publish(_waste_request_event_channel(), serialized)
            pipeline.execute()
            # The relay thread delivers to this process's subscribers too, so
            # returning here is what keeps a local stream from seeing the event
            # twice.
            return
        except Exception:
            logger.exception(
                'Failed to publish waste request event %s for request_id=%s to Redis; '
                'delivering in-process only.',
                event_payload['event'],
                request_id,
            )

    _record_waste_request_event_history_memory(request_id, event_payload)
    _deliver_to_local_subscribers(request_id, event_payload)


def _format_sse_event(event_name, payload, event_id=None):
    frame_lines = []
    if event_id is not None:
        frame_lines.append('id: {}'.format(event_id))
    frame_lines.append('event: {}'.format(event_name))
    frame_lines.append('data: {}'.format(json.dumps(payload, separators=(',', ':'), default=str)))
    return '\n'.join(frame_lines) + '\n\n'
