#!/usr/bin/env python3
"""Bifrost admin API helper. Secret-free: reads admin credentials from env.

Designed to run under `ops secret run` (vault entry my-tech-bifrost-dashboard),
which exports BIFROST_ADMIN_USER / BIFROST_ADMIN_PASSWORD and redacts output:
  bin/ops secret run my-tech-bifrost-dashboard -- 'python3 .agents/skills/bifrost/scripts/bifrost-admin.py list-keys'

Env:
  BIFROST_ADMIN_USER / BIFROST_ADMIN_PASSWORD (required, via ops secret run)
  BIFROST_BASE_URL (default https://routers.munyard.biz)

Commands (read-only unless noted):
  list-keys                 names, ids, budgets, activity (values masked)
  list-providers            providers and key/model allowlists (no secret values)
  models                    model catalog: provider/name pairs (read-only)
  refetch PROVIDER          refresh a provider's model list from upstream
  create-key NAME PROVIDER [MODELS_CSV] [--budget AMT --reset DUR] [--out PATH]   WRITE
  delete-key VK_ID          WRITE: deactivates/deletes a virtual key
  list-rules                routing rules (id, name, scope, priority, enabled)
  create-rule NAME CEL PROVIDER MODEL [FALLBACK_CSV] [--priority N]   WRITE
"""
import base64
import json
import os
import sys
import urllib.request

BASE = os.environ.get("BIFROST_BASE_URL", "https://routers.munyard.biz").rstrip("/")


def auth_headers():
    user = os.environ["BIFROST_ADMIN_USER"]
    pwd = os.environ["BIFROST_ADMIN_PASSWORD"]
    token = base64.b64encode(f"{user}:{pwd}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def call(method, path, body=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=auth_headers(),
        method=method,
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, json.loads(r.read().decode())


def mask(value):
    if not isinstance(value, str) or len(value) < 12:
        return "***"
    return f"{value[:6]}...({len(value)} chars)"


def scrub_key(k):
    return {
        "id": k.get("id"),
        "name": k.get("name"),
        "value": mask(k.get("value", "")),
        "is_active": k.get("is_active"),
        "providers": [p.get("provider") for p in k.get("provider_configs", [])],
        "budgets": k.get("budgets"),
    }


def cmd_list_keys():
    st, data = call("GET", "/api/governance/virtual-keys?limit=100")
    keys = data.get("virtual_keys", []) if isinstance(data, dict) else data
    print(f"STATUS: {st} count: {data.get('total_count', len(keys)) if isinstance(data, dict) else len(keys)}")
    for k in keys:
        print(json.dumps(scrub_key(k)))


def cmd_list_providers():
    st, data = call("GET", "/api/providers")
    print(f"STATUS: {st}")
    provs = data if isinstance(data, list) else data.get("data", data.get("providers", []))
    for p in provs:
        names = [kk.get("name") for kk in p.get("keys", [])] if isinstance(p, dict) else []
        print(json.dumps({"provider": p.get("name") if isinstance(p, dict) else p, "keys": names}))


def cmd_models():
    st, data = call("GET", "/api/models")
    models = data.get("models", []) if isinstance(data, dict) else data
    print(f"STATUS: {st} count: {data.get('total', len(models)) if isinstance(data, dict) else len(models)}")
    for m in models:
        print(f"  {m.get('provider')} / {m.get('name')}")


def cmd_refetch(provider):
    st, res = call("POST", f"/api/v1/providers/{provider}/models/refetch")
    print(f"STATUS: {st} result: {json.dumps(res)[:300]}")


def cmd_create_key(args):
    name, provider = args[0], args[1]
    models = args[2].split(",") if len(args) > 2 and not args[2].startswith("--") else ["*"]
    budget = None
    if "--budget" in args:
        amt = float(args[args.index("--budget") + 1])
        dur = "1M"
        if "--reset" in args:
            dur = args[args.index("--reset") + 1]
        budget = [{"max_limit": amt, "reset_duration": dur}]
    out = None
    if "--out" in args:
        out = args[args.index("--out") + 1]
    body = {
        "name": name,
        "provider_configs": [{"provider": provider, "allowed_models": models, "key_ids": ["*"]}],
        "is_active": True,
    }
    if budget:
        body["budgets"] = budget
    st, created = call("POST", "/api/governance/virtual-keys", body)
    value = created.get("value", "")
    if not out:
        print(f"STATUS: {st} id: {created.get('id')} name: {created.get('name')}")
        print("REFUSED: no --out PATH given; value not displayed. Re-run with --out to save it.")
        return
    with open(os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(f"BIFROST_VK_{name.upper().replace('-', '_')}={value}\n")
    print(f"STATUS: {st} id: {created.get('id')} saved: {out} (value: {mask(value)})")


def cmd_list_rules():
    st, data = call("GET", "/api/routing/rules")
    rules = data.get("rules", []) if isinstance(data, dict) else data
    print(f"STATUS: {st} count: {len(rules)}")
    for r in rules:
        tg = ";".join(f"{t.get('provider')}/{t.get('model')}" for t in r.get("targets", []))
        print(json.dumps({"id": r.get("id"), "name": r.get("name"), "scope": r.get("scope"),
                          "priority": r.get("priority"), "enabled": r.get("enabled"),
                          "cel": r.get("cel_expression"), "targets": tg,
                          "fallbacks": r.get("fallbacks")}, )[:400])


def cmd_create_rule(args):
    name, cel, provider, model = args[0], args[1], args[2], args[3]
    fallbacks = args[4].split(",") if len(args) > 4 and not args[4].startswith("--") else []
    priority = 10
    if "--priority" in args:
        priority = int(args[args.index("--priority") + 1])
    st, created = call(
        "POST",
        "/api/routing/rules",
        {
            "name": name,
            "cel_expression": cel,
            "targets": [{"provider": provider, "model": model, "weight": 1}],
            "fallbacks": fallbacks,
            "scope": "global",
            "priority": priority,
            "enabled": True,
        },
    )
    print(f"STATUS: {st} id: {(created.get('rule', created) or {}).get('id')} name: {name}")


def cmd_delete_key(vk_id):
    st, res = call("DELETE", f"/api/governance/virtual-keys/{vk_id}")
    print(f"STATUS: {st} result: {json.dumps(res)[:200]}")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "list-keys"
    if cmd == "list-keys":
        cmd_list_keys()
    elif cmd == "list-providers":
        cmd_list_providers()
    elif cmd == "models":
        cmd_models()
    elif cmd == "refetch":
        cmd_refetch(argv[2])
    elif cmd == "create-key":
        cmd_create_key(argv[2:])
    elif cmd == "delete-key":
        cmd_delete_key(argv[2])
    elif cmd == "list-rules":
        cmd_list_rules()
    elif cmd == "create-rule":
        cmd_create_rule(argv[2:])
    else:
        sys.exit(f"unknown command: {cmd}")


if __name__ == "__main__":
    main(sys.argv)
