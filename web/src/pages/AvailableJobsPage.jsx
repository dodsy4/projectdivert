import { useState } from 'react';

import RequestTable from '../components/RequestTable.jsx';
import useAsync from '../hooks/useAsync.js';
import { acceptOffer, listRequests } from '../api/client.js';

export default function AvailableJobsPage() {
  const { data, error, loading, reload } = useAsync(
    () => listRequests({ scope: 'available', limit: 100 }),
    [],
  );
  const [claiming, setClaiming] = useState(null);
  const [claimError, setClaimError] = useState(null);

  const claim = async (request) => {
    setClaimError(null);
    setClaiming(request.id);
    try {
      await acceptOffer(request.id);
      reload();
    } catch (err) {
      setClaimError(`Could not claim PD-${String(request.id).padStart(5, '0')}: ${err.message}`);
    } finally {
      setClaiming(null);
    }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Dispatch</span>
          <h1>Available jobs</h1>
        </div>
        <button type="button" className="button--ghost" onClick={reload}>Refresh</button>
      </div>

      {error && <div className="notice notice--error" role="alert">{error.message}</div>}
      {claimError && <div className="notice notice--error" role="alert">{claimError}</div>}

      <div className="card">
        {loading ? (
          <div className="spinner" role="status" aria-label="Loading" />
        ) : (
          <RequestTable
            requests={data?.requests ?? []}
            emptyMessage="No open jobs right now."
            actions={(request) => (
              <button
                type="button"
                className="button--small"
                disabled={claiming === request.id}
                onClick={() => claim(request)}
              >
                {claiming === request.id ? 'Claiming…' : 'Claim'}
              </button>
            )}
          />
        )}
      </div>
    </>
  );
}
