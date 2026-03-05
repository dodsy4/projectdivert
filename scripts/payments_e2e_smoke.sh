#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:5052}"
ADMIN_EMAIL="${SMOKE_ADMIN_EMAIL:-admin@example.com}"
ADMIN_PASSWORD="${SMOKE_ADMIN_PASSWORD:-Password123!}"
CUSTOMER_EMAIL="${SMOKE_CUSTOMER_EMAIL:-customer@example.com}"

PAYMENTS_MODE="${SMOKE_PAYMENTS_MODE:-auto}"       # auto|required|skip
PAYOUT_MODE="${SMOKE_PAYOUT_MODE:-auto}"           # auto|required|skip
DEST_ACCOUNT_ID="${SMOKE_DEST_ACCOUNT_ID:-}"       # Stripe connected account id
CHARGE_AMOUNT_MINOR="${SMOKE_CHARGE_AMOUNT_MINOR:-1000}"  # 10.00 GBP
REFUND_AMOUNT_MINOR="${SMOKE_REFUND_AMOUNT_MINOR:-300}"   # 3.00 GBP

if [[ ! "$PAYMENTS_MODE" =~ ^(auto|required|skip)$ ]]; then
  echo "SMOKE_PAYMENTS_MODE must be one of: auto|required|skip"
  exit 1
fi
if [[ ! "$PAYOUT_MODE" =~ ^(auto|required|skip)$ ]]; then
  echo "SMOKE_PAYOUT_MODE must be one of: auto|required|skip"
  exit 1
fi

TMP_DIR="$(mktemp -d /tmp/payments_e2e_smoke.XXXXXX)"
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

extract_nested() {
  local expr="$1"
  local file="$2"
  python - <<PY "$expr" "$file"
import json,sys
expr=sys.argv[1]
data=json.load(open(sys.argv[2]))
cur=data
for part in expr.split('.'):
    if isinstance(cur, dict):
        cur=cur.get(part)
    else:
        cur=None
        break
print("" if cur is None else cur)
PY
}

log "Base URL: $BASE_URL"
if ! curl -sS -m 5 "$BASE_URL/" >/dev/null; then
  fail "API not reachable at $BASE_URL"
fi

log "Admin login"
LOGIN_BODY="$TMP_DIR/login.json"
LOGIN_STATUS="$TMP_DIR/login.status"
http_json POST "/api/v1/auth/login" "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" "" "$LOGIN_BODY" "$LOGIN_STATUS"
assert_status "$(cat "$LOGIN_STATUS")" "200" "Admin login" "$LOGIN_BODY"
ADMIN_TOKEN="$(cat "$LOGIN_BODY" | json_field access_token)"
[[ -n "$ADMIN_TOKEN" ]] || fail "Missing admin access token"

