# Restore Drill Checklist

## Purpose
Use this checklist for a monthly restore drill and before launch. The goal is to prove backups are usable, not just that backup files exist.

Preferred execution path:

```bash
cd /Users/louisdods/Documents/GitHub/projectdivert
source .venv/bin/activate
export FLASK_APP=app.py
bash ./scripts/restore_drill.sh --backup-file "$HOME/Backups/projectdivert/projectdivert-db_neondb_YYYYMMDDTHHMMSSZ.dump"
```

## Drill Metadata
- Date:
- Operator:
- Backup file:
- Manifest file:
- Source environment:
- Scratch restore target:

## Pre-Checks
- [ ] Backup archive exists
- [ ] Manifest exists next to archive
- [ ] Manifest SHA-256 matches archive SHA-256
- [ ] `pg_restore --list` succeeds on the archive
- [ ] Scratch database target is isolated from production

## Restore Steps
- [ ] Create scratch restore database
- [ ] Run restore with `--clean --if-exists --no-owner --no-privileges`
- [ ] Restore completes without fatal errors
- [ ] Connect successfully to the restored database

## Schema Verification
- [ ] `alembic_version` table exists
- [ ] Current migration revision matches expected release head
- [ ] Core auth tables exist:
  - [ ] `users`
  - [ ] `auth_security_blocklist`
  - [ ] `auth_lifecycle_tokens`
  - [ ] `auth_audit_events`
- [ ] Core dispatch tables exist:
  - [ ] `waste_removal_requests`
  - [ ] `waste_removal_dispatch_offers`
- [ ] Compliance tables exist:
  - [ ] `waste_compliance_documents`
  - [ ] `driver_compliance_documents`
  - [ ] `carrier_companies`
  - [ ] `company_compliance_documents`

## Data Verification
- [ ] At least one admin user row exists
- [ ] At least one waste request row exists or the empty-state is expected
- [ ] Auth audit data shape looks valid
- [ ] Dispatch incident/compliance rows deserialize correctly
- [ ] No obviously truncated critical tables

## Application Verification
- [ ] App boots against the restored database
- [ ] Admin login works in the restore target
- [ ] Ops health endpoint responds
- [ ] Dispatch queue endpoint responds
- [ ] Compliance review queue endpoint responds

## Recovery Readiness Decision
- [ ] Restore target is operationally usable
- [ ] Estimated recovery time recorded
- [ ] Any manual repair steps documented

## Cleanup
- [ ] Destroy scratch app environment
- [ ] Destroy scratch restore database
- [ ] Remove temporary secrets/env files used for the drill

## Record Outcome
- Result: pass / fail
- Recovery time:
- Issues found:
- Follow-up owner:
- Next drill due:
