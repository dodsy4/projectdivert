#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BACKUP_FILE=""
MANIFEST_FILE=""
SCRATCH_DB="${RESTORE_DRILL_DB_NAME:-projectdivert_restore_drill}"
KEEP_DB=0
SKIP_APP_CHECK=0
PG_BIN_DIR="${PG_BIN_DIR:-}"
PSQL_BIN_OVERRIDE="${PSQL_BIN:-}"
PG_RESTORE_BIN_OVERRIDE="${PG_RESTORE_BIN:-}"
CREATEDB_BIN_OVERRIDE="${CREATEDB_BIN:-}"
DROPDB_BIN_OVERRIDE="${DROPDB_BIN:-}"

usage() {
  cat <<'EOF'
Usage: ./scripts/restore_drill.sh --backup-file <path> [options]

Run a restore drill against a scratch PostgreSQL database:
- verify manifest checksum
- verify archive readability
- restore into scratch DB
- verify core tables and row shape
- optionally boot the Flask app against the restored DB

Options:
  --backup-file <path>   Required path to .dump archive
  --manifest-file <path> Optional manifest path (default: <backup>.json)
  --scratch-db <name>    Scratch restore DB name (default: projectdivert_restore_drill)
  --pg-bin-dir <path>    Directory containing psql/pg_restore/createdb/dropdb
  --keep-db              Do not drop the scratch DB at the end
  --skip-app-check       Skip Flask boot/import validation against restored DB
  --help                 Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup-file)
      BACKUP_FILE="${2:-}"
      shift 2
      ;;
    --manifest-file)
      MANIFEST_FILE="${2:-}"
      shift 2
      ;;
    --scratch-db)
      SCRATCH_DB="${2:-}"
      shift 2
      ;;
    --pg-bin-dir)
      PG_BIN_DIR="${2:-}"
      shift 2
      ;;
    --keep-db)
      KEEP_DB=1
      shift
      ;;
    --skip-app-check)
      SKIP_APP_CHECK=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ -n "${BACKUP_FILE}" ]] || { echo "--backup-file is required" >&2; exit 2; }
[[ -f "${BACKUP_FILE}" ]] || { echo "Backup archive not found: ${BACKUP_FILE}" >&2; exit 1; }

if [[ -z "${MANIFEST_FILE}" ]]; then
  MANIFEST_FILE="${BACKUP_FILE}.json"
fi
[[ -f "${MANIFEST_FILE}" ]] || { echo "Manifest not found: ${MANIFEST_FILE}" >&2; exit 1; }

cd "${PROJECT_ROOT}"

PASS_COUNT=0
FAIL_COUNT=0

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  printf 'PASS: %s\n' "$1"
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

need_cmd python
need_cmd shasum

resolve_pg_bin() {
  local tool_name="$1"
  local override_path="${2:-}"
  if [[ -n "${override_path}" && -x "${override_path}" ]]; then
    printf '%s\n' "${override_path}"
    return 0
  fi
  if [[ -n "${PG_BIN_DIR}" && -x "${PG_BIN_DIR}/${tool_name}" ]]; then
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

PSQL_BIN="$(resolve_pg_bin "psql" "${PSQL_BIN_OVERRIDE:-}")" || { fail "psql not found"; }
PG_RESTORE_BIN="$(resolve_pg_bin "pg_restore" "${PG_RESTORE_BIN_OVERRIDE:-}")" || { fail "pg_restore not found"; }
CREATEDB_BIN="$(resolve_pg_bin "createdb" "${CREATEDB_BIN_OVERRIDE:-}")" || { fail "createdb not found"; }
DROPDB_BIN="$(resolve_pg_bin "dropdb" "${DROPDB_BIN_OVERRIDE:-}")" || { fail "dropdb not found"; }

if [[ ${FAIL_COUNT} -gt 0 ]]; then
  printf '\nSummary: %s pass, %s fail\n' "${PASS_COUNT}" "${FAIL_COUNT}"
  exit 1
fi

eval "$(
  python - <<'PY'
import os
import config
from sqlalchemy.engine import make_url

url = make_url(config.SQLALCHEMY_DATABASE_URI)

def emit(name, value):
    if value is None:
        value = ""
    value = str(value).replace("\\", "\\\\").replace('"', '\\"')
    print(f'export {name}="{value}"')

emit("PGHOST", url.host or "")
emit("PGPORT", url.port or 5432)
emit("PGDATABASE", url.database or "")
emit("PGUSER", url.username or "")
emit("PGPASSWORD", url.password or "")
emit("PGSSLMODE", (url.query.get("sslmode") if url.query else "") or os.getenv("PGSSLMODE", ""))
PY
)"

