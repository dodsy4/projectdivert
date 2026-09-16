import { Navigate, Route, Routes } from 'react-router-dom';

import Layout from './components/Layout.jsx';
import { useAuth } from './auth/AuthContext.jsx';
import AvailableJobsPage from './pages/AvailableJobsPage.jsx';
import DashboardPage from './pages/DashboardPage.jsx';
import LoginPage from './pages/LoginPage.jsx';
import MyJobsPage from './pages/MyJobsPage.jsx';
import NewRequestPage from './pages/NewRequestPage.jsx';
import ProfilePage from './pages/ProfilePage.jsx';
import RequestsPage from './pages/RequestsPage.jsx';

/** Where each role lands after signing in. */
export function homeFor(user) {
  return user?.role === 'driver' ? '/jobs' : '/dashboard';
}

export default function App() {
  const { user, loading } = useAuth();

  if (loading) return <div className="spinner" role="status" aria-label="Loading" />;

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  const home = homeFor(user);
  const isDriver = user.role === 'driver';

  return (
    <Layout>
      <Routes>
        <Route path="/login" element={<Navigate to={home} replace />} />
        <Route path="/" element={<Navigate to={home} replace />} />

        {!isDriver && <Route path="/dashboard" element={<DashboardPage />} />}
        {!isDriver && <Route path="/requests" element={<RequestsPage />} />}
        {!isDriver && <Route path="/requests/new" element={<NewRequestPage />} />}

        {user.role !== 'customer' && <Route path="/jobs" element={<AvailableJobsPage />} />}
        {user.role !== 'customer' && <Route path="/my-jobs" element={<MyJobsPage />} />}

        <Route path="/profile" element={<ProfilePage />} />
        <Route path="*" element={<Navigate to={home} replace />} />
      </Routes>
    </Layout>
  );
}
