#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:5052}"
EMAIL="${SMOKE_EMAIL:-smoke.$(date +%s)@example.com}"
PASSWORD="${SMOKE_PASSWORD:-Password123}"
NEW_PASSWORD="${SMOKE_NEW_PASSWORD:-NewPass123}"

echo "Base URL: $BASE_URL"
echo "Email: $EMAIL"

read_json_field() {
  local field="$1"
  python -c "import json,sys; data=json.load(sys.stdin); print(data.get('$field',''))"
}

request() {
  local method="$1"
  local path="$2"
  local body="$3"
  curl -sS -X "$method" "$BASE_URL$path" \
    -H 'Content-Type: application/json' \
    -d "$body"
}

expect_401_with_access_token() {
  local access_token="$1"
  local label="$2"
  local probe_token="$3"
  local status
  local body_file="/tmp/auth_smoke_401_probe.json"

  status="$(curl -sS -o "$body_file" -w '%{http_code}' \
    -X POST "$BASE_URL/api/v1/push-subscriptions" \
    -H "Authorization: Bearer $access_token" \
    -H 'Content-Type: application/json' \
    -d "{\"token\":\"$probe_token\",\"provider\":\"expo\",\"platform\":\"ios\"}")"
  cat "$body_file"
  echo
  if [[ "$status" != "401" ]]; then
    echo "$label expected HTTP 401 but got $status"
    exit 1
  fi
}

echo "1) Signup"
SIGNUP_RESP="$(request POST /api/v1/auth/signup "{\"name\":\"Smoke User\",\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")"
echo "$SIGNUP_RESP"

VERIFICATION_REQUIRED="$(echo "$SIGNUP_RESP" | read_json_field verification_required)"
VERIFY_TOKEN="$(echo "$SIGNUP_RESP" | read_json_field verification_token)"

if [[ "$VERIFICATION_REQUIRED" == "True" || "$VERIFICATION_REQUIRED" == "true" ]]; then
  if [[ -z "$VERIFY_TOKEN" ]]; then
    echo "2) Request verification token (AUTH_RETURN_TOKENS_IN_RESPONSE must be 1 for full smoke)"
    VERIFY_REQ_RESP="$(request POST /api/v1/auth/verify/request "{\"email\":\"$EMAIL\"}")"
    echo "$VERIFY_REQ_RESP"
    VERIFY_TOKEN="$(echo "$VERIFY_REQ_RESP" | read_json_field verification_token)"
  fi

  if [[ -z "$VERIFY_TOKEN" ]]; then
    echo "Missing verification token. Set AUTH_RETURN_TOKENS_IN_RESPONSE=1 for local smoke testing."
    exit 1
  fi

  echo "3) Confirm verification"
  VERIFY_CONFIRM_RESP="$(request POST /api/v1/auth/verify/confirm "{\"token\":\"$VERIFY_TOKEN\"}")"
  echo "$VERIFY_CONFIRM_RESP"
fi

echo "4) Login"
LOGIN_RESP="$(request POST /api/v1/auth/login "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")"
echo "$LOGIN_RESP"
LOGIN_ACCESS_TOKEN="$(echo "$LOGIN_RESP" | read_json_field access_token)"
REFRESH_TOKEN="$(echo "$LOGIN_RESP" | read_json_field refresh_token)"
if [[ -z "$REFRESH_TOKEN" ]]; then
  echo "Login did not return refresh_token."
  exit 1
fi

echo "5) Refresh session"
REFRESH_RESP="$(request POST /api/v1/auth/refresh "{\"refresh_token\":\"$REFRESH_TOKEN\"}")"
echo "$REFRESH_RESP"

echo "6) Request password reset"
RESET_REQ_RESP="$(request POST /api/v1/auth/password-reset/request "{\"email\":\"$EMAIL\"}")"
echo "$RESET_REQ_RESP"
RESET_TOKEN="$(echo "$RESET_REQ_RESP" | read_json_field reset_token)"
if [[ -z "$RESET_TOKEN" ]]; then
  echo "Missing reset token. Set AUTH_RETURN_TOKENS_IN_RESPONSE=1 for local smoke testing."
  exit 1
fi

echo "7) Confirm password reset"
RESET_CONFIRM_RESP="$(request POST /api/v1/auth/password-reset/confirm "{\"token\":\"$RESET_TOKEN\",\"new_password\":\"$NEW_PASSWORD\"}")"
echo "$RESET_CONFIRM_RESP"

echo "7b) Access token from step 4 must be revoked after password reset"
expect_401_with_access_token "$LOGIN_ACCESS_TOKEN" \
  "Password reset revocation check" \
  "ExponentPushToken[smoke-reset-$(date +%s)]"

echo "8) Login with new password"
LOGIN_NEW_RESP="$(request POST /api/v1/auth/login "{\"email\":\"$EMAIL\",\"password\":\"$NEW_PASSWORD\"}")"
echo "$LOGIN_NEW_RESP"
LOGIN_NEW_ACCESS_TOKEN="$(echo "$LOGIN_NEW_RESP" | read_json_field access_token)"

echo "9) Logout/revoke refresh token"
NEW_REFRESH_TOKEN="$(echo "$LOGIN_NEW_RESP" | read_json_field refresh_token)"
if [[ -n "$NEW_REFRESH_TOKEN" ]]; then
  LOGOUT_RESP="$(curl -sS -X POST "$BASE_URL/api/v1/auth/logout" \
    -H "Authorization: Bearer $LOGIN_NEW_ACCESS_TOKEN" \
    -H 'Content-Type: application/json' \
    -d "{\"refresh_token\":\"$NEW_REFRESH_TOKEN\"}")"
  echo "$LOGOUT_RESP"
fi

echo "10) Access token from step 8 must be revoked after logout"
expect_401_with_access_token "$LOGIN_NEW_ACCESS_TOKEN" \
  "Logout revocation check" \
  "ExponentPushToken[smoke-logout-$(date +%s)]"

echo "11) Refresh token from step 8 must be revoked after logout"
POST_LOGOUT_REFRESH_STATUS="$(curl -sS -o /tmp/auth_smoke_refresh_after_logout.json -w '%{http_code}' \
  -X POST "$BASE_URL/api/v1/auth/refresh" \
  -H 'Content-Type: application/json' \
  -d "{\"refresh_token\":\"$NEW_REFRESH_TOKEN\"}")"
cat /tmp/auth_smoke_refresh_after_logout.json
echo
if [[ "$POST_LOGOUT_REFRESH_STATUS" != "401" ]]; then
  echo "Refresh token revocation check expected HTTP 401 but got $POST_LOGOUT_REFRESH_STATUS"
  exit 1
fi

echo "Auth lifecycle smoke test passed."
