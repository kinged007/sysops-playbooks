import pathlib
import sys
import tempfile
import importlib.util

# Shim: make playbooks/9router/scripts/9router-sync.py importable as
# playbooks_9router_scripts_9router_sync (handles hyphen and leading digit)
_MODULE_NAME = "playbooks_9router_scripts_9router_sync"
# Try multiple locations for the scaffold file
_candidates = [
    pathlib.Path(__file__).resolve().parents[2] / "playbooks" / "9router" / "scripts" / "9router-sync.py",
    pathlib.Path("playbooks/9router/scripts/9router-sync.py"),
    pathlib.Path("D:/Data/git/sysops-playbooks/playbooks/9router/scripts/9router-sync.py"),
]
_TARGET = None
for _c in _candidates:
    try:
        if _c.exists():
            _TARGET = _c
            break
    except Exception:
        continue
if _TARGET is not None and _TARGET.exists() and _MODULE_NAME not in sys.modules:
    try:
        _spec = importlib.util.spec_from_file_location(_MODULE_NAME, _TARGET)
        if _spec and _spec.loader:
            _mod = importlib.util.module_from_spec(_spec)
            sys.modules[_MODULE_NAME] = _mod
            _spec.loader.exec_module(_mod)
    except Exception:
        # Let import fail inside test so RED is visible
        if _MODULE_NAME in sys.modules:
            del sys.modules[_MODULE_NAME]
        pass


def test_find_configs_discovers_execution_variant():
    from playbooks_9router_scripts_9router_sync import find_sync_configs
    # should return list, not crash, when no config exists
    with tempfile.TemporaryDirectory() as td:
        configs = find_sync_configs(search_root=pathlib.Path(td))
        assert configs == []


def test_load_inventory_and_map(tmp_path):
    import json, pathlib
    from playbooks_9router_scripts_9router_sync import load_inventory, map_provider
    inv_dir = tmp_path / "model-inventory"
    inv_dir.mkdir()
    data = {"count":2,"models":[
        {"provider":"opencode_zen","model_id":"grok-4.6","intelligence":60.9,"cost_per_task":0.93,"free":False},
        {"provider":"google","model_id":"gemini-3.7-flash","intelligence":56.0,"cost_per_task":0.4,"free":False},
    ]}
    (inv_dir / "models.json").write_text(json.dumps(data), encoding="utf-8")
    models = load_inventory(inv_dir)
    assert len(models)==2
    assert map_provider("opencode_zen","grok-4.6", {"opencode_zen":"oc"}) == "oc/grok-4.6"
    assert map_provider("google","gemini-3.7-flash", {"google":"gemini"}) == "gemini/gemini-3.7-flash"
    # cloudflare empty alias -> as-is, no double prefix
    assert map_provider("cloudflare","@cf/foo", {"cloudflare":""}) == "@cf/foo"
    # already prefixed -> no double
    assert map_provider("openrouter","openrouter/foo:free", {"openrouter":"openrouter"}) == "openrouter/foo:free"


def test_global_filter():
    from playbooks_9router_scripts_9router_sync import apply_global_filter
    models=[
        {"provider":"opencode_zen","model_id":"a","intelligence":60,"cost_per_task":0.12,"free":False},
        {"provider":"google","model_id":"b","intelligence":None,"cost_per_task":0.1,"free":True},
        {"provider":"cloudflare","model_id":"@cf/x","intelligence":10,"cost_per_task":0.01,"free":False},
        {"provider":"opencode_zen","model_id":"transcribe-foo","intelligence":50,"cost_per_task":0.1,"free":False},
    ]
    cfg={
        "min_intelligence":50,
        "include_null_intelligence":False,
        "max_cost_per_task":0.15,
        "provider_whitelist":["opencode_zen","google"],
        "model_blacklist":["*transcribe*"],
        "model_whitelist":[],
        "free":"both"
    }
    out=apply_global_filter(models,cfg)
    # only transcribe excluded, cloudflare excluded by provider whitelist, b excluded by null intelligence
    # Note: original plan had a cost 0.2 with max 0.15 which would incorrectly exclude a; fixed to 0.12 to satisfy filter logic (Deviation Rule 1)
    assert len(out)==1 and out[0]["model_id"]=="a"
    # with include_null True and free both, b passes if cost OK
    cfg["include_null_intelligence"]=True
    out2=apply_global_filter(models,cfg)
    assert any(m["model_id"]=="b" for m in out2)


def test_combo_pipeline():
    from playbooks_9router_scripts_9router_sync import apply_combo_pipeline
    models=[
        {"provider":"oc","model_id":"deepseek-v4-pro","routed":"oc/deepseek-v4-pro","intelligence":53,"cost_per_task":0.26,"free":False},
        {"provider":"oc","model_id":"deepseek-v4-flash","routed":"oc/deepseek-v4-flash","intelligence":51,"cost_per_task":0.11,"free":False},
        {"provider":"openrouter","model_id":"z-ai/glm-5.2:free","routed":"openrouter/z-ai/glm-5.2:free","intelligence":52,"cost_per_task":0.44,"free":True},
        {"provider":"gemini","model_id":"gemini-3.1-pro","routed":"gemini/gemini-3.1-pro","intelligence":47,"cost_per_task":0.33,"free":False},
    ]
    combo_cfg={
        "sort_by":"cost",
        "sort_order":"asc",
        "free":"both",
        "min_intelligence":50,
        "max_cost_per_task":0.5,
        "provider_whitelist":[],
        "provider_blacklist":[],
        "model_whitelist":[],
        "model_blacklist":[],
        "favorites":["deepseek-v4*"]
    }
    out=apply_combo_pipeline(models, combo_cfg)
    # filter min 50 removes gemini 47, cost max 0.5 keeps all others, sort cost asc => flash 0.11, pro 0.26, glm 0.44
    # favorites deepseek* moves both deepseek to top in pattern order, preserving sorted order within pattern
    assert out[0]["routed"]=="oc/deepseek-v4-flash"
    assert out[1]["routed"]=="oc/deepseek-v4-pro"
    assert out[2]["routed"]=="openrouter/z-ai/glm-5.2:free"


def test_ninerouter_auth_helpers_exist():
    from playbooks_9router_scripts_9router_sync import get_ninerouter_creds, http_request, login_and_get_session
    assert callable(get_ninerouter_creds)
    assert callable(http_request)
    assert callable(login_and_get_session)


def test_provider_diff():
    from playbooks_9router_scripts_9router_sync import diff_providers
    current={"oc":["a","b"], "ocg":["x"]}
    desired={"oc":["a","c"], "ocg":["x"]}
    diff=diff_providers(current, desired)
    assert diff=={"oc": ({"c"}, {"b"})}  # to_add, to_remove
    # no diff case
    assert diff_providers(desired, desired)=={}


def test_combo_diff():
    from playbooks_9router_scripts_9router_sync import diff_combos
    current={"free":["a","b"], "coding-low":["x"]}
    desired={"free":["a","c"], "coding-low":["x"]}
    d=diff_combos(current, desired)
    assert "free" in d and "coding-low" not in d
