"""Geocoding and road-distance helpers."""

import requests
from flask import current_app
import project_divert_lca
import math
from project_divert_functions import numeric_distance
from projectdivert.services.utils import _to_float_or_none, _to_int_or_none


def _postcode_coordinates(postcode):
    endpoint = "http://api.postcodes.io/postcodes/{}".format(postcode)
    response = requests.get(endpoint, timeout=10)
    payload = response.json()
    result = payload.get('result') if isinstance(payload, dict) else None
    if not result:
        raise ValueError('Please enter a valid pickup postcode.')

    longitude = _to_float_or_none(result.get('longitude'))
    latitude = _to_float_or_none(result.get('latitude'))
    if longitude is None or latitude is None:
        raise ValueError('Please enter a valid pickup postcode.')
    return latitude, longitude


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
