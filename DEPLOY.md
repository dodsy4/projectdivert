# Deploy Project Divert

## 1. Prerequisites
- Managed Postgres database
- Google Maps API key
- SendGrid account (or compatible email provider)
- Domain name (optional but recommended)

## 2. Environment Variables
Copy `.env.example` values into your host's environment settings.

Required minimum:
- `SECRET_KEY`
- `DATABASE_URL`
- `GOOGLE_MAPS_API_KEY`

For auth + request-notification emails:
- `MAIL_PROVIDER`
- `MAIL_FROM_EMAIL`
- `SENDGRID_API_KEY`
- `REQUEST_NOTIFICATION_EMAIL`

## 3. Deploy (Render)
Option A: use `render.yaml` Blueprint deploy.
Option B: create a Web Service manually with:
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`

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
- operational gaps like missing alert routing or backup env

## 5. Verify Production
- Home page loads (`/`)
- Materials list + map render
- Register/login/logout works
- Material request submits
- Request email notification arrives at `REQUEST_NOTIFICATION_EMAIL`

## 5a. Release Discipline
Use the release runbook for every production cut:
- `docs/runbooks/release-and-rollback.md`

Use the restore drill checklist monthly and before launch:
- `docs/runbooks/restore-drill-checklist.md`

## 6. Security Checklist
- `FLASK_DEBUG=0`
- `SESSION_COOKIE_SECURE=1`
- Rotate `SECRET_KEY` and API keys
- Enable HTTPS custom domain
- Enable DB backups on your provider
- Install local or host-level backup automation (`scripts/db_backup.sh`)
- Run a restore drill before launch and monthly after launch

## 7. Next Improvements
- Add password reset and email verification
- Add rate limiting / anti-spam on request forms
- Move image storage to S3/Cloudinary for durability

## 8. Operations
- Ops health digest: `./scripts/ops_health_digest.sh`
- Full staging smoke: `BASE_URL=http://127.0.0.1:5052 ./scripts/full_staging_smoke.sh`
- DB backup runbook: `docs/runbooks/database-backups.md`
- Production preflight runbook: `docs/runbooks/production-preflight.md`
- Release + rollback runbook: `docs/runbooks/release-and-rollback.md`
- Restore drill checklist: `docs/runbooks/restore-drill-checklist.md`
