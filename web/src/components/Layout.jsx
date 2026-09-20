import { Suspense, lazy, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import {
  Briefcase,
  ClipboardList,
  BarChart3,
  LayoutDashboard,
  LogOut,
  Map,
  Menu,
  PlusCircle,
  Truck,
  User,
  X,
} from 'lucide-react';

import { useAuth } from '../auth/AuthContext.jsx';

// Loaded only when the bundle is built with VITE_DEMO_MODE. Vite replaces that
// with a literal at build time, so with it unset the ternary collapses, the
// dynamic import becomes unreachable, and rollup never emits the chunk -- the
// switcher is absent from the bundle rather than merely inert inside it.
const DemoRoleSwitcher = import.meta.env.VITE_DEMO_MODE
  ? lazy(() => import('./DemoRoleSwitcher.jsx'))
  : null;

const CUSTOMER_NAV = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/requests/new', icon: PlusCircle, label: 'Book a collection' },
  { to: '/requests', icon: ClipboardList, label: 'My collections' },
];

const DRIVER_NAV = [
  { to: '/jobs', icon: Truck, label: 'Available jobs' },
  { to: '/my-jobs', icon: Briefcase, label: 'My jobs' },
];

const ADMIN_NAV = [...CUSTOMER_NAV, ...DRIVER_NAV];

// Available to every role: both views are scoped server-side, so a driver sees
// their own jobs and a customer their own collections.
const SHARED_NAV = [
  { to: '/map', icon: Map, label: 'Map' },
  { to: '/reports', icon: BarChart3, label: 'Reports' },
];

const PROFILE_NAV = { to: '/profile', icon: User, label: 'Profile' };

function navFor(role) {
  if (role === 'driver') return [...DRIVER_NAV, ...SHARED_NAV, PROFILE_NAV];
  if (role === 'admin') return [...ADMIN_NAV, ...SHARED_NAV, PROFILE_NAV];
  return [...CUSTOMER_NAV, ...SHARED_NAV, PROFILE_NAV];
}

export default function Layout({ children }) {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  const handleSignOut = async () => {
    await signOut();
    navigate('/login', { replace: true });
  };

  return (
    <div className="layout">
      {open && <div className="scrim" onClick={() => setOpen(false)} />}

      <aside className={`sidebar ${open ? 'sidebar--open' : ''}`}>
        <div className="sidebar__brand">
          <strong>Project Divert</strong>
          <span className="eyebrow">Diversion operations</span>
        </div>

        <nav className="sidebar__nav">
          {navFor(user?.role).map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/requests'}
              className={({ isActive }) => `navitem ${isActive ? 'navitem--active' : ''}`}
              onClick={() => setOpen(false)}
            >
              <Icon size={17} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__foot">
          {DemoRoleSwitcher && (
            <Suspense fallback={null}>
              <DemoRoleSwitcher />
            </Suspense>
          )}
          <div className="sidebar__user">
            <strong>{user?.name || user?.email}</strong>
            <span>{user?.role}</span>
          </div>
          <button type="button" className="button--ghost" onClick={handleSignOut} style={{ width: '100%' }}>
            <LogOut size={16} aria-hidden="true" />
            Sign out
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button
            type="button"
            className="button--ghost button--small"
            onClick={() => setOpen((value) => !value)}
            aria-label={open ? 'Close menu' : 'Open menu'}
          >
            {open ? <X size={18} /> : <Menu size={18} />}
          </button>
          <strong>Project Divert</strong>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
