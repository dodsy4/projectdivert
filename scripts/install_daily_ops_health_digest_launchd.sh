#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_DIR="${PROJECTDIVERT_PROJECT_DIR:-${DEFAULT_PROJECT_DIR}}"

LABEL="${OPS_HEALTH_DIGEST_LABEL:-com.projectdivert.ops-health-digest}"
HOUR="${OPS_HEALTH_DIGEST_HOUR:-8}"
MINUTE="${OPS_HEALTH_DIGEST_MINUTE:-0}"
ENV_FILE="${PROJECTDIVERT_ENV_FILE:-${HOME}/.projectdivert-ops-health.env}"
AUTH_WINDOW_MINUTES="${OPS_HEALTH_AUTH_WINDOW_MINUTES:-60}"
DISPATCH_LIMIT="${OPS_HEALTH_DISPATCH_LIMIT:-500}"

usage() {
  cat <<'EOF'
Install a daily launchd job for ops health digest.

Usage:
  ./scripts/install_daily_ops_health_digest_launchd.sh [options]

Options:
  --hour <0-23>                 Run hour (default: 8)
  --minute <0-59>               Run minute (default: 0)
  --label <launchd-label>       launchd label (default: com.projectdivert.ops-health-digest)
  --project-dir <path>          Project directory for app.py/.venv (default: this repo)
  --env-file <path>             Env file path loaded by digest runner (default: ~/.projectdivert-ops-health.env)
  --auth-window-minutes <mins>  Auth lookback window (default: 60)
  --dispatch-limit <rows>       Dispatch rows limit (default: 500)
  -h, --help                    Show this help
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
    --project-dir)
      PROJECT_DIR="${2:-}"
      shift 2
      ;;
    --env-file)
      ENV_FILE="${2:-}"
      shift 2
      ;;
    --auth-window-minutes)
      AUTH_WINDOW_MINUTES="${2:-}"
      shift 2
      ;;
    --dispatch-limit)
      DISPATCH_LIMIT="${2:-}"
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
if ! [[ "${AUTH_WINDOW_MINUTES}" =~ ^[1-9][0-9]*$ ]]; then
  echo "--auth-window-minutes must be an integer >= 1" >&2
  exit 1
fi
if ! [[ "${DISPATCH_LIMIT}" =~ ^[1-9][0-9]*$ ]]; then
  echo "--dispatch-limit must be an integer >= 1" >&2
  exit 1
fi
if [[ -z "${PROJECT_DIR}" || ! -d "${PROJECT_DIR}" ]]; then
  echo "--project-dir must point to an existing directory" >&2
  exit 1
fi
if [[ ! -f "${PROJECT_DIR}/app.py" ]]; then
  echo "app.py not found under project dir: ${PROJECT_DIR}" >&2
  exit 1
fi
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Env file not found: ${ENV_FILE}" >&2
  echo "Either create it or pass --env-file pointing to a file with DB env vars." >&2
  exit 1
fi

PLIST_DIR="${HOME}/Library/LaunchAgents"
RUNNER_DIR="${HOME}/Library/Application Support/projectdivert"
RUNNER_PATH="${RUNNER_DIR}/ops-health-digest-runner.sh"
LOG_DIR="${HOME}/Library/Logs/projectdivert"
PLIST_PATH="${PLIST_DIR}/${LABEL}.plist"
LAUNCHD_TARGET="gui/$(id -u)"

mkdir -p "${PLIST_DIR}" "${RUNNER_DIR}" "${LOG_DIR}"

cat > "${RUNNER_PATH}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${PROJECTDIVERT_ENV_FILE:-$HOME/.projectdivert-ops-health.env}"
PROJECT_DIR="${PROJECTDIVERT_PROJECT_DIR:-$HOME/projectdivert}"
AUTH_WINDOW_MINUTES="${OPS_HEALTH_AUTH_WINDOW_MINUTES:-60}"
DISPATCH_LIMIT="${OPS_HEALTH_DISPATCH_LIMIT:-500}"
WEBHOOK_URL="${OPS_HEALTH_DIGEST_WEBHOOK_URL:-}"
EMAIL_TO="${OPS_HEALTH_DIGEST_EMAIL_TO:-}"
INCLUDE_OK="${OPS_HEALTH_DIGEST_INCLUDE_OK:-0}"
FAIL_ON_CRITICAL="${OPS_HEALTH_DIGEST_FAIL_ON_CRITICAL:-0}"
LOG_TS() { date -u +'%Y-%m-%dT%H:%M:%SZ'; }

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a && source "${ENV_FILE}" && set +a
else
  echo "[$(LOG_TS)] ops-health-digest skipped: env file not found (${ENV_FILE})"
  exit 1
