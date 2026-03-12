# Release And Rollback Runbook

## Scope
Use this runbook for:
- production deploys
- release candidate cutovers
- rollback after bad migrations, broken runtime config, or elevated 5xx/error rates

This runbook assumes:
- the preflight script exists and passes
- backup automation exists
- a recent backup restore drill has already been completed

## Release Inputs
Before starting, capture:
- git commit SHA being released
- current production revision from `python -m flask db current`
- latest migration head from `python -m flask db heads`
- latest successful backup timestamp
- operator name and release start time

## Pre-Deploy Gate
Run these in order:

```bash
cd /Users/louisdods/Documents/GitHub/projectdivert
source .venv/bin/activate
export FLASK_APP=app.py
bash ./scripts/production_preflight.sh
python -m flask db heads
python -m flask db current
BASE_URL=http://127.0.0.1:5052 ./scripts/full_staging_smoke.sh
```

Do not continue if:
- preflight returns any `FAIL`
- DB current revision does not match heads
- staging smoke fails

## Deploy Sequence
1. Freeze changes:
   - stop merging non-release work
   - confirm the commit SHA to deploy
2. Confirm backup posture:
   - latest scheduled backup succeeded
   - latest restore drill is still within policy window
3. Deploy application code
4. Run migrations:

```bash
python -m flask db upgrade
```

5. If reference data changed, run:

```bash
python -m flask seed-reference-data
```

6. Restart app workers/processes
7. Run live verification checks

## Live Verification
Run these immediately after deploy:

```bash
bash ./scripts/production_preflight.sh --base-url https://yourdomain.com
```

Then verify:
- home page loads
- admin login works
- auth refresh/logout works
- waste request creation works
- admin dispatch queue loads
- ops health endpoint returns expected status
- compliance review queue loads

If you have a live-like environment available, also run:

```bash
BASE_URL=https://yourdomain.com ./scripts/full_staging_smoke.sh
```

Only do this if the smoke users/flows are safe for that environment.

## Rollback Triggers
Roll back if any of these happen and cannot be corrected quickly:
- sustained 5xx after deploy
- auth/login failures caused by config or migration mismatch
- dispatch assignment failures across multiple requests
- compliance upload/review paths broken
- migration introduced incompatible schema/runtime behavior

## Rollback Decision Rule
- If the failure is code/runtime only and schema remains compatible:
  - roll back app code first
- If the failure is caused by a new migration:
  - stop traffic if needed
  - assess whether migration downgrade is safe
  - prefer restoring service with previous compatible code only if schema allows it
- If data corruption or destructive migration occurred:
  - treat as incident
  - restore from backup into a verified recovery target

## Rollback Procedure
1. Identify the last known good commit SHA
2. Confirm whether the current schema is backward-compatible with that SHA
3. Redeploy the last known good code
4. If downgrade is required and explicitly verified safe:

```bash
python -m flask db downgrade -1
```

Do not run blind downgrades under pressure. Review the specific migration first.

5. Restart workers/processes
6. Re-run:

```bash
bash ./scripts/production_preflight.sh --base-url https://yourdomain.com
```

7. Verify core paths:
- login
- request create
- dispatch queue
- ops health

## Backup Restore Escalation
If rollback cannot recover service or data integrity:
1. Declare incident status
2. Stop writes if possible
3. Restore into a scratch target first
4. Validate tables, row shape, and app boot
5. Promote restore target only after verification

Use:
- [database-backups.md](/Users/louisdods/Documents/GitHub/projectdivert/docs/runbooks/database-backups.md)
- [restore-drill-checklist.md](/Users/louisdods/Documents/GitHub/projectdivert/docs/runbooks/restore-drill-checklist.md)

## Post-Release Record
Record:
- release SHA
- migration revision
- deploy time
- operator
- verification result
- rollback needed: yes/no
- follow-up issues

## Post-Rollback Record
Record:
- failed release SHA
- restored SHA
- migration state
- customer impact window
- root-cause category
- corrective actions
