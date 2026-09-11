#!/usr/bin/env python3
"""
generate-configs.py — 9Router config generator from live /v1/models

Uses the NINEROUTER_URL / NINEROUTER_KEY contracts so configs contain
actual model IDs (including combos like free, coding-pro, etc.) instead
of template provider/model placeholders.

This solves the "CLI not fetching available models and I have to hardcode"
problem: run this on any host (including remote servers) to refresh
opencode/hermes/codex/claude configs from the live gateway.

Usage:
  NINEROUTER_URL=http://development-9router-fe01c0-62-171-191-174.sslip.io \
  NINEROUTER_KEY=sk-... python playbooks/9router/scripts/generate-configs.py

  python playbooks/9router/scripts/generate-configs.py --url http://host --key sk-... --out executions/9router/generated --active-model free
  python playbooks/9router/scripts/generate-configs.py --url http://host:20128 --key-file executions/9router/secrets/9router-api-key.txt

Outputs (gitignored, persistent per-variant):
  executions/9router/generated/opencode.json         (~/.config/opencode/opencode.json)
  executions/9router/generated/hermes-config.yaml    (~/.hermes/config.yaml) + hermes.env
  executions/9router/generated/codex-config.toml     (~/.codex/config.toml)
  executions/9router/generated/claude-settings.json  (~/.claude/settings.json env block)
  executions/9router/generated/generic-env.sh

All configs are copy-paste ready; baseURL is normalized to .../v1 and apiKey is injected.
Never logs the key value — use --key-file or env, not shell history.
"""
import argparse
import json
import os
import pathlib
import sys

try:
    import requests  # prefer requests if available
except ImportError:
    requests = None

def load_secrets():
    candidates_url = [
        pathlib.Path("D:/Data/git/sysops-playbooks/executions/9router/secrets/ninerouter-url.txt"),
        pathlib.Path("executions/9router/secrets/ninerouter-url.txt"),
        pathlib.Path("executions/9router/secrets/ninerouter-url.txt"),
    ]
    candidates_key = [
        pathlib.Path("D:/Data/git/sysops-playbooks/executions/9router/secrets/9router-api-key.txt"),
        pathlib.Path("executions/9router/secrets/9router-api-key.txt"),
        pathlib.Path("D:/Data/git/sysops-playbooks/executions/9router/secrets/ninerouter-key.txt"),
    ]
    url = None
    key = None
    for p in candidates_url:
        if p.exists():
            try:
                url = p.read_text(encoding="utf-8").strip().strip("\ufeff").strip()
                if url:
                    break
            except: pass
    for p in candidates_key:
        if p.exists():
            try:
                key = p.read_text(encoding="utf-8").strip().strip("\ufeff").strip()
                if key:
                    break
            except: pass
    return url, key

