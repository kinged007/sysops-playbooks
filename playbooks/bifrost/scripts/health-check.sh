#!/usr/bin/env bash
# Smoke-probe a Bifrost instance: /health, /v1/models, chat completion.
# Usage: health-check.sh http://<HOST>:<PORT> [VIRTUAL_KEY]
set -euo pipefail
BASE="${1:?usage: health-check.sh http://HOST:PORT [VIRTUAL_KEY]}"
KEY="${2:-}"
AUTH=()
[ -n "$KEY" ] && AUTH=(-H "Authorization: Bearer $KEY")

echo "== /health =="
curl -fsS "$BASE/health"; echo
echo "== /v1/models =="
curl -fsS "${AUTH[@]}" "$BASE/v1/models" | head -c 1000; echo
echo "== chat completion =="
curl -fsS "${AUTH[@]}" "$BASE/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{"model":"openai/gpt-4o-mini","messages":[{"role":"user","content":"ping"}]}' \
  | head -c 1000; echo
echo OK