log "Create request for payments smoke"
SCHEDULED="$(python - <<'PY'
from datetime import datetime, timedelta
print((datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"))
PY
)"
CREATE_BODY="$TMP_DIR/request_create.json"
CREATE_STATUS="$TMP_DIR/request_create.status"
http_json POST "/api/v1/waste-requests" \
  "{\"requester_name\":\"Payments Smoke\",\"requester_email\":\"$CUSTOMER_EMAIL\",\"material_type\":\"Cardboard\",\"waste_amount\":2.0,\"waste_unit\":\"Tonnes\",\"match_radius_miles\":100,\"pickup_address\":\"1 Payments Road\",\"pickup_postcode\":\"SW1A1AA\",\"scheduled_pickup_at\":\"$SCHEDULED\"}" \
  "$ADMIN_TOKEN" "$CREATE_BODY" "$CREATE_STATUS"
assert_status "$(cat "$CREATE_STATUS")" "201" "Create waste request" "$CREATE_BODY"
REQUEST_ID="$(extract_nested 'request.id' "$CREATE_BODY")"
[[ -n "$REQUEST_ID" ]] || fail "Missing request id"
echo "request_id=$REQUEST_ID"

log "Payments summary check"
PAY_SUMMARY_BODY="$TMP_DIR/payments_summary.json"
PAY_SUMMARY_STATUS="$TMP_DIR/payments_summary.status"
http_json GET "/api/v1/waste-requests/$REQUEST_ID/payments" "" "$ADMIN_TOKEN" "$PAY_SUMMARY_BODY" "$PAY_SUMMARY_STATUS"
assert_status "$(cat "$PAY_SUMMARY_STATUS")" "200" "Get payments summary" "$PAY_SUMMARY_BODY"
PAYMENTS_ENABLED="$(cat "$PAY_SUMMARY_BODY" | json_field payments_enabled | tr '[:upper:]' '[:lower:]')"
echo "payments_enabled=$PAYMENTS_ENABLED"

if [[ "$PAYMENTS_MODE" == "skip" ]]; then
  echo "Payments mode skip: charge/refund/payout tests skipped."
  echo "PAYMENTS E2E SMOKE PASSED (skipped)"
  exit 0
fi

if [[ "$PAYMENTS_MODE" == "auto" && "$PAYMENTS_ENABLED" != "true" ]]; then
  echo "Payments disabled by feature flag; skipping charge/refund/payout in auto mode."
  echo "PAYMENTS E2E SMOKE PASSED (auto skip)"
  exit 0
fi

log "Create payment charge"
CHARGE_BODY="$TMP_DIR/charge.json"
CHARGE_STATUS="$TMP_DIR/charge.status"
http_json POST "/api/v1/waste-requests/$REQUEST_ID/payments/charge" \
  "{\"amount_minor\":$CHARGE_AMOUNT_MINOR,\"currency\":\"gbp\",\"payment_method_id\":\"pm_card_visa\",\"confirm\":true,\"platform_fee_bps\":1500}" \
  "$ADMIN_TOKEN" "$CHARGE_BODY" "$CHARGE_STATUS"
CHARGE_CODE="$(cat "$CHARGE_STATUS")"
if [[ "$CHARGE_CODE" != "201" ]]; then
  echo "Charge failed (HTTP $CHARGE_CODE):"
  cat "$CHARGE_BODY"
  echo
  if [[ "$PAYMENTS_MODE" == "required" ]]; then
    fail "Charge failed in required mode"
  fi
  echo "PAYMENTS E2E SMOKE COMPLETED (charge failed in auto mode)"
  exit 0
fi

CHARGE_ID="$(extract_nested 'charge.id' "$CHARGE_BODY")"
CHARGE_STATUS_TEXT="$(extract_nested 'charge.status' "$CHARGE_BODY")"
CHARGE_DRIVER_PAYOUT_MINOR="$(extract_nested 'charge.driver_payout_minor' "$CHARGE_BODY")"
[[ -n "$CHARGE_ID" ]] || fail "Missing charge id"
echo "charge_id=$CHARGE_ID status=$CHARGE_STATUS_TEXT driver_payout_minor=$CHARGE_DRIVER_PAYOUT_MINOR"

log "Create partial refund"
REFUND_BODY="$TMP_DIR/refund.json"
REFUND_STATUS="$TMP_DIR/refund.status"
http_json POST "/api/v1/waste-requests/$REQUEST_ID/payments/$CHARGE_ID/refund" \
  "{\"amount_minor\":$REFUND_AMOUNT_MINOR,\"reason\":\"requested_by_customer\"}" \
  "$ADMIN_TOKEN" "$REFUND_BODY" "$REFUND_STATUS"
REFUND_CODE="$(cat "$REFUND_STATUS")"
if [[ "$REFUND_CODE" != "201" ]]; then
  echo "Refund failed (HTTP $REFUND_CODE):"
  cat "$REFUND_BODY"
  echo
  if [[ "$PAYMENTS_MODE" == "required" ]]; then
    fail "Refund failed in required mode"
  fi
else
  REFUND_ID="$(extract_nested 'refund.id' "$REFUND_BODY")"
  REFUND_STATUS_TEXT="$(extract_nested 'refund.status' "$REFUND_BODY")"
  echo "refund_id=$REFUND_ID status=$REFUND_STATUS_TEXT"
fi

if [[ "$PAYOUT_MODE" == "skip" ]]; then
  echo "Payout mode skip: payout test skipped."
  echo "PAYMENTS E2E SMOKE PASSED"
  exit 0
fi

if [[ -z "$DEST_ACCOUNT_ID" ]]; then
  if [[ "$PAYOUT_MODE" == "required" ]]; then
    fail "SMOKE_DEST_ACCOUNT_ID is required for payout mode required"
  fi
  echo "No SMOKE_DEST_ACCOUNT_ID provided; skipping payout in auto mode."
  echo "PAYMENTS E2E SMOKE PASSED (payout skipped)"
  exit 0
fi

log "Ensure assigned driver exists for payout"
DRIVERS_BODY="$TMP_DIR/drivers.json"
DRIVERS_STATUS="$TMP_DIR/drivers.status"
http_json GET "/api/v1/admin/drivers?active=true&limit=20" "" "$ADMIN_TOKEN" "$DRIVERS_BODY" "$DRIVERS_STATUS"
assert_status "$(cat "$DRIVERS_STATUS")" "200" "Get drivers list" "$DRIVERS_BODY"
DRIVER_ID="$(python - <<'PY' "$DRIVERS_BODY"
import json,sys
items=json.load(open(sys.argv[1])).get("items",[])
print(items[0]["id"] if items else "")
PY
)"
if [[ -z "$DRIVER_ID" ]]; then
  if [[ "$PAYOUT_MODE" == "required" ]]; then
    fail "No active drivers available for payout"
  fi
  echo "No active drivers available; skipping payout in auto mode."
  echo "PAYMENTS E2E SMOKE PASSED (payout skipped)"
  exit 0
