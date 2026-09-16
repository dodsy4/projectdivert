const TONE = {
  pending: 'pending',
  matched: 'active',
  accepted: 'active',
  en_route: 'active',
  arrived: 'active',
  collected: 'active',
  completed: 'done',
  cancelled: 'bad',
};

/** A request's status as a coloured pill. Colour is never the only signal:
 *  the label is always the status itself. */
export default function StatusPill({ status }) {
  const label = String(status || 'unknown').replace(/_/g, ' ');
  return <span className={`pill pill--${TONE[status] || ''}`}>{label}</span>;
}
