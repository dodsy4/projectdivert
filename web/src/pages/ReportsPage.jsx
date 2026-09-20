import useAsync from '../hooks/useAsync.js';
import { collectionReport } from '../api/client.js';

/**
 * What the collections add up to.
 *
 * Every carbon figure here comes from the same assessment the certificate for
 * an individual collection uses, so a total and the certificates behind it
 * cannot disagree.
 *
 * Collections the model could not assess are reported rather than dropped. A
 * total that silently omits them looks identical to one that includes them,
 * and the difference matters when the number is a carbon claim.
 */

function formatCo2e(kg) {
  if (kg == null) return '—';
  if (Math.abs(kg) >= 1000) return `${(kg / 1000).toFixed(2)} t`;
  return `${kg.toFixed(1)} kg`;
}

export default function ReportsPage() {
  const { data, error, loading, reload } = useAsync(() => collectionReport(), []);

  const diverted = data?.diverted;
  const materials = data?.by_material ?? [];
  const statuses = Object.entries(data?.status_counts ?? {});
  const unavailable = diverted?.carbon_unavailable ?? [];

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Operations</span>
          <h1>Reports</h1>
        </div>
        <button type="button" className="button--ghost" onClick={reload}>Refresh</button>
      </div>

      {error && <div className="notice notice--error" role="alert">{error.message}</div>}

      {loading ? (
        <div className="spinner" role="status" aria-label="Loading" />
      ) : (
        <>
          <div className="stat-row">
            <div className="stat">
              <span className="stat__label">Collections</span>
              <strong className="stat__value">{data?.collections ?? 0}</strong>
            </div>
            <div className="stat">
              <span className="stat__label">Diverted from landfill</span>
              <strong className="stat__value">{diverted?.collections ?? 0}</strong>
            </div>
            <div className="stat">
              <span className="stat__label">Material diverted</span>
              <strong className="stat__value">{(diverted?.tonnes ?? 0).toFixed(2)} t</strong>
            </div>
            <div className="stat stat--accent">
              <span className="stat__label">Net avoided</span>
              <strong className="stat__value">
                {formatCo2e(diverted?.net_avoided_kg_co2e)} CO<sub>2</sub>e
              </strong>
            </div>
          </div>

          <div className="card">
            <h2 className="card__title">By material</h2>
            {materials.length === 0 ? (
              <p className="muted">Nothing has completed yet, so there is nothing to total.</p>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Material</th>
                    <th>Collections</th>
                    <th>Tonnes</th>
                    <th>Net avoided</th>
                  </tr>
                </thead>
                <tbody>
                  {materials.map((row) => (
                    <tr key={row.material}>
                      <td>{row.material}</td>
                      <td>{row.collections}</td>
                      <td>{row.tonnes.toFixed(2)}</td>
                      <td>{formatCo2e(row.avoided_kg)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="card">
            <h2 className="card__title">Where collections are</h2>
            {statuses.length === 0 ? (
              <p className="muted">No collections yet.</p>
            ) : (
              <ul className="plain-list">
                {statuses.map(([status, count]) => (
                  <li key={status}>
                    <strong>{count}</strong> {status.replace(/_/g, ' ')}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {unavailable.length > 0 && (
            <div className="card">
              <h2 className="card__title">Not counted</h2>
              <p className="muted">
                {unavailable.length} completed collection{unavailable.length === 1 ? '' : 's'}
                {' '}could not be assessed, so {unavailable.length === 1 ? 'it is' : 'they are'}
                {' '}excluded from the totals above rather than estimated.
              </p>
              <ul className="plain-list">
                {unavailable.map((row) => (
                  <li key={row.id}>
                    PD-{String(row.id).padStart(5, '0')} &middot; {row.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {data?.truncated && (
            <p className="muted">
              Showing the most recent {data.limit} collections.
            </p>
          )}
        </>
      )}
    </>
  );
}
