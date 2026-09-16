import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import * as apiClient from '../api/client';

const AuthContext = createContext(null);

/**
 * Holds the signed-in account.
 *
 * A stored access token outlives a page reload but the user record does not, so
 * on boot we ask the API who the token belongs to rather than decoding it in
 * the browser and trusting its claims.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    if (!apiClient.tokens.access) {
      setLoading(false);
      return () => {};
    }
    apiClient
      .me()
      .then((data) => {
        if (!cancelled) setUser(data.user);
      })
      .catch(() => {
        apiClient.tokens.clear();
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (email, password) => {
    const payload = await apiClient.login(email, password);
    apiClient.tokens.set(payload);
    setUser(payload.user);
    return payload.user;
  }, []);

  const register = useCallback(async (name, email, password) => {
    const payload = await apiClient.signup(name, email, password);
    if (payload.access_token) {
      apiClient.tokens.set(payload);
      setUser(payload.user);
      return payload.user;
    }
    // Email verification is on: the account exists but there is no session yet.
    return null;
  }, []);

  const signOut = useCallback(async () => {
    await apiClient.logout();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, signIn, register, signOut }),
    [user, loading, signIn, register, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside an AuthProvider');
  return context;
}
