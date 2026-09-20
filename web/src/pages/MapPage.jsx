import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

import useAsync from '../hooks/useAsync.js';
import { certificateUrl, listRequests } from '../api/client.js';

/**
 * Collections plotted where they are.
 *
 * OpenStreetMap tiles through Leaflet rather than Google Maps: no API key to
 * distribute to the browser, no billing account behind a demo, and the tiles
 * are images from an https origin, which the application's content security
 * policy already allows.
 *
 * Pins come from pickup_latitude/pickup_longitude, geocoded when the request is
 * created. Collections created before those were stored have none and are
 * listed underneath instead of being silently dropped -- a map that quietly
 * omits half the work is worse than one that says it did.
 */

const BRISTOL = [51.4545, -2.5879];

const STATUS_COLOURS = {
  pending_match: '#b58900',
  matched: '#2563eb',
  accepted: '#2563eb',
  en_route: '#7c3aed',
  arrived: '#7c3aed',
  collected: '#0f766e',
  completed: '#15803d',
  cancelled: '#9ca3af',
  rejected: '#9ca3af',
};

function pin(status) {
  const colour = STATUS_COLOURS[status] || '#6b7280';
  return L.divIcon({
    className: 'map-pin',
    html: `<span style="--pin:${colour}"></span>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
  });
}

function popupFor(request) {
  const reference = `PD-${String(request.id).padStart(5, '0')}`;
  const certificate = request.status === 'completed'
    ? `<p><a href="${certificateUrl(request.id)}" target="_blank" rel="noreferrer">Carbon certificate</a></p>`
    : '';
  return `
    <strong>${reference}</strong>
    <p>${request.material_type} &middot; ${request.waste_amount} ${request.waste_unit}</p>
    <p>${request.pickup_address || ''}<br>${request.pickup_postcode || ''}</p>
    <p><em>${request.status}</em></p>
    ${certificate}
  `;
}

export default function MapPage() {
  const { data, error, loading } = useAsync(() => listRequests({ limit: 200 }), []);
  const container = useRef(null);
  const map = useRef(null);

  const requests = data?.requests ?? [];
  const plottable = requests.filter(
    (request) => request.pickup_latitude != null && request.pickup_longitude != null,
  );
  const unplottable = requests.filter(
    (request) => request.pickup_latitude == null || request.pickup_longitude == null,
  );

  useEffect(() => {
    if (!container.current || loading) return undefined;

    if (!map.current) {
      map.current = L.map(container.current).setView(BRISTOL, 11);
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '&copy; OpenStreetMap contributors',
      }).addTo(map.current);
    }

    const markers = plottable.map((request) => L
      .marker([request.pickup_latitude, request.pickup_longitude], { icon: pin(request.status) })
      .addTo(map.current)
      .bindPopup(popupFor(request)));

    if (markers.length > 0) {
      map.current.fitBounds(
        L.featureGroup(markers).getBounds().pad(0.2),
        { maxZoom: 14 },
      );
    }

    return () => markers.forEach((marker) => marker.remove());
  }, [loading, plottable]);

  // Leaflet owns the DOM inside the container, so tear the map down on unmount
  // rather than leaving it attached to a node React has removed.
  useEffect(() => () => {
    if (map.current) {
      map.current.remove();
      map.current = null;
    }
  }, []);

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Operations</span>
          <h1>Collection map</h1>
        </div>
      </div>

      {error && <div className="notice notice--error" role="alert">{error.message}</div>}

      <div className="card">
        {loading
          ? <div className="spinner" role="status" aria-label="Loading" />
          : <div ref={container} className="map" />}
      </div>

      <div className="map-key">
        {Object.entries(STATUS_COLOURS).map(([status, colour]) => (
          <span key={status} className="map-key__item">
            <i style={{ background: colour }} aria-hidden="true" />
            {status.replace(/_/g, ' ')}
          </span>
        ))}
      </div>

      {unplottable.length > 0 && (
        <div className="card">
          <h2 className="card__title">Not on the map</h2>
          <p className="muted">
            {unplottable.length} collection{unplottable.length === 1 ? '' : 's'} have no
            {' '}coordinates, so they cannot be plotted. Run
            {' '}<code>flask backfill-pickup-coordinates</code> to geocode them.
          </p>
          <ul className="plain-list">
            {unplottable.map((request) => (
              <li key={request.id}>
                PD-{String(request.id).padStart(5, '0')} &middot; {request.pickup_postcode || 'no postcode'}
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
