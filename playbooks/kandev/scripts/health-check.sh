#!/usr/bin/env bash
# health-check.sh — Kandev liveness/readiness/auth/MCP/executor probes
# No secrets are logged. PATs are read from a file (0600) or env KANDEV_PAT.
#
# Usage:
#   ./scripts/health-check.sh --url http://127.0.0.1:38429
#   ./scripts/health-check.sh --url https://kandev.example.com --pat-file executions/kandev/secrets/kandev-pat-admin.txt
#   KANDEV_URL=https://kandev.example.com KANDEV_PAT=kandev_pat_... ./scripts/health-check.sh
#   ./scripts/health-check.sh --url http://127.0.0.1:38429 --home-dir /srv/kandev
#
# Exit codes: 0 = healthy, 1 = unhealthy, 2 = usage error

set -euo pipefail

URL="${KANDEV_URL:-}"
PAT="${KANDEV_PAT:-}"
PAT_FILE=""
HOME_DIR=""
TIMEOUT=10

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url) URL="$2"; shift 2 ;;
    --pat) PAT="$2"; shift 2 ;;
    --pat-file) PAT_FILE="$2"; shift 2 ;;
    --home-dir) HOME_DIR="$2"; shift 2 ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--url URL] [--pat PAT | --pat-file FILE] [--home-dir DIR] [--timeout SECS]"
      echo "  Env: KANDEV_URL, KANDEV_PAT"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -n "$PAT_FILE" ]]; then
  if [[ ! -f "$PAT_FILE" ]]; then
    echo "ERR: PAT file not found: $PAT_FILE" >&2
    exit 2
  fi
  PAT="$(tr -d '\r\n' < "$PAT_FILE")"
fi

if [[ -z "$URL" ]]; then
  echo "ERR: URL not set (--url or KANDEV_URL)" >&2
  exit 2
fi

URL="${URL%/}"
pass=0
fail=0
warn=0

say()   { printf '%s\n' "$*"; }
pass_msg() { say "PASS: $*"; pass=$((pass+1)); }
fail_msg() { say "FAIL: $*"; fail=$((fail+1)); }
warn_msg() { say "WARN: $*"; warn=$((warn+1)); }

# ── 1: /health (liveness — 200 as soon as listener accepts, even mid-startup) ──
say "==> GET $URL/health"
if body="$(curl -sS -w '\n%{http_code}' --max-time "$TIMEOUT" "$URL/health" 2>&1)"; then
  code="$(printf '%s' "$body" | tail -n 1)"
  b="$(printf '%s' "$body" | sed '$d')"
  if [[ "$code" == "200" ]] && echo "$b" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"'; then
    ver="$(printf '%s' "$b" | grep -o '"version"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 || true)"
    pass_msg "/health -> 200 {status:ok} $ver"
  else
    fail_msg "/health -> HTTP $code body: $(printf '%s' "$b" | head -c 600)"
  fi
else
  fail_msg "/health unreachable: $body"
fi

# ── 2: /ready (readiness — 503 during startup, 200 when routes+registry ready) ──
say "==> GET $URL/ready"
if body="$(curl -sS -w '\n%{http_code}' --max-time "$TIMEOUT" "$URL/ready" 2>&1)"; then
  code="$(printf '%s' "$body" | tail -n 1)"
  b="$(printf '%s' "$body" | sed '$d')"
  if [[ "$code" == "200" ]]; then
    pass_msg "/ready -> 200 (can serve real traffic)"
  elif [[ "$code" == "503" ]]; then
    warn_msg "/ready -> 503 starting (process alive, still wiring routes — retry in a few seconds)"
  else
    fail_msg "/ready -> HTTP $code body: $(printf '%s' "$b" | head -c 600)"
  fi
else
  fail_msg "/ready unreachable: $body"
fi

# ── 3: /api/v1/features (unauthenticated, shows auth toggle) ──
say "==> GET $URL/api/v1/features"
if body="$(curl -sS -w '\n%{http_code}' --max-time "$TIMEOUT" "$URL/api/v1/features" 2>&1)"; then
  code="$(printf '%s' "$body" | tail -n 1)"
  b="$(printf '%s' "$body" | sed '$d')"
  if [[ "$code" == "200" ]]; then
    pass_msg "/api/v1/features -> 200"
    echo "$b" | head -c 800 | tr -d '\r' | sed 's/^/  /'
    echo ""
  else
    fail_msg "/api/v1/features -> HTTP $code body: $(printf '%s' "$b" | head -c 600)"
  fi
else
  fail_msg "/api/v1/features unreachable: $body"
fi

# ── 4: Auth gate (if PAT given, expect 200; without, expect 401 when auth ON) ──
say "==> GET $URL/api/v1/workspaces (auth gate)"
if [[ -n "$PAT" ]]; then
  if body="$(curl -sS -w '\n%{http_code}' --max-time "$TIMEOUT" -H "Authorization: Bearer $PAT" "$URL/api/v1/workspaces" 2>&1)"; then
    code="$(printf '%s' "$body" | tail -n 1)"
    if [[ "$code" == "200" ]]; then
      pass_msg "/api/v1/workspaces with PAT -> 200 (auth OK)"
    else
      b="$(printf '%s' "$body" | sed '$d')"
      fail_msg "/api/v1/workspaces with PAT -> HTTP $code body: $(printf '%s' "$b" | head -c 600)"
    fi
  else
    fail_msg "/api/v1/workspaces with PAT unreachable: $body"
  fi
