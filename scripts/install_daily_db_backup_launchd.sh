#!/usr/bin/env bash
set -euo pipefail

LABEL="${DB_BACKUP_LABEL:-com.projectdivert.db-backup}"
HOUR="${DB_BACKUP_HOUR:-2}"
MINUTE="${DB_BACKUP_MINUTE:-45}"
ENV_FILE="${PROJECTDIVERT_ENV_FILE:-${HOME}/.projectdivert-db-backup.env}"
OUTPUT_DIR="${BACKUP_OUTPUT_DIR:-${HOME}/Backups/projectdivert}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
BACKUP_PREFIX="${BACKUP_LABEL:-projectdivert-db}"
PG_BIN_DIR="${PG_BIN_DIR:-}"

usage() {
  cat <<'EOF'
Install a daily launchd job for Project Divert database backups.

Usage:
  ./scripts/install_daily_db_backup_launchd.sh [options]

Options:
  --hour <0-23>                 Run hour (default: 2)
  --minute <0-59>               Run minute (default: 45)
  --label <launchd-label>       launchd label (default: com.projectdivert.db-backup)
  --env-file <path>             Env file path loaded by backup runner (default: ~/.projectdivert-db-backup.env)
  --output-dir <path>           Backup output directory (default: ~/Backups/projectdivert)
  --retention-days <days>       BACKUP_RETENTION_DAYS (default: 14)
  --backup-label <name>         Backup file label prefix (default: projectdivert-db)
  --pg-bin-dir <path>           Directory containing pg_dump/pg_restore
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
    --env-file)
      ENV_FILE="${2:-}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    --retention-days)
      RETENTION_DAYS="${2:-}"
      shift 2
      ;;
    --backup-label)
      BACKUP_PREFIX="${2:-}"
      shift 2
      ;;
    --pg-bin-dir)
      PG_BIN_DIR="${2:-}"
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
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Env file not found: ${ENV_FILE}" >&2
  echo "Either create it or pass --env-file pointing to a file with DB env vars." >&2
  exit 1
fi

PLIST_DIR="${HOME}/Library/LaunchAgents"
RUNNER_DIR="${HOME}/Library/Application Support/projectdivert"
RUNNER_PATH="${RUNNER_DIR}/db-backup-runner.sh"
LOG_DIR="${HOME}/Library/Logs/projectdivert"
PLIST_PATH="${PLIST_DIR}/${LABEL}.plist"
LAUNCHD_TARGET="gui/$(id -u)"

mkdir -p "${PLIST_DIR}" "${RUNNER_DIR}" "${LOG_DIR}" "${OUTPUT_DIR}"

cat > "${RUNNER_PATH}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${PROJECTDIVERT_ENV_FILE:-$HOME/.projectdivert-db-backup.env}"
OUTPUT_DIR="${BACKUP_OUTPUT_DIR:-$HOME/Backups/projectdivert}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
LABEL="${BACKUP_LABEL:-projectdivert-db}"
LOG_TS() { date -u +'%Y-%m-%dT%H:%M:%SZ'; }

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a && source "${ENV_FILE}" && set +a
else
  echo "[$(LOG_TS)] db-backup skipped: env file not found (${ENV_FILE})"
  exit 1
fi

