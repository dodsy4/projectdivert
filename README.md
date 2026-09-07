# Project Divert

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
- Methodology, system boundary and limitations documented in [`docs/lca-methodology.md`](./docs/lca-methodology.md)

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
**Mobile:** Expo, React Native, TypeScript
**Ops:** Gunicorn, Render (deployment), pytest, GitHub Actions (secret scanning)

## Getting started

See [`DEPLOY.md`](./DEPLOY.md) for full backend deployment instructions (environment variables, database migration, production preflight checks), and [`mobile-app/README.md`](./mobile-app/README.md) for running the mobile app locally against a backend instance.

Quick local backend setup:
```bash
pip install -r requirements.txt
flask db upgrade
flask run
```

Or with Docker:
```bash
docker build -t project-divert .
docker run --env-file .env -p 5000:5000 project-divert
```

## Operations

This repo includes runbooks for release/rollback, database backups, restore drills, and incident response under [`docs/runbooks/`](./docs/runbooks/), plus operational scripts under [`scripts/`](./scripts/) for daily health digests, backup automation, and staging smoke tests.

## Testing

```bash
pytest
```

## Author

Louis Dods — [LinkedIn](https://www.linkedin.com/in/louis-dods/)