else
  if body="$(curl -sS -w '\n%{http_code}' --max-time "$TIMEOUT" "$URL/api/v1/workspaces" 2>&1)"; then
    code="$(printf '%s' "$body" | tail -n 1)"
    b="$(printf '%s' "$body" | sed '$d')"
    if [[ "$code" == "401" ]]; then
      say "INFO: /api/v1/workspaces without PAT -> 401 (auth is ON — provide --pat-file for full check)"
    elif [[ "$code" == "200" ]]; then
      say "INFO: /api/v1/workspaces without PAT -> 200 (auth is OFF — single-user)"
    else
      warn_msg "/api/v1/workspaces without PAT -> HTTP $code body: $(printf '%s' "$b" | head -c 500)"
    fi
  fi
fi

# ── 5: External MCP initialize probe ──
say "==> POST $URL/mcp (JSON-RPC initialize)"
if [[ -n "$PAT" ]]; then
  auth_hdr=(-H "Authorization: Bearer $PAT")
else
  auth_hdr=()
fi
if body="$(curl -sS -w '\n%{http_code}' --max-time "$TIMEOUT" "${auth_hdr[@]}" -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' "$URL/mcp" 2>&1)"; then
  code="$(printf '%s' "$body" | tail -n 1)"
  b="$(printf '%s' "$body" | sed '$d')"
  if [[ "$code" == "200" ]]; then
    pass_msg "/mcp initialize -> 200"
  elif [[ "$code" == "401" ]]; then
    if [[ -z "$PAT" ]]; then
      say "INFO: /mcp -> 401 (auth ON, no PAT — provide --pat-file and re-run for full check)"
    else
      fail_msg "/mcp initialize with PAT -> 401 (PAT rejected — re-mint in Settings → Account → API Tokens)"
    fi
  else
    fail_msg "/mcp initialize -> HTTP $code body: $(printf '%s' "$b" | head -c 800)"
  fi
else
  fail_msg "/mcp unreachable: $body"
fi

# ── 6: /ws gate (should NOT be 403 when Host/Origin + trustedProxies are correct) ──
say "==> HEAD $URL/ws (WebSocket upgrade gate)"
if body="$(curl -sS -w '\n%{http_code}' -I --max-time "$TIMEOUT" "$URL/ws" 2>&1)"; then
  code="$(printf '%s' "$body" | grep -i "^HTTP/" | tail -1 | awk '{print $2}' || echo "000")"
  if [[ "$code" == "403" ]]; then
    fail_msg "/ws -> 403 (Host/Origin gate or X-Forwarded-Host from untrusted peer — check KANDEV_TRUSTED_PROXIES, G9)"
  elif [[ "$code" == "426" || "$code" == "400" || "$code" == "101" || "$code" == "200" ]]; then
    say "INFO: /ws -> HTTP $code (upgrade endpoint reachable; 426/101 is normal for non-WS HEAD)"
  else
    say "INFO: /ws -> HTTP $code"
  fi
fi

# ── 7: Local home/DB check (if --home-dir given and path exists locally) ──
if [[ -n "$HOME_DIR" ]]; then
  say "==> Local home checks: $HOME_DIR"
  if [[ -d "$HOME_DIR" ]]; then
    ls -lh "$HOME_DIR/data/kandev.db"* "$HOME_DIR/data/master.key" 2>&1 | sed 's/^/  /' || warn_msg "$HOME_DIR/data/kandev.db or master.key missing"
    ls -ld "$HOME_DIR/logs" "$HOME_DIR/data/backups" 2>&1 | sed 's/^/  /' || true
    if [[ -f "$HOME_DIR/service/install.json" ]]; then
      say "  service/install.json:"
      sed 's/^/    /' < "$HOME_DIR/service/install.json" | head -20
    fi
    # custom DB symlink
    if [[ -n "${KANDEV_DATABASE_PATH:-}" ]]; then
      say "  KANDEV_DATABASE_PATH=$KANDEV_DATABASE_PATH"
      ls -lh "$KANDEV_DATABASE_PATH"* 2>&1 | sed 's/^/  /' || warn_msg "Custom DB path $KANDEV_DATABASE_PATH missing"
    fi
  else
    warn_msg "HOME_DIR $HOME_DIR not found locally (ok if remote-only). Use --url with remote health check instead."
  fi
fi

say "---"
say "Summary: $pass pass, $fail fail, $warn warn"
if [[ $fail -gt 0 ]]; then
  if grep -qi "Connection refused" <<< "${body:-}"; then
    say "Hint: is Kandev listening on $URL? Check 'kandev service logs --home-dir $HOME_DIR' or 'docker logs kandev' and 'ss -tlnp | grep 38429'"
  fi
  exit 1
fi
exit 0