PG_DUMP_BIN=""
resolve_pg_bin() {
  local tool_name="$1"
  if [[ -n "${PG_BIN_DIR:-}" && -x "${PG_BIN_DIR}/${tool_name}" ]]; then
    printf '%s\n' "${PG_BIN_DIR}/${tool_name}"
    return 0
  fi
  if command -v "${tool_name}" >/dev/null 2>&1; then
    command -v "${tool_name}"
    return 0
  fi
  local candidate
  for candidate in \
    "/opt/homebrew/opt/postgresql@18/bin/${tool_name}" \
    "/opt/homebrew/opt/libpq/bin/${tool_name}" \
    "/opt/homebrew/bin/${tool_name}" \
    "/usr/local/opt/postgresql@18/bin/${tool_name}" \
    "/usr/local/opt/libpq/bin/${tool_name}" \
    "/usr/local/bin/${tool_name}"
  do
    if [[ -x "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done
  return 1
}

PG_DUMP_BIN="$(resolve_pg_bin pg_dump)" || {
  echo "[$(LOG_TS)] db-backup skipped: pg_dump not found; set PG_BIN_DIR to a newer PostgreSQL client"
  exit 1
}

PG_RESTORE_BIN="$(resolve_pg_bin pg_restore)" || {
  echo "[$(LOG_TS)] db-backup skipped: pg_restore not found; set PG_BIN_DIR to a newer PostgreSQL client"
  exit 1
}

if ! command -v shasum >/dev/null 2>&1; then
  echo "[$(LOG_TS)] db-backup skipped: shasum not found"
  exit 1
fi

if [[ -z "${DATABASE_URL:-}" && -z "${SQLALCHEMY_DATABASE_URI:-}" ]]; then
  required_vars=(PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD)
  for var_name in "${required_vars[@]}"; do
    if [[ -z "${!var_name:-}" ]]; then
      echo "[$(LOG_TS)] db-backup skipped: missing ${var_name}"
      exit 1
    fi
  done
fi

if [[ -n "${PGHOST:-}" && "${PGHOST}" == *.neon.tech ]] && [[ -z "${PGOPTIONS:-}" ]]; then
  endpoint_id="${PGHOST%%.*}"
  endpoint_id="${endpoint_id%-pooler}"
  export PGOPTIONS="endpoint=${endpoint_id}"
fi

mkdir -p "${OUTPUT_DIR}"

timestamp="$(date -u +'%Y%m%dT%H%M%SZ')"
db_name="${PGDATABASE:-projectdivert}"
backup_file="${OUTPUT_DIR}/${LABEL}_${db_name}_${timestamp}.dump"

echo "[$(LOG_TS)] db-backup starting (output_dir=${OUTPUT_DIR}, retention_days=${RETENTION_DAYS})"
"${PG_DUMP_BIN}" \
  --no-owner \
  --no-privileges \
  --format=custom \
  --compress=9 \
  --file "${backup_file}"
"${PG_RESTORE_BIN}" --list "${backup_file}" >/dev/null

checksum="$(shasum -a 256 "${backup_file}" | awk '{print $1}')"
if stat -f%z "${backup_file}" >/dev/null 2>&1; then
  size_bytes="$(stat -f%z "${backup_file}")"
else
  size_bytes="$(stat -c%s "${backup_file}")"
fi
manifest_file="${backup_file}.json"

cat > "${manifest_file}" <<JSON
{
  "label": "${LABEL}",
  "database": "${db_name}",
  "created_at": "$(LOG_TS)",
  "backup_kind": "full",
  "file_name": "$(basename "${backup_file}")",
  "file_path": "${backup_file}",
  "size_bytes": ${size_bytes},
  "sha256": "${checksum}"
}
JSON

if [[ "${RETENTION_DAYS}" != "0" ]]; then
  find "${OUTPUT_DIR}" -type f \
    \( -name "${LABEL}_*.dump" -o -name "${LABEL}_*.dump.json" \) \
    -mtime +"${RETENTION_DAYS}" \
    -delete
fi

echo "Backup created: ${backup_file}"
echo "Manifest created: ${manifest_file}"
echo "SHA256: ${checksum}"
echo "[$(LOG_TS)] db-backup finished"
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
      <key>PROJECTDIVERT_ENV_FILE</key>
      <string>${ENV_FILE}</string>
      <key>BACKUP_OUTPUT_DIR</key>
      <string>${OUTPUT_DIR}</string>
      <key>BACKUP_RETENTION_DAYS</key>
      <string>${RETENTION_DAYS}</string>
      <key>BACKUP_LABEL</key>
      <string>${BACKUP_PREFIX}</string>
      <key>PG_BIN_DIR</key>
      <string>${PG_BIN_DIR}</string>
    </dict>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/db-backup.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/db-backup.error.log</string>
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
echo "Output dir: ${OUTPUT_DIR}"
echo "To test immediately:"
echo "  launchctl kickstart -k ${LAUNCHD_TARGET}/${LABEL}"
echo "To inspect status:"
echo "  launchctl print ${LAUNCHD_TARGET}/${LABEL}"
echo "Logs:"
echo "  tail -f ${LOG_DIR}/db-backup.log ${LOG_DIR}/db-backup.error.log"
