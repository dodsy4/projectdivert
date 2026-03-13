#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:5052}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-Password123!}"
CUSTOMER_EMAIL="${CUSTOMER_EMAIL:-billing-smoke.$(date +%s)@example.com}"
CUSTOMER_NAME="${CUSTOMER_NAME:-Billing Smoke Customer}"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/projectdivert-billing-smoke.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

log() {
  printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$1"
}

fail() {
  printf 'FAILED: %s\n' "$1" >&2
  exit 1
}

assert_status() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  local body_file="${4:-}"
  if [[ "$actual" != "$expected" ]]; then
    echo "$label expected HTTP $expected, got $actual" >&2
    if [[ -n "$body_file" && -f "$body_file" ]]; then
      cat "$body_file" >&2
      echo >&2
    fi
    exit 1
  fi
}

http_json() {
  local method="$1"
  local path="$2"
  local body="$3"
  local token="$4"
  local out_body="$5"
  local out_status="$6"

  local curl_args=(
    -sS
    -X "$method"
    "$BASE_URL$path"
    -H 'Accept: application/json'
    -o "$out_body"
    -w '%{http_code}'
  )
  if [[ -n "$token" ]]; then
    curl_args+=(-H "Authorization: Bearer $token")
  fi
  if [[ -n "$body" ]]; then
    curl_args+=(-H 'Content-Type: application/json' -d "$body")
  fi

  curl "${curl_args[@]}" > "$out_status"
}

json_field() {
  local key="$1"
  python - <<'PY' "$key"
import json,sys
key=sys.argv[1]
payload=json.load(sys.stdin)
value=payload.get(key)
if isinstance(value, bool):
    print("true" if value else "false")
elif value is None:
    print("")
else:
    print(value)
PY
}

log "Base URL: $BASE_URL"

log "Checking API reachability"
curl -fsS "$BASE_URL/" >/dev/null || fail "API not reachable at $BASE_URL"

log "Admin login"
LOGIN_BODY="$TMP_DIR/login.json"
LOGIN_STATUS="$TMP_DIR/login.status"
http_json POST "/api/v1/auth/login" \
  "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" \
  "" "$LOGIN_BODY" "$LOGIN_STATUS"
assert_status "$(cat "$LOGIN_STATUS")" "200" "Admin login" "$LOGIN_BODY"
ADMIN_TOKEN="$(python - <<'PY' "$LOGIN_BODY"
import json,sys
print(json.load(open(sys.argv[1])).get("access_token",""))
PY
)"
[[ -n "$ADMIN_TOKEN" ]] || fail "Failed to parse admin token"

log "Create request for offline billing smoke"
SCHEDULED="$(python - <<'PY'
from datetime import datetime, timedelta
print((datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"))
PY
)"
CREATE_BODY="$TMP_DIR/create.json"
CREATE_STATUS="$TMP_DIR/create.status"
http_json POST "/api/v1/waste-requests" \
  "{\"requester_name\":\"$CUSTOMER_NAME\",\"requester_email\":\"$CUSTOMER_EMAIL\",\"material_type\":\"Mixed Plastic\",\"waste_amount\":1.5,\"waste_unit\":\"Tonnes\",\"match_radius_miles\":25,\"pickup_address\":\"1 Billing Smoke Road\",\"pickup_postcode\":\"SW1A1AA\",\"scheduled_pickup_at\":\"$SCHEDULED\"}" \
  "$ADMIN_TOKEN" "$CREATE_BODY" "$CREATE_STATUS"
assert_status "$(cat "$CREATE_STATUS")" "201" "Create waste request" "$CREATE_BODY"
REQUEST_ID="$(python - <<'PY' "$CREATE_BODY"
import json,sys
print(json.load(open(sys.argv[1]))["request"]["id"])
PY
)"
[[ -n "$REQUEST_ID" ]] || fail "Failed to parse request id"
echo "request_id=$REQUEST_ID"

