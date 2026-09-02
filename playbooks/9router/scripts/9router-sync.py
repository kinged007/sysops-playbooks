#!/usr/bin/env python3
"""
9router-sync.py — Sync model-inventory -> 9Router providers + combos + CLI configs.
Config discovery mirrors model-inventory.py: scans executions/*9router*/**/9router-sync*.yaml
"""
from __future__ import annotations
import argparse, csv, json, os, pathlib, re, sys, fnmatch, datetime
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:
    yaml = None
try:
    import requests
except ImportError:
    requests = None

DEFAULT_SYNC_CONFIG_CANDIDATES = [
    pathlib.Path("9router-sync.config.yaml"),
    pathlib.Path("playbooks/9router/templates/9router-sync.config.example.yaml"),
    pathlib.Path("executions/9router/9router-sync.config.yaml"),
]

def sanitize_key(value: Any) -> str:
    if value is None: return ""
    s = str(value).strip()
    if not s or "${" in s: return ""
    return s

def expand_env(value: Any) -> Any:
    if isinstance(value, str):
        expanded = os.path.expandvars(value)
        def repl_all(s: str) -> str:
            m = re.search(r"\$\{([^}:]+):-([^}]*)\}", s)
            while m:
                var_name, default = m.group(1), m.group(2)
                val = os.environ.get(var_name, default)
                s = s[:m.start()] + val + s[m.end():]
                m = re.search(r"\$\{([^}:]+):-([^}]*)\}", s)
            m2 = re.search(r"\$\{([^}:]+)\}", s)
            while m2:
                var_name = m2.group(1)
                val = os.environ.get(var_name, "") if var_name in os.environ else ""
                s = s[:m2.start()] + val + s[m2.end():]
                m2 = re.search(r"\$\{([^}:]+)\}", s)
            return s
        expanded = repl_all(expanded)
        if expanded.strip() == "" and "${" in value:
            return ""
        return expanded
    if isinstance(value, dict): return {k: expand_env(v) for k,v in value.items()}
    if isinstance(value, list): return [expand_env(v) for v in value]
    return value

def load_yaml(path: pathlib.Path) -> Dict[str, Any]:
    if yaml is None:
        try: return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"ERR yaml {path}: {e}", file=sys.stderr); return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        print(f"ERR yaml {path}: {e}", file=sys.stderr); return {}

def find_sync_configs(cli_path: Optional[str] = None, search_root: Optional[pathlib.Path] = None) -> List[pathlib.Path]:
    if cli_path:
        p = pathlib.Path(cli_path)
        if p.exists(): return [p]
        print(f"ERR --config {cli_path} not found", file=sys.stderr); sys.exit(2)
    # When search_root is explicitly provided (test isolation), skip static candidates
    # and fallback so empty temp dir truly returns []
    if search_root is None:
        found: List[pathlib.Path] = []
        # 1) static candidates (example deferred)
        for cand in DEFAULT_SYNC_CONFIG_CANDIDATES:
            if cand.name == "9router-sync.config.example.yaml": continue
            if cand.exists(): found.append(cand)
            if found: return found  # first wins if static exists
    # 2) glob executions/*9router* for 9router-sync*.yaml
    roots: List[pathlib.Path] = []
    if search_root: roots.append(search_root)
    else:
        for base in [pathlib.Path("executions"), pathlib.Path("D:/Data/git/sysops-playbooks/executions")]:
            if base.exists(): roots.append(base)
        try:
            repo_root = pathlib.Path(__file__).resolve().parents[3]
            rr = repo_root / "executions"
            if rr.exists() and rr not in roots: roots.append(rr)
        except: pass
    candidates: List[pathlib.Path] = []
    for root in roots:
        for nine_dir in root.glob("*9router*"):
            if not nine_dir.is_dir(): continue
            for pat in ("9router-sync*.yaml","9router-sync*.yml","9router-sync*.json"):
                try:
                    candidates.extend([p for p in nine_dir.rglob(pat) if p.is_file() and "model-inventory" not in str(p).lower()])
                except: pass
    if candidates:
        candidates = sorted(set(candidates), key=lambda p: (len(str(p)), str(p).lower()))
        return candidates
    # 3) fallback committed example (skip when search_root isolated)
    if search_root is None:
        for cand in DEFAULT_SYNC_CONFIG_CANDIDATES:
            if cand.exists(): return [cand]
    return []

