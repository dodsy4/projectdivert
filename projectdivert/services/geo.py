"""Geocoding and road-distance helpers."""

import logging
import math
import re
import threading
from collections import OrderedDict

import requests
from flask import current_app

import project_divert_lca
from project_divert_functions import numeric_distance
from projectdivert.services.utils import _to_float_or_none, _to_int_or_none

logger = logging.getLogger(__name__)

POSTCODE_LOOKUP_URL = 'https://api.postcodes.io/postcodes/{}'

#: A postcode's coordinates do not change, so they are worth remembering rather
#: than asking postcodes.io again on every single booking. Per process, which is
#: fine for immutable data: a second worker simply builds its own copy.
_POSTCODE_CACHE_MAX_ENTRIES = 2048
_postcode_coordinate_cache = OrderedDict()
_postcode_cache_lock = threading.Lock()


class PostcodeLookupUnavailable(RuntimeError):
    """The postcode service could not be reached or gave an unusable answer.

    Distinct from :class:`ValueError`, which means the postcode itself is not
    valid. The difference matters because callers turn a ValueError into a 400
    aimed at the person filling the form, and this is not their fault.
    """


def normalize_postcode(postcode):
    """Upper-case and strip all whitespace, so 'sw1a 1aa' and 'SW1A1AA' agree."""
    return re.sub(r'\s+', '', str(postcode or '')).upper()


def clear_postcode_cache():
    """Forget every cached lookup. Used by the test suite between cases."""
    with _postcode_cache_lock:
        _postcode_coordinate_cache.clear()


def _cached_postcode_coordinates(key):
    with _postcode_cache_lock:
        coordinates = _postcode_coordinate_cache.get(key)
        if coordinates is not None:
            _postcode_coordinate_cache.move_to_end(key)
        return coordinates


def _store_postcode_coordinates(key, coordinates):
    with _postcode_cache_lock:
        _postcode_coordinate_cache[key] = coordinates
        _postcode_coordinate_cache.move_to_end(key)
        while len(_postcode_coordinate_cache) > _POSTCODE_CACHE_MAX_ENTRIES:
            _postcode_coordinate_cache.popitem(last=False)


def _postcode_coordinates(postcode):
    """Look up a UK postcode's latitude and longitude.

    Raises :class:`ValueError` when the postcode is not one postcodes.io knows,
    and :class:`PostcodeLookupUnavailable` when the service itself is the
    problem -- a timeout, a 5xx, or a response that is not the JSON expected.
    Previously both arrived as the same generic failure, so an outage looked
    identical to a typo.
    """
    key = normalize_postcode(postcode)
    if not key:
        raise ValueError('Please enter a valid pickup postcode.')

    cached = _cached_postcode_coordinates(key)
    if cached is not None:
        return cached

    try:
        response = requests.get(POSTCODE_LOOKUP_URL.format(key), timeout=10)
    except requests.RequestException as exc:
        logger.warning('Postcode lookup failed for %s: %s', key, exc)
        raise PostcodeLookupUnavailable(
            'The postcode lookup service is unavailable.'
        ) from exc

    # A 404 is postcodes.io saying it does not know the postcode, which is the
    # caller's problem; anything else in the 4xx/5xx range is the service's.
    status_code = getattr(response, 'status_code', 200)
    if status_code == 404:
        raise ValueError('Please enter a valid pickup postcode.')
    if status_code >= 400:
        logger.warning('Postcode lookup returned status %s for %s', status_code, key)
        raise PostcodeLookupUnavailable(
            'The postcode lookup service is unavailable.'
        )

    try:
        payload = response.json()
    except Exception as exc:
        # json() raises a subclass of ValueError, which would otherwise be
        # reported to the user as though they had mistyped the postcode.
        logger.warning('Postcode lookup returned unparseable JSON for %s: %s', key, exc)
        raise PostcodeLookupUnavailable(
            'The postcode lookup service returned an unreadable response.'
        ) from exc

    result = payload.get('result') if isinstance(payload, dict) else None
    if not result:
        raise ValueError('Please enter a valid pickup postcode.')

    longitude = _to_float_or_none(result.get('longitude'))
    latitude = _to_float_or_none(result.get('latitude'))
    if longitude is None or latitude is None:
        raise ValueError('Please enter a valid pickup postcode.')

    coordinates = (latitude, longitude)
    _store_postcode_coordinates(key, coordinates)
    return coordinates


def _haversine_miles(lat1, lon1, lat2, lon2):
    radius_miles = 3958.8
    lat1_r = math.radians(lat1)
    lon1_r = math.radians(lon1)
    lat2_r = math.radians(lat2)
    lon2_r = math.radians(lon2)
    delta_lat = lat2_r - lat1_r
    delta_lon = lon2_r - lon1_r
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return radius_miles * c


def _drive_time_between_points(origin_latitude, origin_longitude, dest_latitude, dest_longitude):
    api_key = (current_app.config.get('GOOGLE_MAPS_API_KEY') or '').strip()
    if not api_key:
        return None

    endpoint = 'https://maps.googleapis.com/maps/api/distancematrix/json'
    params = {
        'units': 'imperial',
        'key': api_key,
        'origins': '{},{}'.format(origin_latitude, origin_longitude),
        'destinations': '{},{}'.format(dest_latitude, dest_longitude),
    }
    try:
        response = requests.get(endpoint, params=params, timeout=10)
        payload = response.json()
        if payload.get('status') != 'OK':
            return None
        rows = payload.get('rows') or []
        if not rows:
            return None
        elements = rows[0].get('elements') or []
        if not elements or elements[0].get('status') != 'OK':
            return None
        duration = elements[0].get('duration') or {}
        seconds = _to_int_or_none(duration.get('value'))
        text = (duration.get('text') or '').strip() or None
        if seconds is None:
            return None
        return {
            'minutes': round(seconds / 60.0, 1),
            'text': text or '{} mins'.format(round(seconds / 60.0)),
        }
    except Exception:
        return None


def _distance_km_or_error(origin, destination, label):
    miles = numeric_distance(origin, destination, return_none_on_failure=True)
    if miles is None:
        raise ValueError(
            'Could not calculate the {} transport distance because the Google Maps '
            'Distance Matrix API is unavailable. Check the API key and billing.'.format(label)
        )
    return float(miles) * project_divert_lca.MILES_TO_KM