if [[ -z "${PGHOST:-}" || -z "${PGDATABASE:-}" || -z "${PGUSER:-}" ]]; then
  echo "Could not resolve PG* connection values from app config" >&2
  exit 1
fi

if [[ "${PGHOST}" == *.neon.tech ]] && [[ -z "${PGOPTIONS:-}" ]]; then
  endpoint_id="${PGHOST%%.*}"
  endpoint_id="${endpoint_id%-pooler}"
  export PGOPTIONS="endpoint=${endpoint_id}"
fi

run_psql() {
  local db_name="$1"
  shift
  PGPASSWORD="${PGPASSWORD}" \
  "${PSQL_BIN}" \
    -v ON_ERROR_STOP=1 \
    -h "${PGHOST}" \
    -p "${PGPORT:-5432}" \
    -U "${PGUSER}" \
    -d "${db_name}" \
    "$@"
}

run_createdb() {
  PGPASSWORD="${PGPASSWORD}" \
  "${CREATEDB_BIN}" \
    -h "${PGHOST}" \
    -p "${PGPORT:-5432}" \
    -U "${PGUSER}" \
    "${SCRATCH_DB}"
}

run_dropdb() {
  PGPASSWORD="${PGPASSWORD}" \
  "${DROPDB_BIN}" \
    --if-exists \
    -h "${PGHOST}" \
    -p "${PGPORT:-5432}" \
    -U "${PGUSER}" \
    "${SCRATCH_DB}"
}

cleanup() {
  if [[ ${KEEP_DB} -eq 0 ]]; then
    run_dropdb >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

MANIFEST_CHECK_OUTPUT="$(
  python - "${BACKUP_FILE}" "${MANIFEST_FILE}" <<'PY'
import hashlib
import json
import os
import sys

backup_file, manifest_file = sys.argv[1], sys.argv[2]
with open(manifest_file, "r", encoding="utf-8") as handle:
    manifest = json.load(handle)

digest = hashlib.sha256()
with open(backup_file, "rb") as handle:
    while True:
        chunk = handle.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)

actual_sha = digest.hexdigest()
manifest_sha = manifest.get("sha256", "")
manifest_name = manifest.get("file_name", "")
expected_name = os.path.basename(backup_file)
errors = []
if manifest_sha != actual_sha:
    errors.append(f"sha256 mismatch (manifest={manifest_sha}, actual={actual_sha})")
if manifest_name and manifest_name != expected_name:
    errors.append(f"file_name mismatch (manifest={manifest_name}, actual={expected_name})")

if errors:
    print("ERROR")
    for error in errors:
        print(error)
    sys.exit(1)

print("OK")
print(actual_sha)
PY
)" || {
  fail "manifest verification failed"
  printf '%s\n' "${MANIFEST_CHECK_OUTPUT}"
  printf '\nSummary: %s pass, %s fail\n' "${PASS_COUNT}" "${FAIL_COUNT}"
  exit 1
}
pass "manifest checksum matches archive"

if "${PG_RESTORE_BIN}" --list "${BACKUP_FILE}" >/dev/null; then
  pass "pg_restore --list succeeded"
else
  fail "pg_restore --list failed"
  printf '\nSummary: %s pass, %s fail\n' "${PASS_COUNT}" "${FAIL_COUNT}"
  exit 1
fi

run_dropdb >/dev/null 2>&1 || true
run_createdb
pass "scratch database created (${SCRATCH_DB})"

