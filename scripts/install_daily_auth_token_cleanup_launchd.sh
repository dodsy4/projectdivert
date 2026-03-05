#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

LABEL="${AUTH_TOKEN_CLEANUP_LABEL:-com.projectdivert.auth-token-cleanup}"
HOUR="${AUTH_TOKEN_CLEANUP_HOUR:-3}"
MINUTE="${AUTH_TOKEN_CLEANUP_MINUTE:-15}"
ENV_FILE="${PROJECTDIVERT_ENV_FILE:-${HOME}/.projectdivert-auth-cleanup.env}"
RETENTION_DAYS="${AUTH_TOKEN_CLEANUP_RETENTION_DAYS:-30}"
BATCH_SIZE="${AUTH_TOKEN_CLEANUP_BATCH_SIZE:-500}"

usage() {
  cat <<'EOF'
Install a daily launchd job for auth token cleanup.

Usage:
  ./scripts/install_daily_auth_token_cleanup_launchd.sh [options]

Options:
  --hour <0-23>                 Run hour (default: 3)
  --minute <0-59>               Run minute (default: 15)
  --label <launchd-label>       launchd label (default: com.projectdivert.auth-token-cleanup)
  --env-file <path>             Env file path loaded by cleanup runner (default: ~/.projectdivert-auth-cleanup.env)
  --retention-days <days>       AUTH_TOKEN_CLEANUP_RETENTION_DAYS (default: 30)
  --batch-size <size>           AUTH_TOKEN_CLEANUP_BATCH_SIZE (default: 500)
  -h, --help                    Show this help

Examples:
  ./scripts/install_daily_auth_token_cleanup_launchd.sh
  ./scripts/install_daily_auth_token_cleanup_launchd.sh --hour 2 --minute 30
  ./scripts/install_daily_auth_token_cleanup_launchd.sh --env-file /Users/me/.projectdivert-auth-cleanup.env
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hour)
      HOUR="${2:-}"
      shift 2
      ;;
    --minute)
      MINUTE="${2:-}"
      shift 2
      ;;
    --label)
      LABEL="${2:-}"
      shift 2
      ;;
    --env-file)
      ENV_FILE="${2:-}"
      shift 2
      ;;
    --retention-days)
      RETENTION_DAYS="${2:-}"
      shift 2
      ;;
    --batch-size)
      BATCH_SIZE="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! [[ "${HOUR}" =~ ^[0-9]+$ ]] || (( HOUR < 0 || HOUR > 23 )); then
  echo "--hour must be an integer from 0 to 23" >&2
  exit 1
fi
if ! [[ "${MINUTE}" =~ ^[0-9]+$ ]] || (( MINUTE < 0 || MINUTE > 59 )); then
  echo "--minute must be an integer from 0 to 59" >&2
  exit 1
fi
if ! [[ "${RETENTION_DAYS}" =~ ^[0-9]+$ ]]; then
  echo "--retention-days must be a non-negative integer" >&2
  exit 1
fi
if ! [[ "${BATCH_SIZE}" =~ ^[1-9][0-9]*$ ]]; then
  echo "--batch-size must be an integer >= 1" >&2
  exit 1
fi
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Env file not found: ${ENV_FILE}" >&2
  echo "Either create it or pass --env-file pointing to a file with DB env vars." >&2
  exit 1
fi

PLIST_DIR="${HOME}/Library/LaunchAgents"
RUNNER_DIR="${HOME}/Library/Application Support/projectdivert"
RUNNER_PATH="${RUNNER_DIR}/auth-token-cleanup-runner.sh"
LOG_DIR="${HOME}/Library/Logs/projectdivert"
PLIST_PATH="${PLIST_DIR}/${LABEL}.plist"
LAUNCHD_TARGET="gui/$(id -u)"

mkdir -p "${PLIST_DIR}" "${RUNNER_DIR}" "${LOG_DIR}"

cat > "${RUNNER_PATH}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${PROJECTDIVERT_ENV_FILE:-$HOME/.projectdivert-auth-cleanup.env}"
RETENTION_DAYS="${AUTH_TOKEN_CLEANUP_RETENTION_DAYS:-30}"
BATCH_SIZE="${AUTH_TOKEN_CLEANUP_BATCH_SIZE:-500}"
LOG_TS() { date -u +'%Y-%m-%dT%H:%M:%SZ'; }
TOKEN_TABLE="auth_lifecycle_tokens"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a && source "${ENV_FILE}" && set +a
else
  echo "[$(LOG_TS)] auth-token-cleanup skipped: env file not found (${ENV_FILE})"
  exit 1
fi

PSQL_BIN=""
if command -v psql >/dev/null 2>&1; then
  PSQL_BIN="$(command -v psql)"
elif [[ -x "/opt/homebrew/bin/psql" ]]; then
  PSQL_BIN="/opt/homebrew/bin/psql"
elif [[ -x "/usr/local/bin/psql" ]]; then
  PSQL_BIN="/usr/local/bin/psql"
else
  echo "[$(LOG_TS)] auth-token-cleanup skipped: psql not found"
  exit 1
fi

required_vars=(PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD)
for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "[$(LOG_TS)] auth-token-cleanup skipped: missing ${var_name}"
    exit 1
  fi
