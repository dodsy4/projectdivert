import { Link } from 'react-router-dom';

import RequestTable from '../components/RequestTable.jsx';
import useAsync from '../hooks/useAsync.js';
import { listRequests } from '../api/client.js';

const OPEN_STATUSES = new Set(['pending', 'matched', 'accepted', 'en_route', 'arrived', 'collected']);

export default function DashboardPage() {
  const { data, error, loading } = useAsync(() => listRequests({ limit: 100 }), []);

  if (loading) return <div className="spinner" role="status" aria-label="Loading" />;
  if (error) return <div className="notice notice--error" role="alert">{error.message}</div>;

  const requests = data?.requests ?? [];
  const open = requests.filter((request) => OPEN_STATUSES.has(request.status));
  const completed = requests.filter((request) => request.status === 'completed');
  const tonnes = completed.reduce((total, request) => {
    const unit = String(request.waste_unit || '').toLowerCase();
    const amount = Number(request.waste_amount) || 0;
    if (unit.startsWith('tonne')) return total + amount;
    if (unit.startsWith('kg')) return total + amount / 1000;
    return total;
  }, 0);

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Overview</span>
          <h1>Dashboard</h1>
        </div>
        <Link className="button" to="/requests/new">Book a collection</Link>
      </div>

      <div className="stats">
        <div className="stat">
          <div className="stat__num">{data?.total ?? requests.length}</div>
          <div className="stat__label">Collections raised</div>
        </div>
        <div className="stat">
          <div className="stat__num">{open.length}</div>
          <div className="stat__label">In progress</div>
        </div>
        <div className="stat">
          <div className="stat__num">{completed.length}</div>
          <div className="stat__label">Completed</div>
        </div>
        <div className="stat">
          <div className="stat__num">{tonnes.toFixed(1)}</div>
          <div className="stat__label">Tonnes diverted, completed only</div>
        </div>
      </div>

      <div className="card">
        <div className="card__head"><h2>Latest collections</h2></div>
        <RequestTable
          requests={requests.slice(0, 8)}
          emptyMessage="No collections yet. Book one to get started."
        />
      </div>
    </>
  );
}
