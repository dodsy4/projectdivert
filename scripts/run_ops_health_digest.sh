#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_ACTIVATE="${PROJECT_DIR}/.venv/bin/activate"
ENV_FILE="${PROJECTDIVERT_ENV_FILE:-${PROJECT_DIR}/.env}"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a && source "${ENV_FILE}" && set +a
fi

if [[ -f "${VENV_ACTIVATE}" ]]; then
  # shellcheck disable=SC1090
  source "${VENV_ACTIVATE}"
fi

export FLASK_APP="${FLASK_APP:-app.py}"

if [[ -z "${SQLALCHEMY_DATABASE_URI:-}" && -z "${DATABASE_URL:-}" && -z "${PGHOST:-}" ]]; then
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] ops-health-digest skipped: database env not configured"
  exit 1
fi

AUTH_WINDOW_MINUTES="${OPS_HEALTH_AUTH_WINDOW_MINUTES:-60}"
DISPATCH_LIMIT="${OPS_HEALTH_DISPATCH_LIMIT:-500}"
WEBHOOK_URL="${OPS_HEALTH_DIGEST_WEBHOOK_URL:-}"
EMAIL_TO="${OPS_HEALTH_DIGEST_EMAIL_TO:-}"
INCLUDE_OK="${OPS_HEALTH_DIGEST_INCLUDE_OK:-0}"
FAIL_ON_CRITICAL="${OPS_HEALTH_DIGEST_FAIL_ON_CRITICAL:-0}"
MAINTENANCE_ENABLED="${DISPATCH_INCIDENT_MAINTENANCE_ENABLED:-0}"
MAINTENANCE_DRY_RUN="${DISPATCH_INCIDENT_MAINTENANCE_DRY_RUN:-0}"
MAINTENANCE_OWNER_EMAIL="${DISPATCH_INCIDENT_AUTO_ASSIGN_ADMIN_EMAIL:-}"
BILLING_FOLLOWUPS_ENABLED="${OFFLINE_BILLING_FOLLOWUP_AUTOMATION_ENABLED:-0}"
BILLING_FOLLOWUPS_DRY_RUN="${OFFLINE_BILLING_FOLLOWUP_DRY_RUN:-0}"
BILLING_FOLLOWUPS_LIMIT="${OFFLINE_BILLING_FOLLOWUP_LIMIT:-200}"
BILLING_FOLLOWUPS_AFTER_HOURS="${OFFLINE_BILLING_FOLLOWUP_AFTER_HOURS:-72}"
BILLING_FOLLOWUPS_REPEAT_HOURS="${OFFLINE_BILLING_FOLLOWUP_REPEAT_HOURS:-72}"

is_truthy() {
  local value
  value="$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')"
  [[ "${value}" == "1" || "${value}" == "true" || "${value}" == "yes" || "${value}" == "on" ]]
}

args=(
  --auth-window-minutes "${AUTH_WINDOW_MINUTES}"
  --dispatch-limit "${DISPATCH_LIMIT}"
)

if is_truthy "${INCLUDE_OK}"; then
  args+=(--include-ok)
fi
if [[ -n "${WEBHOOK_URL}" ]]; then
  args+=(--webhook-url "${WEBHOOK_URL}")
fi
if [[ -n "${EMAIL_TO}" ]]; then
  args+=(--email-to "${EMAIL_TO}")
fi
if is_truthy "${FAIL_ON_CRITICAL}"; then
  args+=(--fail-on-critical)
fi

if is_truthy "${MAINTENANCE_ENABLED}"; then
  maint_args=(--limit "${DISPATCH_INCIDENT_MAINTENANCE_LIMIT:-500}")
  if is_truthy "${DISPATCH_INCIDENT_AUTO_ASSIGN_ENABLED:-0}"; then
    maint_args+=(--auto-assign)
  fi
  if is_truthy "${DISPATCH_INCIDENT_AUTO_RESOLVE_TEST_ENABLED:-0}"; then
    maint_args+=(--auto-resolve-test --resolve-test-minutes "${DISPATCH_INCIDENT_AUTO_RESOLVE_TEST_MINUTES:-720}")
  fi
  if [[ -n "${MAINTENANCE_OWNER_EMAIL}" ]]; then
    maint_args+=(--owner-admin-email "${MAINTENANCE_OWNER_EMAIL}")
  fi
  if is_truthy "${MAINTENANCE_DRY_RUN}"; then
    maint_args+=(--dry-run)
  fi
  if [[ "${#maint_args[@]}" -gt 0 ]]; then
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] dispatch-incident-maintenance starting"
    python -m flask dispatch-incident-maintenance "${maint_args[@]}" || \
      echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] dispatch-incident-maintenance failed"
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] dispatch-incident-maintenance finished"
  fi
fi

if is_truthy "${BILLING_FOLLOWUPS_ENABLED}"; then
  billing_args=(
    --limit "${BILLING_FOLLOWUPS_LIMIT}"
    --reminder-after-hours "${BILLING_FOLLOWUPS_AFTER_HOURS}"
    --repeat-hours "${BILLING_FOLLOWUPS_REPEAT_HOURS}"
    --log-reminders
  )
  if is_truthy "${BILLING_FOLLOWUPS_DRY_RUN}"; then
    billing_args+=(--dry-run)
  fi
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] offline-billing-followups starting"
  python -m flask offline-billing-followups "${billing_args[@]}" || \
    echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] offline-billing-followups failed"
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] offline-billing-followups finished"
fi

echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] ops-health-digest starting"
python -m flask ops-health-digest "${args[@]}"
echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] ops-health-digest finished"
