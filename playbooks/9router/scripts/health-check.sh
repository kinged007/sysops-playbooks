#!/usr/bin/env bash
# health-check.sh — 9Router skill-based probes
# Uses the NINEROUTER_URL / NINEROUTER_KEY contracts from
# https://raw.githubusercontent.com/decolua/9router/refs/heads/master/skills/9router/SKILL.md
# Never logs the key value.
#
# Usage:
#   NINEROUTER_URL=http://localhost:20128 NINEROUTER_KEY=sk-... ./scripts/health-check.sh
#   ./scripts/health-check.sh --url http://localhost:20128 --key-file executions/9router/secrets/9router-api-key.txt
#   ./scripts/health-check.sh --url https://9router.example.com [--key-file ...]
#
# Exit codes: 0 = healthy, 1 = unhealthy, 2 = usage error

set -euo pipefail

URL="${NINEROUTER_URL:-}"
KEY="${NINEROUTER_KEY:-}"
KEY_FILE=""
MODEL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url) URL="$2"; shift 2 ;;
    --key) KEY="$2"; shift 2 ;;
    --key-file) KEY_FILE="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--url URL] [--key KEY | --key-file FILE] [--model MODEL]"
      echo "  Env: NINEROUTER_URL, NINEROUTER_KEY"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -n "$KEY_FILE" ]]; then
  if [[ ! -f "$KEY_FILE" ]]; then
    echo "ERR: key file not found: $KEY_FILE" >&2
    exit 2
  fi
  KEY="$(tr -d '\r\n' < "$KEY_FILE")"
fi

if [[ -z "$URL" ]]; then
  echo "ERR: NINEROUTER_URL not set (or --url missing)" >&2
  exit 2
fi

# Normalize: strip trailing /
URL="${URL%/}"

pass=0
fail=0

say() { printf '%s\n' "$*"; }
pass_msg() { say "PASS: $*"; pass=$((pass+1)); }
fail_msg() { say "FAIL: $*"; fail=$((fail+1)); }

# 1 — /api/health (no auth)
say "==> GET $URL/api/health"
HEALTH_CODE=""
HEALTH_BODY=""
if HEALTH_BODY="$(curl -sS -w '\n%{http_code}' --max-time 10 "$URL/api/health" 2>&1)"; then
  HEALTH_CODE="$(printf '%s' "$HEALTH_BODY" | tail -n 1)"
  HEALTH_BODY="$(printf '%s' "$HEALTH_BODY" | sed '$d')"
  if [[ "$HEALTH_CODE" == "200" ]] && echo "$HEALTH_BODY" | grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then
    pass_msg "/api/health -> 200 {ok:true}"
  else
    fail_msg "/api/health -> HTTP $HEALTH_CODE body: $(printf '%s' "$HEALTH_BODY" | head -c 500)"
  fi
else
  fail_msg "/api/health unreachable: $HEALTH_BODY"
fi

# 2 — /v1/models (chat/LLM) — auth if REQUIRE_API_KEY=true
say "==> GET $URL/v1/models"
AUTH_HEADER=()
if [[ -n "$KEY" ]]; then
  AUTH_HEADER=(-H "Authorization: Bearer $KEY")
fi
MODELS_CODE=""
MODELS_BODY=""
if MODELS_BODY="$(curl -sS -w '\n%{http_code}' --max-time 10 "${AUTH_HEADER[@]}" "$URL/v1/models" 2>&1)"; then
  MODELS_CODE="$(printf '%s' "$MODELS_BODY" | tail -n 1)"
  MODELS_BODY="$(printf '%s' "$MODELS_BODY" | sed '$d')"
  if [[ "$MODELS_CODE" == "200" ]] && echo "$MODELS_BODY" | grep -q '"object"[[:space:]]*:[[:space:]]*"list"'; then
    COUNT="$(echo "$MODELS_BODY" | grep -o '"id"[[:space:]]*:' | wc -l | tr -d ' ')"
    pass_msg "/v1/models -> 200 with $COUNT model(s)"
    if echo "$MODELS_BODY" | grep -q '"owned_by"[[:space:]]*:[[:space:]]*"combo"'; then
      say "  combos: present (owned_by combo)"
    fi
  elif [[ "$MODELS_CODE" == "401" ]]; then
    if [[ -z "$KEY" ]]; then
      say "INFO: /v1/models -> 401 (REQUIRE_API_KEY is enabled; provide --key-file and re-run for full check)"
      pass=$((pass)) # not a failure — expected without key
    else
      fail_msg "/v1/models -> 401 (key rejected) — refresh NINEROUTER_KEY (Dashboard -> Keys)"
    fi
  else
    fail_msg "/v1/models -> HTTP $MODELS_CODE body: $(printf '%s' "$MODELS_BODY" | head -c 800)"
  fi
else
  fail_msg "/v1/models unreachable: $MODELS_BODY"
fi

# 3 — /v1/models/* per-kind discovery (only if auth succeeded)
if [[ "$MODELS_CODE" == "200" ]]; then
  for kind in image tts embedding web; do
    say "==> GET $URL/v1/models/$kind"
    if out="$(curl -sS -w '\n%{http_code}' --max-time 10 "${AUTH_HEADER[@]}" "$URL/v1/models/$kind" 2>&1)"; then
      code="$(printf '%s' "$out" | tail -n 1)"
      body="$(printf '%s' "$out" | sed '$d')"
      if [[ "$code" == "200" ]]; then
        c2="$(printf '%s' "$body" | grep -o '"id"[[:space:]]*:' | wc -l | tr -d ' ')"
        say "  $kind: 200 with $c2 model(s)"
      else
        say "  $kind: HTTP $code (may be expected if no provider for this kind)"
      fi
    fi
  done
fi

# 4 — optional chat probe if --model given (uses 9router-chat capability shape)
if [[ -n "$MODEL" ]]; then
  if [[ -z "$KEY" ]]; then
    say "SKIP: chat probe (--model $MODEL) requires a key"
  else
    say "==> POST $URL/v1/chat/completions model=$MODEL"
    CHAT_BODY='{"model":"'"$MODEL"'","messages":[{"role":"user","content":"ping"}],"max_tokens":16}'
    if out="$(curl -sS -w '\n%{http_code}' --max-time 30 -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d "$CHAT_BODY" "$URL/v1/chat/completions" 2>&1)"; then
      code="$(printf '%s' "$out" | tail -n 1)"
      body="$(printf '%s' "$out" | sed '$d')"
      if [[ "$code" == "200" ]] && echo "$body" | grep -q '"choices"'; then
        pass_msg "chat/completions ($MODEL) -> 200 with choices"
      else
        fail_msg "chat/completions ($MODEL) -> HTTP $code body: $(printf '%s' "$body" | head -c 1000)"
      fi
    else
      fail_msg "chat/completions unreachable: $out"
    fi
  fi
fi

say "---"
say "Summary: $pass pass, $fail fail"
if [[ $fail -gt 0 ]]; then
  # Hints
  if echo "${HEALTH_BODY:-}" | grep -q "Connection refused"; then
    say "Hint: is 9Router listening on $URL? Check ss -tlnp and docker ps / systemctl status 9router"
  fi
  exit 1
fi
exit 0
