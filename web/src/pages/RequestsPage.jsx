import { useState } from 'react';
import { Link } from 'react-router-dom';

import RequestTable from '../components/RequestTable.jsx';
import useAsync from '../hooks/useAsync.js';
import { listRequests } from '../api/client.js';

const STATUSES = ['', 'pending', 'matched', 'accepted', 'en_route', 'arrived', 'collected', 'completed', 'cancelled'];

export default function RequestsPage() {
  const [status, setStatus] = useState('');
  const { data, error, loading } = useAsync(() => listRequests({ status, limit: 100 }), [status]);

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Collections</span>
          <h1>My collections</h1>
        </div>
        <Link className="button" to="/requests/new">Book a collection</Link>
      </div>

      <div className="card">
        <div className="card__head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
          <h2>{data ? `${data.total} total` : 'Loading'}</h2>
          <div style={{ minWidth: 190 }}>
            <label htmlFor="status" className="visually-hidden" style={{ marginBottom: 0 }}>Filter by status</label>
            <select id="status" value={status} onChange={(event) => setStatus(event.target.value)}>
              {STATUSES.map((value) => (
                <option key={value || 'all'} value={value}>
                  {value ? value.replace(/_/g, ' ') : 'All statuses'}
                </option>
              ))}
            </select>
          </div>
        </div>

        {error && <div className="notice notice--error" role="alert" style={{ margin: 18 }}>{error.message}</div>}
        {loading ? (
          <div className="spinner" role="status" aria-label="Loading" />
        ) : (
          <RequestTable
            requests={data?.requests ?? []}
            emptyMessage={status ? `No collections with status “${status}”.` : 'No collections yet.'}
          />
        )}
      </div>
    </>
  );
}
