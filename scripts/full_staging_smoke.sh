#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:5052}"
ADMIN_EMAIL="${SMOKE_ADMIN_EMAIL:-admin@example.com}"
ADMIN_PASSWORD="${SMOKE_ADMIN_PASSWORD:-Password123!}"
CUSTOMER_EMAIL="${SMOKE_CUSTOMER_EMAIL:-customer@example.com}"
CUSTOMER_PASSWORD="${SMOKE_CUSTOMER_PASSWORD:-Password123!}"
PAYMENTS_MODE="${SMOKE_PAYMENTS_MODE:-auto}"  # auto|required|skip

if [[ ! "$PAYMENTS_MODE" =~ ^(auto|required|skip)$ ]]; then
  echo "SMOKE_PAYMENTS_MODE must be one of: auto|required|skip"
  exit 1
fi

TMP_DIR="$(mktemp -d /tmp/full_staging_smoke.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

log() { printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
fail() { echo "FAILED: $*" >&2; exit 1; }

json_field() {
  local field="$1"
  python -c "import json,sys; d=json.load(sys.stdin); print(d.get('$field',''))"
}

http_json() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local auth="${4:-}"
  local out_file="$5"
  local status_file="$6"

  if [[ -n "$body" ]]; then
    if [[ -n "$auth" ]]; then
      curl -sS -o "$out_file" -w "%{http_code}" -X "$method" "$BASE_URL$path" \
        -H "Authorization: Bearer $auth" \
        -H "Content-Type: application/json" \
        -d "$body" > "$status_file"
    else
      curl -sS -o "$out_file" -w "%{http_code}" -X "$method" "$BASE_URL$path" \
        -H "Content-Type: application/json" \
        -d "$body" > "$status_file"
    fi
  else
    if [[ -n "$auth" ]]; then
      curl -sS -o "$out_file" -w "%{http_code}" -X "$method" "$BASE_URL$path" \
        -H "Authorization: Bearer $auth" > "$status_file"
    else
      curl -sS -o "$out_file" -w "%{http_code}" -X "$method" "$BASE_URL$path" > "$status_file"
    fi
  fi
}

assert_status() {
  local got="$1"
  local expected="$2"
  local label="$3"
  local body_file="$4"
  if [[ "$got" != "$expected" ]]; then
    echo "$label expected HTTP $expected, got $got"
    cat "$body_file"
    echo
    exit 1
  fi
}

log "Base URL: $BASE_URL"
log "Checking API reachability"
if ! curl -sS -m 5 "$BASE_URL/" >/dev/null; then
  fail "API not reachable at $BASE_URL"
fi

login_and_capture() {
  local email="$1"
  local password="$2"
  local prefix="$3"
  local body_file="$TMP_DIR/${prefix}_login.json"
  local status_file="$TMP_DIR/${prefix}_login.status"
  http_json POST "/api/v1/auth/login" "{\"email\":\"$email\",\"password\":\"$password\"}" "" "$body_file" "$status_file"
  local status
  status="$(cat "$status_file")"
  assert_status "$status" "200" "Login ($email)" "$body_file"

  local access
  local refresh
  access="$(cat "$body_file" | json_field access_token)"
  refresh="$(cat "$body_file" | json_field refresh_token)"
  [[ -n "$access" ]] || fail "Missing access_token for $email"
  [[ -n "$refresh" ]] || fail "Missing refresh_token for $email"
  echo "$access|$refresh"
}

log "Auth smoke (login/refresh/logout)"
ADMIN_LOGIN="$(login_and_capture "$ADMIN_EMAIL" "$ADMIN_PASSWORD" admin)"
ADMIN_TOKEN="${ADMIN_LOGIN%%|*}"
ADMIN_REFRESH="${ADMIN_LOGIN##*|}"

REFRESH_BODY="$TMP_DIR/admin_refresh.json"
REFRESH_STATUS="$TMP_DIR/admin_refresh.status"
http_json POST "/api/v1/auth/refresh" "{\"refresh_token\":\"$ADMIN_REFRESH\"}" "" "$REFRESH_BODY" "$REFRESH_STATUS"
assert_status "$(cat "$REFRESH_STATUS")" "200" "Refresh (admin)" "$REFRESH_BODY"
ADMIN_TOKEN="$(cat "$REFRESH_BODY" | json_field access_token)"
ADMIN_REFRESH="$(cat "$REFRESH_BODY" | json_field refresh_token)"
[[ -n "$ADMIN_TOKEN" ]] || fail "Missing refreshed admin access token"
[[ -n "$ADMIN_REFRESH" ]] || fail "Missing refreshed admin refresh token"

