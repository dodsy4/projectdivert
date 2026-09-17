# Project Divert

[![CI](https://github.com/dodsy4/projectdivert/actions/workflows/ci.yml/badge.svg)](https://github.com/dodsy4/projectdivert/actions/workflows/ci.yml)
[![Secret Scan](https://github.com/dodsy4/projectdivert/actions/workflows/secret-scan.yml/badge.svg)](https://github.com/dodsy4/projectdivert/actions/workflows/secret-scan.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)

Project Divert is a full-stack platform for diverting surplus construction and office materials away from landfill — matching materials with reuse/recycling destinations, coordinating waste-removal logistics with real-time driver dispatch, and quantifying the carbon impact of every diversion.

It began as a materials marketplace with a Scope 3 carbon accounting engine, and has grown into a two-sided operational platform: a Flask backend handling everything from JWT-authenticated APIs to Stripe payments and driver compliance, and a companion Expo/React Native mobile app for customers and drivers.

## Core features

**Materials marketplace**
- Post surplus materials (with photos, dimensions, condition) for reuse
- Search and filter by location, radius, and material type
- Request/response workflow between suppliers and reuse partners

**Carbon accounting engine**
- ISO 14040/14044-aligned life-cycle model (`project_divert_lca.py`) calculating net avoided kg CO2e per diversion: landfill baseline vs. reuse/recycle scenarios, with an avoided-virgin-production credit
- Cited emission factors in a versioned dataset (`data/lca/emission_factors.csv`) drawn from UK DESNZ conversion factors, the ICE embodied-carbon database, and WRAP
- Per-stage breakdown (disposal, transport, reprocessing, avoided virgin production) with source provenance; real road distances via the Google Maps Distance Matrix API
- A shareable diversion certificate at `/certificate/<request_id>` for each completed collection, with the avoided emissions computed by the engine at render time from the real collection distance rather than a stored figure
- Methodology, system boundary and limitations documented in [`docs/lca-methodology.md`](./docs/lca-methodology.md)
- [`docs/lca-demo.html`](./docs/lca-demo.html) is a standalone, self-contained page that runs the whole model in the browser on the same cited dataset — no database, API keys or backend. Built by `scripts/build_lca_demo.py`; `scripts/verify_lca_demo.py` checks the JavaScript port against the Python engine across every material, both pathways and a spread of masses and distances (544 cases) and fails on any disagreement

**Web dashboard**
- A React dashboard in [`web/`](./web/) over the same `/api/v1` surface the mobile app uses: customers book collections and track them, drivers claim and progress jobs, completed collections link to their diversion certificate
- Token refresh is handled in one place, with concurrent 401s sharing a single in-flight refresh so rotated refresh tokens are not burned by a burst of parallel requests
- Navigation follows the signed-in role, but every list is scoped server-side, so the UI cannot widen what it is permitted to see

**WhatsApp assistant**
- Site managers and drivers can book collections, list material for reuse, search and claim open jobs, and check status by messaging in plain English
- Claude drives an agentic loop over eight tools, each a thin wrapper over the same service functions the JSON API uses, so the conversational path cannot drift from the API path
- Every state change it makes is written to the audit trail with `source='whatsapp_bot'`
- Inbound webhooks are verified against Twilio's request signature and fail closed; conversation history is held in Redis where configured, so it survives across workers
- Off by default behind `WHATSAPP_ENABLED` and `CHATBOT_ENABLED`; with the assistant unavailable the webhook falls back to keyword replies rather than going silent

**Waste removal & dispatch**
- Customers submit waste-removal requests; drivers receive and accept dispatch offers
- Live GPS location tracking for active jobs, streamed to the mobile app over Server-Sent Events
- Admin dispatch console with manual override, incident tracking, and telemetry

**Compliance & statutory tracking**
- Digital tracking of Waste Transfer Notes (WTNs) and other compliance documents
- Driver and carrier-company compliance document upload, review, and verification workflow

**Audit logging**
- `AuthAuditEvent` — dedicated trail for authentication events
- `AuditEvent` — application-wide trail: every state-changing request is captured (actor, IP, action, entity, status) by an `after_request` hook, with explicit before/after diffs recorded at critical sites (dispatch, payments, compliance, status changes)
- Admin views: `GET /admin/audit` (HTML) and `GET /api/v1/admin/audit-events` (JSON)

**API documentation**
- OpenAPI 3.1 document generated from the application itself and served at `/api/v1/openapi.json`, with a rendered reference at `/api/docs`
- A contract test fails the build if a route is added, removed or renamed without regenerating the spec, so the documentation cannot drift from the code

**Authentication & security**
- JWT-based auth with refresh tokens, email verification, and password reset flows
- Rate limiting and an auth-security blocklist for abuse prevention
- A pre-push git hook that scans for accidentally committed secrets before they reach GitHub

**Payments**
- Stripe integration for charging customers and paying out drivers, gated behind a feature flag until fully configured
- Billing follow-up automation for outstanding invoices

**Mobile app**
- Expo/React Native app for customers (request to status tracking) and drivers (offer inbox to active job)
- Push notifications, live location updates, and in-app compliance document upload

## Tech stack

**Backend:** Python, Flask, SQLAlchemy, Alembic, PostgreSQL, Redis, PyJWT, Stripe API, boto3 (S3-compatible storage), SendGrid, Pandas
**Web:** React 19, Vite, React Router
**Mobile:** Expo, React Native, TypeScript
**Ops:** Gunicorn, RQ (background jobs), Render (deployment), pytest, GitHub Actions (tests, mobile typecheck, gitleaks secret scanning)

## Architecture

The backend is a Flask application package assembled by an app factory
(`create_app`). Modules are layered and the import graph is a strict DAG,
verified before the split — nothing imports sideways or back up a layer:

```
projectdivert/
  __init__.py       create_app(): config, extensions, blueprints, hooks, CLI, logging
  extensions.py     db / migrate / login_manager / moment, created unbound
  models/           29 SQLAlchemy models grouped by domain
  services/         business logic: auth, dispatch, billing, compliance,
                    payments, audit, events, notifications, LCA adapters
  blueprints/       HTTP layer only — parse, authorise, delegate, serialise
    api/            the versioned JSON API under /api/v1
  hooks.py          request id, table bootstrap, audit capture, error pages
  cli.py            seeding, token cleanup, ops digest, billing follow-ups

services/utils → extensions → models → services → blueprints → app
```

Because the services layer never imports the application, it is callable from a
request, a CLI command, an RQ worker or a unit test without change, and it logs
through module loggers rather than `app.logger`.

A request takes one of two paths. Browser traffic reaches the `web` and `admin`
blueprints, which render Jinja templates against a Flask-Login session. Mobile
and integration traffic reaches the `/api/v1` blueprints, which verify a JWT via
the `jwt_required` decorator and return JSON. Both paths converge on the same
services, and every successful state-changing request — on either path — is
captured by the `after_request` audit hook, keyed by URL rule rather than
endpoint name.

Three modules deliberately sit outside the package. `project_divert_lca.py` is
the ISO 14040/44 engine: pure Python with no Flask import, so it can be read,
tested and cited on its own (`docs/lca-methodology.md` does exactly that).
`project_divert_functions.py` holds the legacy CSV/XLSX reference loaders, and
`forms.py` the WTForms definitions.

The server-rendered front end is intentionally plain — Bootstrap 3 and jQuery,
inherited from the project's first version. The engineering effort here is in
the backend, the carbon model and the operational tooling rather than the
browser layer; the mobile app is where the modern client work lives.

## Getting started

See [`DEPLOY.md`](./DEPLOY.md) for full backend deployment instructions (environment variables, database migration, production preflight checks), and [`mobile-app/README.md`](./mobile-app/README.md) for running the mobile app locally against a backend instance.

Quick local backend setup:
```bash
pip install -r requirements.txt
export FLASK_APP=wsgi.py
export FLASK_DEBUG=1          # or set SECRET_KEY: the app refuses to serve with the placeholder
flask db upgrade             # required: nothing creates tables at runtime
flask seed-materials
flask run
```

In production the app is served through `gunicorn.conf.py`, which configures
threaded workers — the live job stream is a long-lived SSE response, and
gunicorn's default single synchronous worker cannot serve it alongside anything
else. See [`DEPLOY.md`](./DEPLOY.md).

Or with Docker:
```bash
docker build -t project-divert .
docker run --env-file .env -p 5000:5000 project-divert
```

## Operations

This repo includes runbooks for release/rollback, database backups, restore drills, and incident response under [`docs/runbooks/`](./docs/runbooks/), plus operational scripts under [`scripts/`](./scripts/) for backup automation and staging smoke tests.

Scheduled work — ops health digests, dispatch incident maintenance, billing
follow-ups and auth token cleanup — runs as RQ jobs. A cron service enqueues,
a worker executes: `flask enqueue <job>` and `python -m projectdivert.tasks.worker`.
Each job calls the same service function as its CLI equivalent, and falls back
to running inline when no queue is configured.

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

The suite is split by surface: `tests/unit` for service-layer logic and app
assembly, `tests/web` for the server-rendered routes, and `tests/api` for the
JSON API — including a contract test that fails if `docs/openapi.json` drifts
from the routes the application actually serves.

## Author

Louis Dods — [LinkedIn](https://www.linkedin.com/in/louis-dods/)
