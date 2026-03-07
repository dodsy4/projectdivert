#!/usr/bin/env bash
set -euo pipefail

AUTH_WINDOW_MINUTES="${OPS_HEALTH_AUTH_WINDOW_MINUTES:-60}"
DISPATCH_LIMIT="${OPS_HEALTH_DISPATCH_LIMIT:-500}"

python -m flask ops-health-digest \
  --auth-window-minutes "$AUTH_WINDOW_MINUTES" \
  --dispatch-limit "$DISPATCH_LIMIT" \
  "$@"