LOGOUT_BODY="$TMP_DIR/admin_logout.json"
LOGOUT_STATUS="$TMP_DIR/admin_logout.status"
http_json POST "/api/v1/auth/logout" "{\"refresh_token\":\"$ADMIN_REFRESH\"}" "$ADMIN_TOKEN" "$LOGOUT_BODY" "$LOGOUT_STATUS"
assert_status "$(cat "$LOGOUT_STATUS")" "200" "Logout (admin)" "$LOGOUT_BODY"

# Re-login admin for remaining checks.
ADMIN_LOGIN="$(login_and_capture "$ADMIN_EMAIL" "$ADMIN_PASSWORD" admin2)"
ADMIN_TOKEN="${ADMIN_LOGIN%%|*}"

log "Dispatch smoke (create request + queue visibility)"
SCHEDULED="$(python - <<'PY'
from datetime import datetime, timedelta
print((datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"))
PY
)"

CREATE_BODY="$TMP_DIR/request_create.json"
CREATE_STATUS="$TMP_DIR/request_create.status"
http_json POST "/api/v1/waste-requests" \
  "{\"requester_name\":\"Smoke Customer\",\"requester_email\":\"$CUSTOMER_EMAIL\",\"material_type\":\"Mixed Plastic\",\"waste_amount\":1.5,\"waste_unit\":\"Tonnes\",\"match_radius_miles\":150,\"pickup_address\":\"1 Smoke Test Road\",\"pickup_postcode\":\"SW1A1AA\",\"scheduled_pickup_at\":\"$SCHEDULED\"}" \
  "$ADMIN_TOKEN" \
  "$CREATE_BODY" "$CREATE_STATUS"
assert_status "$(cat "$CREATE_STATUS")" "201" "Create waste request" "$CREATE_BODY"
REQUEST_ID="$(python -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["request"]["id"])' "$CREATE_BODY")"
[[ -n "$REQUEST_ID" ]] || fail "Failed to parse request id"
echo "Created request_id=$REQUEST_ID"

QUEUE_BODY="$TMP_DIR/dispatch_queue.json"
QUEUE_STATUS="$TMP_DIR/dispatch_queue.status"
http_json GET "/api/v1/admin/dispatch/queue?limit=50" "" "$ADMIN_TOKEN" "$QUEUE_BODY" "$QUEUE_STATUS"
assert_status "$(cat "$QUEUE_STATUS")" "200" "Admin dispatch queue" "$QUEUE_BODY"
python - <<PY "$QUEUE_BODY" "$REQUEST_ID"
import json,sys
payload=json.load(open(sys.argv[1]))
rid=int(sys.argv[2])
ids=[item.get("request",{}).get("id") for item in payload.get("items",[])]
if rid not in ids:
    print("Request id not found in dispatch queue items")
    sys.exit(1)
print("Queue includes created request")
PY

log "Admin ops smoke (drivers + override assign/unassign)"
DRIVERS_BODY="$TMP_DIR/drivers.json"
DRIVERS_STATUS="$TMP_DIR/drivers.status"
http_json GET "/api/v1/admin/drivers?active=true&limit=20" "" "$ADMIN_TOKEN" "$DRIVERS_BODY" "$DRIVERS_STATUS"
assert_status "$(cat "$DRIVERS_STATUS")" "200" "Admin drivers list" "$DRIVERS_BODY"
DRIVER_ID="$(python - <<'PY' "$DRIVERS_BODY"
import json,sys
items=json.load(open(sys.argv[1])).get("items",[])
print(items[0]["id"] if items else "")
PY
)"
if [[ -n "$DRIVER_ID" ]]; then
  ASSIGN_BODY="$TMP_DIR/assign.json"
  ASSIGN_STATUS="$TMP_DIR/assign.status"
  http_json POST "/api/v1/admin/waste-requests/$REQUEST_ID/dispatch/override" \
    "{\"driver_user_id\":$DRIVER_ID,\"reason\":\"full staging smoke assign\"}" \
    "$ADMIN_TOKEN" "$ASSIGN_BODY" "$ASSIGN_STATUS"
  assert_status "$(cat "$ASSIGN_STATUS")" "200" "Dispatch override assign" "$ASSIGN_BODY"

  UNASSIGN_BODY="$TMP_DIR/unassign.json"
  UNASSIGN_STATUS="$TMP_DIR/unassign.status"
  http_json POST "/api/v1/admin/waste-requests/$REQUEST_ID/dispatch/override" \
    "{\"driver_user_id\":null,\"reason\":\"full staging smoke unassign\"}" \
    "$ADMIN_TOKEN" "$UNASSIGN_BODY" "$UNASSIGN_STATUS"
  assert_status "$(cat "$UNASSIGN_STATUS")" "200" "Dispatch override unassign" "$UNASSIGN_BODY"
else
  echo "WARN: No active drivers found; skipping assign/unassign override checks."
fi

