#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ALLOW_LOCAL_DB=0
SKIP_DB=0
BASE_URL_OVERRIDE="${BASE_URL:-}"

usage() {
  cat <<'EOF'
Usage: ./scripts/production_preflight.sh [options]

Checks production-readiness blockers before deploy:
- required binaries
- env/config sanity
- DB connectivity and migration status
- provider-specific config gates

Options:
  --allow-local-db     Permit localhost/127.0.0.1 database URIs
  --skip-db            Skip DB connectivity and migration checks
  --base-url URL       Check a live app health endpoint at URL
  --help               Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --allow-local-db)
      ALLOW_LOCAL_DB=1
      ;;
    --skip-db)
      SKIP_DB=1
      ;;
    --base-url)
      shift
      [[ $# -gt 0 ]] || { echo "Missing value for --base-url" >&2; exit 2; }
      BASE_URL_OVERRIDE="$1"
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

cd "${PROJECT_ROOT}"

PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  printf 'PASS: %s\n' "$1"
}

warn() {
  WARN_COUNT=$((WARN_COUNT + 1))
  printf 'WARN: %s\n' "$1"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  printf 'FAIL: %s\n' "$1"
}

need_cmd() {
  local cmd="$1"
  if command -v "${cmd}" >/dev/null 2>&1; then
    pass "binary available: ${cmd}"
  else
    fail "missing required binary: ${cmd}"
  fi
}

is_placeholder_value() {
  local value="${1:-}"
  local lowered
  lowered="$(printf '%s' "${value}" | tr '[:upper:]' '[:lower:]')"
  [[ -z "${value}" ]] && return 0
  [[ "${lowered}" == replace-me* ]] && return 0
  [[ "${lowered}" == changeme* ]] && return 0
  [[ "${lowered}" == example* ]] && return 0
  [[ "${lowered}" == your-* ]] && return 0
  [[ "${lowered}" == test_* ]] && return 0
  [[ "${lowered}" == sk_test_* ]] && return 0
  [[ "${lowered}" == whsec_replace_me* ]] && return 0
  return 1
}

require_env() {
  local name="$1"
  local value="${!name:-}"
  if is_placeholder_value "${value}"; then
    fail "${name} is missing or placeholder"
  else
    pass "${name} is set"
  fi
}

warn_if_blank() {
  local name="$1"
  local value="${!name:-}"
  if [[ -z "${value}" ]]; then
    warn "${name} is not set"
  else
    pass "${name} is set"
  fi
}

need_cmd python
need_cmd curl

if [[ ${SKIP_DB} -eq 0 ]]; then
  need_cmd pg_dump
  need_cmd pg_restore
fi

if [[ ! -f ".venv/bin/python" ]]; then
  warn "project virtualenv not found at .venv/bin/python"
else
  pass "project virtualenv found"
fi

if [[ "${FLASK_APP:-}" != "app.py" ]]; then
  warn "FLASK_APP is not set to app.py in this shell"
else
  pass "FLASK_APP is set to app.py"
fi

require_env SECRET_KEY
if [[ "${SECRET_KEY:-}" == "dev-only-change-me" ]]; then
  fail "SECRET_KEY is using the development default"
fi

if [[ -z "${JWT_SECRET_KEY:-}" ]]; then
  warn "JWT_SECRET_KEY not set; app will fall back to SECRET_KEY"
else
  if [[ "${JWT_SECRET_KEY}" == "${SECRET_KEY:-}" ]]; then
    warn "JWT_SECRET_KEY matches SECRET_KEY; separate rotation is recommended"
  else
    pass "JWT_SECRET_KEY is separately configured"
  fi
fi

if [[ "${SESSION_COOKIE_SECURE:-1}" =~ ^(1|true|TRUE|yes|YES|on|ON)$ ]]; then
  pass "SESSION_COOKIE_SECURE is enabled"
else
  fail "SESSION_COOKIE_SECURE must be enabled for production"
fi

require_env GOOGLE_MAPS_API_KEY
require_env APP_BASE_URL

MAIL_PROVIDER_VALUE="${MAIL_PROVIDER:-console}"
case "${MAIL_PROVIDER_VALUE}" in
  sendgrid)
    require_env MAIL_FROM_EMAIL
    require_env SENDGRID_API_KEY
    ;;
  console)
    warn "MAIL_PROVIDER=console; emails are not deliverable in production"
    ;;
  *)
    require_env MAIL_FROM_EMAIL
    warn "MAIL_PROVIDER=${MAIL_PROVIDER_VALUE}; verify provider wiring manually"
    ;;
esac

if [[ "${PAYMENTS_ENABLED:-0}" =~ ^(1|true|TRUE|yes|YES|on|ON)$ ]]; then
  require_env STRIPE_SECRET_KEY
  require_env STRIPE_WEBHOOK_SECRET
else
  warn "PAYMENTS_ENABLED is off; payment flows are disabled"
fi

