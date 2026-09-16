import StatusPill from './StatusPill.jsx';
import { certificateUrl } from '../api/client.js';

function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

/** Shared table of waste requests. `actions` renders the trailing cell. */
export default function RequestTable({ requests, emptyMessage, actions }) {
  if (!requests.length) {
    return <div className="empty">{emptyMessage}</div>;
  }

  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th scope="col">Ref</th>
            <th scope="col">Material</th>
            <th scope="col">Amount</th>
            <th scope="col">Collection</th>
            <th scope="col">Postcode</th>
            <th scope="col">Status</th>
            <th scope="col" style={{ textAlign: 'right' }}>{actions ? 'Action' : ''}</th>
          </tr>
        </thead>
        <tbody>
          {requests.map((request) => (
            <tr key={request.id}>
              <td className="num mono">PD-{String(request.id).padStart(5, '0')}</td>
              <td>{request.material_type}</td>
              <td className="num">
                {request.waste_amount} {request.waste_unit}
              </td>
              <td className="num">{formatDate(request.scheduled_pickup_at)}</td>
              <td className="mono">{request.pickup_postcode}</td>
              <td><StatusPill status={request.status} /></td>
              <td>
                <div className="row-actions">
                  {actions ? actions(request) : null}
                  {request.status === 'completed' && (
                    <a
                      className="button button--ghost button--small"
                      href={certificateUrl(request.id)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Certificate
                    </a>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
