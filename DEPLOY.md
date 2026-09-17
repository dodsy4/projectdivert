# Deploy Project Divert

## 1. Prerequisites
- Managed Postgres database
- Google Maps API key
- SendGrid account (or compatible email provider)
- Domain name (optional but recommended)

## 2. Environment Variables
Copy `.env.example` values into your host's environment settings.

Required minimum:
- `SECRET_KEY` (the app refuses to start without it unless `FLASK_DEBUG=1`)
- `DATABASE_URL`
- `GOOGLE_MAPS_API_KEY`
- `REDIS_URL` or `RQ_REDIS_URL` — needed for the job queue and for live job
  tracking to work across more than one web worker

For auth + request-notification emails:
- `MAIL_PROVIDER`
- `MAIL_FROM_EMAIL`
- `SENDGRID_API_KEY`
- `REQUEST_NOTIFICATION_EMAIL`

## 3. Deploy (Render)
Option A: use `render.yaml` Blueprint deploy.
Option B: create a Web Service manually with:
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn --config gunicorn.conf.py wsgi:app`

The config file is not optional. Gunicorn's defaults are a single synchronous
worker, which the Server-Sent Events endpoint at
`/api/v1/waste-requests/<id>/events` will occupy for as long as one client is
watching a job, and which the default 30s timeout would kill anyway.
`gunicorn.conf.py` sets threaded workers and the matching timeouts.

## 4. Database Migration
After first deploy, run:
- `flask db upgrade`
- `flask seed-reference-data` (loads supplier/site/offset reference tables from existing files)

## 4a. Production Preflight
Before each release or deploy, run:
- `bash ./scripts/production_preflight.sh`

This checks:
- required secrets and provider config
- DB connectivity
- migration drift
- unsafe localhost DB fallback
- operational gaps like missing alert routing, offline billing follow-up automation, or backup env

## 5. Verify Production
- Home page loads (`/`)
- Materials list + map render
- Register/login/logout works
- Material request submits
- Request email notification arrives at `REQUEST_NOTIFICATION_EMAIL`
- Offline billing ops smoke passes for no-payments launch:
  `BASE_URL=http://127.0.0.1:5052 ./scripts/offline_billing_ops_smoke.sh`

## 5a. Release Discipline
Use the release runbook for every production cut:
- `docs/runbooks/release-and-rollback.md`

Use the restore drill checklist monthly and before launch:
- `docs/runbooks/restore-drill-checklist.md`

## 6. Security Checklist
- `FLASK_DEBUG=0`
- `SESSION_COOKIE_SECURE=1`
- Rotate `SECRET_KEY` and API keys
- `SECRET_KEY` and `JWT_SECRET_KEY` must not be the development placeholder;
  the app refuses to boot if they are, and
  `scripts/production_preflight.sh` checks the same thing before a deploy
- CSRF protection covers every cookie-authenticated form; the `/api/v1`
  blueprints are exempt because they authenticate by Bearer token or provider
  signature rather than by cookie
- Enable HTTPS custom domain
- Enable DB backups on your provider
- Install local or host-level backup automation (`scripts/db_backup.sh`)
- Run a restore drill before launch and monthly after launch

## 7. Roadmap

Shipped since this guide was first written, and no longer outstanding:
password reset and email verification (`/api/v1/auth/password-reset/*`,
`/api/v1/auth/verify/*`), auth rate limiting with escalating login lockout and
a security blocklist, and S3-backed storage for compliance documents.

Still open:
- Rate limiting / anti-spam on the public web request forms. Only the auth API
  is rate limited today.
- Material images still write to local disk (`static/uploads/`); only
  compliance uploads use object storage. On a single Render instance this is
  ephemeral, so material photos do not survive a redeploy.
- Background jobs run through RQ (`rq worker`), but the scheduler is still
  driven by Render cron rather than a persistent scheduler process.

## 7a. Background Jobs

Scheduled work runs through RQ. Scheduling and execution are separate on
purpose: a Render cron service enqueues a job, and a single worker service
executes it, so retries and failures are visible in one place instead of cron
shelling into the web instance.

- Worker: `python -m projectdivert.tasks.worker`
- Enqueue by hand: `flask enqueue <job>` (add `--sync` to run it inline,
  `--dry-run` to compute without persisting)
- Jobs: `ops-health-digest`, `dispatch-incident-maintenance`,
  `offline-billing-followups`, `auth-token-cleanup`

Each job calls the same service function as the equivalent CLI command, so a
scheduled run and a manual run cannot diverge.

If `RQ_REDIS_URL` (or `REDIS_URL`) is unset, or Redis is unreachable, `flask
enqueue` runs the job inline and logs that it did. Work still happens without a
queue; it just happens in the calling process.

The `scripts/install_daily_*_launchd.sh` helpers remain for running these on a
local macOS machine. On Render, the cron services in `render.yaml` are the
scheduler.

## 8. Operations
- Ops health digest: `./scripts/ops_health_digest.sh`
- Full staging smoke: `BASE_URL=http://127.0.0.1:5052 ./scripts/full_staging_smoke.sh`
- Offline billing ops smoke: `BASE_URL=http://127.0.0.1:5052 ./scripts/offline_billing_ops_smoke.sh`
- DB backup runbook: `docs/runbooks/database-backups.md`
- Production preflight runbook: `docs/runbooks/production-preflight.md`
- Release + rollback runbook: `docs/runbooks/release-and-rollback.md`
- Restore drill checklist: `docs/runbooks/restore-drill-checklist.md`
