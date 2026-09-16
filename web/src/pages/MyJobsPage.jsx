import { useState } from 'react';

import RequestTable from '../components/RequestTable.jsx';
import useAsync from '../hooks/useAsync.js';
import { listRequests, setStatus } from '../api/client.js';

/* The step a driver can move a job to next. Completion is gated server-side on
   verified compliance documents, so the API may still refuse it. */
const NEXT_STATUS = {
  accepted: 'en_route',
  en_route: 'arrived',
  arrived: 'collected',
  collected: 'completed',
};

export default function MyJobsPage() {
  const { data, error, loading, reload } = useAsync(
    () => listRequests({ scope: 'assigned', limit: 100 }),
    [],
  );
  const [busy, setBusy] = useState(null);
  const [actionError, setActionError] = useState(null);

  const advance = async (request) => {
    const next = NEXT_STATUS[request.status];
    if (!next) return;
    setActionError(null);
    setBusy(request.id);
    try {
      await setStatus(request.id, next);
      reload();
    } catch (err) {
      setActionError(
        err.status === 409
          ? `PD-${String(request.id).padStart(5, '0')} cannot be completed yet: ${err.message}`
          : err.message,
      );
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Dispatch</span>
          <h1>My jobs</h1>
        </div>
        <button type="button" className="button--ghost" onClick={reload}>Refresh</button>
      </div>

      {error && <div className="notice notice--error" role="alert">{error.message}</div>}
      {actionError && <div className="notice notice--error" role="alert">{actionError}</div>}

      <div className="card">
        {loading ? (
          <div className="spinner" role="status" aria-label="Loading" />
        ) : (
          <RequestTable
            requests={data?.requests ?? []}
            emptyMessage="Nothing assigned to you yet. Claim a job to get started."
            actions={(request) =>
              NEXT_STATUS[request.status] ? (
                <button
                  type="button"
                  className="button--small"
                  disabled={busy === request.id}
                  onClick={() => advance(request)}
                >
                  {busy === request.id
                    ? 'Saving…'
                    : `Mark ${NEXT_STATUS[request.status].replace(/_/g, ' ')}`}
                </button>
              ) : null
            }
          />
        )}
      </div>
    </>
  );
}