done

# Neon + older libpq/psql may need explicit endpoint option.
if [[ "${PGHOST}" == *.neon.tech ]] && [[ -z "${PGOPTIONS:-}" ]]; then
  endpoint_id="${PGHOST%%.*}"
  endpoint_id="${endpoint_id%-pooler}"
  export PGOPTIONS="endpoint=${endpoint_id}"
fi

if ! [[ "${RETENTION_DAYS}" =~ ^[0-9]+$ ]]; then
  echo "[$(LOG_TS)] auth-token-cleanup skipped: invalid AUTH_TOKEN_CLEANUP_RETENTION_DAYS (${RETENTION_DAYS})"
  exit 1
fi
if ! [[ "${BATCH_SIZE}" =~ ^[1-9][0-9]*$ ]]; then
  echo "[$(LOG_TS)] auth-token-cleanup skipped: invalid AUTH_TOKEN_CLEANUP_BATCH_SIZE (${BATCH_SIZE})"
  exit 1
fi

cutoff="$("${PSQL_BIN}" -qtAX -c "SELECT to_char((now() - interval '${RETENTION_DAYS} days') at time zone 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')")"
candidates="$("${PSQL_BIN}" -qtAX -c "SELECT count(*) FROM ${TOKEN_TABLE} WHERE expires_at <= (now() - interval '${RETENTION_DAYS} days') OR (revoked_at IS NOT NULL AND revoked_at <= (now() - interval '${RETENTION_DAYS} days'))")"

echo "[$(LOG_TS)] auth-token-cleanup starting (retention_days=${RETENTION_DAYS}, batch_size=${BATCH_SIZE})"
echo "Auth token cleanup cutoff: ${cutoff}"
echo "Candidates: ${candidates}"

if [[ "${candidates}" == "0" ]]; then
  echo "No rows to delete."
  echo "[$(LOG_TS)] auth-token-cleanup finished"
  exit 0
fi

deleted_total=0
while true; do
  deleted_batch="$("${PSQL_BIN}" -qtAX <<SQL
WITH to_delete AS (
  SELECT id
  FROM ${TOKEN_TABLE}
  WHERE expires_at <= (now() - interval '${RETENTION_DAYS} days')
     OR (revoked_at IS NOT NULL AND revoked_at <= (now() - interval '${RETENTION_DAYS} days'))
  ORDER BY id ASC
  LIMIT ${BATCH_SIZE}
),
deleted AS (
  DELETE FROM ${TOKEN_TABLE}
  WHERE id IN (SELECT id FROM to_delete)
  RETURNING id
)
SELECT count(*) FROM deleted;
SQL
)"
  deleted_batch="${deleted_batch//[[:space:]]/}"
  if [[ -z "${deleted_batch}" ]]; then
    deleted_batch=0
  fi
  if (( deleted_batch == 0 )); then
    break
  fi
  deleted_total=$((deleted_total + deleted_batch))
done

echo "Deleted rows: ${deleted_total}"
echo "[$(LOG_TS)] auth-token-cleanup finished"
EOF

chmod +x "${RUNNER_PATH}"

cat > "${PLIST_PATH}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
      <string>/bin/bash</string>
      <string>${RUNNER_PATH}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${HOME}</string>
    <key>StartCalendarInterval</key>
    <dict>
      <key>Hour</key>
      <integer>${HOUR}</integer>
      <key>Minute</key>
      <integer>${MINUTE}</integer>
    </dict>
    <key>EnvironmentVariables</key>
    <dict>
      <key>PATH</key>
      <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
      <key>FLASK_APP</key>
      <string>app.py</string>
      <key>PROJECTDIVERT_ENV_FILE</key>
      <string>${ENV_FILE}</string>
      <key>AUTH_TOKEN_CLEANUP_RETENTION_DAYS</key>
      <string>${RETENTION_DAYS}</string>
      <key>AUTH_TOKEN_CLEANUP_BATCH_SIZE</key>
      <string>${BATCH_SIZE}</string>
    </dict>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/auth-token-cleanup.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/auth-token-cleanup.error.log</string>
    <key>RunAtLoad</key>
    <false/>
  </dict>
</plist>
EOF

if launchctl print "${LAUNCHD_TARGET}/${LABEL}" >/dev/null 2>&1; then
  launchctl bootout "${LAUNCHD_TARGET}" "${PLIST_PATH}" >/dev/null 2>&1 || true
fi

launchctl bootstrap "${LAUNCHD_TARGET}" "${PLIST_PATH}"
launchctl enable "${LAUNCHD_TARGET}/${LABEL}" >/dev/null 2>&1 || true

echo "Installed: ${PLIST_PATH}"
echo "Runner: ${RUNNER_PATH}"
echo "Schedule: daily at $(printf '%02d:%02d' "${HOUR}" "${MINUTE}")"
echo "To test immediately:"
echo "  launchctl kickstart -k ${LAUNCHD_TARGET}/${LABEL}"
echo "To inspect status:"
echo "  launchctl print ${LAUNCHD_TARGET}/${LABEL}"
echo "Logs:"
echo "  tail -f ${LOG_DIR}/auth-token-cleanup.log ${LOG_DIR}/auth-token-cleanup.error.log"
