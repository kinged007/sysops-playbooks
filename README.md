# SysOps Playbook Repository

[![CI](https://github.com/kinged007/sysops-playbooks/actions/workflows/ci.yml/badge.svg)](https://github.com/kinged007/sysops-playbooks/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](pyproject.toml)

Reusable SysOps runbooks executed by agents under a strict read-only-by-default permission model.

> Agent-operated runbooks for repeatable server work — fleet setup, migrations, service configuration, and hardening — with a safety doctrine that keeps production read-only until the operator explicitly allows writes. See `AGENTS.md` §1 for the full permission model.

## What it is

This repo stores **procedures, not state**. Each playbook is one subject — e.g. `coder-remote-servers`, `netdata-monitoring`, `9router` — as a canonical, copy-paste executable procedure with placeholder values only, plus templates, scripts, and lessons learned. Nothing committed contains real IPs, hostnames, or credentials. Real values live in a **persistent, gitignored execution folder** (`executions/<playbook>[-<suffix>]/`) that survives across sessions so the agent reuses secrets and history.

Browse **[`playbooks/`](playbooks/)** for available procedures. Seven playbooks are included.

## Install

No install step. Clone and read the playbook you need:

```bash
git clone https://github.com/kinged007/sysops-playbooks
cd sysops-playbooks
# Optional: Python tooling for 9router sync checks
pip install pyyaml requests
```

## Usage

1. Pick a playbook in `playbooks/<name>/` and read its `README.md` and `notes/`.
2. Ask the agent to run it (e.g. "run `netdata-monitoring` on host `<ALIAS>`").
3. The agent discovers existing `executions/<playbook>*` folders, asks whether to reuse one or create a new variant (`-<suffix>`), presents a plan with every production **WRITE** flagged, and waits for approval.
4. On approval the operator sets the permission mode: **A** per-write confirm (default) or **B** plan-as-approved.

See `AGENTS.md` for the full execution lifecycle (seven gates plus discovery) and committing rules.

### Worked example — agent running a playbook under the permission model

Playbook: `netdata-monitoring`. Target: host alias `node-a` (key in `~/.ssh/config`). Prior run exists at `executions/netdata-monitoring/`.

```
Operator:  run netdata-monitoring on node-a

Agent:     Reading playbooks/netdata-monitoring/notes/gotchas.md (G1–G18).
           Found executions/netdata-monitoring/ — reuse this variant or create a new one?
Operator:  reuse it
Agent:     Loaded inventory.md (previous hostname: old-host) + secrets/.
           Plan (reads free, writes flagged WRITE):

             1. Discover current state                    [reads]
             2. Hostname decision — ask operator            [WRITE if renaming]
             3. Exposure check :19999                      [read]
             4. Harden bearer token + restart netdata     [WRITE]
             5. Emit mcp/<alias>.mcp.json artifact        [local, no prod write]
           Permission mode? A (confirm each WRITE) or B (plan-as-approved)
Operator:  Mode A. Approve steps 1–3 only for now; don't restart yet.

Agent:     [reads] netdata -v / claim / repolist / curl :19999 -> API open (v2.1.3, unclaimed)
           [WRITE] May I run `sudo hostnamectl set-hostname <NEW_HOSTNAME>` on node-a?
Operator:  yes, proceed
Agent:     hostname set; logged to logs/2026-10-15T1200-02-hostname.log (append-only)
           Discovery done. Writes paused at step 4 per approval — awaiting next go.
           Findings appended to notes.md; promotion to playbook notes proposed.
```

Key properties visible: prior state reuse (no re-asking for secrets), every production write flagged and confirmed, read/write separation, append-only logs, and the operator in control of scope.

## How it is tested

- Unit tests in `tests/scripts/` validate the sync logic for the `9router` playbook (model inventory, provider mapping, combo pipeline, config generation, dry-run guards).
- CI runs on every push and pull request to `master`:

```bash
# run locally
pip install pyyaml requests pytest ruff mypy   # or: pip install -e . (once published)
pytest -q
ruff check .
mypy .
```

The `playbooks/` scripts are legacy helpers excluded from lint/type gates — tracked separately. See `pyproject.toml`.

## Repository layout

```
playbooks/              ← static, reusable procedures (committed)
  _playbook-template/      skeleton for authoring new playbooks
  <name>/                  one folder per subject: README, playbook.md,
                            plan/runbook templates, templates/, scripts/,
                            notes/
executions/             ← persistent per-variant state (GITIGNORED)
  <playbook>/              default variant
    plan.md  runbook.md  inventory.md  notes.md  secrets/  logs/
  <playbook>-<suffix>/     additional variant (e.g. -personal vs -company)
docs/superpowers/       ← design specs for execution restructuring
```

`AGENTS.md` is the admin guide: safety doctrine, execution lifecycle, folder discipline, and publishability rules. Agents read it before touching anything.

## Contributing a playbook

Copy `playbooks/_playbook-template/`, fill in `README.md` (what/why/risk/servers + "Agent: read `notes/` BEFORE any run"), `playbook.md` (procedure with `WRITE` flags + rollback), templates and scripts. Promote lessons from `executions/<playbook>/notes.md` into `playbooks/<playbook>/notes/` after the run with operator approval. See `AGENTS.md` §6.

## License

MIT — see [LICENSE](LICENSE).