COMPLIANCE_STORAGE_VALUE="${COMPLIANCE_STORAGE_BACKEND:-local}"
case "${COMPLIANCE_STORAGE_VALUE}" in
  s3)
    require_env COMPLIANCE_S3_BUCKET
    if [[ -z "${COMPLIANCE_S3_ENDPOINT_URL:-}" ]]; then
      require_env COMPLIANCE_S3_REGION
    else
      pass "COMPLIANCE_S3_ENDPOINT_URL is set"
    fi
    require_env COMPLIANCE_S3_ACCESS_KEY_ID
    require_env COMPLIANCE_S3_SECRET_ACCESS_KEY
    require_env COMPLIANCE_S3_PUBLIC_BASE_URL
    ;;
  local)
    warn "COMPLIANCE_STORAGE_BACKEND=local; uploaded evidence is stored on app disk"
    ;;
  *)
    fail "Unsupported COMPLIANCE_STORAGE_BACKEND=${COMPLIANCE_STORAGE_VALUE}"
    ;;
esac

OPS_DIGEST_CONFIGURED=0
if [[ -n "${OPS_HEALTH_DIGEST_WEBHOOK_URL:-}" || -n "${OPS_HEALTH_DIGEST_EMAIL_TO:-}" ]]; then
  OPS_DIGEST_CONFIGURED=1
fi
if [[ ${OPS_DIGEST_CONFIGURED} -eq 1 ]]; then
  pass "ops health alert delivery is configured"
else
  warn "ops health digest delivery is not configured"
fi

if [[ "${PAYMENTS_ENABLED:-0}" =~ ^(1|true|TRUE|yes|YES|on|ON)$ ]]; then
  pass "offline billing follow-up automation not required while payments are enabled"
else
  if [[ "${OFFLINE_BILLING_FOLLOWUP_AUTOMATION_ENABLED:-0}" =~ ^(1|true|TRUE|yes|YES|on|ON)$ ]]; then
    pass "offline billing follow-up automation is enabled"
  else
    warn "offline billing follow-up automation is disabled"
  fi

  if [[ -n "${OFFLINE_BILLING_FOLLOWUP_AFTER_HOURS:-}" ]]; then
    pass "offline billing follow-up threshold is configured"
  else
    warn "OFFLINE_BILLING_FOLLOWUP_AFTER_HOURS not set; default threshold will be used"
  fi
fi

if [[ -f "${HOME}/.projectdivert-db-backup.env" || -n "${BACKUP_OUTPUT_DIR:-}" ]]; then
  pass "backup automation env appears configured"
else
  warn "backup automation env not detected in current shell/user home"
fi

if [[ ${SKIP_DB} -eq 0 ]]; then
  DB_URI="$(python - <<'PY'
import config
print(config.SQLALCHEMY_DATABASE_URI)
PY
)"

  if [[ -z "${DB_URI}" ]]; then
    fail "could not resolve SQLALCHEMY_DATABASE_URI"
  else
    pass "SQLALCHEMY_DATABASE_URI resolved"
  fi

  if [[ ${ALLOW_LOCAL_DB} -eq 0 ]]; then
    if [[ "${DB_URI}" == *"localhost"* || "${DB_URI}" == *"127.0.0.1"* ]]; then
      fail "database URI points at localhost; production preflight requires managed DB"
    else
      pass "database URI is not localhost"
    fi
  else
    warn "localhost DB allowed by --allow-local-db"
  fi

  if python - <<'PY'
import os
import psycopg2

conn = psycopg2.connect(
    host=os.environ.get("PGHOST", ""),
    port=os.environ.get("PGPORT", "5432"),
    dbname=os.environ.get("PGDATABASE", ""),
    user=os.environ.get("PGUSER", ""),
    password=os.environ.get("PGPASSWORD", ""),
    sslmode=os.environ.get("PGSSLMODE", "prefer"),
)
conn.close()
PY
  then
    pass "database connection succeeded via PG* env"
  elif python - <<'PY'
import config
import psycopg2

conn = psycopg2.connect(config.SQLALCHEMY_DATABASE_URI)
conn.close()
PY
  then
    pass "database connection succeeded via SQLALCHEMY_DATABASE_URI"
  else
    fail "database connection test failed"
  fi

  CURRENT_REV="$(python -m flask db current 2>/tmp/projectdivert_db_current.err | tail -n 1 || true)"
  HEAD_REV="$(python -m flask db heads 2>/tmp/projectdivert_db_heads.err | tail -n 1 || true)"

  if [[ -n "${CURRENT_REV}" && -n "${HEAD_REV}" ]]; then
    CURRENT_REV="${CURRENT_REV%% *}"
    HEAD_REV="${HEAD_REV%% *}"
    if [[ "${CURRENT_REV}" == "${HEAD_REV}" ]]; then
      pass "database is at migration head (${HEAD_REV})"
    else
      fail "database migration drift detected (current=${CURRENT_REV}, head=${HEAD_REV})"
    fi
  else
    fail "could not determine migration status"
  fi
fi

if [[ -n "${BASE_URL_OVERRIDE}" ]]; then
  if curl -fsS "${BASE_URL_OVERRIDE}/api/v1/health" >/dev/null 2>&1; then
    pass "live health endpoint reachable at ${BASE_URL_OVERRIDE}/api/v1/health"
  elif curl -fsS "${BASE_URL_OVERRIDE}/" >/dev/null 2>&1; then
    warn "base URL reachable but /api/v1/health not available"
  else
    fail "base URL not reachable: ${BASE_URL_OVERRIDE}"
  fi
fi

printf '\nSummary: %s pass, %s warn, %s fail\n' "${PASS_COUNT}" "${WARN_COUNT}" "${FAIL_COUNT}"
if [[ ${FAIL_COUNT} -gt 0 ]]; then
  exit 1
fi
