import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { createRequest } from '../api/client.js';
import { useAuth } from '../auth/AuthContext.jsx';

const MATERIALS = [
  'Aggregate', 'Carpet Tiles', 'Compost', 'Correx', 'Ferrous metals', 'Glass',
  'Gravel', 'Non-ferrous metals', 'Pallets', 'Paper and card', 'Plasterboard',
  'Plastic (dense)', 'Plastic (film)', 'Sand', 'Task Chair', 'Textiles', 'Timber',
];
const UNITS = ['tonnes', 'kg', 'per item', 'square metres'];

/* Default to tomorrow at 09:00, in the format datetime-local expects. */
function defaultPickup() {
  const when = new Date();
  when.setDate(when.getDate() + 1);
  when.setHours(9, 0, 0, 0);
  const pad = (value) => String(value).padStart(2, '0');
  return `${when.getFullYear()}-${pad(when.getMonth() + 1)}-${pad(when.getDate())}T${pad(when.getHours())}:${pad(when.getMinutes())}`;
}

export default function NewRequestPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    requester_name: user?.name || '',
    requester_email: user?.email || '',
    material_type: 'Timber',
    waste_amount: '',
    waste_unit: 'tonnes',
    pickup_address: '',
    pickup_city: '',
    pickup_postcode: '',
    scheduled_pickup_at: defaultPickup(),
    match_radius_miles: '25',
    notes: '',
  });
  const [error, setError] = useState(null);
  const [fieldErrors, setFieldErrors] = useState([]);
  const [busy, setBusy] = useState(false);

  const update = (key) => (event) => setForm((prev) => ({ ...prev, [key]: event.target.value }));

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    setFieldErrors([]);
    setBusy(true);
    try {
      const result = await createRequest({
        ...form,
        scheduled_pickup_at: new Date(form.scheduled_pickup_at).toISOString(),
      });
      navigate('/requests', {
        state: { created: result?.request?.id },
        replace: true,
      });
    } catch (err) {
      setError(err.message);
      setFieldErrors(err.payload?.fields ?? []);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Collections</span>
          <h1>Book a collection</h1>
        </div>
      </div>

      {error && (
        <div className="notice notice--error" role="alert">
          {error}
          {fieldErrors.length > 0 && <> — missing: {fieldErrors.join(', ')}</>}
        </div>
      )}

      <div className="card">
        <form className="card__body" onSubmit={submit}>
          <div className="grid-2">
            <div className="field">
              <label htmlFor="material_type">Material</label>
              <select id="material_type" value={form.material_type} onChange={update('material_type')}>
                {MATERIALS.map((material) => <option key={material}>{material}</option>)}
              </select>
              <p className="field__hint">Drives the carbon model, so pick the closest match.</p>
            </div>
            <div className="field">
              <label htmlFor="waste_amount">Amount</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  id="waste_amount" type="number" min="0.001" step="0.25" required
                  value={form.waste_amount} onChange={update('waste_amount')}
                />
                <select
                  aria-label="Unit" value={form.waste_unit} onChange={update('waste_unit')}
                  style={{ width: 'auto' }}
                >
                  {UNITS.map((unit) => <option key={unit}>{unit}</option>)}
                </select>
              </div>
            </div>
          </div>

          <div className="field">
            <label htmlFor="pickup_address">Site address</label>
            <input id="pickup_address" required value={form.pickup_address} onChange={update('pickup_address')} />
          </div>

          <div className="grid-2">
            <div className="field">
              <label htmlFor="pickup_city">Town or city</label>
              <input id="pickup_city" value={form.pickup_city} onChange={update('pickup_city')} />
            </div>
            <div className="field">
              <label htmlFor="pickup_postcode">Postcode</label>
              <input
                id="pickup_postcode" required value={form.pickup_postcode}
                onChange={update('pickup_postcode')} autoComplete="postal-code"
              />
              <p className="field__hint">Used to find carriers nearby and to measure the haul.</p>
            </div>
          </div>

          <div className="grid-2">
            <div className="field">
              <label htmlFor="scheduled_pickup_at">Collection date and time</label>
              <input
                id="scheduled_pickup_at" type="datetime-local" required
                value={form.scheduled_pickup_at} onChange={update('scheduled_pickup_at')}
              />
            </div>
            <div className="field">
              <label htmlFor="match_radius_miles">Search radius (miles)</label>
              <input
                id="match_radius_miles" type="number" min="1" step="1"
                value={form.match_radius_miles} onChange={update('match_radius_miles')}
              />
            </div>
          </div>

          <div className="field">
            <label htmlFor="notes">Notes for the driver</label>
            <textarea id="notes" value={form.notes} onChange={update('notes')} />
          </div>

          <button type="submit" disabled={busy}>{busy ? 'Booking…' : 'Book collection'}</button>
        </form>
      </div>
    </>
  );
}
