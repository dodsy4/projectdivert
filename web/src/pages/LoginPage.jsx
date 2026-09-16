import { useState } from 'react';

import { useAuth } from '../auth/AuthContext.jsx';

export default function LoginPage() {
  const { signIn, register } = useAuth();
  const [mode, setMode] = useState('signin');
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);

  const isSignUp = mode === 'signup';
  const update = (key) => (event) => setForm((prev) => ({ ...prev, [key]: event.target.value }));

  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      if (isSignUp) {
        const user = await register(form.name, form.email, form.password);
        if (!user) {
          setNotice('Account created. Check your email to verify it, then sign in.');
          setMode('signin');
        }
      } else {
        await signIn(form.email, form.password);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth">
      <div className="auth__card">
        <div className="auth__brand">
          <span className="eyebrow">Project Divert</span>
          <h1>{isSignUp ? 'Create an account' : 'Sign in'}</h1>
        </div>

        {error && <div className="notice notice--error" role="alert">{error}</div>}
        {notice && <div className="notice notice--good">{notice}</div>}

        <form onSubmit={submit}>
          {isSignUp && (
            <div className="field">
              <label htmlFor="name">Name</label>
              <input id="name" value={form.name} onChange={update('name')} required autoComplete="name" />
            </div>
          )}
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email" type="email" value={form.email} onChange={update('email')}
              required autoComplete="email"
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password" type="password" value={form.password} onChange={update('password')}
              required autoComplete={isSignUp ? 'new-password' : 'current-password'}
            />
          </div>
          <button type="submit" disabled={busy} style={{ width: '100%', justifyContent: 'center' }}>
            {busy ? 'Working…' : isSignUp ? 'Create account' : 'Sign in'}
          </button>
        </form>

        <p className="auth__switch">
          {isSignUp ? 'Already have an account?' : 'No account yet?'}{' '}
          <button
            type="button"
            onClick={() => { setMode(isSignUp ? 'signin' : 'signup'); setError(null); }}
          >
            {isSignUp ? 'Sign in' : 'Create one'}
          </button>
        </p>
      </div>
    </div>
  );
}
