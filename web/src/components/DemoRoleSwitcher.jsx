import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Repeat } from 'lucide-react';

import { useAuth } from '../auth/AuthContext.jsx';

/**
 * Jump between the seeded demo accounts without signing out and back in.
 *
 * Presenting this product means showing the same collection from two sides --
 * the site manager who booked it and the driver who collects it -- and doing
 * that through the login screen breaks the thread of the demonstration every
 * time.
 *
 * Layout only imports this when the bundle is built with VITE_DEMO_MODE, so a
 * normal production build does not contain it at all. The accounts match
 * `flask seed-demo`.
 */

export const DEMO_ACCOUNTS = [
  { role: 'customer', label: 'Site manager', email: 'site.manager@demo.projectdivert.test', lands: '/dashboard' },
  { role: 'driver', label: 'Driver', email: 'driver@demo.projectdivert.test', lands: '/jobs' },
  { role: 'admin', label: 'Admin', email: 'admin@demo.projectdivert.test', lands: '/dashboard' },
];

export default function DemoRoleSwitcher() {
  const { user, signIn } = useAuth();
  const navigate = useNavigate();
  // Held in component state only: never written to storage, and never built
  // into the bundle. Typed once per session, which is the price of not
  // shipping a password to everyone who loads the page.
  const [password, setPassword] = useState('');
  const [switching, setSwitching] = useState(null);
  const [error, setError] = useState(null);

  const switchTo = async (account) => {
    setError(null);
    if (!password) {
      setError('Enter the demo password first.');
      return;
    }
    setSwitching(account.role);
    try {
      await signIn(account.email, password);
      navigate(account.lands, { replace: true });
    } catch (err) {
      setError(`Could not switch to ${account.label}: ${err.message}`);
    } finally {
      setSwitching(null);
    }
  };

  return (
    <div className="demo-switcher">
      <div className="demo-switcher__head">
        <Repeat size={14} aria-hidden="true" />
        <span>Demo mode</span>
      </div>

      <label className="demo-switcher__field">
        <span className="visually-hidden">Demo account password</span>
        <input
          type="password"
          value={password}
          placeholder="Demo password"
          autoComplete="off"
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>

      <div className="demo-switcher__roles">
        {DEMO_ACCOUNTS.map((account) => (
          <button
            key={account.role}
            type="button"
            className={`demo-switcher__role ${user?.role === account.role ? 'is-current' : ''}`}
            disabled={Boolean(switching) || user?.role === account.role}
            onClick={() => switchTo(account)}
          >
            {switching === account.role ? 'Switching…' : account.label}
          </button>
        ))}
      </div>

      {error && <p className="demo-switcher__error" role="alert">{error}</p>}
    </div>
  );
}
