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

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description="9Router sync: inventory -> providers+combos+CLI")
    parser.add_argument("--config", help="path to 9router-sync config yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args=parser.parse_args()
    print(find_sync_configs(args.config))