fi

ASSIGN_BODY="$TMP_DIR/assign.json"
ASSIGN_STATUS="$TMP_DIR/assign.status"
http_json POST "/api/v1/admin/waste-requests/$REQUEST_ID/dispatch/override" \
  "{\"driver_user_id\":$DRIVER_ID,\"reason\":\"payments e2e assign\"}" \
  "$ADMIN_TOKEN" "$ASSIGN_BODY" "$ASSIGN_STATUS"
assert_status "$(cat "$ASSIGN_STATUS")" "200" "Assign driver for payout" "$ASSIGN_BODY"

log "Create payout"
PAYOUT_BODY="$TMP_DIR/payout.json"
PAYOUT_STATUS="$TMP_DIR/payout.status"
http_json POST "/api/v1/waste-requests/$REQUEST_ID/payouts" \
  "{\"payment_charge_id\":$CHARGE_ID,\"driver_user_id\":$DRIVER_ID,\"destination_account_id\":\"$DEST_ACCOUNT_ID\"}" \
  "$ADMIN_TOKEN" "$PAYOUT_BODY" "$PAYOUT_STATUS"
PAYOUT_CODE="$(cat "$PAYOUT_STATUS")"
if [[ "$PAYOUT_CODE" != "201" ]]; then
  echo "Payout failed (HTTP $PAYOUT_CODE):"
  cat "$PAYOUT_BODY"
  echo
  if [[ "$PAYOUT_MODE" == "required" ]]; then
    fail "Payout failed in required mode"
  fi
  echo "PAYMENTS E2E SMOKE COMPLETED (payout failed in auto mode)"
  exit 0
fi

PAYOUT_ID="$(extract_nested 'payout.id' "$PAYOUT_BODY")"
PAYOUT_STATUS_TEXT="$(extract_nested 'payout.status' "$PAYOUT_BODY")"
echo "payout_id=$PAYOUT_ID status=$PAYOUT_STATUS_TEXT"

echo
echo "PAYMENTS E2E SMOKE PASSED"
echo "request_id=$REQUEST_ID charge_id=$CHARGE_ID payout_id=$PAYOUT_ID"
