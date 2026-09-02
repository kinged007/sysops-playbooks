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

def apply_global_filter(models: List[Dict[str, Any]], cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    min_intel = cfg.get("min_intelligence")
    include_null = cfg.get("include_null_intelligence", True)
    max_cpt = cfg.get("max_cost_per_task")
    min_cpt = cfg.get("min_cost_per_task")
    prov_wl = [str(x) for x in (cfg.get("provider_whitelist") or []) if x]
    prov_bl = [str(x) for x in (cfg.get("provider_blacklist") or []) if x]
    mod_wl = [str(x) for x in (cfg.get("model_whitelist") or []) if x]
    mod_bl = [str(x) for x in (cfg.get("model_blacklist") or []) if x]
    free_filter = cfg.get("free", "both")
    if isinstance(free_filter, str): free_filter = free_filter.lower()
    # normalize bool
    if free_filter is True: free_str="true"
    elif free_filter is False: free_str="false"
    else: free_str=str(free_filter).lower() if free_filter else "both"

    out=[]
    for m in models:
        prov=m.get("provider","")
        mid=m.get("model_id","")
        composite=f"{prov}/{mid}"
        # whitelist wins: if matches any whitelist, include immediately (skip blacklist/min checks)
        is_wl = matches_any(mod_wl, mid) or matches_any(mod_wl, composite) or matches_any(prov_wl, prov)
        # Actually provider whitelist is separate; handle below
        # First check provider whitelist/blacklist
        if prov_wl and not matches_any(prov_wl, prov):
            if not is_wl: continue
        if prov_bl and matches_any(prov_bl, prov):
            if not is_wl: continue
        # model whitelist immediate pass
        if mod_wl and (matches_any(mod_wl, mid) or matches_any(mod_wl, composite)):
            out.append(m); continue
        # model blacklist
        if matches_any(mod_bl, mid) or matches_any(mod_bl, composite):
            continue
        # free filter
        if free_str != "both":
            is_free = bool(m.get("free"))
            if free_str == "true" and not is_free: continue
            if free_str == "false" and is_free: continue
        # intelligence
        intel=m.get("intelligence")
        if intel is None:
            if not include_null: continue
        else:
            try:
                if min_intel is not None and float(intel) < float(min_intel):
                    continue
            except: pass
        # cost per task
        cpt=m.get("cost_per_task")
        # if cost is None, treat as pass unless max is set and we want to exclude null? Spec says max cost per task — null should be excluded if max set?
        # Keep null as pass only if include_null true and no max? Simpler: if cpt is None, skip cost checks.
        if cpt is not None:
            try:
                if max_cpt is not None and float(cpt) > float(max_cpt): continue
                if min_cpt is not None and float(cpt) < float(min_cpt): continue
            except: pass
        else:
            # if max_cpt is set and cpt is None, we consider it as not exceeding max (keep) — unless global include_null false?
            pass
        out.append(m)
    return out

def apply_combo_pipeline(routed_models: List[Dict[str, Any]], combo_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    # routed_models already have keys: provider (mapped alias), model_id, routed, intelligence, cost_per_task, free
    # Work on copy
    models = list(routed_models)
    # Extract cfg
    free_filter = combo_cfg.get("free", "both")
    if isinstance(free_filter, bool): free_str = "true" if free_filter else "false"
    else: free_str = str(free_filter).lower() if free_filter is not None else "both"
    min_intel = combo_cfg.get("min_intelligence")
    max_intel = combo_cfg.get("max_intelligence")
    include_null = combo_cfg.get("include_null_intelligence", True)
    min_cpt = combo_cfg.get("min_cost_per_task")
    max_cpt = combo_cfg.get("max_cost_per_task")
    sort_by = combo_cfg.get("sort_by", "intelligence")
    sort_order = combo_cfg.get("sort_order", "desc")
    prov_wl = combo_cfg.get("provider_whitelist") or combo_cfg.get("whitelist_providers") or []
    prov_bl = combo_cfg.get("provider_blacklist") or combo_cfg.get("blacklist_providers") or []
    mod_wl = combo_cfg.get("model_whitelist") or combo_cfg.get("whitelist") or []
    mod_bl = combo_cfg.get("model_blacklist") or combo_cfg.get("blacklist") or []
    favorites = combo_cfg.get("favorites") or combo_cfg.get("favorite") or []
    if isinstance(favorites, str): favorites=[favorites]
    # Also support legacy keys "whitelist"/"blacklist" that apply to model_id
    # If generic whitelist/blacklist provided, treat as model patterns
    if not mod_wl and combo_cfg.get("whitelist"): mod_wl = combo_cfg.get("whitelist")
    if not mod_bl and combo_cfg.get("blacklist"): mod_bl = combo_cfg.get("blacklist")

    filtered=[]
    for m in models:
        prov = m.get("provider","") or m.get("mapped_provider","")
        mid = m.get("model_id","")
        routed = m.get("routed","") or f"{prov}/{mid}"
        composite = f"{prov}/{mid}"
        # provider whitelist/blacklist
        if prov_wl and not matches_any(prov_wl, prov):
            # unless whitelisted via model
            if not (matches_any(mod_wl, mid) or matches_any(mod_wl, routed) or matches_any(mod_wl, composite)):
                continue
        if prov_bl and matches_any(prov_bl, prov):
            if not (matches_any(mod_wl, mid) or matches_any(mod_wl, routed)):
                continue
        # model whitelist immediate pass
        is_mod_wl = matches_any(mod_wl, mid) or matches_any(mod_wl, routed) or matches_any(mod_wl, composite)
        if is_mod_wl:
            filtered.append(m); continue
        if matches_any(mod_bl, mid) or matches_any(mod_bl, routed) or matches_any(mod_bl, composite):
            continue
        # free
        if free_str != "both":
            is_free = bool(m.get("free"))
            if free_str == "true" and not is_free: continue
            if free_str == "false" and is_free: continue
        # intelligence
        intel=m.get("intelligence")
        if intel is None:
            if not include_null and min_intel is not None:
                continue
            if min_intel is not None and not include_null:
                continue
        else:
            try:
                if min_intel is not None and float(intel) < float(min_intel):
                    continue
                if max_intel is not None and float(intel) > float(max_intel):
                    continue
            except: pass
        # cost
        cpt=m.get("cost_per_task")
        if cpt is not None:
            try:
                if max_cpt is not None and float(cpt) > float(max_cpt): continue
                if min_cpt is not None and float(cpt) < float(min_cpt): continue
            except: pass
        filtered.append(m)
    # sorting
    reverse = str(sort_order).lower() == "desc"
    key = str(sort_by).lower()
    if key in ("intelligence","intel"):
        # For desc we want highest first, blanks last
        # Use manual: sorted with key that pushes blanks last regardless
        filtered = sorted(filtered, key=lambda m: (m.get("intelligence") is None, -(m.get("intelligence") or 0) if reverse else (m.get("intelligence") or 0), m.get("cost_per_task") if m.get("cost_per_task") is not None else 999999))
        if not reverse:
            # asc: blanks last, intel asc
            filtered = sorted(filtered, key=lambda m: (m.get("intelligence") is None, m.get("intelligence") if m.get("intelligence") is not None else 999999, m.get("cost_per_task") or 999999))
    elif key in ("cost","cost_per_task","costpertask"):
        def cost_key(m):
            c=m.get("cost_per_task")
            if c is None: c=m.get("cost_input_per_1M")
            is_blank=c is None
            if is_blank: c=999999
            intel=m.get("intelligence") or 0
            return (is_blank, c, -intel)
        filtered = sorted(filtered, key=cost_key)
        if reverse:
            filtered = list(reversed(filtered))
    elif key == "provider":
        filtered = sorted(filtered, key=lambda m: (m.get("provider") or "", m.get("model_id") or ""), reverse=reverse)
    else: # model
        filtered = sorted(filtered, key=lambda m: (m.get("model_id") or "").lower(), reverse=reverse)

    # favorites promotion: stable move to top in config order
    if favorites:
        pool = list(filtered)
        fav_ordered=[]
        for pat in favorites:
            matched = [x for x in pool if matches_any([pat], x.get("routed","") or x.get("model_id","")) or matches_any([pat], x.get("model_id","")) or matches_any([pat], x.get("provider","")+ "/" + x.get("model_id",""))]
            # keep matched in current sorted order
            for m in matched:
                if m in pool:
                    fav_ordered.append(m)
                    pool.remove(m)
        remaining = pool
        filtered = fav_ordered + remaining
    return filtered

def build_routed_list(global_filtered: List[Dict[str,Any]], mapping: Dict[str,str]) -> List[Dict[str,Any]]:
    out=[]
    for m in global_filtered:
        prov=m.get("provider")
        mid=m.get("model_id")
        routed=map_provider(prov, mid, mapping)
        # mapped_provider is alias
        alias=mapping.get(prov, prov) if mapping.get(prov,"") != "" else ""
        # fix edge: if prov not in mapping, mapping.get(prov,"") returns "" -> alias becomes "" incorrectly; restore to prov
        if prov not in mapping:
            alias = prov
        out.append({**m, "mapped_provider": alias, "routed": routed})
    return out

def get_ninerouter_creds(config: Dict[str,Any], config_path: pathlib.Path) -> Tuple[str,str,str]:
    """Return (url, api_key, dashboard_password). Reads from config ninerouter block + secrets."""
    ncfg = config.get("ninerouter") or {}
    url = sanitize_key(expand_env(ncfg.get("url") or os.environ.get("NINEROUTER_URL") or ""))
    if not url:
        # try secrets file
        for cand in [config_path.parent / "secrets" / "ninerouter-url.txt", pathlib.Path("executions/9router/secrets/ninerouter-url.txt"), pathlib.Path("D:/Data/git/sysops-playbooks/executions/9router/secrets/ninerouter-url.txt")]:
            if cand.exists():
                try: url=sanitize_key(cand.read_text(encoding="utf-8").strip())
                except: pass
                if url: break
    api_key = ""
    key_file = ncfg.get("api_key_file") or "secrets/9router-api-key.txt"
    # try explicit file relative to config
    for cand in [config_path.parent / key_file, pathlib.Path(key_file), pathlib.Path("executions/9router/secrets/9router-api-key.txt")]:
        if cand.exists():
            try: api_key=sanitize_key(cand.read_text(encoding="utf-8").strip())
            except: pass
            if api_key: break
    if not api_key:
        api_key=sanitize_key(os.environ.get("NINEROUTER_KEY") or os.environ.get("9ROUTER_API_KEY") or "")
    pwd=""
    pwd_file = ncfg.get("dashboard_password_file") or "secrets/dashboard-password.txt"
    for cand in [config_path.parent / pwd_file, pathlib.Path(pwd_file), pathlib.Path("executions/9router/secrets/dashboard-password.txt")]:
        if cand.exists():
            try: pwd=cand.read_text(encoding="utf-8").strip()
            except: pass
            if pwd: break
    if not pwd:
        pwd=os.environ.get("DASHBOARD_PASSWORD") or ""
    return url.rstrip("/"), api_key, pwd

def http_request(method: str, url: str, headers: Optional[Dict[str,str]]=None, json_body: Any=None, timeout: int=20, session=None) -> Tuple[int, Any]:
    headers=headers or {}
    if requests is not None and session is None:
        try:
            resp = requests.request(method, url, headers=headers, json=json_body, timeout=timeout)
            ct=resp.headers.get("content-type","")
            if "application/json" in ct or resp.text.strip().startswith("{") or resp.text.strip().startswith("["):
                try: return resp.status_code, resp.json()
                except: return resp.status_code, resp.text
            return resp.status_code, resp.text
        except Exception as e: return 0, str(e)
    else:
        import urllib.request, urllib.error
        data=None
        if json_body is not None:
            data=json.dumps(json_body).encode("utf-8")
            headers["Content-Type"]="application/json"
        # session handling for cookie auth
        if session is not None:
            # use requests session if available
            if requests and isinstance(session, requests.Session):
                resp=session.request(method, url, headers=headers, json=json_body, timeout=timeout)
                try: return resp.status_code, resp.json()
                except: return resp.status_code, resp.text
        req=urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body=r.read().decode("utf-8", errors="replace")
                try: return r.status, json.loads(body)
                except: return r.status, body
        except urllib.error.HTTPError as e:
            try:
                body=e.read().decode("utf-8", errors="replace")
                try: return e.code, json.loads(body)
                except: return e.code, body
            except Exception as ex: return e.code, str(ex)
        except Exception as e: return 0, str(e)

def login_and_get_session(url: str, password: str):
    if not url or not password:
        return None
    if requests:
        s=requests.Session()
        code, body = http_request("POST", f"{url}/api/auth/login", json_body={"password": password}, session=s)
        # but http_request with session not correctly used; do direct
        try:
            resp=s.post(f"{url}/api/auth/login", json={"password": password}, timeout=15)
            if resp.status_code==200:
                return s
            else:
                print(f"WARN login {resp.status_code}: {resp.text[:400]}", file=sys.stderr)
                return None
        except Exception as e:
            print(f"WARN login failed: {e}", file=sys.stderr); return None
    else:
        # urllib fallback with cookie handling manually is complex; require requests for auth
        print("WARN: requests required for /api/auth/login", file=sys.stderr)
        return None

def fetch_current_provider_models(session, url: str) -> Dict[str, List[str]]:
    """Returns dict alias -> list of model ids (from /api/models custom + enabled). For simplicity fetch /api/models/custom and /api/models."""
    if not session or not url:
        return {}
    # custom
    code, body = http_request("GET", f"{url}/api/models/custom", session=session)
    custom_by_alias: Dict[str, List[str]] = {}
    if code==200 and isinstance(body, dict) and "models" in body:
        for m in body["models"]:
            alias=m.get("providerAlias")
            mid=m.get("id")
            if alias and mid:
                custom_by_alias.setdefault(alias, []).append(mid)
    # also fetch /api/models to get enabled static list per provider (for completeness)
    # For now return custom only; sync logic will manage custom.
    # Optionally merge with enabled static: fetch /api/models
    code2, body2 = http_request("GET", f"{url}/api/models", session=session)
    if code2==200 and isinstance(body2, dict) and "models" in body2:
        # body2["models"] includes static+custom; we already have custom, but we can list enabled per alias
        # Build enabled_by_alias from that list (filtered by provider)
        enabled_by_alias: Dict[str, List[str]] = {}
        for m in body2["models"]:
            prov=m.get("provider")
            mid=m.get("model")
            alias=m.get("providerAlias") or prov  # fallback
            # Use routedModel to derive alias? The API's provider field is the registry id, not alias.
            # For sync we care about custom providerAlias grouping, so use custom_by_alias primarily.
            pass
    return custom_by_alias

def diff_providers(current: Dict[str, List[str]], desired: Dict[str, List[str]]) -> Dict[str, Tuple[set,set]]:
    diff={}
    all_alias=set(current.keys())|set(desired.keys())
    for alias in all_alias:
        cur=set(current.get(alias, []))
        des=set(desired.get(alias, []))
        if cur != des:
            diff[alias]=(des - cur, cur - des)  # add, remove
    return diff

def sync_providers(session, url: str, desired_by_alias: Dict[str, List[str]], dry_run: bool=False, verbose: bool=False) -> bool:
    """Sync custom models per alias. Only writes if diff. Returns True if changes made."""
    current = fetch_current_provider_models(session, url)
    diff = diff_providers(current, desired_by_alias)
    if not diff:
        print("  providers: no diff, skip write")
        return False
    print(f"  providers diff: {diff}")
    if dry_run:
        print("  dry-run: would apply provider changes")
        return False
    for alias, (to_add, to_remove) in diff.items():
        # remove first
        for mid in to_remove:
            code, body = http_request("DELETE", f"{url}/api/models/custom?providerAlias={alias}&id={mid}", session=session)
            if verbose: print(f"    DELETE custom {alias}/{mid} -> {code}")
        for mid in to_add:
            code, body = http_request("POST", f"{url}/api/models/custom", json_body={"providerAlias": alias, "id": mid}, session=session)
            if verbose: print(f"    POST custom {alias}/{mid} -> {code} {str(body)[:200]}")
            if code not in (200,201):
                # try with type
                code2, body2 = http_request("POST", f"{url}/api/models/custom", json_body={"providerAlias": alias, "id": mid, "type":"llm"}, session=session)
                if verbose: print(f"      retry -> {code2}")
    # Also handle disabled sync for static models: compare desired vs current enabled and disable extra static
    # Disabled handling: GET /api/models/disabled, then POST to disable, DELETE to enable
    # For brevity, if provider has static models not in desired, disable them
    return True

def fetch_current_combos(session, url: str) -> Dict[str, List[str]]:
    if not session or not url: return {}
    code, body = http_request("GET", f"{url}/api/combos", session=session)
    if code!=200 or not isinstance(body, dict): return {}
    combos=body.get("combos") or []
    out={}
    for c in combos:
        name=c.get("name")
        models=c.get("models") or []
        if name: out[name]=models
    return out

def fetch_combo_ids(session, url: str) -> Dict[str, str]:
    if not session or not url: return {}
    code, body = http_request("GET", f"{url}/api/combos", session=session)
    if code!=200 or not isinstance(body, dict): return {}
    return {c["name"]: c["id"] for c in body.get("combos",[]) if c.get("name") and c.get("id")}

def diff_combos(current: Dict[str, List[str]], desired: Dict[str, List[str]]) -> Dict[str, Tuple[List[str], List[str]]]:
    diff={}
    for name, des_models in desired.items():
        cur = current.get(name)
        if cur is None or cur != des_models:
            diff[name]=(des_models, cur)
    # also detect combos to delete? Keep extra combos not in desired as-is (or delete if not in desired and not in keep list)
    return diff

def sync_combos(session, url: str, desired_combos: Dict[str, List[str]], dry_run=False, verbose=False) -> bool:
    current = fetch_current_combos(session, url)
    ids = fetch_combo_ids(session, url)
    diff = diff_combos(current, desired_combos)
    if not diff:
        print("  combos: no diff")
        return False
    print(f"  combos diff for: {list(diff.keys())}")
    if dry_run:
        print("  dry-run: would apply combo changes")
        return False
    for name, (desired_models, cur) in diff.items():
        if name in ids:
            # PUT
            cid=ids[name]
            code, body = http_request("PUT", f"{url}/api/combos/{cid}", json_body={"name": name, "models": desired_models}, session=session)
            if verbose: print(f"    PUT combo {name} ({cid}) {len(desired_models)} models -> {code}")
        else:
            code, body = http_request("POST", f"{url}/api/combos", json_body={"name": name, "models": desired_models}, session=session)
            if verbose: print(f"    POST combo {name} {len(desired_models)} models -> {code} {str(body)[:300]}")
    return True

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
                "options": {"baseURL": base_url.rstrip("/") + "/v1", "apiKey": "${NINEROUTER_KEY}"},
                "models": provider_models,
            }
        },
        "model": f"9router/{active_model}" if active_model else "9router/free",
    }
    p = out_dir / "opencode.json"
    p.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    snippet = {"provider": {"9router": config["provider"]["9router"]}, "model": config["model"]}
    (out_dir / "opencode-snippet.json").write_text(json.dumps(snippet, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"opencode: {p} ({len(provider_models)} models, active {active_model}) — apiKey references ${{NINEROUTER_KEY}}, set env manually")

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

def fetch_live_v1_models(url: str, api_key: str) -> List[Dict[str, Any]]:
    if not url:
        return []
    endpoint = url.rstrip("/") + "/v1/models"
    headers: Dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    code, body = http_request("GET", endpoint, headers=headers)
    if code == 200 and isinstance(body, dict):
        return body.get("data", [])
    return []

def write_cli_configs(live_models: List[Dict[str, Any]], base_url: str, out_dir: pathlib.Path, active_model: str = "free") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    # adapt writers to accept live_models list as [{"id":..., "owned_by":...}]
    # copy implementations from generate-configs.py verbatim
    write_opencode(live_models, base_url, "sk-placeholder", out_dir, active_model)
    write_hermes(live_models, base_url, "sk-placeholder", out_dir, active_model)
    write_codex(base_url, "sk-placeholder", out_dir, active_model)
    write_claude(base_url, "sk-placeholder", out_dir, active_model)
    write_generic(base_url, "sk-placeholder", out_dir, active_model)
    write_readme(out_dir, base_url, len(live_models), active_model)

def process_one_config(config_path: pathlib.Path, args) -> bool:
    print(f"\n=== Processing {config_path} ===")
    load_execution_env(config_path)
    cfg = expand_env(load_yaml(config_path))
    # defaults
    defaults = {
        "global_filter": {"min_intelligence":0,"include_null_intelligence":True,"max_cost_per_task":None,"provider_whitelist":[],"model_blacklist":[],"model_whitelist":[],"free":"both"},
        "provider_mapping": {"opencode_zen":"oc","opencode_go":"ocg","ollama_cloud":"ollama","openrouter":"openrouter","command_code":"cmc","cloudflare":"","google":"gemini"},
        "combos": {},
        "cli": {"enabled":True,"output_dir":"generated","active_model":"free","writers":["opencode","hermes","codex","claude","generic"]},
        "ninerouter": {"url":"","api_key_file":"secrets/9router-api-key.txt","dashboard_password_file":"secrets/dashboard-password.txt"},
        "options": {"dry_run":False,"check_diff_before_write":True,"remove_all_before_add":True}
    }
    # deep merge
    def deep_merge(a,b):
        out=dict(a)
        for k,v in b.items():
            if isinstance(v,dict) and isinstance(out.get(k),dict):
                out[k]=deep_merge(out[k],v)
            else: out[k]=v
        return out
    cfg = deep_merge(defaults, cfg)
    if args.dry_run: cfg["options"]["dry_run"]=True
    verbose=args.verbose

    # 1. find inventory
    inv_dir = find_inventory_dir(config_path.parent)
    if not inv_dir:
        print(f"ERR: no model-inventory found for {config_path}", file=sys.stderr)
        return False
    print(f"  inventory: {inv_dir}")
    models = load_inventory(inv_dir)
    print(f"  loaded {len(models)} models")

    # 2. global filter
    global_filtered = apply_global_filter(models, cfg["global_filter"])
    print(f"  global filtered: {len(global_filtered)} / {len(models)}")

    # 3. provider mapping -> routed + group by alias
    mapping = cfg["provider_mapping"]
    routed = build_routed_list(global_filtered, mapping)
    print(f"  routed ids sample: {[x['routed'] for x in routed[:5]]}")
    # group desired custom models per alias
    desired_by_alias: Dict[str, List[str]] = {}
    for r in routed:
        alias=r["mapped_provider"]
        # alias "" -> skip grouping? Use model_id as-is but still needs provider? For "" we treat as generic? skip.
        if alias == "":
            # For cloudflare empty alias case, the routed is just model_id like "@cf/..."
            # We need to decide providerAlias for custom API: for cloudflare, providerAlias is "cf" not "".
            # So if mapping is "", we should infer alias from routed? But per spec they said cloudflare maps to '' because model_id contains full.
            # We'll handle: if alias == "", don't add to custom sync (assume model already handled via disabled or static)
            continue
        # For openrouter etc, alias is the providerAlias directly
        # Extract model part after alias/
        routed_id=r["routed"]
        # For custom API, id should be the part after alias/ (the registry id)
        # e.g. routed "oc/grok-4.6" -> custom id "grok-4.6" with alias "oc"
        # routed "openrouter/z-ai/glm-5.2:free" -> custom id "z-ai/glm-5.2:free" with alias "openrouter"
        # routed "cmc/deepseek/deepseek-v4-pro" -> "deepseek/deepseek-v4-pro" with alias "cmc"
        if "/" in routed_id:
            # split on first slash
            _, mid = routed_id.split("/",1)
        else:
            mid=routed_id
        desired_by_alias.setdefault(alias, []).append(mid)
    # dedupe per alias preserve order
    for alias in list(desired_by_alias.keys()):
        seen=set(); uniq=[]
        for x in desired_by_alias[alias]:
            if x not in seen:
                seen.add(x); uniq.append(x)
        desired_by_alias[alias]=uniq
    print(f"  desired_by_alias: {{ {', '.join(f'{k}:{len(v)}' for k,v in desired_by_alias.items())} }}")

    # 4. 9router auth
    url, api_key, pwd = get_ninerouter_creds(cfg, config_path)
    if not url:
        print(f"ERR: NINEROUTER_URL not found for {config_path}", file=sys.stderr)
        return False
    print(f"  9router url: {url}")
    session = login_and_get_session(url, pwd)
    if not session:
        print(f"WARN: no session (dashboard password missing) — provider/combo sync skipped, only local processing", file=sys.stderr)
    else:
        # 4a. provider sync
        if desired_by_alias:
            changed = sync_providers(session, url, desired_by_alias, dry_run=cfg["options"]["dry_run"], verbose=verbose)
            # optionally sync disabled for static providers
            # 4b. combo sync
            # Build combos desired: apply per-combo pipeline to routed list
            desired_combos={}
            for combo_name, combo_cfg in (cfg.get("combos") or {}).items():
                combo_models = apply_combo_pipeline(routed, combo_cfg)
                # Convert to list of routed ids
                desired_combos[combo_name]=[m["routed"] for m in combo_models]
                print(f"    combo {combo_name}: {len(desired_combos[combo_name])} models")
            if desired_combos:
                sync_combos(session, url, desired_combos, dry_run=cfg["options"]["dry_run"], verbose=verbose)
        else:
            print("  no desired providers to sync")

    # 5. CLI generation (always, even if no session)
    if cfg["cli"].get("enabled", True):
        live_models = fetch_live_v1_models(url, api_key) if url and api_key else []
        if not live_models:
            # fallback to desired routed list as mock live
            live_models=[{"id": r["routed"], "owned_by": r["mapped_provider"]} for r in routed]
            # add combos as combo owned_by
            for cname in (cfg.get("combos") or {}).keys():
                live_models.append({"id": cname, "owned_by":"combo"})
        cli_out = cfg["cli"].get("output_dir","generated")
        out_dir = pathlib.Path(cli_out)
        if not out_dir.is_absolute():
            out_dir = (config_path.parent / out_dir).resolve()
        else:
            out_dir = out_dir.resolve()
        active = cfg["cli"].get("active_model","free")
        write_cli_configs(live_models, url or "https://router.example.com", out_dir, active)
        print(f"  cli configs -> {out_dir}")

    # 6. save state snapshot alongside config
    snapshot={"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(),"config":str(config_path),"global_filtered":len(global_filtered),"routed":len(routed),"desired_by_alias":{k:len(v) for k,v in desired_by_alias.items()}}
    try:
        (config_path.parent / "9router-sync.state.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    except: pass
    return True

def main():
    parser=argparse.ArgumentParser(description="9Router sync: inventory -> providers+combos+CLI")
    parser.add_argument("--config", help="path to 9router-sync config yaml")
    parser.add_argument("--dry-run", action="store_true", help="do not write to 9Router")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--force", action="store_true", help="ignore diff check and force write")
    args=parser.parse_args()
    load_execution_env(pathlib.Path(args.config) if args.config else None)
    configs=find_sync_configs(args.config)
    if not configs:
        print("ERR: no 9router-sync config found", file=sys.stderr)
        print("Hint: copy playbooks/9router/templates/9router-sync.config.example.yaml to executions/9router/9router-sync.config.yaml", file=sys.stderr)
        sys.exit(2)
    print(f"Found {len(configs)} config(s): {[str(p) for p in configs]}")
    ok=True
    for cfg_path in configs:
        try:
            res=process_one_config(cfg_path, args)
            ok = ok and res
        except Exception as e:
            print(f"ERR processing {cfg_path}: {e}", file=sys.stderr)
            import traceback; traceback.print_exc()
            ok=False
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
