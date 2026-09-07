# Project Divert

Project Divert is a full-stack platform for diverting surplus construction and office materials away from landfill — matching materials with reuse/recycling destinations, coordinating waste-removal logistics with real-time driver dispatch, and quantifying the carbon impact of every diversion.

It began as a materials marketplace with a Scope 3 carbon accounting engine, and has grown into a two-sided operational platform: a Flask backend handling everything from JWT-authenticated APIs to Stripe payments and driver compliance, and a companion Expo/React Native mobile app for customers and drivers.

## Core features

**Materials marketplace**
- Post surplus materials (with photos, dimensions, condition) for reuse
- Search and filter by location, radius, and material type
- Request/response workflow between suppliers and reuse partners

**Carbon accounting engine**
- Calculates net avoided CO2e for every diversion, comparing landfill vs. recycling vs. reuse pathways
- Emission factors sourced from DEFRA, WRAP, and other public datasets, applied per material type and transport distance
- Distance-weighted routing via the Google Maps Distance Matrix API

**Waste removal & dispatch**
- Customers submit waste-removal requests; drivers receive and accept dispatch offers
- Live GPS location tracking for active jobs, streamed to the mobile app over Server-Sent Events
- Admin dispatch console with manual override, incident tracking, and telemetry

**Compliance & statutory tracking**
- Digital tracking of Waste Transfer Notes (WTNs) and other compliance documents
- Driver and carrier-company compliance document upload, review, and verification workflow
- Full audit trail (`AuthAuditEvent`) for authentication and admin actions

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

**Backend:** Python, Flask, SQLAlchemy, PostgreSQL, Redis, PyJWT, Stripe API, boto3 (S3-compatible storage), SendGrid, Pandas
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