def load_execution_env(config_path: Optional[pathlib.Path] = None) -> None:
    # Reuse model-inventory.py logic: load .env + secrets/*.txt
    candidates: List[pathlib.Path] = []
    cwd = pathlib.Path.cwd()
    if config_path and config_path.exists():
        candidates.append(config_path.parent / ".env")
        candidates.append(config_path.parent / "secrets" / ".env")
    for base in [pathlib.Path("executions/9router"), pathlib.Path("D:/Data/git/sysops-playbooks/executions/9router")]:
        candidates.extend([base / ".env", base / "secrets" / ".env", base / "secrets" / "api_keys.env"])
    try:
        for d in pathlib.Path("executions").glob("9router-*"):
            candidates.extend([d / ".env", d / "secrets" / ".env"])
    except: pass
    candidates.extend([cwd / ".env", pathlib.Path(".env")])
    seen=set()
    for cand in candidates:
        try: r=cand.resolve()
        except: r=cand
        if str(r) in seen or not cand.exists(): continue
        seen.add(str(r))
        # load dotenv
        try:
            for line in cand.read_text(encoding="utf-8").splitlines():
                line=line.strip()
                if not line or line.startswith("#") or "=" not in line: continue
                k,v=line.split("=",1)
                k=k.strip(); v=v.strip().strip('"').strip("'")
                if not k or (k in os.environ and os.environ[k]): continue
                if v: os.environ[k]=v
        except Exception as e: print(f"WARN load {cand}: {e}", file=sys.stderr)
    # per-key .txt
    for base in [pathlib.Path("executions/9router/secrets"), pathlib.Path("D:/Data/git/sysops-playbooks/executions/9router/secrets")]:
        if not base.exists(): continue
        for p in base.glob("*.txt"):
            key=p.stem.upper().replace("-","_")
            try:
                val=p.read_text(encoding="utf-8").strip().strip("\ufeff")
                if val and not os.environ.get(key): os.environ[key]=val
            except: pass
    if config_path:
        sp=config_path.parent / "secrets"
        if sp.exists():
            for p in sp.glob("*.txt"):
                key=p.stem.upper().replace("-","_")
                try:
                    val=p.read_text(encoding="utf-8").strip().strip("\ufeff")
                    if val and not os.environ.get(key): os.environ[key]=val
                except: pass

def load_inventory(inv_dir: pathlib.Path) -> List[Dict[str, Any]]:
    """Try models.json then models.csv in inv_dir. Returns list of dicts with normalized keys."""
    jpath = inv_dir / "models.json"
    if jpath.exists():
        try:
            data = json.loads(jpath.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "models" in data:
                return data["models"]
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "data" in data:  # 9router shape fallback
                return data["data"]
        except Exception as e:
            print(f"WARN load_inventory json {jpath}: {e}", file=sys.stderr)
    cpath = inv_dir / "models.csv"
    if cpath.exists():
        out=[]
        try:
            with cpath.open("r", encoding="utf-8", newline="") as f:
                reader=csv.DictReader(f)
                for row in reader:
                    # normalize numeric fields
                    for k in ("intelligence","cost_per_task","cost_input_per_1M","cost_output_per_1M"):
                        if row.get(k) in ("", None):
                            row[k]=None
                        else:
                            try: row[k]=float(row[k]) if row[k]!="" else None
                            except: pass
                    if "free" in row:
                        v=row["free"]
                        if isinstance(v, str): row["free"]=v.lower() in ("true","1","yes")
                    out.append(row)
            return out
        except Exception as e:
            print(f"WARN load_inventory csv {cpath}: {e}", file=sys.stderr)
    return []

def matches_any(patterns: List[str], text: str) -> bool:
    if not patterns or not text: return False
    low=text.lower()
    for pat in patterns:
        pat_low=pat.lower()
        if fnmatch.fnmatch(low, pat_low): return True
        if pat_low in low: return True
        try:
            if re.search(pat, text, re.IGNORECASE): return True
        except re.error: pass
    return False

def map_provider(inventory_provider: str, model_id: str, mapping: Dict[str,str]) -> str:
    alias = mapping.get(inventory_provider, inventory_provider)
    # allow mapping values like "" for cloudflare
    if alias == "" or alias is None:
        return model_id
    # avoid double prefix: if model_id already starts with alias + "/"
    if model_id.lower().startswith(alias.lower() + "/"):
        return model_id
    # also handle case where model_id is like "cmc/..." already contains slash but alias is cmc
    # above check covers it
    return f"{alias}/{model_id}"

def find_inventory_dir(config_dir: pathlib.Path) -> Optional[pathlib.Path]:
    candidates = [
        config_dir / "model-inventory",
        config_dir / "model-inventory-output",
        pathlib.Path("executions/9router/model-inventory"),
        pathlib.Path("D:/Data/git/sysops-playbooks/executions/9router/model-inventory"),
    ]
    for c in candidates:
        if (c / "models.json").exists() or (c / "models.csv").exists():
            return c
    # glob fallback: any model-inventory under executions/*9router*
    try:
        for root in [pathlib.Path("executions"), pathlib.Path("D:/Data/git/sysops-playbooks/executions")]:
            if not root.exists(): continue
            for nine_dir in root.glob("*9router*"):
                for pat in ("model-inventory/models.json","model-inventory/models.csv"):
                    p = nine_dir / pat
                    if p.exists(): return p.parent
    except: pass
    return None

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description="9Router sync: inventory -> providers+combos+CLI")
    parser.add_argument("--config", help="path to 9router-sync config yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args=parser.parse_args()
    print(find_sync_configs(args.config))
