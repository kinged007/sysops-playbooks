#!/usr/bin/env python3
"""
model-inventory.py — Personal multi-provider model database
Fetches model lists from:
  - google (Generative Language / Gemini)
  - opencode zen (https://opencode.ai/zen/v1/models)
  - opencode go  (https://opencode.ai/zen/go/v1/models)
  - cloudflare (Workers AI)
  - ollama cloud
  - openrouter (free models only)
  - command code (generic OpenAI-compatible)

Produces:
  - Comprehensive spreadsheet: models.csv / models.json / models.xlsx
  - Per-run "added" list: added_YYYY-MM-DD.csv + .json  (only models new since last run)

100% programmatic: no LLM needed. Intelligence and cost are estimated via
config patterns + static maps + optional ArtificialAnalysis cache.

Usage:
  python playbooks/9router/scripts/model-inventory.py
  python playbooks/9router/scripts/model-inventory.py --config /path/to/config.yaml
  python playbooks/9router/scripts/model-inventory.py --output-dir ./out --dry-run
  python playbooks/9router/scripts/model-inventory.py --providers google,openrouter

Config:
  See playbooks/9router/templates/model-inventory.config.example.yaml
  Copy it to executions/9router/model-inventory.config.yaml for real keys (gitignored).

Automation (cron / systemd timer / GitHub Actions):
  0 6 * * * /usr/bin/python3 /opt/sysops-playbooks/playbooks/9router/scripts/model-inventory.py --config /opt/sysops-playbooks/executions/9router/model-inventory.config.yaml >> /var/log/model-inventory.log 2>&1
"""
from __future__ import annotations

import argparse
import csv
import datetime
from datetime import timezone
import fnmatch
import json
import os
import pathlib
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Optional deps
# ---------------------------------------------------------------------------
try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore

try:
    import requests  # type: ignore
except ImportError:
    requests = None  # type: ignore

# ---------------------------------------------------------------------------
# Constants / defaults
# ---------------------------------------------------------------------------
DEFAULT_CONFIG_CANDIDATES = [
    pathlib.Path("model-inventory.config.yaml"),
    pathlib.Path("playbooks/9router/scripts/model-inventory.config.yaml"),
    pathlib.Path("executions/9router/model-inventory.config.yaml"),
    pathlib.Path("D:/Data/git/sysops-playbooks/executions/9router/model-inventory.config.yaml"),
    pathlib.Path("playbooks/9router/templates/model-inventory.config.example.yaml"),
]

# Cost — no static fallback (AA/provider only). Keep empty to force blank when no provider pricing.
CF_PRICING: Dict[str, Dict[str, Optional[float]]] = {}

# ---------------------------------------------------------------------------
# Secrets / .env auto-load (AGENTS.md §1.5 + execution layout §2)
# ---------------------------------------------------------------------------
# Auto-loads keys from executions/<playbook>/secrets/ so the operator can keep
# API keys out of the shell history. Checked at startup before config expansion.
# Candidates (first existing wins per-file, but all are merged):
#   executions/9router/.env
#   executions/9router/secrets/.env
#   executions/9router/secrets/api_keys.env
#   executions/9router-<suffix>/.env and .../secrets/.env (if config lives there)
#   .env (repo root / CWD)
#   Plus per-key files executions/9router/secrets/<KEY>.txt (e.g. AA_API_KEY.txt)
DOTENV_CANDIDATES: List[pathlib.Path] = []

def _load_dotenv_file(path: pathlib.Path) -> int:
    if not path.exists() or not path.is_file():
        return 0
    loaded = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if not k or k in os.environ and os.environ[k]:
                # don't overwrite already-set env (explicit shell wins)
                continue
            if v:
                os.environ[k] = v
                loaded += 1
    except Exception as e:
        print(f"WARN: failed to load {path}: {e}", file=sys.stderr)
    if loaded:
        print(f"  env: loaded {loaded} keys from {path}", file=sys.stderr)
    return loaded

def _load_secret_files(secrets_dir: pathlib.Path) -> int:
    if not secrets_dir.exists():
        return 0
    loaded = 0
    # Common key filenames (upper + lower variants)
    for p in secrets_dir.glob("*.txt"):
        key = p.stem.upper().replace("-", "_")
        # only map known key patterns to env
        if key not in {"AA_API_KEY", "ARTIFICIAL_ANALYSIS_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "OPENCODE_ZEN_API_KEY", "OPENCODE_GO_API_KEY", "OPENCODE_API_KEY", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "OLLAMA_API_KEY", "OPENROUTER_API_KEY", "COMMAND_CODE_API_KEY", "CMC_API_KEY"}:
            # also allow generic uppercase txt files as env
            if not key.isupper():
                continue
        try:
            val = p.read_text(encoding="utf-8").strip().strip("\ufeff")
            if val and not os.environ.get(key):
                os.environ[key] = val
                loaded += 1
        except Exception:
            pass
    if loaded:
        print(f"  env: loaded {loaded} keys from secret files in {secrets_dir}", file=sys.stderr)
    return loaded

def load_execution_env(config_path: Optional[pathlib.Path] = None) -> None:
    candidates: List[pathlib.Path] = []
    # repo root detection: look for AGENTS.md or playbooks/
    cwd = pathlib.Path.cwd()
    repo_root = cwd
    # if config_path given, its dir and secrets subdir are candidates
    if config_path and config_path.exists():
        candidates.append(config_path.parent / ".env")
        candidates.append(config_path.parent / "secrets" / ".env")
        candidates.append(config_path.parent / "secrets" / "api_keys.env")
    # standard execution layouts
    for base in [pathlib.Path("executions/9router"), pathlib.Path("D:/Data/git/sysops-playbooks/executions/9router")]:
        candidates.append(base / ".env")
        candidates.append(base / "secrets" / ".env")
        candidates.append(base / "secrets" / "api_keys.env")
        candidates.append(base / ".env.example")  # not loaded, but hint
    # also suffix variants executions/9router-*
    try:
        for d in pathlib.Path("executions").glob("9router-*"):
            candidates.append(d / ".env")
            candidates.append(d / "secrets" / ".env")
    except Exception:
        pass
    # CWD and repo root
    candidates.append(cwd / ".env")
    candidates.append(pathlib.Path(".env"))
    # dedupe, keep order, load each if exists
    seen = set()
    for cand in candidates:
        try:
            r = cand.resolve()
        except Exception:
            r = cand
        if str(r) in seen or not cand.exists():
            continue
        seen.add(str(r))
        _load_dotenv_file(cand)
    # also load per-key .txt files from secrets/
    for base in [pathlib.Path("executions/9router/secrets"), pathlib.Path("D:/Data/git/sysops-playbooks/executions/9router/secrets")]:
        _load_secret_files(base)
    if config_path:
        # config's secrets dir as well
        _load_secret_files(config_path.parent / "secrets")

# ---------------------------------------------------------------------------
# Helpers: env expansion, YAML, HTTP
# ---------------------------------------------------------------------------
_ENV_RE = re.compile(r"\$\{([^}:]+)(?::-[^}]*)?\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def sanitize_key(value: Any) -> str:
    """Return '' if value is empty, placeholder, or contains unexpanded ${}."""
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if "${" in s:
        # unexpanded placeholder -> treat as empty (no real key)
        return ""
    return s


def expand_env(value: Any) -> Any:
    """Recursively expand ${VAR} and $VAR in strings using current env."""
    if isinstance(value, str):
        # Fast path: if string looks like a single ${VAR} and env missing, return ""
        # Also handle embedded placeholders.
        # First use expandvars (Windows: %VAR%, Unix: $VAR) then custom ${} handling
        expanded = os.path.expandvars(value)
        # Custom ${VAR} and ${VAR:-default} handling for cross-platform
        # Replace all ${...} occurrences
        def repl_all(s: str) -> str:
            # handle ${VAR:-default}
            m = re.search(r"\$\{([^}:]+):-([^}]*)\}", s)
            while m:
                var_name, default = m.group(1), m.group(2)
                val = os.environ.get(var_name, default)
                s = s[: m.start()] + val + s[m.end() :]
                m = re.search(r"\$\{([^}:]+):-([^}]*)\}", s)
            # handle plain ${VAR}
            m2 = re.search(r"\$\{([^}:]+)\}", s)
            while m2:
                var_name = m2.group(1)
                if var_name in os.environ:
                    val = os.environ[var_name]
                else:
                    val = ""  # treat missing as empty (personal DB: no key)
                s = s[: m2.start()] + val + s[m2.end() :]
                m2 = re.search(r"\$\{([^}:]+)\}", s)
            return s
        expanded = repl_all(expanded)
        # If after expansion still contains ${, something unexpanded -> treat as empty
        if "${" in expanded:
            # If the original value was purely a placeholder and env missing, we already replaced with ""
            # But if mixed string like "prefix-${VAR}-suffix" and VAR missing, expanded will have "prefix--suffix"
            # That's okay; keep it.
            if expanded.strip() == "":
                return ""
        # If original was only whitespace placeholder that got wiped, return ""
        if expanded.strip() == "" and "${" in value:
            return ""
        return expanded
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    return value


def load_yaml(path: pathlib.Path) -> Dict[str, Any]:
    if yaml is None:
        print(f"WARN: PyYAML not installed — cannot load {path}, trying JSON fallback", file=sys.stderr)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"ERR: failed to load {path}: {e}", file=sys.stderr)
            return {}
    try:
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        return data
    except Exception as e:
        print(f"ERR: yaml load {path}: {e}", file=sys.stderr)
        return {}


def find_config(cli_path: Optional[str]) -> Optional[pathlib.Path]:
    if cli_path:
        p = pathlib.Path(cli_path)
        if p.exists():
            return p
        print(f"ERR: --config {cli_path} not found", file=sys.stderr)
        sys.exit(2)
    # 1) Static candidates (fast path) — includes executions/9router/model-inventory.config.yaml
    for cand in DEFAULT_CONFIG_CANDIDATES:
        # Defer the committed example template until after glob search so execution customizations win
        if cand.name == "model-inventory.config.example.yaml":
            continue
        if cand.exists():
            return cand
    # 2) Glob search: any model-inventory*.yaml under any *9router* execution folder
    #    Matches executions/9router/model-inventory.config.yaml, executions/9router-*/**/model-inventory*.yaml, etc.
    #    This satisfies the operator request: search executions for *9router*/**/model-inventory*.yaml
    try:
        search_roots: List[pathlib.Path] = []
        # CWD-relative executions
        try:
            if pathlib.Path("executions").exists():
                search_roots.append(pathlib.Path("executions"))
        except Exception:
            pass
        # Repo-root relative (script at playbooks/9router/scripts/model-inventory.py -> repo root = parents[3])
        try:
            repo_root = pathlib.Path(__file__).resolve().parents[3]
            rr_exec = repo_root / "executions"
            if rr_exec.exists() and rr_exec not in search_roots:
                search_roots.append(rr_exec)
        except Exception:
            pass
        # Absolute fallback from defaults
        abs_exec = pathlib.Path("D:/Data/git/sysops-playbooks/executions")
        if abs_exec.exists() and abs_exec not in search_roots:
            search_roots.append(abs_exec)
        candidates: List[pathlib.Path] = []
        for root in search_roots:
            # Any folder matching *9router* at top level
            for nine_dir in root.glob("*9router*"):
                if not nine_dir.is_dir():
                    continue
                # recursive search for model-inventory*.yaml / .yml
                for pat in ("model-inventory*.yaml", "model-inventory*.yml", "model-inventory*.json"):
                    try:
                        candidates.extend([p for p in nine_dir.rglob(pat) if p.is_file()])
                    except Exception:
                        pass
            # Also direct rglob across root filtered by both strings (catches deeper nesting)
            for pat in ("model-inventory*.yaml", "model-inventory*.yml"):
                try:
                    for p in root.rglob(pat):
                        if p.is_file() and "9router" in str(p).lower() and p not in candidates:
                            candidates.append(p)
                except Exception:
                    pass
        if candidates:
            # Deterministic: shortest path first, then lexical (prefers executions/9router/model-inventory.config.yaml over deeper)
            candidates = sorted(set(candidates), key=lambda p: (len(str(p)), str(p).lower()))
            return candidates[0]
    except Exception as e:
        print(f"WARN: glob search for execution config failed: {e}", file=sys.stderr)
    # 3) Fallback to committed example template (read-only, no customizations)
    for cand in DEFAULT_CONFIG_CANDIDATES:
        if cand.exists():
            return cand
    return None


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def http_get(url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, str]] = None, timeout: int = 20) -> Tuple[int, Any]:
    """Return (status_code, json_or_text). Uses requests if available else urllib."""
    headers = headers or {}
    # attach params to url if needed for urllib fallback
    if params:
        from urllib.parse import urlencode
        sep = "&" if "?" in url else "?"
        url = url + sep + urlencode(params)
    if requests is not None:
        try:
            resp = requests.get(url, headers=headers, params=None if params is None else {}, timeout=timeout)
            # params already encoded above for consistency; if requests, let it handle but we already encoded, so don't double.
            # Actually for requests we should NOT have encoded params above; undo duplication.
            # Quick fix: if we used requests, we appended params manually, so clear params.
            ct = resp.headers.get("content-type", "")
            if "application/json" in ct or resp.text.strip().startswith("{") or resp.text.strip().startswith("["):
                try:
                    return resp.status_code, resp.json()
                except Exception:
                    return resp.status_code, resp.text
            return resp.status_code, resp.text
        except Exception as e:
            return 0, str(e)
    else:
        import urllib.request
        import urllib.error
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode("utf-8", errors="replace")
                code = r.status
                try:
                    return code, json.loads(body)
                except Exception:
                    return code, body
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")
                try:
                    return e.code, json.loads(body)
                except Exception:
                    return e.code, body
            except Exception as ex:
                return e.code, str(ex)
        except Exception as e:
            return 0, str(e)


