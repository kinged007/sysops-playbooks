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