def fetch_models(url, key):
    endpoint = url.rstrip("/") + "/v1/models"
    headers = {}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if requests:
        r = requests.get(endpoint, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()
    else:
        import urllib.request, json as js
        req = urllib.request.Request(endpoint, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return js.loads(resp.read().decode())

def write_opencode(models, base_url, api_key, out_dir, active_model):
    # api_key is ignored — never hardcode, reference env var only (per user request)
    provider_models = {}
    for m in models:
        mid = m.get("id")
        if not mid:
            continue
        provider_models[mid] = {"name": mid, "modalities": {"input": ["text", "image"], "output": ["text"]}}
    config = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "9router": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "9Router",
                "options": {"baseURL": base_url.rstrip("/") + "/v1", "apiKey": "{env:NINEROUTER_KEY}"},
                "models": provider_models,
            }
        },
        "model": f"9router/{active_model}" if active_model else "9router/free",
    }
    p = out_dir / "opencode.json"
    p.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    snippet = {"provider": {"9router": config["provider"]["9router"]}, "model": config["model"]}
    (out_dir / "opencode-snippet.json").write_text(json.dumps(snippet, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"opencode: {p} ({len(provider_models)} models, active {active_model}) — apiKey references {{env:NINEROUTER_KEY}}, set env manually")

def write_hermes(models, base_url, api_key, out_dir, active_model):
    # include all combos/models like opencode, referencing env var only
    base_url_v1 = base_url.rstrip("/") + "/v1"
    # Build providers block with all models for Desktop picker
    models_yaml = ""
    for m in models:
        mid = m.get("id")
        if not mid:
            continue
        # per-model context_length if available, else omitted
        models_yaml += f"      {mid}:\n        display_name: {mid}\n"
    yaml_block = f"""model:
  default: "{active_model}"
  provider: "custom"
  base_url: "{base_url_v1}"
  api_key: ${{OPENAI_API_KEY}}

# Provider inventory for Desktop picker — all {len(models)} models/combos from live /v1/models
providers:
  9router:
    name: 9Router
    base_url: "{base_url_v1}"
    api_key: ${{OPENAI_API_KEY}}
    transport: openai_chat
    models:
{models_yaml}"""
    (out_dir / "hermes-config.yaml").write_text(yaml_block, encoding="utf-8")
    # Do not write actual key — user adds manually. Reference is already in yaml via ${OPENAI_API_KEY}
    (out_dir / "hermes.env").write_text("# Add manually: OPENAI_API_KEY=sk-... (or NINEROUTER_KEY)\n# The yaml above references ${OPENAI_API_KEY}, set it in ~/.hermes/.env\n", encoding="utf-8")
    (out_dir / "hermes-README.txt").write_text(f"# Hermes - copy to ~/.hermes/config.yaml\n{yaml_block}\n# Hermes env - add to ~/.hermes/.env manually:\n# OPENAI_API_KEY=sk-...\n", encoding="utf-8")
    print(f"hermes: {out_dir/'hermes-config.yaml'} ({len(models)} models, default {active_model}) — api_key references ${{OPENAI_API_KEY}}")

def write_codex(base_url, api_key, out_dir, active_model):
    base_url_v1 = base_url.rstrip("/") + "/v1"
    # api_key is ignored — reference env var only
    toml = f"""# Codex - copy to ~/.codex/config.toml
# Set OPENAI_API_KEY or NINEROUTER_KEY in env / ~/.codex/auth.json manually
model = "{active_model}"
model_provider = "9router"

[model_providers.9router]
name = "9Router"
base_url = "{base_url_v1}"
wire_api = "responses"
http_headers = {{ Authorization = "Bearer ${{OPENAI_API_KEY}}" }}

[agents]
default_subagent_model = "{active_model}"
"""
    (out_dir / "codex-config.toml").write_text(toml, encoding="utf-8")
    print(f"codex: {out_dir/'codex-config.toml'} — api key references ${{OPENAI_API_KEY}}")

def write_claude(base_url, api_key, out_dir, active_model):
    base_url_v1 = base_url.rstrip("/") + "/v1"
    # reference env var, do not hardcode key
    settings = {"env": {"ANTHROPIC_BASE_URL": base_url_v1, "ANTHROPIC_AUTH_TOKEN": "${NINEROUTER_KEY}", "ANTHROPIC_MODEL": active_model}, "hasCompletedOnboarding": True}
    (out_dir / "claude-settings.json").write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "claude-env.sh").write_text(f"export ANTHROPIC_BASE_URL=\"{base_url_v1}\"\nexport ANTHROPIC_AUTH_TOKEN=\"${{NINEROUTER_KEY}}\"  # set NINEROUTER_KEY manually\n", encoding="utf-8")
    print(f"claude: {out_dir/'claude-settings.json'} — token references ${{NINEROUTER_KEY}}")

def write_generic(base_url, api_key, out_dir, active_model):
    base_url_v1 = base_url.rstrip("/") + "/v1"
    # only base_url, reference env var placeholder — do not hardcode key
    (out_dir / "generic-env.sh").write_text(f"# Generic OpenAI-compatible - source or copy (set keys manually)\nexport OPENAI_BASE_URL=\"{base_url_v1}\"\nexport OPENAI_API_KEY=\"${{OPENAI_API_KEY}}\"  # set manually: export OPENAI_API_KEY=sk-...\nexport NINEROUTER_URL=\"{base_url}\"\nexport NINEROUTER_KEY=\"${{NINEROUTER_KEY}}\"  # set manually\n# active model: {active_model}\n", encoding="utf-8")
    (out_dir / ".env.example").write_text(f"NINEROUTER_URL={base_url}\nNINEROUTER_KEY=${{NINEROUTER_KEY}}\nOPENAI_BASE_URL={base_url_v1}\nOPENAI_API_KEY=${{OPENAI_API_KEY}}\n# Set the above vars manually — do not commit real keys\n", encoding="utf-8")
    print(f"generic: {out_dir/'generic-env.sh'} — keys referenced as ${{OPENAI_API_KEY}}/${{NINEROUTER_KEY}}")