fi

if [[ -z "${SQLALCHEMY_DATABASE_URI:-}" && -z "${DATABASE_URL:-}" && -z "${PGHOST:-}" ]]; then
  echo "[$(LOG_TS)] ops-health-digest skipped: database env not configured"
  exit 1
fi

MAINTENANCE_ENABLED="${DISPATCH_INCIDENT_MAINTENANCE_ENABLED:-0}"
MAINTENANCE_DRY_RUN="${DISPATCH_INCIDENT_MAINTENANCE_DRY_RUN:-0}"
MAINTENANCE_LIMIT="${DISPATCH_INCIDENT_MAINTENANCE_LIMIT:-500}"
MAINTENANCE_OWNER_EMAIL="${DISPATCH_INCIDENT_AUTO_ASSIGN_ADMIN_EMAIL:-}"
BILLING_FOLLOWUPS_ENABLED="${OFFLINE_BILLING_FOLLOWUP_AUTOMATION_ENABLED:-0}"
BILLING_FOLLOWUPS_DRY_RUN="${OFFLINE_BILLING_FOLLOWUP_DRY_RUN:-0}"
BILLING_FOLLOWUPS_LIMIT="${OFFLINE_BILLING_FOLLOWUP_LIMIT:-200}"
BILLING_FOLLOWUPS_AFTER_HOURS="${OFFLINE_BILLING_FOLLOWUP_AFTER_HOURS:-72}"
BILLING_FOLLOWUPS_REPEAT_HOURS="${OFFLINE_BILLING_FOLLOWUP_REPEAT_HOURS:-72}"

VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python"
if [[ -x "${VENV_PYTHON}" ]]; then
  PYTHON_BIN="${VENV_PYTHON}"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "[$(LOG_TS)] ops-health-digest skipped: python not found"
  exit 1
fi

export FLASK_APP="${FLASK_APP:-${PROJECT_DIR}/app.py}"
export PYTHONPATH="${PROJECT_DIR}:${PYTHONPATH:-}"

if [[ ! -d "${PROJECT_DIR}" ]]; then
  echo "[$(LOG_TS)] ops-health-digest skipped: project dir not found (${PROJECT_DIR})"
  exit 1
fi
cd "${PROJECT_DIR}"

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
  maint_args=(--limit "${MAINTENANCE_LIMIT}")
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
  echo "[$(LOG_TS)] dispatch-incident-maintenance starting"
  "${PYTHON_BIN}" -m flask dispatch-incident-maintenance "${maint_args[@]}" || \
    echo "[$(LOG_TS)] dispatch-incident-maintenance failed"
  echo "[$(LOG_TS)] dispatch-incident-maintenance finished"
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
  echo "[$(LOG_TS)] offline-billing-followups starting"
  "${PYTHON_BIN}" -m flask offline-billing-followups "${billing_args[@]}" || \
    echo "[$(LOG_TS)] offline-billing-followups failed"
  echo "[$(LOG_TS)] offline-billing-followups finished"
fi

echo "[$(LOG_TS)] ops-health-digest starting"
"${PYTHON_BIN}" -m flask ops-health-digest "${args[@]}"
echo "[$(LOG_TS)] ops-health-digest finished"
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
    <string>${PROJECT_DIR}</string>
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
      <key>PROJECTDIVERT_PROJECT_DIR</key>
      <string>${PROJECT_DIR}</string>
      <key>OPS_HEALTH_AUTH_WINDOW_MINUTES</key>
      <string>${AUTH_WINDOW_MINUTES}</string>
      <key>OPS_HEALTH_DISPATCH_LIMIT</key>
      <string>${DISPATCH_LIMIT}</string>
    </dict>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/ops-health-digest.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/ops-health-digest.error.log</string>
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
echo "  tail -f ${LOG_DIR}/ops-health-digest.log ${LOG_DIR}/ops-health-digest.error.log"