log "Telemetry smoke"
TELEM_BODY="$TMP_DIR/telemetry.json"
TELEM_STATUS="$TMP_DIR/telemetry.status"
http_json GET "/api/v1/admin/dispatch/telemetry?limit=20" "" "$ADMIN_TOKEN" "$TELEM_BODY" "$TELEM_STATUS"
assert_status "$(cat "$TELEM_STATUS")" "200" "Dispatch telemetry" "$TELEM_BODY"

log "Incident workflow smoke (list + ack + resolve)"
INCIDENTS_BODY="$TMP_DIR/incidents.json"
INCIDENTS_STATUS="$TMP_DIR/incidents.status"
http_json GET "/api/v1/admin/dispatch/incidents?active_only=true&limit=50" "" "$ADMIN_TOKEN" "$INCIDENTS_BODY" "$INCIDENTS_STATUS"
assert_status "$(cat "$INCIDENTS_STATUS")" "200" "Dispatch incidents list" "$INCIDENTS_BODY"
INCIDENT_PRESENT="$(python - <<PY "$INCIDENTS_BODY" "$REQUEST_ID"
import json,sys
payload=json.load(open(sys.argv[1]))
rid=int(sys.argv[2])
ids=[item.get("request",{}).get("id") for item in payload.get("items",[])]
print("yes" if rid in ids else "no")
PY
)"

if [[ "$INCIDENT_PRESENT" == "yes" ]]; then
  echo "Incidents list includes created request"

  ACK_BODY="$TMP_DIR/inc_ack.json"
  ACK_STATUS="$TMP_DIR/inc_ack.status"
  http_json POST "/api/v1/admin/dispatch/incidents/$REQUEST_ID/ack" \
    "{\"notes\":\"full staging smoke ack\"}" \
    "$ADMIN_TOKEN" "$ACK_BODY" "$ACK_STATUS"
  assert_status "$(cat "$ACK_STATUS")" "200" "Incident acknowledge" "$ACK_BODY"

  RESOLVE_BODY="$TMP_DIR/inc_resolve.json"
  RESOLVE_STATUS="$TMP_DIR/inc_resolve.status"
  http_json POST "/api/v1/admin/dispatch/incidents/$REQUEST_ID/resolve" \
    "{\"notes\":\"full staging smoke resolve\"}" \
    "$ADMIN_TOKEN" "$RESOLVE_BODY" "$RESOLVE_STATUS"
  assert_status "$(cat "$RESOLVE_STATUS")" "200" "Incident resolve" "$RESOLVE_BODY"
else
  echo "WARN: Request is not currently in active incidents list; skipping ack/resolve smoke."
fi

log "Payments readiness smoke"
PAY_BODY="$TMP_DIR/payments_get.json"
PAY_STATUS="$TMP_DIR/payments_get.status"
http_json GET "/api/v1/waste-requests/$REQUEST_ID/payments" "" "$ADMIN_TOKEN" "$PAY_BODY" "$PAY_STATUS"
assert_status "$(cat "$PAY_STATUS")" "200" "Payments summary endpoint" "$PAY_BODY"
PAYMENTS_ENABLED="$(cat "$PAY_BODY" | json_field payments_enabled | tr '[:upper:]' '[:lower:]')"
echo "payments_enabled=$PAYMENTS_ENABLED"

if [[ "$PAYMENTS_MODE" == "skip" ]]; then
  echo "Payments charge smoke skipped (SMOKE_PAYMENTS_MODE=skip)."
elif [[ "$PAYMENTS_MODE" == "required" || "$PAYMENTS_ENABLED" == "true" ]]; then
  CHARGE_BODY="$TMP_DIR/charge.json"
  CHARGE_STATUS="$TMP_DIR/charge.status"
  http_json POST "/api/v1/waste-requests/$REQUEST_ID/payments/charge" \
    "{\"amount_minor\":500,\"currency\":\"gbp\",\"payment_method_id\":\"pm_card_visa\",\"confirm\":true,\"platform_fee_bps\":1500}" \
    "$ADMIN_TOKEN" "$CHARGE_BODY" "$CHARGE_STATUS"
  CHARGE_CODE="$(cat "$CHARGE_STATUS")"
  if [[ "$CHARGE_CODE" == "201" ]]; then
    echo "Payments charge smoke passed."
  else
    echo "Payments charge smoke failed (HTTP $CHARGE_CODE):"
    cat "$CHARGE_BODY"
    echo
    if [[ "$PAYMENTS_MODE" == "required" ]]; then
      exit 1
    fi
  fi
else
  echo "Payments not enabled; charge smoke skipped (SMOKE_PAYMENTS_MODE=auto)."
fi

echo
echo "FULL STAGING SMOKE PASSED"
echo "request_id=$REQUEST_ID"