# ---------------------------------------------------------------------------
# Intelligence & cost helpers
# ---------------------------------------------------------------------------
def is_free(model_id: str, cost_input: Optional[float], cost_output: Optional[float]) -> bool:
    low = model_id.lower()
    if "free" in low or "big-pickle" in low:
        return True
    if cost_input == 0 and cost_output == 0:
        return True
    # also if cost is 0.0 explicitly
    if cost_input == 0.0 and cost_output == 0.0:
        return True
    return False


def provider_assumes_free(provider: str, cfg: Dict[str, Any]) -> bool:
    """Provider-level free classification (replaces hardcoded provider logic)."""
    # Supports multiple aliases for flexibility; config uses `free: true` but also accepts free_tier/assume_free
    prov_cfg = cfg.get("providers", {}).get(provider, {}) or {}
    for key in ("free", "free_tier", "assume_free", "mark_all_free", "assumeFree", "freeTier"):
        val = prov_cfg.get(key)
        if isinstance(val, bool):
            if val:
                return True
        elif isinstance(val, str) and val.lower() in ("true", "1", "yes", "y"):
            return True
        elif isinstance(val, (int, float)) and val == 1:
            return True
    return False


def lookup_cost(model_id: str, cost_config: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """Return (input, output, notes) via substring match (case-insensitive) against overrides."""
    overrides: Dict[str, Any] = cost_config.get("overrides", {}) or {}
    low = model_id.lower()
    # direct CF pricing first
    if low in CF_PRICING:
        v = CF_PRICING[low]
        return v.get("input"), v.get("output"), "cloudflare_static"
    # also try without @cf prefix variance
    for key, val in overrides.items():
        if key.lower() == "default":
            continue
        if key.lower() in low:
            if isinstance(val, dict):
                return val.get("input"), val.get("output"), val.get("notes")
            # else maybe plain number
    # no match
    default = overrides.get("default")
    if isinstance(default, dict):
        return default.get("input"), default.get("output"), default.get("notes")
    return None, None, None


def estimate_intelligence(
    model_id: str,
    intel_config: Dict[str, Any],
    aa_cache: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[float], str]:
    low = model_id.lower()
    # 1. ArtificialAnalysis cache lookup (if enabled and cache present)
    if aa_cache and isinstance(aa_cache, dict):
        # Build candidate keys to try: full low, slug, provider-stripped, base model
        candidates: List[str] = []
        slug = re.sub(r"[^a-z0-9]+", "-", low).strip("-")
        candidates.extend([low, slug])
        # provider prefix stripping: e.g. "openrouter/z-ai/glm-5.2:free" -> "glm-5.2"
        # also "z-ai/glm-5.2:free" -> "glm-5.2"
        base = low.split("/")[-1].split(":")[0]  # last segment before colon
        base_slug = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
        candidates.extend([base, base_slug, base.replace("_", "-"), base_slug.replace("_", "-")])
        # also original without :free suffix
        no_free = low.replace(":free", "").replace("-free", "")
        candidates.append(re.sub(r"[^a-z0-9]+", "-", no_free).strip("-"))
        # dedupe preserving order
        seen = set()
        uniq_cands = []
        for c in candidates:
            if c and c not in seen:
                seen.add(c)
                uniq_cands.append(c)
        for cand in uniq_cands:
            if cand in aa_cache:
                v = aa_cache[cand]
                if isinstance(v, (int, float)):
                    return float(v), "artificial_analysis"
                if isinstance(v, dict) and "intelligence" in v:
                    try:
                        return float(v["intelligence"]), "artificial_analysis"
                    except Exception:
                        pass
            # also try with cost suffix not needed for intelligence
            # substring fallback: if AA slug is substring of candidate or vice versa
        # substring scan as last resort (e.g. "glm-5-2" in "z-ai-glm-5-2-free")
        for aa_key, v in aa_cache.items():
            if aa_key.endswith("__cost"):
                continue
            if not isinstance(v, (int, float)):
                continue
            ak = aa_key.lower()
            # if AA key appears inside model id slug or base
            if ak in slug or ak in base_slug or slug in ak or base_slug in ak:
                return float(v), "artificial_analysis"
            # also check base without version dash: glm-5.2 vs glm-5-2
            if ak.replace("-", "") == base_slug.replace("-", ""):
                return float(v), "artificial_analysis"
    # 2. Pattern matching
    patterns = intel_config.get("patterns") or []
    for entry in patterns:
        pat = entry.get("pattern", "")
        score = entry.get("score")
        if not pat:
            continue
        try:
            if re.search(pat, low):
                return float(score) if score is not None else None, "pattern"
        except re.error:
            # treat as glob fallback
            if fnmatch.fnmatch(low, pat.lower()):
                return float(score) if score is not None else None, "pattern"
    # 3. No heuristic fallback — AA only (scalable). Return unknown if not in AA.
    # 4. default_score
    default = intel_config.get("default_score")
    if default is not None:
        try:
            return float(default), "default"
        except Exception:
            return None, "unknown"
    return None, "unknown"


def get_aa_cost(model_id: str, aa_cache: Optional[Dict[str, Any]]) -> Optional[float]:
    if not aa_cache:
        return None
    low = model_id.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", low).strip("-")
    base = low.split("/")[-1].split(":")[0]
    base_slug = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    candidates = [
        f"{low}__cost", f"{slug}__cost", f"{base}__cost", f"{base_slug}__cost",
        f"{slug.replace('-', '_')}__cost", f"{base_slug.replace('-', '_')}__cost",
        f"{low.replace('_','-')}__cost", f"{base.replace('_','-')}__cost",
    ]
    for key in candidates:
        if key in aa_cache:
            try:
                return float(aa_cache[key])
            except Exception:
                pass
    # substring fallback
    for ak, v in aa_cache.items():
        if not ak.endswith("__cost"):
            continue
        base_key = ak[:-6]  # strip __cost
        if base_key in slug or base_key in base_slug or slug in base_key or base_slug in base_key:
            try:
                return float(v)
            except Exception:
                pass
    return None


def cost_per_task_estimate(cost_input: Optional[float], cost_output: Optional[float]) -> Optional[float]:
    """Rough costPerTask like ArtificialAnalysis: weighted avg. If both present, simple mean scaled."""
    if cost_input is None and cost_output is None:
        return None
    # Use formula similar to free.json: costPerTask not directly derivable from per-1M alone,
    # but we approximate as (input*0.5 + output*0.5) / 10 for task scaling.
    # The point is to have a sortable cheaper-first metric; exact value not critical.
    if cost_input is not None and cost_output is not None:
        return round((cost_input * 0.6 + cost_output * 0.4) * 0.1, 6)
    if cost_input is not None:
        return round(cost_input * 0.06, 6)
    if cost_output is not None:
        return round(cost_output * 0.04, 6)
    return None


def matches_any(patterns: List[str], text: str) -> bool:
    low = text.lower()
    for pat in patterns:
        pat_low = pat.lower()
        # fnmatch is case-sensitive on windows? force lower
        if fnmatch.fnmatch(low, pat_low):
            return True
        # also substring fallback
        if pat_low in low:
            return True
        # regex attempt if pattern contains regex chars and fnmatch didn't match
        try:
            if re.search(pat, text, re.IGNORECASE):
                return True
        except re.error:
            pass
    return False


def apply_model_overrides(models: List[Dict[str, Any]], cfg: Dict[str, Any]) -> int:
    """Apply per-model field overrides.

    Config shape (any of):
      overrides:
        - pattern: "muse-spark-.*-contributor"   # regex or glob (fnmatch, case-insensitive)
          providers: ["opencode_go", "command_code"]  # optional filter; alias commandcode -> command_code
          cost_per_task: 0.2   # alias price_per_task also accepted
          intelligence: 48.5   # any field is overrideable (free, supports_vision, etc.)
      # per-provider shorthand also supported:
      providers:
        opencode_go:
          overrides:
            - pattern: "muse-spark-.*-contributor"
              cost_per_task: 0.2
    Later rules win. Matching uses fnmatch + regex via matches_any (case-insensitive).
    Returns number of model/rule matches applied.
    """
    raw_overrides: List[Dict[str, Any]] = []
    top = cfg.get("overrides") or cfg.get("model_overrides") or []
    if isinstance(top, dict):
        for k, v in top.items():
            if isinstance(v, dict):
                raw_overrides.append({"pattern": k, **v})
            elif v is not None:
                raw_overrides.append({"pattern": k, "cost_per_task": v})
    elif isinstance(top, list):
        raw_overrides.extend([o for o in top if isinstance(o, dict)])
    provs = cfg.get("providers") or {}
    if isinstance(provs, dict):
        for prov_key, pc in provs.items():
            if not isinstance(pc, dict):
                continue
            por = pc.get("overrides") or pc.get("model_overrides")
            if not por:
                continue
            if isinstance(por, dict):
                for k, v in por.items():
                    if isinstance(v, dict):
                        d = {"pattern": k, **v}
                    elif v is not None:
                        d = {"pattern": k, "cost_per_task": v}
                    else:
                        continue
                    if "providers" not in d and "provider" not in d:
                        d["providers"] = [prov_key]
                    raw_overrides.append(d)
            elif isinstance(por, list):
                for o in por:
                    if not isinstance(o, dict):
                        continue
                    d = dict(o)
                    if "providers" not in d and "provider" not in d:
                        d["providers"] = [prov_key]
                    raw_overrides.append(d)
    if not raw_overrides:
        return 0
    applied = 0
    for m in models:
        mid = m.get("model_id") or ""
        prov = m.get("provider") or ""
        prov_norm = prov.lower().replace("-", "_")
        if prov_norm == "commandcode":
            prov_norm = "command_code"
        for ov in raw_overrides:
            pat = ov.get("pattern") or ov.get("match") or ov.get("regex") or ov.get("model_pattern") or ""
            if not pat:
                continue
            allowed = ov.get("providers") or ov.get("provider") or ov.get("providers_whitelist")
            if allowed is not None:
                if isinstance(allowed, str):
                    allowed = [allowed]
                norm_allowed: List[str] = []
                for a in allowed:  # type: ignore
                    an = str(a).lower().replace("-", "_")
                    if an == "commandcode":
                        an = "command_code"
                    if an in ("opencode_go", "opencode-go"):
                        an = "opencode_go"
                    norm_allowed.append(an)
                if prov_norm not in norm_allowed:
                    continue
            if not matches_any([pat], mid):
                continue
            for k, v in ov.items():
                if k in ("pattern", "match", "regex", "model_pattern", "providers", "provider", "providers_whitelist"):
                    continue
                k2 = k
                if k in ("price_per_task", "pricePerTask", "price", "cost"):
                    k2 = "cost_per_task"
                if isinstance(v, str) and k2 in ("free", "supports_vision", "supports_image_generation"):
                    lv = v.lower()
                    if lv in ("true", "1", "yes", "y"):
                        v = True
                    elif lv in ("false", "0", "no", "n"):
                        v = False
                m[k2] = v  # type: ignore
                if k2 == "intelligence" and v is not None and "intelligence_source" not in ov:
                    m["intelligence_source"] = "override"
                if k2 == "cost_per_task":
                    notes = (m.get("cost_notes") or "").strip()
                    if "override" not in notes:
                        m["cost_notes"] = (notes + " override").strip() if notes else "override"
                    try:
                        m["cost_per_task"] = float(v) if v is not None else None  # type: ignore
                    except Exception:
                        pass
            applied += 1
    if applied:
        print(f"  overrides: applied {applied} matches from {len(raw_overrides)} rule(s)")
    return applied


# ---------------------------------------------------------------------------
# Provider fetchers
# Each returns List[Dict] with normalized fields
# ---------------------------------------------------------------------------
def fetch_google(cfg: Dict[str, Any], timeout: int = 20) -> List[Dict[str, Any]]:
    ep = cfg.get("endpoints", {}).get("google", "https://generativelanguage.googleapis.com/v1beta/models")
    keys_cfg = cfg.get("api_keys", {}) or {}
    # try multiple env fallbacks
    api_key = sanitize_key(keys_cfg.get("google") or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY") or "")
    require_key = cfg.get("providers", {}).get("google", {}).get("require_key", False)
    if require_key and not api_key:
        print("WARN: google require_key=true but no API key — skipping", file=sys.stderr)
        return []
    # pagination
    page_size = cfg.get("providers", {}).get("google", {}).get("page_size", 100)
    models: List[Dict[str, Any]] = []
    next_token: Optional[str] = None
    headers: Dict[str, str] = {}
    if api_key:
        headers["x-goog-api-key"] = api_key
    url = ep
    params_base: Dict[str, str] = {"pageSize": str(page_size)}
    if api_key:
        params_base["key"] = api_key  # also as query param
    tries = 0
    while tries < 10:
        tries += 1
        params = dict(params_base)
        if next_token:
            params["pageToken"] = next_token
        code, body = http_get(url, headers=headers, params=params, timeout=timeout)
        if code == 401 or code == 403:
            print(f"WARN: google /models HTTP {code} — check GOOGLE_API_KEY; body={str(body)[:400]}", file=sys.stderr)
            if not models:
                return []
            break
        if code == 0:
            print(f"WARN: google fetch failed: {body}", file=sys.stderr)
            return models
        if code != 200:
            print(f"WARN: google HTTP {code}: {str(body)[:800]}", file=sys.stderr)
            return models
        items = []
        if isinstance(body, dict):
            items = body.get("models") or body.get("data") or []
            next_token = body.get("nextPageToken")
        else:
            print(f"WARN: google unexpected body type: {type(body)}", file=sys.stderr)
            break
        for m in items:
            # m shape: {"name":"models/gemini-3-pro-preview","baseModelId":"gemini-3-pro",...}
            raw_name = m.get("name") or m.get("id") or m.get("baseModelId") or ""
            # strip "models/" prefix
            if raw_name.startswith("models/"):
                raw_name = raw_name[len("models/") :]
            display = m.get("displayName") or m.get("display_name") or raw_name
            # only keep generateContent-capable
            supported = m.get("supportedGenerationMethods") or m.get("supported_generation_methods") or []
            if supported and "generateContent" not in supported and "generate_content" not in [s.lower() for s in supported]:
                # still include but mark as non-chat? we include all; filter later if needed
                pass
            input_limit = m.get("inputTokenLimit") or m.get("input_token_limit")
            output_limit = m.get("outputTokenLimit") or m.get("output_token_limit")
            # cost / intelligence via helpers
            cost_i, cost_o, cost_notes = lookup_cost(raw_name, cfg.get("cost", {}))
            intel, intel_src = estimate_intelligence(raw_name, cfg.get("intelligence", {}), cfg.get("_aa_cache"))
            free_flag = is_free(raw_name, cost_i, cost_o) or provider_assumes_free("google", cfg)
            _cpt = cost_per_task_estimate(cost_i, cost_o)
            _aa_cpt = get_aa_cost(raw_name, cfg.get("_aa_cache"))
            if _aa_cpt is not None:
                _cpt = _aa_cpt
                cost_notes = (cost_notes + " aa_cost") if cost_notes else "aa_cost"
            # cloudflare-style owned_by not present; use google
            models.append({
                "provider": "google",
                "model_id": raw_name,
                "display_name": display,
                "owned_by": m.get("owned_by") or "google",
                "context_window": input_limit,
                "max_output": output_limit,
                "cost_input_per_1M": cost_i,
                "cost_output_per_1M": cost_o,
                "cost_per_task": _cpt,
                "cost_notes": cost_notes,
                "intelligence": intel,
                "intelligence_source": intel_src,
                "free": free_flag,
                "raw": m,
            })
        if not next_token:
            break
    print(f"  google: fetched {len(models)} models")
    return models


def fetch_opencode(provider_key: str, cfg: Dict[str, Any], timeout: int = 20) -> List[Dict[str, Any]]:
    """
    provider_key: opencode_zen or opencode_go
    """
    ep_map = cfg.get("endpoints", {}) or {}
    endpoint = ep_map.get(provider_key, f"https://opencode.ai/zen/v1/models" if provider_key == "opencode_zen" else "https://opencode.ai/zen/go/v1/models")
    keys_cfg = cfg.get("api_keys", {}) or {}
    api_key = sanitize_key(keys_cfg.get(provider_key) or "")
    if not api_key:
        # fallback to generic OPENCODE_API_KEY
        api_key = sanitize_key(os.environ.get("OPENCODE_API_KEY") or os.environ.get("OPENCODE_ZEN_API_KEY") or os.environ.get("ZEN_API_KEY") or "")
        if provider_key == "opencode_go":
            api_key = sanitize_key(keys_cfg.get("opencode_go") or os.environ.get("OPENCODE_GO_API_KEY") or api_key)
    # final sanitize in case env contained placeholder
    api_key = sanitize_key(api_key)
    headers: Dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["x-api-key"] = api_key
    print(f"  {provider_key}: GET {endpoint} {'(with key)' if api_key else '(no key)'}")
    code, body = http_get(endpoint, headers=headers, timeout=timeout)
    if code == 401 or code == 403:
        print(f"WARN: {provider_key} HTTP {code} — check API key; body={str(body)[:400]}", file=sys.stderr)
        # retry without key once if we sent one and it failed (public list may work)
        if api_key:
            print(f"  {provider_key}: retrying without key ...")
            code, body = http_get(endpoint, headers={}, timeout=timeout)
            if code != 200:
                print(f"WARN: {provider_key} retry HTTP {code}: {str(body)[:400]}", file=sys.stderr)
                return []
        else:
            return []
    if code == 0:
        print(f"WARN: {provider_key} fetch error: {body}", file=sys.stderr)
        return []
    if code != 200:
        print(f"WARN: {provider_key} HTTP {code}: {str(body)[:800]}", file=sys.stderr)
        return []
    # body may be {"object":"list","data":[...]} or {"models":[...]} or list directly
    data_list: List[Dict[str, Any]] = []
    if isinstance(body, dict):
        if "data" in body and isinstance(body["data"], list):
            data_list = body["data"]
        elif "models" in body and isinstance(body["models"], list):
            data_list = body["models"]
        elif "object" in body and "data" in body:
            data_list = body["data"]
        else:
            # maybe dict keyed by id -> values
            # check models.dev shape: {"opencode":{"models":{...}}}
            if "opencode" in body and isinstance(body["opencode"], dict):
                # fallback not expected here but handle
                pass
            print(f"WARN: {provider_key} unexpected dict keys: {list(body.keys())[:10]}", file=sys.stderr)
            # try to treat body as single model?
            data_list = []
    elif isinstance(body, list):
        data_list = body
    else:
        print(f"WARN: {provider_key} unexpected body type {type(body)}", file=sys.stderr)
        return []

    out: List[Dict[str, Any]] = []
    for m in data_list:
        if not isinstance(m, dict):
            continue
        raw_id = m.get("id") or m.get("name") or m.get("model") or ""
        if not raw_id:
            continue
        display = m.get("display_name") or m.get("displayName") or m.get("name") or raw_id
        ctx = m.get("context_length") or m.get("contextWindow") or m.get("context_window") or m.get("inputTokenLimit")
        # capabilities
        owned = m.get("owned_by") or provider_key
        cost_i, cost_o, cost_notes = lookup_cost(raw_id, cfg.get("cost", {}))
        # try extract pricing if present
        pricing = m.get("pricing") or {}
        if isinstance(pricing, dict) and pricing:
            try:
                pi = pricing.get("input") or pricing.get("prompt") or pricing.get("input_cost")
                po = pricing.get("output") or pricing.get("completion") or pricing.get("output_cost")
                if pi is not None:
                    cost_i = float(pi) * 1_000_000 if float(pi) < 1 else float(pi)
                if po is not None:
                    cost_o = float(po) * 1_000_000 if float(po) < 1 else float(po)
                if pi is not None or po is not None:
                    cost_notes = "provider_pricing"
            except Exception:
                pass
        intel, intel_src = estimate_intelligence(raw_id, cfg.get("intelligence", {}), cfg.get("_aa_cache"))
        free_flag = is_free(raw_id, cost_i, cost_o) or provider_assumes_free(provider_key, cfg)
        free_only_cfg = ((cfg.get("providers", {}) or {}).get(provider_key, {}) or {})
        free_only = free_only_cfg.get("free_only", False) if isinstance(free_only_cfg, dict) else False
        if free_only and not free_flag:
            continue
        _cpt = cost_per_task_estimate(cost_i, cost_o)
        _aa_cpt = get_aa_cost(raw_id, cfg.get("_aa_cache"))
        if _aa_cpt is not None:
            _cpt = _aa_cpt
            cost_notes = (cost_notes + " aa_cost") if cost_notes else "aa_cost"
        out.append({
            "provider": provider_key,
            "model_id": raw_id,
            "display_name": display,
            "owned_by": owned,
            "context_window": ctx,
            "cost_input_per_1M": cost_i,
            "cost_output_per_1M": cost_o,
            "cost_per_task": _cpt,
            "cost_notes": cost_notes,
            "intelligence": intel,
            "intelligence_source": intel_src,
            "free": free_flag,
            "raw": m,
        })
    suffix2 = " free_only" if free_only else ""
    print(f"  {provider_key}: fetched {len(out)} models" + (f" (of {len(data_list)} total —{suffix2})" if suffix2 else ""))
    return out


def fetch_cloudflare(cfg: Dict[str, Any], timeout: int = 20) -> List[Dict[str, Any]]:
    endpoints = cfg.get("endpoints", {}) or {}
    ep_template = endpoints.get("cloudflare", "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/models/search")
    ep_fallback = endpoints.get("cloudflare_fallback", "https://api.cloudflare.com/client/v4/ai/models")
    keys = cfg.get("api_keys", {}) or {}
    cf_keys = keys.get("cloudflare") or {}
    if isinstance(cf_keys, str):
        # if someone set cloudflare: "token" string
        cf_keys = {"api_token": cf_keys}
    api_token = sanitize_key(cf_keys.get("api_token") or os.environ.get("CLOUDFLARE_API_TOKEN") or "")
    account_id = sanitize_key(cf_keys.get("account_id") or os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "")

    # If no credentials at all, skip gracefully - Workers AI catalogue requires auth
    if not api_token and not account_id:
        require = cfg.get("providers", {}).get("cloudflare", {}).get("require_key", False)
        if not require:
            print("  cloudflare: no token/account_id and require_key=false — skipping (set CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID to enable)", file=sys.stderr)
            return []
        # if require_key true, fall through to attempt and warn

    headers: Dict[str, str] = {}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    url = ep_template
    if "{account_id}" in url:
        if account_id:
            url = url.replace("{account_id}", account_id)
        else:
            print("WARN: cloudflare account_id missing — trying fallback endpoint without substitution", file=sys.stderr)
            url = ep_fallback

    print(f"  cloudflare: GET {url} {'(with token)' if api_token else '(no token)'}")
    code, body = http_get(url, headers=headers, timeout=timeout)
    # if 401 and we have no token, try again without auth to public catalogue
    if code in (401, 403) and not api_token:
        print("WARN: cloudflare requires token for model list — skipping (set CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID). Trying public fallback ...", file=sys.stderr)
        code, body = http_get(ep_fallback, headers={}, timeout=timeout)
    if code == 0:
        print(f"WARN: cloudflare fetch error: {body}", file=sys.stderr)
        return []
    if code != 200:
        # try fallback once
        if url != ep_fallback:
            print(f"WARN: cloudflare HTTP {code}, trying fallback {ep_fallback}", file=sys.stderr)
            code2, body2 = http_get(ep_fallback, headers=headers, timeout=timeout)
            if code2 == 200:
                code, body = code2, body2
            else:
                print(f"WARN: cloudflare fallback HTTP {code2}: {str(body2)[:600]}", file=sys.stderr)
                return []
        else:
            print(f"WARN: cloudflare HTTP {code}: {str(body)[:800]}", file=sys.stderr)
            return []

    # body shape: {"success":true,"result":[{"id":"@cf/...", ...}], "errors":[]} or direct list
    result_list: List[Dict[str, Any]] = []
    if isinstance(body, dict):
        if "result" in body and isinstance(body["result"], list):
            result_list = body["result"]
        elif "data" in body and isinstance(body["data"], list):
            result_list = body["data"]
        elif "models" in body and isinstance(body["models"], list):
            result_list = body["models"]
        else:
            # maybe result is dict of models?
            res = body.get("result")
            if isinstance(res, dict) and "models" in res:
                result_list = res["models"]
            else:
                print(f"WARN: cloudflare unexpected body keys: {list(body.keys())[:10]}", file=sys.stderr)
                return []
    elif isinstance(body, list):
        result_list = body

    out: List[Dict[str, Any]] = []
    for m in result_list:
        if not isinstance(m, dict):
            continue
        # Cloudflare returns UUID in "id" and human name in "name" (@cf/...). Per operator request, use display_name for both.
        display = m.get("name") or m.get("display_name") or m.get("id") or m.get("model") or ""
        if not display:
            continue
        raw_id = display  # model_id == display_name for cloudflare (e.g. @cf/google/gemma-2b-it-lora)
        # context window may be absent
        ctx = m.get("context_length") or m.get("contextWindow") or m.get("context_window")
        # pricing from static CF map overrides lookup_cost already
        cost_i, cost_o, cost_notes = lookup_cost(raw_id, cfg.get("cost", {}))
        # If CF map missed, estimate 0 for free tier models?
        # Keep None if not found.
        intel, intel_src = estimate_intelligence(raw_id, cfg.get("intelligence", {}), cfg.get("_aa_cache"))
        free_flag = is_free(raw_id, cost_i, cost_o) or provider_assumes_free("cloudflare", cfg)
        _cpt = cost_per_task_estimate(cost_i, cost_o)
        _aa_cpt = get_aa_cost(raw_id, cfg.get("_aa_cache"))
        if _aa_cpt is not None:
            _cpt = _aa_cpt
            cost_notes = (cost_notes + " aa_cost") if cost_notes else "aa_cost"
        # Cloudflare free tier is now provider-config driven (providers.cloudflare.free), not hardcoded
        out.append({
            "provider": "cloudflare",
            "model_id": raw_id,
            "display_name": display,
            "owned_by": m.get("owned_by") or "cloudflare",
            "context_window": ctx,
            "cost_input_per_1M": cost_i,
            "cost_output_per_1M": cost_o,
            "cost_per_task": _cpt,
            "cost_notes": cost_notes or "cloudflare",
            "intelligence": intel,
            "intelligence_source": intel_src,
            "free": free_flag,
            "raw": m,
        })
    print(f"  cloudflare: fetched {len(out)} models")
    return out


def fetch_ollama_cloud(cfg: Dict[str, Any], timeout: int = 20) -> List[Dict[str, Any]]:
    endpoints = cfg.get("endpoints", {}) or {}
    primary = endpoints.get("ollama_cloud", "https://ollama.com/api/tags")
    fallback = endpoints.get("ollama_cloud_fallback", "https://api.ollama.ai/v1/models")
    keys = cfg.get("api_keys", {}) or {}
    api_key = sanitize_key(keys.get("ollama_cloud") or os.environ.get("OLLAMA_API_KEY") or os.environ.get("OLLAMA_CLOUD_API_KEY") or "")
    headers: Dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    out: List[Dict[str, Any]] = []

    # try primary
    print(f"  ollama_cloud: GET {primary} {'(with key)' if api_key else '(no key)'}")
    code, body = http_get(primary, headers=headers, timeout=timeout)
    if code == 200 and isinstance(body, dict):
        # shapes: {"models":[{"name":"gpt-oss:20b",...}]} or {"data":[...]}
        lst = body.get("models") or body.get("data") or body.get("tags") or []
        if isinstance(lst, list) and lst:
            for m in lst:
                if not isinstance(m, dict):
                    continue
                raw_id = m.get("name") or m.get("id") or m.get("model") or ""
                if not raw_id:
                    continue
                display = m.get("name") or raw_id
                ctx = m.get("context_length") or m.get("context_window")
                cost_i, cost_o, cost_notes = lookup_cost(raw_id, cfg.get("cost", {}))
                intel, intel_src = estimate_intelligence(raw_id, cfg.get("intelligence", {}), cfg.get("_aa_cache"))
                free_flag = is_free(raw_id, cost_i, cost_o) or provider_assumes_free("ollama_cloud", cfg)
                _cpt = cost_per_task_estimate(cost_i, cost_o)
                _aa_cpt = get_aa_cost(raw_id, cfg.get("_aa_cache"))
                if _aa_cpt is not None:
                    _cpt = _aa_cpt
                    cost_notes = (cost_notes + " aa_cost") if cost_notes else "aa_cost"
                out.append({
                    "provider": "ollama_cloud",
                    "model_id": raw_id,
                    "display_name": display,
                    "owned_by": m.get("owned_by") or "ollama",
                    "context_window": ctx,
                    "cost_input_per_1M": cost_i,
                    "cost_output_per_1M": cost_o,
                    "cost_per_task": _cpt,
                    "cost_notes": cost_notes,
                    "intelligence": intel,
                    "intelligence_source": intel_src,
                    "free": free_flag,
                    "raw": m,
                })
            print(f"  ollama_cloud: fetched {len(out)} models from primary")
            if out:
                return out
    # try fallback
    if not out:
        print(f"  ollama_cloud: trying fallback {fallback}")
        code2, body2 = http_get(fallback, headers=headers, timeout=timeout)
        if code2 == 200:
            lst2: List[Dict[str, Any]] = []
            if isinstance(body2, dict):
                lst2 = body2.get("data") or body2.get("models") or []
            elif isinstance(body2, list):
                lst2 = body2
            for m in lst2:
                if not isinstance(m, dict):
                    continue
                raw_id = m.get("id") or m.get("name") or ""
                if not raw_id:
                    continue
                display = m.get("name") or raw_id
                ctx = m.get("context_length")
                cost_i, cost_o, cost_notes = lookup_cost(raw_id, cfg.get("cost", {}))
                intel, intel_src = estimate_intelligence(raw_id, cfg.get("intelligence", {}), cfg.get("_aa_cache"))
                free_flag = is_free(raw_id, cost_i, cost_o) or provider_assumes_free("ollama_cloud", cfg)
                _cpt = cost_per_task_estimate(cost_i, cost_o)
                _aa_cpt = get_aa_cost(raw_id, cfg.get("_aa_cache"))
                if _aa_cpt is not None:
                    _cpt = _aa_cpt
                    cost_notes = (cost_notes + " aa_cost") if cost_notes else "aa_cost"
                out.append({
                    "provider": "ollama_cloud",
                    "model_id": raw_id,
                    "display_name": display,
                    "owned_by": m.get("owned_by") or "ollama",
                    "context_window": ctx,
                    "cost_input_per_1M": cost_i,
                    "cost_output_per_1M": cost_o,
                    "cost_per_task": _cpt,
                    "cost_notes": cost_notes,
                    "intelligence": intel,
                    "intelligence_source": intel_src,
                    "free": free_flag,
                    "raw": m,
                })
            print(f"  ollama_cloud: fetched {len(out)} models from fallback")
    if not out and code not in (200,):
        print(f"WARN: ollama_cloud HTTP {code}: {str(body)[:600]}", file=sys.stderr)
    return out


def fetch_openrouter(cfg: Dict[str, Any], timeout: int = 20) -> List[Dict[str, Any]]:
    endpoint = cfg.get("endpoints", {}).get("openrouter", "https://openrouter.ai/api/v1/models")
    keys = cfg.get("api_keys", {}) or {}
    api_key = sanitize_key(keys.get("openrouter") or os.environ.get("OPENROUTER_API_KEY") or "")
    headers: Dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    print(f"  openrouter: GET {endpoint} {'(with key)' if api_key else '(no key, public)'}")
    code, body = http_get(endpoint, headers=headers, timeout=timeout)
    if code == 0:
        print(f"WARN: openrouter fetch error: {body}", file=sys.stderr)
        return []
    if code != 200:
        print(f"WARN: openrouter HTTP {code}: {str(body)[:800]}", file=sys.stderr)
        return []
    data_list: List[Dict[str, Any]] = []
    if isinstance(body, dict):
        data_list = body.get("data") or body.get("models") or []
    elif isinstance(body, list):
        data_list = body
    out: List[Dict[str, Any]] = []
    free_only = cfg.get("providers", {}).get("openrouter", {}).get("free_only", True)
    for m in data_list:
        if not isinstance(m, dict):
            continue
        raw_id = m.get("id") or m.get("name") or ""
        if not raw_id:
            continue
        display = m.get("name") or raw_id
        ctx = m.get("context_length") or m.get("contextWindow") or m.get("top_provider", {}).get("context_length")
        pricing = m.get("pricing") or {}
        cost_i: Optional[float] = None
        cost_o: Optional[float] = None
        if isinstance(pricing, dict):
            try:
                # pricing.prompt/completion are strings per token like "0.00000014"
                pi = pricing.get("prompt")
                po = pricing.get("completion")
                if pi is not None:
                    cost_i = float(pi) * 1_000_000
                if po is not None:
                    cost_o = float(po) * 1_000_000
                # also check request/completion?
            except Exception:
                pass
        # fallback to cost overrides if still None
        if cost_i is None and cost_o is None:
            ci2, co2, _ = lookup_cost(raw_id, cfg.get("cost", {}))
            cost_i, cost_o = ci2, co2
        intel, intel_src = estimate_intelligence(raw_id, cfg.get("intelligence", {}), cfg.get("_aa_cache"))
        # pricing may have zero
        free_flag = is_free(raw_id, cost_i, cost_o) or provider_assumes_free("openrouter", cfg)
        _cpt = cost_per_task_estimate(cost_i, cost_o)
        _aa_cpt = get_aa_cost(raw_id, cfg.get("_aa_cache"))
        _cost_notes = "openrouter_pricing" if pricing else None
        if _aa_cpt is not None:
            _cpt = _aa_cpt
            _cost_notes = (_cost_notes + " aa_cost") if _cost_notes else "aa_cost"
        # free_only filter: defer to post step but we can apply now to reduce size
        if free_only and not free_flag:
            continue
        out.append({
            "provider": "openrouter",
            "model_id": raw_id,
            "display_name": display,
            "owned_by": m.get("owned_by") or "openrouter",
            "context_window": ctx,
            "cost_input_per_1M": cost_i,
            "cost_output_per_1M": cost_o,
            "cost_per_task": _cpt,
            "cost_notes": _cost_notes,
            "intelligence": intel,
            "intelligence_source": intel_src,
            "free": free_flag,
            "raw": m,
        })
    print(f"  openrouter: fetched {len(out)} free models (of {len(data_list)} total{' — free_only' if free_only else ''})")
    return out


def fetch_command_code(cfg: Dict[str, Any], timeout: int = 20) -> List[Dict[str, Any]]:
    # CommandCode is an upstream provider, NOT router.munyard.biz (the router is
    # where collected models get stored, never a collection source). No default
    # URL on purpose: operator must set endpoints.command_code explicitly.
    endpoint = (cfg.get("endpoints", {}) or {}).get("command_code") or ""
    if not endpoint:
        print("  command_code: SKIP — endpoints.command_code not set (refusing to fall back to router.munyard.biz)")
        return []
    keys = cfg.get("api_keys", {}) or {}
    # CommandCode keys only — never fall back to router (NINEROUTER/9ROUTER) keys.
    api_key = sanitize_key(
        keys.get("command_code")
        or os.environ.get("COMMAND_CODE_API_KEY")
        or os.environ.get("CMC_API_KEY")
        or ""
    )
    headers: Dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    print(f"  command_code: GET {endpoint} {'(with key)' if api_key else '(no key)'}")
    code, body = http_get(endpoint, headers=headers, timeout=timeout)
    if code == 0:
        print(f"WARN: command_code fetch error: {body} — check endpoints.command_code in config", file=sys.stderr)
        return []
    if code == 401 or code == 403:
        print(f"WARN: command_code HTTP {code} — check COMMAND_CODE_API_KEY/CMC_API_KEY; body={str(body)[:400]}", file=sys.stderr)
        return []
    if code == 404:
        print(f"WARN: command_code HTTP 404 — endpoint not found ({endpoint}); update config endpoints.command_code", file=sys.stderr)
        return []
    if code != 200:
        print(f"WARN: command_code HTTP {code}: {str(body)[:800]}", file=sys.stderr)
        return []
    data_list: List[Dict[str, Any]] = []
    if isinstance(body, dict):
        data_list = body.get("data") or body.get("models") or body.get("result") or []
        if not data_list and "object" in body and "data" in body:
            data_list = body["data"]
    elif isinstance(body, list):
        data_list = body
    out: List[Dict[str, Any]] = []
    for m in data_list:
        if not isinstance(m, dict):
            continue
        raw_id = m.get("id") or m.get("name") or m.get("model") or ""
        if not raw_id:
            continue
        display = m.get("name") or m.get("display_name") or raw_id
        ctx = m.get("context_length") or m.get("context_window") or m.get("contextWindow")
        pricing = m.get("pricing") or {}
        cost_i, cost_o, cost_notes = lookup_cost(raw_id, cfg.get("cost", {}))
        if isinstance(pricing, dict) and pricing:
            try:
                pi = pricing.get("prompt") or pricing.get("input") or pricing.get("input_cost")
                po = pricing.get("completion") or pricing.get("output") or pricing.get("output_cost")
                if pi is not None:
                    cost_i = float(pi) * 1_000_000 if float(pi) < 1 else float(pi)
                if po is not None:
                    cost_o = float(po) * 1_000_000 if float(po) < 1 else float(po)
                cost_notes = "provider_pricing"
            except Exception:
                pass
        intel, intel_src = estimate_intelligence(raw_id, cfg.get("intelligence", {}), cfg.get("_aa_cache"))
        free_flag = is_free(raw_id, cost_i, cost_o) or provider_assumes_free("command_code", cfg)
        _cpt = cost_per_task_estimate(cost_i, cost_o)
        _aa_cpt = get_aa_cost(raw_id, cfg.get("_aa_cache"))
        if _aa_cpt is not None:
            _cpt = _aa_cpt
            cost_notes = (cost_notes + " aa_cost") if cost_notes else "aa_cost"
        out.append({
            "provider": "command_code",
            "model_id": raw_id,
            "display_name": display,
            "owned_by": m.get("owned_by") or "command_code",
            "context_window": ctx,
            "cost_input_per_1M": cost_i,
            "cost_output_per_1M": cost_o,
            "cost_per_task": _cpt,
            "cost_notes": cost_notes,
            "intelligence": intel,
            "intelligence_source": intel_src,
            "free": free_flag,
            "raw": m,
        })
    print(f"  command_code: fetched {len(out)} models")
    return out


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------
def apply_filters(models: List[Dict[str, Any]], cfg: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Returns (included, excluded) lists.
    Whitelist always wins. Then blacklist, then intelligence threshold.
    """
    filt = cfg.get("filters", {}) or {}
    min_intel = filt.get("minimum_intelligence", 0)
    include_unknown = filt.get("include_unknown_intelligence", True)
    blacklist: List[str] = filt.get("blacklist") or []
    whitelist: List[str] = filt.get("whitelist") or []
    # normalize None -> []
    if blacklist is None:
        blacklist = []
    if whitelist is None:
        whitelist = []
    # ensure list of strings
    blacklist = [str(x) for x in blacklist if x]
    whitelist = [str(x) for x in whitelist if x]

    included: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []

    for m in models:
        mid = m.get("model_id", "")
        composite = f"{m.get('provider')}/{mid}"
        # whitelist check (against model_id and composite)
        is_whitelisted = matches_any(whitelist, mid) or matches_any(whitelist, composite)
        if is_whitelisted:
            m["_filter_reason"] = "whitelisted"
            included.append(m)
            continue
        # blacklist
        if matches_any(blacklist, mid) or matches_any(blacklist, composite):
            m["_filter_reason"] = "blacklisted"
            excluded.append(m)
            continue
        # intelligence threshold
        intel = m.get("intelligence")
        if intel is None:
            if not include_unknown:
                m["_filter_reason"] = "unknown_intelligence"
                excluded.append(m)
                continue
            else:
                # include_unknown == True -> allow through unless min_intel > 0 and we consider unknown as failing
                # If min_intel >0 and include_unknown is True, we still include unknown (user asked).
                pass
        else:
            try:
                if float(intel) < float(min_intel):
                    m["_filter_reason"] = f"below_threshold:{intel}<{min_intel}"
                    excluded.append(m)
                    continue
            except Exception:
                pass
        m["_filter_reason"] = "passed"
        included.append(m)

    return included, excluded


# ---------------------------------------------------------------------------
# AA cache
# ---------------------------------------------------------------------------
def load_aa_cache(cfg: Dict[str, Any], output_dir: pathlib.Path) -> Optional[Dict[str, Any]]:
    intel_cfg = cfg.get("intelligence", {}) or {}
    aa_cfg = intel_cfg.get("artificial_analysis", {}) or {}
    if not aa_cfg.get("enabled", True):
        return None
    # Endpoint is now the correct free-tier paginated endpoint per docs.
    endpoint = aa_cfg.get("endpoint", "https://artificialanalysis.ai/api/v2/language/models/free")
    api_key = sanitize_key(aa_cfg.get("api_key") or os.environ.get("AA_API_KEY") or os.environ.get("ARTIFICIAL_ANALYSIS_API_KEY") or "")
    cache_file_name = aa_cfg.get("cache_file", "artificial_analysis_cache.json")
    ttl_hours = aa_cfg.get("cache_ttl_hours", 24)
    # fallback_local_file removed per operator request — no fallback to _enriched.json. Keep var for compat but ignore if set.
    fallback_local = aa_cfg.get("fallback_local_file", "")
    if fallback_local:
        print(f"  intelligence: note: fallback_local_file '{fallback_local}' is configured but ignored (removed per request — AA live only).", file=sys.stderr)
    cache_path = output_dir / cache_file_name
    if not cache_path.exists():
        cache_path = pathlib.Path(cache_file_name)
    use_cache = False
    cache_data: Optional[Dict[str, Any]] = None
    if cache_path.exists():
        try:
            age_h = (time.time() - cache_path.stat().st_mtime) / 3600
            if age_h < float(ttl_hours):
                use_cache = True
                cache_data = json.loads(cache_path.read_text(encoding="utf-8"))
                print(f"  intelligence: using AA cache ({cache_path}, age {age_h:.1f}h, {len(cache_data) if isinstance(cache_data, dict) else 'unknown'} entries) — TTL {ttl_hours}h not yet expired, skipping live fetch")
            else:
                print(f"  intelligence: AA cache expired ({age_h:.1f}h > {ttl_hours}h), refreshing ...")
        except Exception as e:
            print(f"WARN: AA cache read failed: {e}", file=sys.stderr)
    if use_cache:
        return cache_data
    if not api_key:
        print("WARN: AA live fetch skipped — no AA_API_KEY set (set AA_API_KEY env or intelligence.artificial_analysis.api_key). Intelligence will be blank (AA only, no fallback).", file=sys.stderr)
        return None
    print(f"  intelligence: fetching AA dataset {endpoint} (live, with AA_API_KEY) ...")
    headers: Dict[str, str] = {"x-api-key": api_key}
    all_data_network: List[Dict[str, Any]] = []
    page = 1
    max_pages = 10
    while page <= max_pages:
        url = f"{endpoint}{'&' if '?' in endpoint else '?'}page={page}"
        code, body = http_get(url, headers=headers, timeout=20)
        if code == 401:
            print(f"WARN: AA fetch HTTP 401 — missing/invalid x-api-key (check AA_API_KEY). Body: {str(body)[:300]}", file=sys.stderr)
            break
        if code == 429:
            print(f"WARN: AA fetch HTTP 429 rate-limited — backing off. Body: {str(body)[:300]}", file=sys.stderr)
            break
        if code != 200 or not isinstance(body, dict):
            print(f"WARN: AA fetch HTTP {code}: {str(body)[:400]}", file=sys.stderr)
            break
        data = body.get("data") or []
        if not isinstance(data, list) or not data:
            break
        all_data_network.extend(data)
        pagination = body.get("pagination") or {}
        # Correct pagination: prefer has_more / total_pages (free tier returns total_pages:4, has_more:true), not total count
        has_more = pagination.get("has_more")
        total_pages = pagination.get("total_pages")
        page_size = pagination.get("page_size") or 200
        if has_more is not None:
            if not has_more:
                break
        elif total_pages is not None:
            if page >= int(total_pages):
                break
        else:
            total = pagination.get("total") or pagination.get("total_count")
            if total is not None and len(all_data_network) >= int(total):
                break
            if len(data) < page_size:
                break
        page += 1
        time.sleep(0.3)
    if all_data_network:
        try:
            mapping: Dict[str, Any] = {}
            for entry in all_data_network:
                if not isinstance(entry, dict):
                    continue
                slug = entry.get("slug") or entry.get("id") or ""
                evals = entry.get("evaluations") or {}
                intel = evals.get("artificial_analysis_intelligence_index")
                cost_block = entry.get("artificial_analysis_intelligence_index_cost") or {}
                cpt = None
                if isinstance(cost_block, dict):
                    cpt = (cost_block.get("cost_per_task") or {}).get("total_cost")
                    if cpt is None:
                        cpt = cost_block.get("total_cost")
                if slug and intel is not None:
                    sl = slug.lower()
                    mapping[sl] = intel
                    # dash/underscore variants for robust matching (e.g. glm-5-2 vs glm_5_2)
                    mapping[sl.replace("-", "_")] = intel
                    mapping[sl.replace("_", "-")] = intel
                    if cpt is not None:
                        mapping[f"{sl}__cost"] = cpt
                    # also store name slug variant (AA name vs slug can differ)
                    name = entry.get("name") or ""
                    if name:
                        name_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
                        if name_slug and name_slug != sl:
                            mapping[name_slug] = intel
                            mapping[name_slug.replace("-", "_")] = intel
                            if cpt is not None:
                                mapping[f"{name_slug}__cost"] = cpt
            if mapping:
                try:
                    out_path = output_dir / cache_file_name
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
                    print(f"  intelligence: AA live cache saved ({len([k for k in mapping if not k.endswith('__cost')])} models -> {out_path}) — pages fetched: {page}")
                except Exception as e:
                    print(f"WARN: AA cache save failed: {e}", file=sys.stderr)
                return mapping
        except Exception as e:
            print(f"WARN: AA parsing failed: {e}", file=sys.stderr)
    print("WARN: AA live fetch failed/empty — intelligence will be blank (AA only, no heuristic/fallback). Will retry on next run after cache TTL or when AA_API_KEY is valid.", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Vision cache (models.dev + OpenRouter architecture + Cloudflare task)
# ---------------------------------------------------------------------------
def load_vision_cache(cfg: Dict[str, Any], output_dir: pathlib.Path) -> Optional[Dict[str, Any]]:
    """Load or fetch vision/image-generation mapping from models.dev.

    Returns dict with keys = normalized model slugs, value = {supports_vision: bool, supports_image_generation: bool}
    plus a special key _meta for diagnostics.
    Public endpoint https://models.dev/api.json (no key, ~7495 models, 4171 vision input, 178 image output).
    Cached like AA to avoid hammering. Falls back to OpenRouter architecture if fetch fails.
    """
    vision_cfg = cfg.get("vision", {}) or cfg.get("modalities", {}) or {}
    # default enable unless explicitly disabled
    if vision_cfg.get("enabled") is False:
        return None
    endpoint = vision_cfg.get("endpoint") or vision_cfg.get("models_dev_endpoint") or "https://models.dev/api.json"
    cache_file_name = vision_cfg.get("cache_file") or vision_cfg.get("cacheFile") or "vision_cache.json"
    ttl_hours = vision_cfg.get("cache_ttl_hours", 24)
    cache_path = output_dir / cache_file_name
    if not cache_path.exists():
        # also try repo root fallback
        alt = pathlib.Path(cache_file_name)
        if alt.exists():
            cache_path = alt
    # check fresh cache
    if cache_path.exists():
        try:
            age_h = (time.time() - cache_path.stat().st_mtime) / 3600
            if age_h < float(ttl_hours):
                try:
                    data = json.loads(cache_path.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and data:
                        cnt = len([k for k in data if not k.startswith("_")])
                        print(f"  vision: using cache ({cache_path}, age {age_h:.1f}h, {cnt} entries) — TTL {ttl_hours}h not yet expired")
                        return data
                except Exception as e:
                    print(f"WARN: vision cache read failed: {e}", file=sys.stderr)
            else:
                print(f"  vision: cache expired ({age_h:.1f}h > {ttl_hours}h), refreshing ...")
        except Exception:
            pass
    # fetch live
    print(f"  vision: fetching {endpoint} (models.dev, no key) ...")
    code, body = http_get(endpoint, timeout=30)
    if code != 200 or not isinstance(body, dict):
        # try fallback openrouter as source (already fetched elsewhere, but we try here as last resort)
        print(f"WARN: vision fetch HTTP {code}: {str(body)[:400]} — vision will be inferred from provider-native signals only", file=sys.stderr)
        # return empty but not None so we don't retry every time within TTL – return None to signal no cache
        # If we have stale cache, return it
        if cache_path.exists():
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    print(f"  vision: using stale cache due to fetch failure")
                    return data
            except Exception:
                pass
        return None
    # parse models.dev shape: { provider_id: {models: {model_id: {modalities:{input:[],output:[]}, attachment, ...}}}}
    mapping: Dict[str, Any] = {}
    total = 0
    vision_in = 0
    image_out = 0
    try:
        for _prov_id, prov_data in body.items():
            if not isinstance(prov_data, dict):
                continue
            models = prov_data.get("models")
            if not isinstance(models, dict):
                continue
            for mid, mdata in models.items():
                if not isinstance(mdata, dict):
                    continue
                mods = mdata.get("modalities") or {}
                inp = mods.get("input") or []
                out = mods.get("output") or []
                # also consider attachment flag? attachment true often means image input but modalities is authoritative
                has_vision = "image" in [str(x).lower() for x in inp]
                has_image_gen = "image" in [str(x).lower() for x in out]
                # store for multiple key variants for robust matching (like AA)
                base_variants: List[str] = []
                low = str(mid).lower()
                base_variants.append(low)
                # slug
                slug = re.sub(r"[^a-z0-9]+", "-", low).strip("-")
                if slug and slug not in base_variants:
                    base_variants.append(slug)
                    base_variants.append(slug.replace("-", "_"))
                # base after slash/colon
                base = low.split("/")[-1].split(":")[0]
                if base and base not in base_variants:
                    base_variants.append(base)
                base_slug = re.sub(r"[^a-z0-9]+", "-", base).strip("-") if base else ""
                if base_slug and base_slug not in base_variants:
                    base_variants.append(base_slug)
                    base_variants.append(base_slug.replace("-", "_"))
                # also underscore variants
                low_us = low.replace("-", "_")
                low_dash = low.replace("_", "-")
                if low_us not in base_variants:
                    base_variants.append(low_us)
                if low_dash not in base_variants:
                    base_variants.append(low_dash)
                # de-dupe
                seen = set()
                uniq: List[str] = []
                for v in base_variants:
                    if v and v not in seen:
                        seen.add(v)
                        uniq.append(v)
                for key in uniq:
                    # keep most permissive (if any variant has vision, mark true)
                    existing = mapping.get(key)
                    if existing is None:
                        mapping[key] = {"supports_vision": has_vision, "supports_image_generation": has_image_gen}
                    else:
                        # OR merge – if one provider says vision, keep true
                        mapping[key]["supports_vision"] = existing["supports_vision"] or has_vision
                        mapping[key]["supports_image_generation"] = existing["supports_image_generation"] or has_image_gen
                total += 1
                if has_vision:
                    vision_in += 1
                if has_image_gen:
                    image_out += 1
        # meta
        mapping["_meta"] = {"endpoint": endpoint, "fetched_at": datetime.datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), "total_models": total, "vision_input": vision_in, "image_output": image_out}
        # save
        try:
            out_path = output_dir / cache_file_name
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  vision: cache saved ({len([k for k in mapping if not k.startswith('_')])} entries, {vision_in} vision, {image_out} image_gen -> {out_path})")
        except Exception as e:
            print(f"WARN: vision cache save failed: {e}", file=sys.stderr)
        return mapping
    except Exception as e:
        print(f"WARN: vision parsing failed: {e}", file=sys.stderr)
        return None


def get_vision_flags(
    model_id: str,
    raw: Optional[Dict[str, Any]],
    provider: str,
    vision_cache: Optional[Dict[str, Any]] = None,
    openrouter_map: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[bool], Optional[bool], str]:
    """Return (supports_vision, supports_image_generation, source) for a model.

    Source priority:
      1) OpenRouter architecture (provider==openrouter)
      2) Cloudflare task.name (Text-to-Image / Image-to-Text / Image Classification)
      3) models.dev vision_cache (modalities.input/output contains image)
      4) OpenRouter cross-ref map (slug match from openrouter fetch)
      5) heuristic fallback (name contains vision hints) -> unknown
    Returns None for unknown (blank) to distinguish from false.
    """
    low = model_id.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", low).strip("-")
    base = low.split("/")[-1].split(":")[0]
    base_slug = re.sub(r"[^a-z0-9]+", "-", base).strip("-") if base else ""
    candidates: List[str] = [low, slug, base, base_slug, low.replace("-", "_"), base.replace("-", "_") if base else "", slug.replace("-", "_") if slug else ""]
    # dedupe
    seen = set()
    cands: List[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            cands.append(c)

    # 1) OpenRouter native
    if provider == "openrouter" and isinstance(raw, dict):
        arch = raw.get("architecture") or {}
        if isinstance(arch, dict) and arch:
            inp = arch.get("input_modalities") or []
            out = arch.get("output_modalities") or []
            # also handle older arch.modality string like "text+image->text"
            # but prefer explicit arrays
            if inp or out:
                has_vision = "image" in [str(x).lower() for x in inp]
                has_gen = "image" in [str(x).lower() for x in out]
                return has_vision, has_gen, "openrouter_architecture"
            # fallback parse modality string
            mod_str = arch.get("modality") or ""
            if isinstance(mod_str, str) and "->" in mod_str:
                left, right = mod_str.split("->", 1)
                has_vision = "image" in left.lower()
                has_gen = "image" in right.lower()
                return has_vision, has_gen, "openrouter_modality_string"

    # 2) Cloudflare task
    if provider == "cloudflare" and isinstance(raw, dict):
        task = raw.get("task") or {}
        task_name = ""
        if isinstance(task, dict):
            task_name = (task.get("name") or "").lower()
        else:
            task_name = str(task).lower()
        # also properties vision flag
        props = raw.get("properties") or []
        prop_vision = False
        if isinstance(props, list):
            for p in props:
                if isinstance(p, dict) and p.get("property_id") == "vision" and str(p.get("value")).lower() == "true":
                    prop_vision = True
                    break
        if task_name == "image-to-text":
            return True, False, "cloudflare_task"
        if task_name == "text-to-image":
            return False, True, "cloudflare_task"
        if task_name == "image classification":
            return True, False, "cloudflare_task"
        if prop_vision:
            return True, False, "cloudflare_properties"
        if task_name in ("text generation", "text embeddings", "translation", "automatic speech recognition", "text-to-speech", "text classification", "dumb pipe"):
            # explicit text-only
            return False, False, "cloudflare_task"
        # if name contains flux/stable-diffusion etc but task missing -> fall through to cache
        # we still return explicit false for known text tasks above

    # 3) models.dev cache
    if vision_cache:
        for cand in cands:
            entry = vision_cache.get(cand)
            if isinstance(entry, dict) and "supports_vision" in entry:
                return bool(entry["supports_vision"]), bool(entry["supports_image_generation"]), "models_dev"
        # substring fallback like AA
        for k, v in vision_cache.items():
            if k.startswith("_"):
                continue
            if not isinstance(v, dict):
                continue
            ak = k.lower()
            if ak in slug or ak in base_slug or slug in ak or base_slug in ak:
                # ensure not too short spurious match
                if len(ak) >= 4:
                    return bool(v.get("supports_vision")), bool(v.get("supports_image_generation")), "models_dev_substring"
            if ak.replace("-", "") == base_slug.replace("-", "") and len(ak) >= 4:
                return bool(v.get("supports_vision")), bool(v.get("supports_image_generation")), "models_dev_substring"

    # 4) OpenRouter cross-ref map
    if openrouter_map:
        for cand in cands:
            entry = openrouter_map.get(cand)
            if isinstance(entry, dict) and "supports_vision" in entry:
                return bool(entry["supports_vision"]), bool(entry["supports_image_generation"]), "openrouter_crossref"

    # 5) unknown
    return None, None, "unknown"


# ---------------------------------------------------------------------------
# Spreadsheet I/O
# ---------------------------------------------------------------------------
def ensure_output_dir(path: pathlib.Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_csv(models: List[Dict[str, Any]], path: pathlib.Path, columns: List[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for m in models:
            row = {}
            for c in columns:
                v = m.get(c)
                if v is None:
                    row[c] = ""
                elif isinstance(v, bool):
                    row[c] = "true" if v else "false"
                else:
                    row[c] = v
            w.writerow(row)


def write_json(models: List[Dict[str, Any]], path: pathlib.Path) -> None:
    # strip raw for json to keep size reasonable unless save_raw requested
    slim = []
    for m in models:
        copy = {k: v for k, v in m.items() if k != "raw" and not k.startswith("_")}
        slim.append(copy)
    path.write_text(json.dumps({"generated": datetime.datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), "count": len(slim), "models": slim}, indent=2, ensure_ascii=False), encoding="utf-8")


def write_xlsx(models: List[Dict[str, Any]], path: pathlib.Path, columns: List[str]) -> bool:
    try:
        import openpyxl  # type: ignore
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side  # type: ignore
        from openpyxl.utils import get_column_letter  # type: ignore
    except ImportError:
        return False
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "models"
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=10)
    free_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    thin_border = Border(left=Side(style="thin", color="D9D9D9"), right=Side(style="thin", color="D9D9D9"), top=Side(style="thin", color="D9D9D9"), bottom=Side(style="thin", color="D9D9D9"))
    # header
    for col_idx, col in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
    # rows
    for row_idx, m in enumerate(models, start=2):
        is_free = bool(m.get("free"))
        row_fill = free_fill if is_free else PatternFill(fill_type=None)
        for col_idx, col in enumerate(columns, start=1):
            v = m.get(col)
            if v is None:
                v = ""
            elif isinstance(v, bool):
                v = "TRUE" if v else "FALSE"
            cell = ws.cell(row=row_idx, column=col_idx, value=v)
            cell.border = thin_border
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if is_free:
                cell.fill = free_fill
            # numeric formatting
            if col in ("intelligence", "cost_input_per_1M", "cost_output_per_1M", "cost_per_task", "context_window"):
                try:
                    if v != "":
                        cell.number_format = "0.00" if col != "context_window" else "0"
                except Exception:
                    pass
    # column widths
    widths = {
        "provider": 16,
        "model_id": 42,
        "display_name": 30,
        "intelligence": 12,
        "intelligence_source": 16,
        "cost_input_per_1M": 16,
        "cost_output_per_1M": 16,
        "cost_per_task": 14,
        "free": 8,
        "supports_vision": 12,
        "supports_image_generation": 18,
        "vision_source": 18,
        "context_window": 14,
        "owned_by": 14,
        "last_seen": 18,
    }
    for col_idx, col in enumerate(columns, start=1):
        letter = get_column_letter(col_idx)
        ws.column_dimensions[letter].width = widths.get(col, 18)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    # add summary sheet
    ws2 = wb.create_sheet(title="summary")
    ws2["A1"] = "Model Inventory — Generated"
    ws2["A1"].font = Font(bold=True, size=14, color="1F4E78")
    ws2["A2"] = f"Generated: {datetime.datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}"
    ws2["A3"] = f"Total models: {len(models)}"
    free_count = sum(1 for m in models if m.get("free"))
    ws2["A4"] = f"Free models: {free_count}"
    ws2["A5"] = f"Providers: {', '.join(sorted(set(m.get('provider','') for m in models)))}"
    ws2.column_dimensions["A"].width = 60
    wb.save(path)
    return True


def load_previous_ids(csv_path: pathlib.Path, provider_col: str = "provider", model_col: str = "model_id") -> set:
    if not csv_path.exists():
        return set()
    ids: set = set()
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return set()
            # detect which columns exist
            has_provider = provider_col in reader.fieldnames
            has_model = model_col in reader.fieldnames
            if not has_model:
                # try alternative
                for alt in ["Id", "model", "id", "Model"]:
                    if alt in reader.fieldnames:
                        model_col = alt
                        has_model = True
                        break
            for row in reader:
                mid = (row.get(model_col) or "").strip()
                if not mid:
                    continue
                if has_provider:
                    prov = (row.get(provider_col) or "").strip()
                    key = f"{prov}/{mid}" if prov else mid
                else:
                    key = mid
                ids.add(key.lower())
    except Exception as e:
        print(f"WARN: failed to read previous CSV {csv_path}: {e}", file=sys.stderr)
    return ids


def sort_models(models: List[Dict[str, Any]], sort_by: str, sort_order: str) -> List[Dict[str, Any]]:
    reverse = sort_order.lower() == "desc"
    key = sort_by.lower()
    def sort_key(m: Dict[str, Any]):
        if key == "intelligence":
            v = m.get("intelligence")
            # blanks last regardless of order: push None to end
            is_blank = v is None
            return (is_blank, -(v or 0) if reverse else (v or 0))
        if key == "cost":
            v = m.get("cost_per_task")
            if v is None:
                # try input cost
                v = m.get("cost_input_per_1M")
            is_blank = v is None
            return (is_blank, v if not reverse else -(v or 0))
        if key == "provider":
            return (m.get("provider") or "", m.get("model_id") or "")
        # default model
        return (m.get("model_id") or "").lower()
    # For intelligence desc we want highest first, blanks last
    if key == "intelligence":
        # custom: sort with blanks last, then intelligence desc, then cost asc as tie breaker
        def intel_key(m: Dict[str, Any]):
            intel = m.get("intelligence")
            is_blank = intel is None
            cost = m.get("cost_per_task")
            if cost is None:
                cost = 999999
            # blanks last -> is_blank True sorts after False
            # For desc, we want -intel
            return (is_blank, -(intel or 0), cost)
        return sorted(models, key=intel_key)
    if key == "cost":
        def cost_key(m: Dict[str, Any]):
            c = m.get("cost_per_task")
            if c is None:
                c = m.get("cost_input_per_1M")
            is_blank = c is None
            if is_blank:
                c = 999999
            intel = m.get("intelligence") or 0
            return (is_blank, c, -intel)
        return sorted(models, key=cost_key)
    return sorted(models, key=sort_key, reverse=reverse)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Personal multi-provider model inventory (no LLM, 100% programmatic)")
    parser.add_argument("--config", help="path to config YAML (default: auto-discover)")
    parser.add_argument("--output-dir", help="override output_dir from config")
    parser.add_argument("--providers", help="comma-separated subset to fetch: google,opencode_zen,opencode_go,cloudflare,ollama_cloud,openrouter,command_code")
    parser.add_argument("--dry-run", action="store_true", help="fetch and show summary but do not write files")
    parser.add_argument("--no-aa", action="store_true", help="skip ArtificialAnalysis cache fetch")
    parser.add_argument("--verbose", action="store_true", help="verbose logging")
    args = parser.parse_args()

    # Auto-load .env / secret files from execution layout before any ${} expansion
    # (so AA_API_KEY etc. in executions/9router/.env or secrets/.env are picked up)
    try:
        load_execution_env(pathlib.Path(args.config) if args.config else None)
    except Exception:
        pass

    # Load config
    cfg_path = find_config(args.config)
    # also load env relative to the discovered config path (e.g. executions/9router-*/.env)
    if cfg_path:
        try:
            load_execution_env(cfg_path)
        except Exception:
            pass
    cfg: Dict[str, Any] = {}
    if cfg_path:
        print(f"Config: {cfg_path}")
        cfg = load_yaml(cfg_path)
        cfg = expand_env(cfg)
        cfg["_config_path"] = str(cfg_path)
    else:
        print("WARN: no config found — using defaults (public endpoints, no keys, no filters)", file=sys.stderr)
        cfg = {}

    # Minimal defaults so script works without config
    # ponytail: ceiling is per-run inventory files; if overrides need history/audit add override_source+applied_at columns.
    defaults: Dict[str, Any] = {
        "overrides": [],
        "general": {"output_dir": "executions/9router/model-inventory", "spreadsheet_name": "models.csv", "json_name": "models.json", "added_list_prefix": "added", "save_raw_snapshot": True, "raw_snapshot_name": "raw_snapshot_{{date}}.json", "sort_by": "intelligence", "sort_order": "desc"},
        "filters": {"minimum_intelligence": 0, "include_unknown_intelligence": True, "blacklist": [], "whitelist": ["*big-pickle*", "*free*"] if False else ["big-pickle", "*big-pickle*"]},
        "intelligence": {"default_score": None, "artificial_analysis": {"enabled": True, "endpoint": "https://artificialanalysis.ai/api/v2/language/models/free", "api_key": "", "cache_file": "artificial_analysis_cache.json", "cache_ttl_hours": 24, "fallback_local_file": ""}, "patterns": []},
        "vision": {"enabled": True, "endpoint": "https://models.dev/api.json", "cache_file": "vision_cache.json", "cache_ttl_hours": 24},
        "cost": {"currency": "USD", "unit": "per_1M_tokens", "overrides": {}},
        "api_keys": {"google": "", "opencode_zen": "", "opencode_go": "", "cloudflare": {"api_token": "", "account_id": ""}, "ollama_cloud": "", "openrouter": "", "command_code": ""},
        "endpoints": {"google": "https://generativelanguage.googleapis.com/v1beta/models", "opencode_zen": "https://opencode.ai/zen/v1/models", "opencode_go": "https://opencode.ai/zen/go/v1/models", "cloudflare": "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/models/search", "cloudflare_fallback": "https://api.cloudflare.com/client/v4/ai/models", "ollama_cloud": "https://ollama.com/api/tags", "ollama_cloud_fallback": "https://api.ollama.ai/v1/models", "openrouter": "https://openrouter.ai/api/v1/models", "command_code": ""},
        "providers": {"enabled": ["google", "opencode_zen", "opencode_go", "cloudflare", "ollama_cloud", "openrouter", "command_code"], "google": {"require_key": False, "free": True}, "opencode_zen": {"require_key": False}, "opencode_go": {"require_key": False}, "cloudflare": {"require_key": False, "free": True}, "ollama_cloud": {"require_key": False, "free": True}, "openrouter": {"require_key": False, "free_only": True}, "command_code": {"require_key": False}},
        "output": {"columns": ["provider", "model_id", "display_name", "intelligence", "intelligence_source", "cost_input_per_1M", "cost_output_per_1M", "cost_per_task", "free", "supports_vision", "supports_image_generation", "vision_source", "context_window", "owned_by", "last_seen"]},
    }
    # Deep merge defaults with loaded cfg (loaded wins)
    cfg = deep_merge(defaults, cfg)
    if args.output_dir:
        cfg["general"]["output_dir"] = args.output_dir
    if args.no_aa:
        cfg["intelligence"]["artificial_analysis"]["enabled"] = False

    output_dir = pathlib.Path(cfg["general"]["output_dir"])
    # resolve relative against repo root if needed
    if not output_dir.is_absolute():
        # try repo root discovery: look for playbooks folder
        cwd = pathlib.Path.cwd()
        repo_root = cwd
        # if cwd is inside repo, output_dir relative to repo root is fine
        # We'll resolve against cwd, then ensure parent exists
        output_dir = (cwd / output_dir).resolve() if not output_dir.exists() else output_dir.resolve()
        # fallback: if we are in playbooks/9router/scripts vs repo root, adjust
        # keep as is - mkdir will create correctly
    ensure_output_dir(output_dir)

    # AA cache
    aa_cache: Optional[Dict[str, Any]] = None
    if cfg["intelligence"].get("artificial_analysis", {}).get("enabled"):
        aa_cache = load_aa_cache(cfg, output_dir)
        cfg["_aa_cache"] = aa_cache
    else:
        cfg["_aa_cache"] = None

    # Vision cache (models.dev) – for supports_vision / supports_image_generation
    vision_cache: Optional[Dict[str, Any]] = None
    try:
        vision_cache = load_vision_cache(cfg, output_dir)
        cfg["_vision_cache"] = vision_cache
    except Exception as e:
        print(f"WARN: vision cache load failed: {e}", file=sys.stderr)
        cfg["_vision_cache"] = None

    # Determine providers to fetch
    enabled = cfg.get("providers", {}).get("enabled") or []
    if args.providers:
        subset = [p.strip().lower() for p in args.providers.split(",") if p.strip()]
        # normalize aliases
        alias_map = {"opencode-zen": "opencode_zen", "opencode-go": "opencode_go", "ollama": "ollama_cloud", "cf": "cloudflare", "cc": "command_code", "commandcode": "command_code"}
        subset = [alias_map.get(p, p) for p in subset]
        enabled = [p for p in enabled if p in subset]
        if not subset:
            enabled = subset
        # if subset requested not in enabled, include anyway
        for p in subset:
            if p not in enabled:
                enabled.append(p)
    print(f"Providers enabled: {', '.join(enabled) or '(none)'}")
    print(f"Output dir: {output_dir}")
    print(f"Filters: min_intel={cfg['filters'].get('minimum_intelligence')} include_unknown={cfg['filters'].get('include_unknown_intelligence')} blacklist={len(cfg['filters'].get('blacklist') or [])} whitelist={len(cfg['filters'].get('whitelist') or [])}")

    # Fetch loop
    all_models: List[Dict[str, Any]] = []
    raw_snapshots: Dict[str, Any] = {}
    provider_funcs = {
        "google": fetch_google,
        "opencode_zen": lambda c, timeout=20: fetch_opencode("opencode_zen", c, timeout),
        "opencode_go": lambda c, timeout=20: fetch_opencode("opencode_go", c, timeout),
        "cloudflare": fetch_cloudflare,
        "ollama_cloud": fetch_ollama_cloud,
        "openrouter": fetch_openrouter,
        "command_code": fetch_command_code,
    }
    for prov in enabled:
        fn = provider_funcs.get(prov)
        if not fn:
            print(f"WARN: unknown provider '{prov}' — skipping", file=sys.stderr)
            continue
        prov_cfg_key = prov
        # respect require_key if enabled list says skip but we already handle per provider
        try:
            print(f"Fetching {prov} ...")
            fetched = fn(cfg)  # type: ignore
            raw_snapshots[prov] = {"count": len(fetched), "endpoint": cfg.get("endpoints", {}).get(prov, "")}
            all_models.extend(fetched)
        except Exception as e:
            print(f"ERR: provider {prov} failed: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()

    # Build OpenRouter cross-ref map for vision (architecture -> vision flags) to enrich other providers
    openrouter_map: Dict[str, Any] = {}
    try:
        # collect openrouter models from all_models (already fetched)
        for m in all_models:
            if m.get("provider") != "openrouter":
                continue
            raw = m.get("raw") or {}
            arch = raw.get("architecture") or {}
            if not isinstance(arch, dict):
                continue
            inp = arch.get("input_modalities") or []
            out = arch.get("output_modalities") or []
            has_vision = False
            has_gen = False
            if inp or out:
                has_vision = "image" in [str(x).lower() for x in inp]
                has_gen = "image" in [str(x).lower() for x in out]
            else:
                mod_str = arch.get("modality") or ""
                if isinstance(mod_str, str) and "->" in mod_str:
                    left, right = mod_str.split("->", 1)
                    has_vision = "image" in left.lower()
                    has_gen = "image" in right.lower()
                else:
                    continue
            # store under multiple keys like vision_cache for matching
            mid = m.get("model_id") or ""
            low = mid.lower()
            keys = [low, re.sub(r"[^a-z0-9]+","-",low).strip("-"), low.split("/")[-1].split(":")[0], re.sub(r"[^a-z0-9]+","-", low.split("/")[-1].split(":")[0]).strip("-")]
            for k in set(k for k in keys if k):
                if k not in openrouter_map:
                    openrouter_map[k] = {"supports_vision": has_vision, "supports_image_generation": has_gen}
                # also underscore variants
                ku = k.replace("-", "_")
                if ku != k and ku not in openrouter_map:
                    openrouter_map[ku] = {"supports_vision": has_vision, "supports_image_generation": has_gen}
        if openrouter_map:
            print(f"  vision: built OpenRouter cross-ref map ({len(openrouter_map)} keys from {sum(1 for m in all_models if m.get('provider')=='openrouter')} models)")
    except Exception as e:
        print(f"WARN: openrouter vision map build failed: {e}", file=sys.stderr)
        openrouter_map = {}

    # Annotate vision flags for every model (supports_vision / supports_image_generation)
    for m in all_models:
        mid = m.get("model_id") or ""
        raw = m.get("raw")
        prov = m.get("provider") or ""
        try:
            v, g, src = get_vision_flags(mid, raw if isinstance(raw, dict) else None, prov, vision_cache, openrouter_map)
            # store as bool (true/false) or None for unknown; column will blank if None
            m["supports_vision"] = v
            m["supports_image_generation"] = g
            m["vision_source"] = src
        except Exception as e:
            print(f"WARN: vision flag failed for {prov}/{mid}: {e}", file=sys.stderr)
            m["supports_vision"] = None
            m["supports_image_generation"] = None
            m["vision_source"] = "error"

    # Per-model overrides (stored in inventory): regex model match + fields (cost_per_task/price, intelligence, booleans, etc.)
    # Each rule: {pattern: regex/glob, providers?:[...], cost_per_task|price_per_task: 0.2, intelligence: .., free: ..}
    # Top-level `overrides:` array wins, but per-provider `providers.<k>.overrides` also supported.
    try:
        apply_model_overrides(all_models, cfg)
    except Exception as e:
        print(f"WARN: overrides failed: {e}", file=sys.stderr)

    # annotate last_seen
    now_iso = datetime.datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    for m in all_models:
        m["last_seen"] = now_iso

    print(f"\nTotal raw fetched: {len(all_models)} models across {len(enabled)} providers")

    # Dedupe by provider+model_id (keep first, but merge if duplicate with higher intelligence)
    deduped: Dict[str, Dict[str, Any]] = {}
    for m in all_models:
        key = f"{m.get('provider')}/{m.get('model_id')}".lower()
        if key not in deduped:
            deduped[key] = m
        else:
            # keep richer (higher intelligence or lower cost)
            existing = deduped[key]
            # prefer entry with intelligence not null
            if existing.get("intelligence") is None and m.get("intelligence") is not None:
                deduped[key] = m
    all_models = list(deduped.values())
    print(f"After dedupe: {len(all_models)} unique provider/model combos")

    # Filtering
    included, excluded = apply_filters(all_models, cfg)
    print(f"After filters: {len(included)} included, {len(excluded)} excluded")
    if excluded and args.verbose:
        from collections import Counter
        reasons = Counter(m.get("_filter_reason", "unknown") for m in excluded)
        print(f"  Excluded reasons: {dict(reasons)}")
        for m in excluded[:10]:
            print(f"    - {m.get('provider')}/{m.get('model_id')}  ({m.get('_filter_reason')})  intel={m.get('intelligence')}")

    # Sorting
    sort_by = cfg["general"].get("sort_by", "intelligence")
    sort_order = cfg["general"].get("sort_order", "desc")
    included = sort_models(included, sort_by, sort_order)

    # Previous spreadsheet load for "added" detection
    spreadsheet_name = cfg["general"].get("spreadsheet_name", "models.csv")
    json_name = cfg["general"].get("json_name", "models.json")
    spreadsheet_path = output_dir / spreadsheet_name
    json_path = output_dir / json_name

    prev_ids = load_previous_ids(spreadsheet_path)
    print(f"Previous spreadsheet: {spreadsheet_path} ({len(prev_ids)} ids)" if spreadsheet_path.exists() else f"Previous spreadsheet not found: {spreadsheet_path} (first run)")

    # Compute added
    current_keys: List[str] = []
    current_map: Dict[str, Dict[str, Any]] = {}
    for m in included:
        key = f"{m.get('provider')}/{m.get('model_id')}".lower()
        current_keys.append(key)
        current_map[key] = m
    added_keys = [k for k in current_keys if k not in prev_ids]
    added_models = [current_map[k] for k in added_keys]

    # Also handle removed? Not required but log
    removed_keys = [k for k in prev_ids if k not in set(current_keys)]
    print(f"New models this run: {len(added_models)}")
    if removed_keys:
        print(f"Removed since last run: {len(removed_keys)} (not in added list)")

    columns: List[str] = cfg.get("output", {}).get("columns") or defaults["output"]["columns"]

    if args.dry_run:
        print("\n--- DRY RUN: not writing files ---")
        print(f"Would write: {spreadsheet_path} ({len(included)} rows)")
        print(f"Would write: {json_path}")
        if added_models:
            date_tag = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d")
            print(f"Would write added: {output_dir / f'{cfg['general'].get('added_list_prefix','added')}_{date_tag}.csv'} ({len(added_models)} rows)")
        # preview
        print("\nTop 10 by sort:")
        for m in included[:10]:
            print(f"  {m.get('provider'):15} {m.get('model_id'):45} intel={m.get('intelligence')} free={m.get('free')} cost_in={m.get('cost_input_per_1M')} cost_out={m.get('cost_output_per_1M')}")
        if added_models:
            print("\nAdded models:")
            for m in added_models[:20]:
                print(f"  + {m.get('provider')}/{m.get('model_id')} intel={m.get('intelligence')} free={m.get('free')}")
        return

    # Write main spreadsheet
    write_csv(included, spreadsheet_path, columns)
    print(f"Wrote CSV: {spreadsheet_path} ({len(included)} rows)")
    write_json(included, json_path)
    print(f"Wrote JSON: {json_path}")

    # XLSX
    xlsx_path = spreadsheet_path.with_suffix(".xlsx")
    if xlsx_path != spreadsheet_path:
        ok = write_xlsx(included, xlsx_path, columns)
        if ok:
            print(f"Wrote XLSX: {xlsx_path}")
        else:
            print("XLSX: openpyxl not installed — skipping .xlsx (pip install openpyxl to enable)")

    # Raw snapshot
    if cfg["general"].get("save_raw_snapshot"):
        raw_name_tmpl = cfg["general"].get("raw_snapshot_name", "raw_snapshot_{{date}}.json")
        date_str = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d")
        raw_name = raw_name_tmpl.replace("{{date}}", date_str)
        raw_path = output_dir / raw_name
        snapshot = {
            "generated": now_iso,
            "config_path": cfg.get("_config_path"),
            "providers": raw_snapshots,
            "counts": {"raw_total": len(all_models), "included": len(included), "excluded": len(excluded), "added": len(added_models)},
            "filters": cfg.get("filters"),
        }
        raw_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote raw snapshot: {raw_path}")

    # Added list files (always write, even if empty, for audit)
    date_tag = datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prefix = cfg["general"].get("added_list_prefix", "added")
    added_csv = output_dir / f"{prefix}_{date_tag}.csv"
    added_json = output_dir / f"{prefix}_{date_tag}.json"
    # If file exists today, append time suffix to avoid overwrite
    if added_csv.exists():
        time_tag = datetime.datetime.now(timezone.utc).strftime("%H%M%S")
        added_csv = output_dir / f"{prefix}_{date_tag}_{time_tag}.csv"
        added_json = output_dir / f"{prefix}_{date_tag}_{time_tag}.json"
    write_csv(added_models, added_csv, columns)
    write_json(added_models, added_json)
    print(f"Wrote added CSV: {added_csv} ({len(added_models)} rows)")
    print(f"Wrote added JSON: {added_json}")

    # Summary log
    free_count = sum(1 for m in included if m.get("free"))
    print("\n" + "=" * 60)
    print(f"Done. Total included: {len(included)} | Free: {free_count} | Added this run: {len(added_models)}")
    print(f"Main spreadsheet: {spreadsheet_path}")
    # if added_models:
    #     print("Added models:")
    #     # for m in added_models:
    #     #     print(f"  + {m.get('provider')}/{m.get('model_id')}  intel={m.get('intelligence')} ({m.get('intelligence_source')})  free={m.get('free')}  cost_in={m.get('cost_input_per_1M')} cost_out={m.get('cost_output_per_1M')}")
    # else:
    #     print("No new models since last run (or first run).")
    print("=" * 60)


if __name__ == "__main__":
    main()