log "Set invoice_sent billing state"
BILLING_BODY="$TMP_DIR/billing.json"
BILLING_STATUS="$TMP_DIR/billing.status"
http_json POST "/api/v1/admin/waste-requests/$REQUEST_ID/billing" \
  "{\"state\":\"invoice_sent\",\"reference\":\"SMOKE-INV-$REQUEST_ID\",\"notes\":\"offline billing smoke invoice\"}" \
  "$ADMIN_TOKEN" "$BILLING_BODY" "$BILLING_STATUS"
assert_status "$(cat "$BILLING_STATUS")" "200" "Billing workflow update" "$BILLING_BODY"

log "Templates, communications report, and export"
TEMPLATE_BODY="$TMP_DIR/templates.json"
TEMPLATE_STATUS="$TMP_DIR/templates.status"
http_json GET "/api/v1/admin/waste-requests/$REQUEST_ID/communications/templates" "" "$ADMIN_TOKEN" "$TEMPLATE_BODY" "$TEMPLATE_STATUS"
assert_status "$(cat "$TEMPLATE_STATUS")" "200" "Communication templates endpoint" "$TEMPLATE_BODY"
python - <<'PY' "$TEMPLATE_BODY"
import json,sys
payload=json.load(open(sys.argv[1]))
keys=[item.get("key") for item in payload.get("templates",[])]
if "invoice_sent" not in keys or "payment_reminder" not in keys:
    print("Required communication templates missing")
    sys.exit(1)
print("Templates include invoice_sent and payment_reminder")
PY

COMM_CREATE_BODY="$TMP_DIR/comm_create.json"
COMM_CREATE_STATUS="$TMP_DIR/comm_create.status"
http_json POST "/api/v1/admin/waste-requests/$REQUEST_ID/communications" \
  "{\"direction\":\"outbound\",\"channel\":\"email\",\"subject\":\"Smoke invoice\",\"message\":\"Sent offline invoice SMOKE-INV-$REQUEST_ID to customer\",\"outcome\":\"invoice_sent\",\"contact_email\":\"$CUSTOMER_EMAIL\",\"customer_visible\":true}" \
  "$ADMIN_TOKEN" "$COMM_CREATE_BODY" "$COMM_CREATE_STATUS"
assert_status "$(cat "$COMM_CREATE_STATUS")" "201" "Communication log create" "$COMM_CREATE_BODY"

COMM_REPORT_BODY="$TMP_DIR/comm_report.json"
COMM_REPORT_STATUS="$TMP_DIR/comm_report.status"
http_json GET "/api/v1/admin/communications/report?direction=outbound&channel=email&search=SMOKE-INV-$REQUEST_ID&limit=20" "" "$ADMIN_TOKEN" "$COMM_REPORT_BODY" "$COMM_REPORT_STATUS"
assert_status "$(cat "$COMM_REPORT_STATUS")" "200" "Communications report endpoint" "$COMM_REPORT_BODY"
python - <<'PY' "$COMM_REPORT_BODY" "$REQUEST_ID"
import json,sys
payload=json.load(open(sys.argv[1]))
rid=int(sys.argv[2])
ids=[(item.get("request") or {}).get("id") for item in payload.get("items",[])]
if rid not in ids:
    print("Request missing from communications report")
    sys.exit(1)
print("Communications report includes request")
PY

log "Billing follow-up queue and reminder maintenance"
FOLLOWUP_BODY="$TMP_DIR/followup.json"
FOLLOWUP_STATUS="$TMP_DIR/followup.status"
http_json GET "/api/v1/admin/billing/followups?reminder_after_hours=0&repeat_hours=48&limit=20" "" "$ADMIN_TOKEN" "$FOLLOWUP_BODY" "$FOLLOWUP_STATUS"
assert_status "$(cat "$FOLLOWUP_STATUS")" "200" "Billing follow-ups endpoint" "$FOLLOWUP_BODY"
python - <<'PY' "$FOLLOWUP_BODY" "$REQUEST_ID"
import json,sys
payload=json.load(open(sys.argv[1]))
rid=int(sys.argv[2])
ids=[(item.get("request") or {}).get("id") for item in payload.get("items",[])]
if rid not in ids:
    print("Request missing from billing follow-ups report")
    sys.exit(1)
