#!/usr/bin/env bash
set -euo pipefail

LABEL="${OPS_HEALTH_DIGEST_LABEL:-com.projectdivert.ops-health-digest}"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
RUNNER_PATH="${HOME}/Library/Application Support/projectdivert/ops-health-digest-runner.sh"
LAUNCHD_TARGET="gui/$(id -u)"

if launchctl print "${LAUNCHD_TARGET}/${LABEL}" >/dev/null 2>&1; then
  launchctl bootout "${LAUNCHD_TARGET}" "${PLIST_PATH}" >/dev/null 2>&1 || true
fi

if [[ -f "${PLIST_PATH}" ]]; then
  rm -f "${PLIST_PATH}"
  echo "Removed: ${PLIST_PATH}"
else
  echo "No plist found at: ${PLIST_PATH}"
fi

if [[ -f "${RUNNER_PATH}" ]]; then
  rm -f "${RUNNER_PATH}"
  echo "Removed: ${RUNNER_PATH}"
fi
