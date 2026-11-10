#!/bin/bash
# SysOps Hermes A2A helper — safe, no restart/kill commands
# Run: coder ssh sysops-playbooks -- '~/sysops-playbooks/hermes-a2a-help.sh'
set -e
HERMES=~/.local/bin/hermes
echo "=== hermes gateway status ==="; $HERMES gateway status 2>&1 | head -n 20
echo "=== hermes status ==="; $HERMES status 2>&1 | head -n 40
echo "=== A2A env (keys masked) ==="; grep "^A2A_" ~/.hermes/.env 2>&1 | sed "s/=.*/=MASKED/" | head -n 20
echo "=== ss 9900 ==="; ss -tlnp 2>&1 | grep 9900 | head
echo "=== gateway pid ==="; cat ~/.hermes/logs/gateway.pid 2>&1 | head; ps -p $(cat ~/.hermes/logs/gateway.pid 2>/dev/null) -o pid,cmd 2>&1 | head -n 10
echo "=== cloudflared ==="; cat ~/.hermes/logs/cloudflared.pid 2>&1 | head; ps -p $(cat ~/.hermes/logs/cloudflared.pid 2>/dev/null) -o pid,cmd 2>&1 | head -n 10; cat /tmp/cf_url.txt 2>&1 | head -n 5
echo "=== Agent Card URL ==="; curl -s http://127.0.0.1:9900/.well-known/agent-card.json 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['name'], d['url'])" 2>&1 | head
echo "=== recent gateway log ==="; tail -n 20 ~/.hermes/logs/gateway.log 2>&1 | tail -n 20
echo "=== test ping (no auth should be 401) ==="; curl -s http://127.0.0.1:9900/ -X POST -H "Content-Type: application/json" -d '{"jsonrpc":"2.0","id":1,"method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"text","text":"ping"}]}}}' 2>&1 | python3 -m json.tool 2>&1 | head -n 20
