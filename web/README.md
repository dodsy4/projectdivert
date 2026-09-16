# Project Divert — web dashboard

A React dashboard for the Project Divert API: customers book collections and
follow them, drivers claim and progress jobs, and completed collections link to
their diversion certificate.

It talks to the same `/api/v1` surface as the mobile app, documented at
`/api/docs` on a running backend.

## Running it

```bash
npm install
npm run dev
```

`npm run dev` serves on <http://localhost:5173> and proxies `/api` to
`http://127.0.0.1:5000`, so the browser stays on one origin and there is no CORS
configuration to get wrong. Point it elsewhere with `VITE_API_PROXY`.

Start the backend alongside it:

```bash
cd ..
export FLASK_APP=wsgi.py
flask run
```

## Building

```bash
npm run build     # -> dist/
npm run preview   # serve the build locally
npm run lint
```

The production build uses same-origin relative URLs. To point a build at an API
on another host, set `VITE_API_BASE_URL` at build time.

## How it is put together

- `src/api/client.js` is the only module that talks to the network. It attaches
  the access token, and on a 401 it refreshes once and replays the request.
  Concurrent 401s share one in-flight refresh, so rotated refresh tokens are not
  burned by a burst of parallel requests.
- `src/auth/AuthContext.jsx` holds the signed-in account. On boot it asks
  `/api/v1/auth/me` who the stored token belongs to rather than decoding the
  token in the browser and trusting its claims.
- Pages are thin: fetch through `useAsync`, render, and hand actions back to the
  client module. Role decides navigation, but the API scopes every list
  server-side, so the UI cannot widen what it is allowed to see.

## What is not here yet

The live map and CSV reporting from the earlier prototype are not ported. The
map needs pickup coordinates on the request, which the API does not currently
return, and the reporting needs a customer-scoped export endpoint to sit beside
the existing admin ones.
