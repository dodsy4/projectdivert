"""Server-sent event pub/sub for live waste-request updates."""

import json
import queue
import threading
from collections import deque
from datetime import datetime
from flask import current_app


_waste_request_event_subscribers = {}


_waste_request_event_lock = threading.Lock()


_waste_request_event_queue_size = 100


_waste_request_event_history = {}


_waste_request_event_sequence = 0


def _waste_request_event_history_size():
    """Per-stream history depth.

    Read lazily: importing this module must not require an application context.
    """
    try:
        configured = current_app.config.get('WASTE_REQUEST_STREAM_HISTORY_SIZE')
    except RuntimeError:  # outside an application context
        configured = None
    return max(20, int(configured or 200))


def _subscribe_waste_request_events(request_id):
    channel = queue.Queue(maxsize=_waste_request_event_queue_size)
    with _waste_request_event_lock:
        subscribers = _waste_request_event_subscribers.setdefault(request_id, set())
        subscribers.add(channel)
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


def _waste_request_replay_events_since(request_id, event_id):
    if event_id is None:
        return []
    with _waste_request_event_lock:
        history = list(_waste_request_event_history.get(request_id, ()))
    return [row for row in history if _parse_waste_request_last_event_id(row.get('event_id')) is not None and int(row['event_id']) > event_id]


def _publish_waste_request_event(request_id, event_name, payload=None, metadata=None):
    global _waste_request_event_sequence
    with _waste_request_event_lock:
        _waste_request_event_sequence += 1
        event_payload = {
            'event_id': _waste_request_event_sequence,
            'event': str(event_name or 'update').strip() or 'update',
            'request_id': request_id,
            'occurred_at': datetime.utcnow().isoformat() + 'Z',
            'payload': payload,
            'metadata': metadata or {},
        }
        history = _waste_request_event_history.setdefault(
            request_id,
            deque(maxlen=_waste_request_event_history_size()),
        )
        history.append(event_payload)
        channels = list(_waste_request_event_subscribers.get(request_id, set()))

    for channel in channels:
        try:
            channel.put_nowait(event_payload)
        except queue.Full:
            try:
                channel.get_nowait()
                channel.put_nowait(event_payload)
            except Exception:
                _unsubscribe_waste_request_events(request_id, channel)
        except Exception:
            _unsubscribe_waste_request_events(request_id, channel)


def _format_sse_event(event_name, payload, event_id=None):
    frame_lines = []
    if event_id is not None:
        frame_lines.append('id: {}'.format(event_id))
    frame_lines.append('event: {}'.format(event_name))
    frame_lines.append('data: {}'.format(json.dumps(payload, separators=(',', ':'))))
    return '\n'.join(frame_lines) + '\n\n'
