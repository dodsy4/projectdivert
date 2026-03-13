# Incident Response Runbook

## Scope
This runbook covers operational response for:
- dispatch backlog/SLA breaches
- auth abuse spikes (lockouts, rate limits, blocklist events)
- API stability issues surfaced by auth/audit 5xx signals

## Primary Signals
Use these endpoints first:
- `GET /api/v1/admin/ops/health`
- `GET /api/v1/admin/dispatch/telemetry`
- `GET /api/v1/admin/auth-security/telemetry`
- `GET /api/v1/admin/dispatch/incidents`
- `GET /api/v1/admin/waste-requests/<id>/timeline`

## Severity Definition
- `P1`:
  - `ops/health.status=critical`
  - any `incident_critical_breach`
  - sustained auth/audit 5xx events above threshold
- `P2`:
  - `ops/health.status=warning`
  - dispatch backlog warning threshold crossed
  - lockout/admin-rate-limit spikes
- `P3`:
  - transient warning cleared within one observation window

## Immediate Triage (First 10 Minutes)
1. Confirm impact:
   - Count affected requests (`/api/v1/admin/dispatch/incidents`)
   - Identify auth pressure (`/api/v1/admin/auth-security/telemetry`)
2. Stabilize:
   - Reassign stuck requests via `/api/v1/admin/waste-requests/<id>/dispatch/override`
   - Acknowledge active incidents via `/api/v1/admin/dispatch/incidents/<id>/ack`
3. Contain abuse:
   - Add temporary blocks via `/api/v1/admin/auth-security/blocks`
   - Revoke suspicious sessions via `/api/v1/admin/users/<id>/sessions/revoke`

## Investigation
1. Pull request-level timeline:
   - `/api/v1/admin/waste-requests/<id>/timeline?include_actor_auth=true`
2. Correlate actor activity:
   - `/api/v1/admin/auth-audit?user_id=<id>`
3. Validate queue health:
   - `/api/v1/admin/dispatch/queue?incidents_only=true`

## Recovery Actions
- Dispatch overload:
  - Temporarily increase admin overrides for top overdue jobs
  - Clear ownership ambiguity (set explicit incident owners)
- Auth attack pressure:
  - Tighten temporary blocks
  - Revoke sessions for targeted users
  - Monitor lockout and admin-rate-limit events every 5 minutes
- Platform instability:
  - Roll back latest change if 5xx continues
  - Verify DB connectivity and migration status

## Verification Checklist
- `ops/health.status` returns `ok` or stable `warning` with declining trends
- no unresolved critical incident breaches
- dispatch backlog below warning threshold
- lockout/admin-rate-limit events back to baseline

## Daily Digest
Run manually:
```bash
cd /Users/louisdods/Documents/GitHub/projectdivert
source .venv/bin/activate
export FLASK_APP=app.py
./scripts/ops_health_digest.sh --dry-run --include-ok
```

Send notifications:
```bash
./scripts/ops_health_digest.sh
```

Fail pipeline on critical:
```bash
./scripts/ops_health_digest.sh --fail-on-critical
```

Dry-run incident auto-maintenance:
```bash
python -m flask dispatch-incident-maintenance \
  --dry-run \
  --auto-assign \
  --auto-resolve-test \
  --resolve-test-minutes 720
```

Apply incident auto-maintenance:
```bash
python -m flask dispatch-incident-maintenance \
  --auto-assign \
  --auto-resolve-test \
  --resolve-test-minutes 720
```

Install daily launchd automation (macOS):
```bash
./scripts/install_daily_ops_health_digest_launchd.sh \
  --project-dir "$HOME/projectdivert-runtime" \
  --hour 8 --minute 0 \
  --env-file "$HOME/.projectdivert-ops-health.env"
```

For an offline-billing launch, add these to the same env file so the daily runner also logs reminder communications for stale `invoice_sent` requests:
```bash
OFFLINE_BILLING_FOLLOWUP_AUTOMATION_ENABLED=1
OFFLINE_BILLING_FOLLOWUP_DRY_RUN=0
OFFLINE_BILLING_FOLLOWUP_LIMIT=200
OFFLINE_BILLING_FOLLOWUP_AFTER_HOURS=72
OFFLINE_BILLING_FOLLOWUP_REPEAT_HOURS=72
```

Remove automation:
```bash
./scripts/uninstall_daily_ops_health_digest_launchd.sh
```

## Escalation and Communication
- `P1`: notify on-call immediately, update stakeholders every 15 minutes
- `P2`: notify within 30 minutes, update hourly until stable
- Attach:
  - `ops/health` snapshot JSON
  - top incident timeline links
  - auth telemetry summary
