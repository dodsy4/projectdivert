#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${BACKUP_OUTPUT_DIR:-$HOME/Backups/projectdivert}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
LABEL="${BACKUP_LABEL:-projectdivert-db}"
PG_BIN_DIR="${PG_BIN_DIR:-}"
PG_DUMP_BIN_OVERRIDE="${PG_DUMP_BIN:-}"
PG_RESTORE_BIN_OVERRIDE="${PG_RESTORE_BIN:-}"
SCHEMA_ONLY=0
SKIP_PRUNE=0

usage() {
  cat <<'EOF'
Create a PostgreSQL backup archive for Project Divert.

Usage:
  ./scripts/db_backup.sh [options]

Options:
  --output-dir <path>          Backup output directory (default: ~/Backups/projectdivert)
  --retention-days <days>      Delete matching backup files older than this many days (default: 14)
  --label <name>               Backup file prefix label (default: projectdivert-db)
  --pg-bin-dir <path>          Directory containing pg_dump/pg_restore
  --schema-only                Create a schema-only SQL backup instead of a full custom archive
  --skip-prune                 Do not delete old backup files
  -h, --help                   Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    --retention-days)
      RETENTION_DAYS="${2:-}"
      shift 2
      ;;
    --label)
      LABEL="${2:-}"
      shift 2
      ;;
    --pg-bin-dir)
      PG_BIN_DIR="${2:-}"
      shift 2
      ;;
    --schema-only)
      SCHEMA_ONLY=1
      shift
      ;;
    --skip-prune)
      SKIP_PRUNE=1
      shift
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

if ! [[ "${RETENTION_DAYS}" =~ ^[0-9]+$ ]]; then
  echo "--retention-days must be a non-negative integer" >&2
  exit 1
fi

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

PG_DUMP_BIN="$(resolve_pg_bin "pg_dump" "${PG_DUMP_BIN_OVERRIDE:-}")" || {
  echo "pg_dump not found. Install a PostgreSQL client matching your server version, or set PG_BIN_DIR/PG_DUMP_BIN." >&2
  exit 1
}

PG_RESTORE_BIN="$(resolve_pg_bin "pg_restore" "${PG_RESTORE_BIN_OVERRIDE:-}")" || {
  echo "pg_restore not found. Install a PostgreSQL client matching your server version, or set PG_BIN_DIR/PG_RESTORE_BIN." >&2
  exit 1
}

if ! command -v shasum >/dev/null 2>&1; then
  echo "shasum not found in PATH" >&2
  exit 1
fi

if [[ -z "${DATABASE_URL:-}" && -z "${SQLALCHEMY_DATABASE_URI:-}" ]]; then
  required_vars=(PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD)
  for var_name in "${required_vars[@]}"; do
    if [[ -z "${!var_name:-}" ]]; then
      echo "Missing database env: ${var_name}" >&2
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
if [[ "${SCHEMA_ONLY}" == "1" ]]; then
  backup_file="${OUTPUT_DIR}/${LABEL}_${db_name}_${timestamp}_schema.sql"
  backup_kind="schema-only"
  "${PG_DUMP_BIN}" \
    --no-owner \
    --no-privileges \
    --schema-only \
    --file "${backup_file}"
else
  backup_file="${OUTPUT_DIR}/${LABEL}_${db_name}_${timestamp}.dump"
  backup_kind="full"
  "${PG_DUMP_BIN}" \
    --no-owner \
    --no-privileges \
    --format=custom \
    --compress=9 \
    --file "${backup_file}"
fi

if [[ "${SCHEMA_ONLY}" == "0" ]]; then
  if [[ -z "${PG_RESTORE_BIN}" ]]; then
    echo "pg_restore not found; cannot verify custom archive" >&2
    exit 1
  fi
  "${PG_RESTORE_BIN}" --list "${backup_file}" >/dev/null
fi

checksum="$(shasum -a 256 "${backup_file}" | awk '{print $1}')"
if stat -f%z "${backup_file}" >/dev/null 2>&1; then
  size_bytes="$(stat -f%z "${backup_file}")"
else
  size_bytes="$(stat -c%s "${backup_file}")"
fi
manifest_file="${backup_file}.json"

cat > "${manifest_file}" <<EOF
{
  "label": "${LABEL}",
  "database": "${db_name}",
  "created_at": "$(date -u +'%Y-%m-%dT%H:%M:%SZ')",
  "backup_kind": "${backup_kind}",
  "file_name": "$(basename "${backup_file}")",
  "file_path": "${backup_file}",
  "size_bytes": ${size_bytes},
  "sha256": "${checksum}"
}
EOF

if [[ "${SKIP_PRUNE}" != "1" && "${RETENTION_DAYS}" != "0" ]]; then
  find "${OUTPUT_DIR}" -type f \
    \( -name "${LABEL}_*.dump" -o -name "${LABEL}_*.sql" -o -name "${LABEL}_*.dump.json" -o -name "${LABEL}_*.sql.json" \) \
    -mtime +"${RETENTION_DAYS}" \
    -delete
fi

echo "Backup created: ${backup_file}"
echo "Manifest created: ${manifest_file}"
echo "SHA256: ${checksum}"
