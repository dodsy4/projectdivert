import { useAuth } from '../auth/AuthContext.jsx';

function Row({ label, value }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, padding: '10px 0', borderBottom: '1px solid var(--rule)' }}>
      <span className="muted">{label}</span>
      <strong>{value ?? '—'}</strong>
    </div>
  );
}

export default function ProfilePage() {
  const { user } = useAuth();

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Account</span>
          <h1>Profile</h1>
        </div>
      </div>

      <div className="card" style={{ maxWidth: 560 }}>
        <div className="card__body">
          <Row label="Name" value={user?.name} />
          <Row label="Email" value={user?.email} />
          <Row label="Role" value={user?.role} />
          <Row label="Email verified" value={user?.email_verified ? 'Yes' : 'No'} />
          <p className="field__hint" style={{ marginTop: 14 }}>
            Roles are set by an administrator. If yours is wrong, ask them to change it
            rather than creating a second account.
          </p>
        </div>
      </div>
    </>
  );
}
