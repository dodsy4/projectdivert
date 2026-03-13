# Production Preflight

## Purpose
Run this before each production deploy or release candidate cut. It catches the common failure modes already seen in this project:
- wrong Python environment
- app falling back to localhost Postgres
- unset or placeholder secrets
- migrations not applied
- provider config missing for mail, payments, or compliance storage

## Run

```bash
cd /Users/louisdods/Documents/GitHub/projectdivert
source .venv/bin/activate
export FLASK_APP=app.py
bash ./scripts/production_preflight.sh
```

If you want to test a running deployment too:

```bash
bash ./scripts/production_preflight.sh --base-url https://yourdomain.com
```

## Required Inputs
The script reads the same environment the app uses:
- `SECRET_KEY`
- `JWT_SECRET_KEY`
- database via `DATABASE_URL` or `PG*`
- `GOOGLE_MAPS_API_KEY`
- `APP_BASE_URL`

Conditional checks:
- `MAIL_PROVIDER=sendgrid` requires `SENDGRID_API_KEY` and `MAIL_FROM_EMAIL`
- `PAYMENTS_ENABLED=1` requires Stripe secrets
- `COMPLIANCE_STORAGE_BACKEND=s3` requires S3 config
- `PAYMENTS_ENABLED=0` checks whether offline billing follow-up automation is enabled and thresholded

## Important Flags
- `--allow-local-db`: only for local rehearsal; disables the managed-DB requirement
- `--skip-db`: skips DB connectivity and migration checks
- `--base-url URL`: checks a live deployment endpoint

## Pass Standard
Do not deploy if the script returns any `FAIL`.

Warnings are allowed only when they are intentional for the specific release. Typical examples:
- payments disabled for a non-payment launch
- mail provider still set to `console` in a local rehearsal
- local compliance storage in development

## Release Sequence
1. Run `bash ./scripts/production_preflight.sh`
2. Run `python -m flask db upgrade`
3. Run the staging smoke:
   `BASE_URL=http://127.0.0.1:5052 ./scripts/full_staging_smoke.sh`
4. For an offline-billing launch, also run:
   `BASE_URL=http://127.0.0.1:5052 ./scripts/offline_billing_ops_smoke.sh`
5. Confirm backup automation exists and the last restore drill is still current

## Failure Interpretation
- `database URI points at localhost`: app will miss Neon/managed Postgres and break at runtime
- `database migration drift detected`: deploy would boot with schema mismatch
- `SECRET_KEY is using the development default`: session and auth security are not launch-safe
- `MAIL_PROVIDER=console`: notifications will not leave the process
- `COMPLIANCE_STORAGE_BACKEND=local`: evidence files are not durable across app instances
- `offline billing follow-up automation is disabled`: invoicing reminders still depend entirely on manual review
