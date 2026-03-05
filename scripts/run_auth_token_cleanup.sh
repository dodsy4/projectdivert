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
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] auth-token-cleanup skipped: database env not configured"
  exit 1
fi

RETENTION_DAYS="${AUTH_TOKEN_CLEANUP_RETENTION_DAYS:-30}"
BATCH_SIZE="${AUTH_TOKEN_CLEANUP_BATCH_SIZE:-500}"

echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] auth-token-cleanup starting (retention_days=${RETENTION_DAYS}, batch_size=${BATCH_SIZE})"
python -m flask auth-token-cleanup --retention-days "${RETENTION_DAYS}" --batch-size "${BATCH_SIZE}"
echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] auth-token-cleanup finished"