PGPASSWORD="${PGPASSWORD}" \
"${PG_RESTORE_BIN}" \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  -h "${PGHOST}" \
  -p "${PGPORT:-5432}" \
  -U "${PGUSER}" \
  -d "${SCRATCH_DB}" \
  "${BACKUP_FILE}" >/dev/null
pass "archive restored into scratch database"

EXPECTED_HEADS="$(
  python - <<'PY'
from alembic.config import Config
from alembic.script import ScriptDirectory

config = Config()
config.set_main_option("script_location", "migrations")
script = ScriptDirectory.from_config(config)
print(",".join(script.get_heads()))
PY
)"
RESTORED_REV="$(run_psql "${SCRATCH_DB}" -Atqc "SELECT version_num FROM alembic_version LIMIT 1;")"
if [[ -n "${RESTORED_REV}" && ",${EXPECTED_HEADS}," == *",${RESTORED_REV},"* ]]; then
  pass "restored database revision matches repo head (${RESTORED_REV})"
else
  fail "restored database revision mismatch (restored=${RESTORED_REV:-none}, repo_heads=${EXPECTED_HEADS:-none})"
fi

required_tables=(
  users
  auth_security_blocklist
  auth_lifecycle_tokens
  auth_audit_events
  waste_removal_requests
  waste_removal_dispatch_offers
  waste_compliance_documents
  driver_compliance_documents
  carrier_companies
  company_compliance_documents
)

for table_name in "${required_tables[@]}"; do
  if [[ "$(run_psql "${SCRATCH_DB}" -Atqc "SELECT to_regclass('public.${table_name}');")" == "${table_name}" ]]; then
    pass "required table exists: ${table_name}"
  else
    fail "required table missing: ${table_name}"
  fi
done

admin_count="$(run_psql "${SCRATCH_DB}" -Atqc "SELECT COUNT(*) FROM users WHERE role = 'admin';")"
if [[ "${admin_count}" =~ ^[0-9]+$ && "${admin_count}" -ge 1 ]]; then
  pass "admin user rows present (${admin_count})"
else
  fail "no admin user rows found"
fi

request_count="$(run_psql "${SCRATCH_DB}" -Atqc "SELECT COUNT(*) FROM waste_removal_requests;")"
audit_count="$(run_psql "${SCRATCH_DB}" -Atqc "SELECT COUNT(*) FROM auth_audit_events;")"
pass "waste_removal_requests row count: ${request_count}"
pass "auth_audit_events row count: ${audit_count}"

if [[ ${SKIP_APP_CHECK} -eq 0 ]]; then
  APP_CHECK_OUTPUT="$(
    SCRATCH_DB="${SCRATCH_DB}" python - <<'PY'
import os
from sqlalchemy.engine import make_url
import config

url = make_url(config.SQLALCHEMY_DATABASE_URI)
restored_url = url.set(database=os.environ["SCRATCH_DB"])
os.environ["SQLALCHEMY_DATABASE_URI"] = str(restored_url)
os.environ["DATABASE_URL"] = str(restored_url)

from app import app

client = app.test_client()
response = client.get("/")
if response.status_code >= 500:
    raise SystemExit(f"app boot check failed with HTTP {response.status_code}")

print(f"home_status={response.status_code}")
PY
  )" || {
    fail "Flask app boot check failed against restored DB"
    printf '%s\n' "${APP_CHECK_OUTPUT}"
    printf '\nSummary: %s pass, %s fail\n' "${PASS_COUNT}" "${FAIL_COUNT}"
    exit 1
  }
  pass "Flask app booted against restored DB"
else
  pass "app boot check skipped by flag"
fi

printf '\nRestore drill complete for %s\n' "${SCRATCH_DB}"
printf 'Summary: %s pass, %s fail\n' "${PASS_COUNT}" "${FAIL_COUNT}"

if [[ ${FAIL_COUNT} -gt 0 ]]; then
  exit 1
fi

if [[ ${KEEP_DB} -eq 1 ]]; then
  printf 'Scratch database preserved: %s\n' "${SCRATCH_DB}"
else
  printf 'Scratch database will be dropped on exit: %s\n' "${SCRATCH_DB}"
fi
