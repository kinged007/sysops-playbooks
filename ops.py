"""ops: fleet admin CLI (init, fleet, ssh, exec, log, inbox, wake, incident, secret, doctor)."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
from pathlib import Path

try:
    import requests
    import yaml
except ImportError as exc:
    sys.exit(f"ops: missing Python module '{exc.name}'; install with: pip install pyyaml requests")

ROOT = Path(__file__).resolve().parent
if not (ROOT / "AGENTS.md").exists() and not (ROOT / ".agents").is_dir():
    sys.exit("ops: ops must be installed editable: uv tool install --editable <repo>")
FLEET_FILES = ["servers", "sites", "services", "providers", "notify"]
SEVERITIES = ["info", "warn", "crit"]
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")
LEAK = re.compile(
    r"tskey-|BEGIN (?:[A-Z]+ )?PRIVATE KEY|BEGIN CERTIFICATE|AKIA[0-9A-Z]{16}|sk-ant-|ghp_"
)
PLACEHOLDER = re.compile(r"^(<.*>|CHANGE_?ME|TODO|)$", re.I)
HOOKS_PATH_KEY = "core.hooksPath"
MIN_SECRET_LINE = 6

DEFAULTS: dict[str, dict] = {
    "wake": {
        "agent_cmd": "claude",
        "model": "claude-sonnet-5-5",
        "flags": ["-p"],
        "prompt": "Process incidents/inbox.md per AGENTS.md and report via notify target.",
        "inbox": "incidents/inbox.md",
        "lock": ".ops-wake.lock",
        "state": ".ops-wake.state",
        "path": "/usr/local/bin:/usr/bin:/bin",
        "notify": "operator",
    },
    "inbox": {"sources": ["cron", "netdata", "uptime", "webhook", "operator"]},
    "vault": {"rotation_days": 90},
}


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def load_config() -> dict:
    cfg = {k: dict(v) for k, v in DEFAULTS.items()}
    path = ROOT / "ops.config.yaml"
    if path.exists():
        for key, val in (yaml.safe_load(path.read_text()) or {}).items():
            cfg.setdefault(key, {}).update(val or {})
    return cfg


def load_fleet(name: str) -> list[dict]:
    path = ROOT / "fleet" / f"{name}.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text()) or []
    if not isinstance(data, list):
        raise ValueError(f"{path.name}: expected a list of records")
    return data


def find_record(name: str, rec: str) -> dict:
    for item in load_fleet(name):
        if item.get("name") == rec:
            return item
    raise SystemExit(f"ops: no record '{rec}' in fleet/{name}.yaml")


def parse_env_file(path: Path) -> dict[str, str]:
    env = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip("\"'")
    return env


# shortcut: vault is plaintext 0600 files; upgrade is sops + age with the key outside the workspace.
def vault_value(name: str) -> str:
    path = ROOT / "vault" / f"{name}.env"
    if not path.exists():
        raise SystemExit(f"ops: no vault entry '{name}'")
    values = list(parse_env_file(path).values())
    if not values:
        raise SystemExit(f"ops: vault entry '{name}' has no value")
    return values[0]


def vault_values() -> list[str]:
    values: list[str] = []
    for path in sorted((ROOT / "vault").rglob("*")):
        if path.is_symlink() or not path.is_file() or path.name == "index.yaml":
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        lines = [ln.strip().strip("\"'") for ln in text.split("\n")]
        values += [ln for ln in lines if len(ln) >= MIN_SECRET_LINE]
        if path.suffix == ".env":
            values += [v for v in parse_env_file(path).values() if len(v) >= 4]
    return values


def redact(text: str) -> str:
    for value in sorted(vault_values(), key=len, reverse=True):
        text = text.replace(value, "[REDACTED]")
    return text


def audit(action: str, target: str = "", via: str = "", cmd: str = "", result: str = "ok",
          ref: str = "", actor: str = "") -> None:
    entry = {
        "ts": now().isoformat(),
        "actor": actor or os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown",
        "action": redact(action),
        "target": redact(target),
        "via": via,
        "cmd": redact(cmd),
        "result": result,
        "ref": redact(ref),
    }
    path = ROOT / "logs" / "audit" / f"{now():%Y-%m}.jsonl"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a") as fh:
        fh.write(json.dumps(entry) + "\n")


def perm_problems() -> list[str]:
    vault = ROOT / "vault"
    if not vault.exists():
        return []
    problems = []
    for path in [vault, *vault.rglob("*")]:
        if path.is_symlink():
            continue
        if path.stat().st_mode & 0o077:
            problems.append(f"{path.relative_to(ROOT)}: group/world accessible")
    return problems


def pending_lines(inbox: Path) -> list[str]:
    if not inbox.exists():
        return []
    lines = [ln.strip() for ln in inbox.read_text().split("\n")]
    return [ln for ln in lines if ln and not ln.startswith("#")]


def pending_hash(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def cmd_init(args) -> int:
    (ROOT / "fleet").mkdir(exist_ok=True)
    for name in FLEET_FILES:
        real = ROOT / "fleet" / f"{name}.yaml"
        example = ROOT / "fleet" / f"{name}.example.yaml"
        if not real.exists() and example.exists():
            shutil.copyfile(example, real)
            print(f"created {real.relative_to(ROOT)}")
    config = ROOT / "ops.config.yaml"
    config_example = ROOT / "ops.config.example.yaml"
    if not config.exists() and config_example.exists():
        shutil.copyfile(config_example, config)
        print("created ops.config.yaml")
    vault = ROOT / "vault"
    if not vault.exists():
        vault.mkdir(mode=0o700)
        vault.chmod(0o700)
    index = vault / "index.yaml"
    if not index.exists():
        index.write_text("# names only, never values\n[]\n")
        index.chmod(0o600)
    inbox = ROOT / load_config()["wake"]["inbox"]
    inbox.parent.mkdir(exist_ok=True)
    if not inbox.exists():
        inbox.touch()
    (ROOT / "logs" / "audit").mkdir(parents=True, exist_ok=True)
    (ROOT / "runs").mkdir(exist_ok=True)
    if not os.path.lexists(ROOT / "executions"):
        (ROOT / "executions").symlink_to("runs")
    hooks = subprocess.run(["git", "config", HOOKS_PATH_KEY, ".githooks"], cwd=ROOT,
                           capture_output=True, text=True)
    if hooks.returncode != 0:
        print(f"warning: could not set git hooks path: {hooks.stderr.strip()}")
    for problem in perm_problems():
        print(f"warning: {problem}")
    audit("init")
    print("next: fill fleet/*.yaml and ops.config.yaml with real values, then run `ops doctor`")
    return 0


def fleet_kinds() -> list[str]:
    return sorted(p.name[: -len(".yaml")] for p in (ROOT / "fleet").glob("*.yaml")
                  if not p.name.endswith(".example.yaml"))


def flatten(obj, prefix: str = "") -> list[tuple[str, str]]:
    if isinstance(obj, dict):
        items = [(f"{prefix}.{k}" if prefix else str(k), v) for k, v in obj.items()]
    elif isinstance(obj, list):
        items = [(f"{prefix}[{i}]", v) for i, v in enumerate(obj)]
    else:
        return [(prefix, "" if obj is None else str(obj))]
    out: list[tuple[str, str]] = []
    for path, value in items:
        out += flatten(value, path)
    return out


def search_terms(patterns: list[str]) -> list[str]:
    return [t.strip().lower() for p in patterns for t in p.split("|") if t.strip()]


def matching_paths(record, terms: list[str]) -> list[str]:
    return [path for path, value in flatten(record)
            if any(t in path.lower() or t in value.lower() for t in terms)]


def print_search(groups: list[tuple[str, list[dict]]], patterns: list[str]) -> int:
    terms = search_terms(patterns)
    if not terms:
        print("ops: empty search pattern", file=sys.stderr)
        return 2
    found = 0
    for label, records in groups:
        for rec in records:
            for path in matching_paths(rec, terms):
                print(f"{label}: {rec.get('name', '?')} ({path})")
                found += 1
    return 0 if found else 1


def cmd_fleet_list(args) -> int:
    kinds = fleet_kinds()
    if args.kind is None:
        for kind in kinds:
            print(f"{kind}: {len(load_fleet(kind))}")
        return 0
    if args.kind not in kinds:
        raise SystemExit(f"ops: unknown kind '{args.kind}'; available: {', '.join(kinds)}")
    for rec in load_fleet(args.kind):
        fields = [f"{k}={rec[k]}" for k in ("role", "provider", "client")
                  if isinstance(rec.get(k), (str, int))]
        print(" ".join([str(rec.get("name", "?")), *fields]))
    return 0


def cmd_fleet_search(args) -> int:
    return print_search([(k, load_fleet(k)) for k in fleet_kinds()], args.pattern)


def cmd_fleet_view(args) -> int:
    kinds = fleet_kinds()
    if args.kind not in kinds:
        raise SystemExit(f"ops: unknown kind '{args.kind}'; available: {', '.join(kinds)}")
    records = load_fleet(args.kind)
    rec = next((r for r in records if r.get("name") == args.name), None)
    if rec is None:
        names = ", ".join(str(r.get("name", "?")) for r in records)
        raise SystemExit(f"ops: no record '{args.name}' in fleet/{args.kind}.yaml; "
                         f"available: {names}")
    for path, value in flatten(rec):
        print(f"{path}: {value}")
    return 0


def vault_index() -> list[dict]:
    index = ROOT / "vault" / "index.yaml"
    return (yaml.safe_load(index.read_text()) or []) if index.exists() else []


def cmd_secret_list(args) -> int:
    if args.stale:
        return print_stale()
    for entry in vault_index():
        purpose = str(entry.get("purpose") or "")
        purpose = purpose if len(purpose) <= 60 else purpose[:59] + "…"
        print(f"{entry.get('name')}  {entry.get('owner') or '-'}  {purpose}")
    return 0


def cmd_secret_search(args) -> int:
    return print_search([("secrets", vault_index())], args.pattern)


def digest(value: bytes | str) -> str:
    data = value.encode() if isinstance(value, str) else value
    return f"sha256:{hashlib.sha256(data).hexdigest()[:12]}"


def mask(value: str) -> str:
    if len(value) >= 30:
        return f"{value[:5]}…{value[-5:]}"
    if len(value) >= 16:
        return f"…{value[-4:]}"
    return ""


def safe_entry_name(name: str) -> str:
    if not name or Path(name).name != name or name.startswith("."):
        raise SystemExit(f"ops: invalid vault entry name '{name}'")
    return name


def cmd_secret_view(args) -> int:
    name = safe_entry_name(args.name)
    entry = next((e for e in vault_index() if e.get("name") == name), None)
    env_path = ROOT / "vault" / f"{name}.env"
    files_dir = ROOT / "vault" / "files" / name
    if entry is None and not env_path.exists() and not files_dir.is_dir():
        raise SystemExit(f"ops: no vault entry '{name}'")
    for path, value in flatten(entry or {}):
        print(f"{path}: {value}")
    if env_path.exists():
        for key, value in parse_env_file(env_path).items():
            line = f"var {key}: length={len(value)} {digest(value)}"
            print(f"{line} {mask(value)}".rstrip())
    if files_dir.is_dir():
        for item in sorted(files_dir.iterdir()):
            if item.is_file() and not item.is_symlink():
                print(f"file {item.name}: size={item.stat().st_size} {digest(item.read_bytes())}")
    print("Values are never shown in full. "
          "Use `ops secret run` or `ops secret insert` to use them.")
    audit("secret view", target=name)
    return 0


def print_stale() -> int:
    entries = vault_index()
    window = int(load_config()["vault"]["rotation_days"])
    today = now().date()
    stale = 0
    for entry in entries:
        rotated = entry.get("last_rotated")
        expires = entry.get("expires")
        reason = ""
        if not rotated:
            reason = "never rotated"
        elif (today - dt.date.fromisoformat(str(rotated))).days > window:
            reason = f"rotated {rotated}, window {window}d"
        if expires and dt.date.fromisoformat(str(expires)) < today:
            reason = f"expired {expires}"
        if reason:
            stale += 1
            print(f"{entry.get('name')}: {reason}")
    print(f"{stale} stale")
    return 0


def connect_argv(server: dict, via: str | None, extra: list[str]) -> tuple[str, list[str]]:
    blocks = server.get("connect") or []
    block = next((b for b in blocks if via is None or b.get("via") == via), None)
    if block is None:
        raise SystemExit(f"ops: server '{server['name']}' has no connect block for via={via}")
    kind = block.get("via")
    required = {"ssh": ("host", "user", "key"), "coder": ("workspace",),
                "docker-context": ("context",)}
    missing = [f for f in required.get(kind, ()) if not block.get(f)]
    if missing:
        raise SystemExit(f"ops: server '{server['name']}': {kind} block lacks {', '.join(missing)}")
    for field in ("host", "user", "workspace", "context"):
        if str(block.get(field, "")).startswith("-"):
            raise SystemExit(f"ops: server '{server['name']}': invalid {field} value")
    if kind == "ssh":
        argv = ["ssh", "-i", str(ROOT / block["key"]), "-l", block["user"], "--", block["host"]]
    elif kind == "coder":
        argv = ["coder", "ssh", "--", block["workspace"]]
    elif kind == "docker-context":
        argv = ["docker", f"--context={block['context']}"]
    else:
        raise SystemExit(f"ops: server '{server['name']}': unsupported via '{kind}'")
    return kind, argv + extra


def cmd_ssh(args) -> int:
    server = find_record("servers", args.server)
    via, argv = connect_argv(server, args.via, args.cmd)
    audit("ssh", target=args.server, via=via, cmd=" ".join(args.cmd) or "interactive session")
    return subprocess.run(argv).returncode


def vault_env(entries: list[str]) -> dict[str, str]:
    env = dict(os.environ)
    for entry in entries:
        path = ROOT / "vault" / f"{safe_entry_name(entry)}.env"
        if not path.exists():
            raise SystemExit(f"ops: no vault entry '{entry}'")
        env.update(parse_env_file(path))
    return env


def run_with_vault(action: str, entries: list[str], command: str, target: str) -> int:
    if not command.strip():
        raise SystemExit("ops: empty command")
    env = vault_env(entries)
    try:
        proc = subprocess.run(["sh", "-c", command], cwd=ROOT, env=env, capture_output=True,
                              text=True, errors="replace")
    except OSError as exc:
        audit(action, target=target, cmd=command, result="fail")
        print(f"ops: cannot run command: {exc.strerror}", file=sys.stderr)
        return 127
    sys.stdout.write(redact(proc.stdout))
    sys.stderr.write(redact(proc.stderr))
    audit(action, target=target, cmd=command, result="ok" if proc.returncode == 0 else "fail")
    return proc.returncode


def cmd_exec(args) -> int:
    service = find_record("services", args.service)
    return run_with_vault("exec", list(service.get("vault") or []), args.cmd, args.service)


def cmd_secret_run(args) -> int:
    command = args.cmd[1:] if args.cmd[:1] == ["--"] else args.cmd
    entries = [e for e in args.entries.split(",") if e]
    if not entries:
        raise SystemExit("ops: no vault entries given")
    return run_with_vault("secret run", entries, " ".join(command), ",".join(entries))


def cmd_log(args) -> int:
    if not args.action:
        print("ops: log needs an action or --from-hook", file=sys.stderr)
        return 2
    audit(args.action, target=args.target, result=args.result)
    return 0


def log_from_hook() -> int:
    try:
        data = json.load(sys.stdin)
        command = (data.get("tool_input") or {}).get("command")
        if data.get("tool_name", "Bash") == "Bash" and command:
            failed = data.get("hook_event_name") == "PostToolUseFailure"
            audit("bash", cmd=str(command), result="fail" if failed else "ok",
                  ref=str(data.get("session_id", "")), actor="claude")
    except Exception:
        pass
    return 0


def format_inbox_line(source: str, severity: str, summary: str, sources: list[str]) -> str:
    if source not in sources:
        raise ValueError(f"source must be one of {', '.join(sources)}")
    if severity not in SEVERITIES:
        raise ValueError(f"severity must be one of {', '.join(SEVERITIES)}")
    summary = CONTROL.sub(" ", summary.replace("|", "/")).strip()[:200]
    if not summary:
        raise ValueError("summary is empty")
    return f"{now().isoformat()} | {source} | {severity} | {summary}"


def cmd_inbox_add(args) -> int:
    cfg = load_config()
    try:
        line = format_inbox_line(args.source, args.severity, args.summary, cfg["inbox"]["sources"])
    except ValueError as exc:
        print(f"ops: {exc}", file=sys.stderr)
        return 2
    inbox = ROOT / cfg["wake"]["inbox"]
    inbox.parent.mkdir(exist_ok=True)
    with inbox.open("a") as fh:
        fh.write(line + "\n")
    audit("inbox add", target=args.source, cmd=line)
    return 0


def notify_telegram(name: str, text: str) -> None:
    record = find_record("notify", name)
    token = vault_value(record["token"])
    resp = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         json={"chat_id": record["chat_id"], "text": text}, timeout=15)
    resp.raise_for_status()


def acquire_lock(lock: Path) -> int | None:
    fd = os.open(lock, os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode())
    return fd


def run_agent(argv: list[str], env: dict) -> int:
    try:
        proc = subprocess.Popen(argv, cwd=ROOT, env=env, start_new_session=True)
    except OSError as exc:
        print(f"ops: cannot start agent: {type(exc).__name__}", file=sys.stderr)
        return 127
    try:
        return proc.wait()
    except BaseException:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait()
        raise


def cmd_wake(args) -> int:
    wake = load_config()["wake"]
    inbox = ROOT / wake["inbox"]
    lock = ROOT / wake["lock"]
    state = ROOT / wake["state"]
    pending = pending_lines(inbox)
    if not pending:
        return 0
    previous = signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    lock_fd = acquire_lock(lock)
    if lock_fd is None:
        signal.signal(signal.SIGTERM, previous)
        return 0
    try:
        if not args.force and state.exists() and state.read_text().strip() == pending_hash(pending):
            return 0
        argv = [wake["agent_cmd"]]
        if wake.get("model"):
            argv += ["--model", wake["model"]]
        argv += [*wake["flags"], wake["prompt"]]
        audit("wake start", target=str(len(pending)), cmd=" ".join(argv))
        env = dict(os.environ, PATH=wake["path"])
        rc = 1
        try:
            rc = run_agent(argv, env)
        finally:
            remaining = pending_lines(inbox)
            state.write_text(pending_hash([ln for ln in remaining if ln in pending]))
            audit("wake end", target=str(len(remaining)), result="ok" if rc == 0 else f"exit {rc}")
        if remaining:
            try:
                notify_telegram(wake["notify"],
                                f"ops wake: {len(remaining)} inbox line(s) still pending, "
                                f"agent exit status {rc}")
            except (Exception, SystemExit) as exc:
                print(f"ops: notification failed: {type(exc).__name__}", file=sys.stderr)
        return rc
    finally:
        os.close(lock_fd)
        signal.signal(signal.SIGTERM, previous)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "incident"


def cmd_incident_new(args) -> int:
    inbox = ROOT / load_config()["wake"]["inbox"]
    source_line = ""
    if args.from_inbox:
        lines = inbox.read_text().split("\n") if inbox.exists() else []
        if lines and lines[-1] == "":
            lines.pop()
        matches = [ln for ln in lines if ln.strip() == args.from_inbox.strip()]
        if not matches:
            print("ops: inbox line not found", file=sys.stderr)
            return 2
        source_line = matches[0]
        lines.remove(source_line)
        inbox.write_text("".join(ln + "\n" for ln in lines))
    base = f"{now():%Y-%m-%d}-{slugify(args.title)}"
    folder = ROOT / "incidents" / base
    n = 1
    while folder.exists():
        n += 1
        folder = ROOT / "incidents" / f"{base}-{n}"
    folder.mkdir(parents=True)
    templates = {
        "issue.md": f"# {args.title}\n\nSource: {source_line or 'operator'}\n\n"
                    "## Symptom\n\n## Independent verification\n",
        "plan.md": "# Plan\n\nWrite the plan before any write. Flag each production write WRITE.\n",
        "actions.log": "",
        "resolution.md": "# Resolution\n\n## Fix\n\n## Verification\n\n## Follow-ups\n\n"
                         "What check would have caught this, and does it now run fleet-wide?\n",
    }
    for name, content in templates.items():
        (folder / name).write_text(content)
    audit("incident new", target=folder.name, ref=source_line)
    print(folder.name)
    return 0


def cmd_incident_close(args) -> int:
    found = [p for p in (ROOT / "incidents").iterdir()
             if p.is_dir() and args.id and p.name.startswith(args.id)]
    if len(found) != 1:
        print(f"ops: expected one incident matching '{args.id}', found {len(found)}",
              file=sys.stderr)
        return 2
    with (found[0] / "actions.log").open("a") as fh:
        fh.write(f"{now().isoformat()} closed\n")
    audit("incident close", target=found[0].name)
    return 0


def cmd_secret_check(args) -> int:
    problems = perm_problems()
    scan = [ROOT / "vault" / "index.yaml", ROOT / "ops.config.example.yaml",
            *(ROOT / "fleet").glob("*.example.yaml")]
    for path in scan:
        if path.exists() and LEAK.search(path.read_text()):
            problems.append(f"{path.relative_to(ROOT)}: matches a leak pattern")
    for path in sorted((ROOT / "vault").glob("*.env")):
        for key, value in parse_env_file(path).items():
            if PLACEHOLDER.match(value):
                problems.append(f"{path.relative_to(ROOT)}: {key} is empty or a placeholder")
    for problem in problems:
        print(problem)
    print(f"{len(problems)} problem(s)")
    return 1 if problems else 0


def cmd_secret_fingerprint(args) -> int:
    value = vault_value(args.name)
    dig = digest(value)
    if len(value) >= 16:
        print(f"{dig} last4:{value[-4:]}")
    else:
        print(f"{dig} (value is short, last characters not shown)")
    audit("secret fingerprint", target=args.name)
    return 0


ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
GH_REPO = re.compile(r"^[\w.-]+/[\w.-]+$")
INSERT_PREFIXES = ("host", "github", "file")


def upsert_env(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    pattern = re.compile(rf"^\s*(export\s+)?{re.escape(key)}=")
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def parse_target(target: str) -> tuple[str, list[str]]:
    kind, _, rest = target.partition(":")
    if kind not in INSERT_PREFIXES:
        raise SystemExit(f"ops: unsupported target '{target}'; use host:<server>:<abs path>, "
                         "github:<owner/repo>:<NAME> or file:<path>")
    parts = [rest] if kind == "file" else rest.split(":", 1)
    if len(parts) != (1 if kind == "file" else 2) or not all(parts):
        raise SystemExit(f"ops: malformed target '{target}'")
    if kind == "host" and (not parts[1].startswith("/") or "\n" in parts[1]):
        raise SystemExit(f"ops: host target needs an absolute path: '{target}'")
    if kind == "github" and not (GH_REPO.match(parts[0]) and ENV_KEY.match(parts[1])):
        raise SystemExit(f"ops: malformed github target '{target}'")
    return kind, parts


def pick_var(env: dict[str, str], var: str | None, name: str) -> str:
    if var:
        if var not in env:
            raise SystemExit(f"ops: entry '{name}' has no variable '{var}'; has: {', '.join(env)}")
        return var
    if len(env) != 1:
        raise SystemExit(f"ops: entry '{name}' has {len(env)} variables, "
                         f"use --var: {', '.join(env)}")
    return next(iter(env))


def remote_argv(server_name: str, script: str) -> list[str]:
    server = find_record("servers", server_name)
    via = next((b.get("via") for b in server.get("connect") or []
                if b.get("via") in ("ssh", "coder")), None)
    return connect_argv(server, via, [f"sh -c {shlex.quote(script)}"])[1]


def write_local_env(path: Path, key: str, value: str) -> None:
    existing = path.read_text() if path.exists() else ""
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(upsert_env(existing, key, value))
    tmp.chmod(mode)
    os.replace(tmp, path)


def insert_host(server: str, path: str, key: str, value: str) -> str:
    quoted = shlex.quote(path)
    read = subprocess.run(remote_argv(server, f"test -f {quoted} && cat {quoted}"),
                          capture_output=True, text=True, errors="replace")
    if read.returncode not in (0, 1):
        return f"cannot read {path}: {redact(read.stderr).strip()}"
    tmp = shlex.quote(path + ".tmp")
    script = (f"umask 077; cat > {tmp} && {{ if [ -e {quoted} ]; "
              f"then chmod --reference={quoted} {tmp}; fi; mv {tmp} {quoted}; }}")
    write = subprocess.run(remote_argv(server, script), input=upsert_env(read.stdout, key, value),
                           capture_output=True, text=True, errors="replace")
    return "" if write.returncode == 0 else f"write failed: {redact(write.stderr).strip()}"


def insert_github(repo: str, name: str, value: str) -> str:
    proc = subprocess.run(["gh", "secret", "set", name, "--repo", repo], input=value,
                          capture_output=True, text=True, errors="replace")
    return "" if proc.returncode == 0 else f"gh failed: {redact(proc.stderr).strip()}"


def insert_one(target: str, var: str, value: str) -> str:
    kind, parts = parse_target(target)
    try:
        if kind == "host":
            return insert_host(parts[0], parts[1], var, value)
        if kind == "github":
            return insert_github(parts[0], parts[1], value)
        write_local_env(Path(parts[0]).expanduser(), var, value)
    except OSError as exc:
        return f"{type(exc).__name__}: {exc.strerror}"
    return ""


def cmd_secret_insert(args) -> int:
    name = safe_entry_name(args.entry)
    if bool(args.target) == args.all:
        raise SystemExit("ops: give exactly one of <target> or --all")
    env_path = ROOT / "vault" / f"{name}.env"
    if not env_path.exists():
        raise SystemExit(f"ops: no vault entry '{name}'")
    env = parse_env_file(env_path)
    var = pick_var(env, args.var, name)
    value = env[var]
    if "\n" in value or "\r" in value:
        raise SystemExit(f"ops: variable '{var}' is not a single line")
    if args.all:
        entry = next((e for e in vault_index() if e.get("name") == name), None) or {}
        targets = [t for t in entry.get("used_by") or [] if t.partition(":")[0] in INSERT_PREFIXES]
        if not targets:
            raise SystemExit(f"ops: entry '{name}' has no insertable used_by targets")
    else:
        targets = [args.target]
    for target in targets:
        parse_target(target)
    if args.dry_run:
        for target in targets:
            print(f"would insert {var} into {target}")
        return 0
    failed = 0
    for target in targets:
        error = insert_one(target, var, value)
        audit("secret insert", target=target, cmd=f"var={var} {digest(value)}",
              result="fail" if error else "ok")
        print(f"fail {target}: {error}" if error else f"ok {target}")
        failed += bool(error)
    return 1 if failed else 0


def cmd_doctor(args) -> int:
    problems = perm_problems()
    for name in FLEET_FILES:
        try:
            load_fleet(name)
        except Exception as exc:
            problems.append(f"fleet/{name}.yaml: {exc}")
        if not (ROOT / "fleet" / f"{name}.yaml").exists():
            problems.append(f"fleet/{name}.yaml: missing (run ops init)")
    index = ROOT / "vault" / "index.yaml"
    try:
        entries = (yaml.safe_load(index.read_text()) or []) if index.exists() else []
        indexed = {e["name"] for e in entries}
        present = {p.stem for p in (ROOT / "vault").glob("*.env")}
        present |= {p.name for p in (ROOT / "vault" / "files").glob("*") if p.is_dir()}
        for entry in entries:
            for fname in entry.get("files") or []:
                path = ROOT / "vault" / "files" / entry["name"] / fname
                if Path(fname).name != fname or not path.is_file():
                    problems.append(f"vault: {entry['name']} lists missing file '{fname}'")
        problems += [f"vault: {n} indexed but no file" for n in sorted(indexed - present)]
        problems += [f"vault: {n} has a file but no index entry" for n in sorted(present - indexed)]
    except Exception as exc:
        problems.append(f"vault/index.yaml: {exc}")
    hooks = subprocess.run(["git", "config", HOOKS_PATH_KEY], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip()
    if hooks != ".githooks":
        problems.append("git hooks: hooks path is not .githooks (run ops init)")
    elif not (ROOT / ".githooks" / "pre-commit").exists():
        problems.append("git hooks: .githooks/pre-commit missing")
    for problem in problems:
        print(problem)
    print("ok" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ops")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init").set_defaults(func=cmd_init)
    fleet = sub.add_parser("fleet").add_subparsers(dest="sub", required=True)
    p = fleet.add_parser("list")
    p.add_argument("kind", nargs="?")
    p.set_defaults(func=cmd_fleet_list)
    p = fleet.add_parser("search")
    p.add_argument("pattern", nargs="+")
    p.set_defaults(func=cmd_fleet_search)
    p = fleet.add_parser("view")
    p.add_argument("kind")
    p.add_argument("name")
    p.set_defaults(func=cmd_fleet_view)
    p = sub.add_parser("ssh")
    p.add_argument("server")
    p.add_argument("--via")
    p.add_argument("cmd", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_ssh)
    p = sub.add_parser("exec")
    p.add_argument("service")
    p.add_argument("cmd")
    p.set_defaults(func=cmd_exec)
    p = sub.add_parser("log")
    p.add_argument("action", nargs="?")
    p.add_argument("--from-hook", action="store_true", help="read a Claude Code hook JSON on stdin")
    p.add_argument("--target", default="")
    p.add_argument("--result", choices=["ok", "fail"], default="ok")
    p.set_defaults(func=cmd_log)
    inbox = sub.add_parser("inbox").add_subparsers(dest="sub", required=True)
    p = inbox.add_parser("add")
    p.add_argument("source")
    p.add_argument("severity")
    p.add_argument("summary")
    p.set_defaults(func=cmd_inbox_add)
    p = sub.add_parser("wake")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_wake)
    inc = sub.add_parser("incident").add_subparsers(dest="sub", required=True)
    p = inc.add_parser("new")
    p.add_argument("title")
    p.add_argument("--from-inbox")
    p.set_defaults(func=cmd_incident_new)
    p = inc.add_parser("close")
    p.add_argument("id")
    p.set_defaults(func=cmd_incident_close)
    sec = sub.add_parser("secret").add_subparsers(dest="sub", required=True)
    sec.add_parser("check").set_defaults(func=cmd_secret_check)
    p = sec.add_parser("list")
    p.add_argument("--stale", action="store_true")
    p.set_defaults(func=cmd_secret_list)
    p = sec.add_parser("search")
    p.add_argument("pattern", nargs="+")
    p.set_defaults(func=cmd_secret_search)
    p = sec.add_parser("view")
    p.add_argument("name")
    p.set_defaults(func=cmd_secret_view)
    p = sec.add_parser("run")
    p.add_argument("entries")
    p.add_argument("cmd", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_secret_run)
    p = sec.add_parser("insert")
    p.add_argument("entry")
    p.add_argument("target", nargs="?")
    p.add_argument("--var")
    p.add_argument("--all", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_secret_insert)
    p = sec.add_parser("fingerprint")
    p.add_argument("name")
    p.set_defaults(func=cmd_secret_fingerprint)
    sub.add_parser("doctor").set_defaults(func=cmd_doctor)
    return parser


def hoist_via(argv: list[str]) -> list[str]:
    """argparse.REMAINDER would pass `--via X` after the server name to the remote command."""
    if len(argv) > 2 and argv[0] == "ssh" and not argv[1].startswith("-"):
        if argv[2] == "--via" and len(argv) > 3:
            return ["ssh", *argv[2:4], argv[1], *argv[4:]]
        if argv[2].startswith("--via="):
            return ["ssh", argv[2], argv[1], *argv[3:]]
    return argv


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["log", "--from-hook"]:
        return log_from_hook()
    args = build_parser().parse_args(hoist_via(argv))
    if args.command not in ("init", "doctor"):
        problems = perm_problems()
        if problems:
            print("ops: refusing to run, fix permissions (chmod go-rwx):", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
    try:
        return args.func(args)
    except (ValueError, OSError, yaml.YAMLError) as exc:
        print(f"ops: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