print("Billing follow-up report includes request")
PY

MAINT_BODY="$TMP_DIR/followup_maint.json"
MAINT_STATUS="$TMP_DIR/followup_maint.status"
http_json POST "/api/v1/admin/billing/followups/maintenance" \
  "{\"reminder_after_hours\":0,\"repeat_hours\":48,\"limit\":20,\"dry_run\":false,\"log_reminders\":true}" \
  "$ADMIN_TOKEN" "$MAINT_BODY" "$MAINT_STATUS"
assert_status "$(cat "$MAINT_STATUS")" "200" "Billing follow-up maintenance endpoint" "$MAINT_BODY"
python - <<'PY' "$MAINT_BODY"
import json,sys
payload=json.load(open(sys.argv[1]))
if payload.get("summary",{}).get("reminders_logged",0) < 1:
    print("No reminders logged")
    sys.exit(1)
print("Billing follow-up maintenance logged reminder communication")
PY

COMM_LIST_BODY="$TMP_DIR/comm_list.json"
COMM_LIST_STATUS="$TMP_DIR/comm_list.status"
http_json GET "/api/v1/waste-requests/$REQUEST_ID/communications?limit=20" "" "$ADMIN_TOKEN" "$COMM_LIST_BODY" "$COMM_LIST_STATUS"
assert_status "$(cat "$COMM_LIST_STATUS")" "200" "Communication list endpoint" "$COMM_LIST_BODY"
python - <<'PY' "$COMM_LIST_BODY"
import json,sys
payload=json.load(open(sys.argv[1]))
outcomes=[item.get("outcome") for item in payload.get("communications",[])]
if "payment_reminder_sent" not in outcomes:
    print("Payment reminder outcome missing")
    sys.exit(1)
print("Payment reminder communication created")
PY

log "Billing follow-up acknowledgement and closure"
FOLLOWUP_ACK_BODY="$TMP_DIR/followup_ack.json"
FOLLOWUP_ACK_STATUS="$TMP_DIR/followup_ack.status"
http_json POST "/api/v1/admin/waste-requests/$REQUEST_ID/billing-followup" \
  "{\"state\":\"acknowledged\",\"notes\":\"Billing smoke acknowledgement\"}" \
  "$ADMIN_TOKEN" "$FOLLOWUP_ACK_BODY" "$FOLLOWUP_ACK_STATUS"
assert_status "$(cat "$FOLLOWUP_ACK_STATUS")" "200" "Billing follow-up acknowledge endpoint" "$FOLLOWUP_ACK_BODY"
python - <<'PY' "$FOLLOWUP_ACK_BODY"
import json,sys
payload=json.load(open(sys.argv[1]))
if (payload.get("followup") or {}).get("state") != "acknowledged":
    print("Billing follow-up acknowledgement did not persist")
    sys.exit(1)
print("Billing follow-up acknowledged")
PY

FOLLOWUP_CLOSE_BODY="$TMP_DIR/followup_close.json"
FOLLOWUP_CLOSE_STATUS="$TMP_DIR/followup_close.status"
http_json POST "/api/v1/admin/waste-requests/$REQUEST_ID/billing-followup" \
  "{\"state\":\"closed\",\"notes\":\"Billing smoke closure\"}" \
  "$ADMIN_TOKEN" "$FOLLOWUP_CLOSE_BODY" "$FOLLOWUP_CLOSE_STATUS"
assert_status "$(cat "$FOLLOWUP_CLOSE_STATUS")" "200" "Billing follow-up close endpoint" "$FOLLOWUP_CLOSE_BODY"
python - <<'PY' "$FOLLOWUP_CLOSE_BODY"
import json,sys
payload=json.load(open(sys.argv[1]))
if (payload.get("followup") or {}).get("state") != "closed":
    print("Billing follow-up closure did not persist")
    sys.exit(1)
print("Billing follow-up closed")
PY

echo
echo "OFFLINE BILLING OPS SMOKE PASSED"
echo "request_id=$REQUEST_ID"
