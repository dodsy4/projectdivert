/**
 * Client for the Project Divert API.
 *
 * Two things this handles that the calling code should not have to:
 *
 * 1. Token refresh. Access tokens are short-lived and refresh tokens rotate, so
 *    a 401 triggers one refresh attempt and one replay of the original request.
 *    Concurrent 401s share a single in-flight refresh rather than each starting
 *    their own, which would burn rotated tokens and log the user out.
 * 2. Errors. Every failure arrives as an ApiError carrying the status and the
 *    server's own `error` message, so pages can show what actually went wrong.
 */

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const ACCESS_KEY = 'pd.access_token';
const REFRESH_KEY = 'pd.refresh_token';

export class ApiError extends Error {
  constructor(status, message, payload) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

/* Storage can throw in a private window; never let that break the app. */
function read(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key, value) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* ignore: the session simply will not survive a reload */
  }
}

export const tokens = {
  get access() {
    return read(ACCESS_KEY);
  },
  get refresh() {
    return read(REFRESH_KEY);
  },
  set({ access_token: accessToken, refresh_token: refreshToken }) {
    if (accessToken) write(ACCESS_KEY, accessToken);
    if (refreshToken) write(REFRESH_KEY, refreshToken);
  },
  clear() {
    write(ACCESS_KEY, null);
    write(REFRESH_KEY, null);
  },
};

let refreshInFlight = null;

async function refreshAccessToken() {
  const refreshToken = tokens.refresh;
  if (!refreshToken) return false;

  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${BASE_URL}/api/v1/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!response.ok) return false;
        tokens.set(await response.json());
        return true;
      } catch {
        return false;
      } finally {
        // Let the next 401 start a fresh attempt.
        setTimeout(() => {
          refreshInFlight = null;
        }, 0);
      }
    })();
  }
  return refreshInFlight;
}

async function parse(response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function send(path, { method = 'GET', body, headers = {}, retry = true } = {}) {
  const accessToken = tokens.access;
  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: {
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 401 && retry && tokens.refresh) {
    if (await refreshAccessToken()) {
      return send(path, { method, body, headers, retry: false });
    }
    tokens.clear();
  }

  const payload = await parse(response);
  if (!response.ok) {
    const message =
      (payload && payload.error) || `Request failed (${response.status})`;
    throw new ApiError(response.status, message, payload);
  }
  return payload;
}

export const api = {
  get: (path) => send(path),
  post: (path, body) => send(path, { method: 'POST', body: body ?? {} }),
  del: (path) => send(path, { method: 'DELETE' }),
};

/* ---- endpoints ---------------------------------------------------------- */

export const login = (email, password) =>
  send('/api/v1/auth/login', { method: 'POST', body: { email, password }, retry: false });

export const signup = (name, email, password) =>
  send('/api/v1/auth/signup', { method: 'POST', body: { name, email, password }, retry: false });

export const me = () => api.get('/api/v1/auth/me');

export const logout = () => {
  const refreshToken = tokens.refresh;
  const done = refreshToken
    ? send('/api/v1/auth/logout', {
        method: 'POST',
        body: { refresh_token: refreshToken },
        retry: false,
      }).catch(() => null)
    : Promise.resolve(null);
  return done.finally(() => tokens.clear());
};

export const listRequests = (params = {}) => {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => value !== undefined && value !== ''),
  ).toString();
  return api.get(`/api/v1/waste-requests${query ? `?${query}` : ''}`);
};

export const getRequest = (id) => api.get(`/api/v1/waste-requests/${id}`);

export const createRequest = (payload) => api.post('/api/v1/waste-requests', payload);

export const acceptOffer = (id, token) =>
  api.post(`/api/v1/waste-requests/${id}/dispatch/accept`, token ? { offer_token: token } : {});

export const setStatus = (id, status) =>
  api.post(`/api/v1/waste-requests/${id}/status`, { status });

export const certificateUrl = (id) => `${BASE_URL}/certificate/${id}`;