def write_readme(out_dir, base_url, models_count, active_model):
    readme = f"""# 9Router Generated Configs

Generated: from live {base_url}/v1/models ({models_count} models/combos) via generate-configs.py
Active model: {active_model}
Base URL: {base_url.rstrip("/")}/v1

## Files
- opencode.json - Full opencode config (~/.config/opencode/opencode.json). Contains all {models_count} models as 9router provider. Use model 9router/{active_model} or any id.
- opencode-snippet.json - Minimal snippet to merge into existing opencode.json
- hermes-config.yaml + hermes.env - Hermes (~/.hermes/config.yaml + .env)
- codex-config.toml - Codex (~/.codex/config.toml)
- claude-settings.json - Claude Code (~/.claude/settings.json env block)
- generic-env.sh / .env.example - Exports for any OpenAI-compatible CLI (cursor, cline, roo, continue, droid, copilot custom endpoint)

## Usage on remote servers
1. Copy NINEROUTER_URL and NINEROUTER_KEY to remote host env or secrets file.
2. Run on remote: `python generate-configs.py --url $NINEROUTER_URL --key $NINEROUTER_KEY` to refresh with live models.
3. Copy desired config to tool's config path (see file headers).

## Models included
All ids from GET /v1/models (including combos owned_by=combo: free, coding-pro, coding-med, coding-low, vision).
Check opencode.json -> provider.9router.models keys for full list, or GET {base_url.rstrip("/")}/v1/models

## Verification
curl -H "Authorization: Bearer $NINEROUTER_KEY" {base_url.rstrip("/")}/v1/models | jq '.data[].id'
curl {base_url.rstrip("/")}/api/health
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")

def main():
    parser = argparse.ArgumentParser(description="Generate 9Router configs from live /v1/models")
    parser.add_argument("--url", help="NINEROUTER_URL base without /v1")
    parser.add_argument("--key", help="NINEROUTER_KEY")
    parser.add_argument("--key-file", help="file containing NINEROUTER_KEY")
    parser.add_argument("--out", help="output dir")
    parser.add_argument("--active-model", default="free", help="active model/combo to set as default")
    args = parser.parse_args()

    url, key = args.url, args.key
    sec_url, sec_key = load_secrets()
    url = url or sec_url or os.environ.get("NINEROUTER_URL")
    key = key or sec_key or os.environ.get("NINEROUTER_KEY")
    if args.key_file:
        try:
            key = pathlib.Path(args.key_file).read_text(encoding="utf-8").strip()
        except Exception as e:
            print(f"error reading key file: {e}", file=sys.stderr)
            sys.exit(1)
    if not url:
        print("error: NINEROUTER_URL not found (arg --url, env, or secrets file)", file=sys.stderr)
        sys.exit(1)
    if not key:
        print("warning: NINEROUTER_KEY not found, generating with placeholder sk-...", file=sys.stderr)
        key = "sk-placeholder"

    base_url = url.strip().rstrip("/")
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]

    out_dir = pathlib.Path(args.out) if args.out else pathlib.Path(__file__).resolve().parents[1] / "generated" if (pathlib.Path(__file__).resolve().parents[1] / "generated").exists() or True else pathlib.Path("generated")
    # prefer executions/9router/generated when run from playbooks, else ./generated
    try:
        # if script is in playbooks/9router/scripts, generated should be executions/9router/generated
        if "playbooks" in str(pathlib.Path(__file__).resolve()):
            cand = pathlib.Path("D:/Data/git/sysops-playbooks/executions/9router/generated")
            if cand.exists() or True:
                out_dir = cand if not args.out else pathlib.Path(args.out)
        else:
            out_dir = pathlib.Path(args.out) if args.out else pathlib.Path("generated")
    except:
        out_dir = pathlib.Path(args.out) if args.out else pathlib.Path("generated")
    # final fallback
    if not args.out:
        # check executions variant
        if pathlib.Path("D:/Data/git/sysops-playbooks/executions/9router").exists():
            out_dir = pathlib.Path("D:/Data/git/sysops-playbooks/executions/9router/generated")
        else:
            out_dir = pathlib.Path("generated")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching {base_url}/v1/models ...")
    data = fetch_models(base_url, key if key != "sk-placeholder" else "sk-placeholder")
    models = data.get("data", []) if isinstance(data, dict) else []
    print(f"Got {len(models)} models (including {sum(1 for m in models if m.get('owned_by')=='combo')} combos)")

    active = args.active_model
    ids = [m.get("id") for m in models if m.get("id")]
    if active not in ids and ids:
        print(f"active model {active} not in list, using {ids[0]}", file=sys.stderr)
        active = ids[0]

    api_key = key

    write_opencode(models, base_url, api_key, out_dir, active)
    write_hermes(models, base_url, api_key, out_dir, active)
    write_codex(base_url, api_key, out_dir, active)
    write_claude(base_url, api_key, out_dir, active)
    write_generic(base_url, api_key, out_dir, active)
    write_readme(out_dir, base_url, len(models), active)
    print(f"Done -> {out_dir}")

if __name__ == "__main__":
    main()
