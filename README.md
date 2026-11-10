# SysOps Workspace

[![CI](https://github.com/kinged007/sysops-playbooks/actions/workflows/ci.yml/badge.svg)](https://github.com/kinged007/sysops-playbooks/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](pyproject.toml)

A DevOps admin workspace for an agent working on servers, sites, and
deployments. It holds a fleet inventory, a credential vault, procedures
(skills), an incident inbox, and a CLI (`ops`). Production is read-only
until the operator allows writes. See `AGENTS.md` for the safety doctrine.

The repo is public. Procedures and tooling are committed with placeholder
values. Real hosts, credentials, and run state stay local and gitignored.

## Public and private

| Path | Contents | Committed? |
|---|---|---|
| `.agents/skills/<name>/` | Procedures: `SKILL.md`, `scripts/`, `templates/`, `references/` | yes |
| `ops.py`, `bin/ops`, `tests/`, `.githooks/`, `.claude/`, `.github/` | CLI, tests, hooks, CI | yes |
| `fleet/*.example.yaml`, `ops.config.example.yaml`, `incidents/inbox.example.md` | Synthetic examples (RFC 5737 IPs, `example.*` domains) | yes |
| `fleet/*.yaml` | Real servers, sites, services, providers, notify channels | no |
| `vault/` | Credentials, ssh keys, and `index.yaml` (names, owners, `used_by`, rotation dates) | no |
| `runs/` | Planned-work state per skill variant | no |
| `incidents/` | Inbox and incident folders | no |
| `logs/audit/` | Local audit trail | no |
| `ops.config.yaml` | Local settings for `ops wake` and the vault | no |

## Quick start

```bash
git clone https://github.com/kinged007/sysops-playbooks
cd sysops-playbooks
uv tool install --editable .   # puts `ops` on PATH (~/.local/bin); must stay editable
ops init                       # creates gitignored files from examples, installs git hooks
```

`bin/ops` runs without the install (needs `pyyaml` and `requests` in the Python
used), for example from cron.

1. Fill `fleet/servers.yaml`, `sites.yaml`, `services.yaml`, `providers.yaml`,
   and `notify.yaml`, using the `*.example.yaml` files as a guide.
2. Put credentials in `vault/<client>-<provider>-<purpose>.env` (`chmod 600`)
   and ssh keys in `vault/ssh/`. List each in `vault/index.yaml`.
3. Edit `ops.config.yaml` (agent command, model, launch flags, notify target).
4. Run `ops doctor` to check the fleet files, vault index, and hooks.

Then ask the agent to run a skill, for example "run `netdata-monitoring` on
`<server>`". The agent finds or creates `runs/<skill>[-<suffix>]/`, proposes a
plan with every production write flagged WRITE, and waits for approval.

## `ops` commands

```
ops init                         scaffold gitignored files, install hooks, check permissions
ops fleet list [<kind>]          kinds with counts, or the record names of one kind
ops fleet search <pattern>...    match values and key paths in all records (| = OR)
ops fleet view <kind> <name>     one record as key.path: value lines
ops ssh <server> [--via V] [cmd] connect with the server's connect block (ssh, coder, docker-context)
ops exec <service> <cmd>         run `sh -c <cmd>` with the service's vault entries in env (output redacted)
ops log "<action>" [--target X] [--result ok|fail]
                                 append an audit log line
ops log --from-hook              read a Claude Code hook JSON on stdin and log the Bash command
ops inbox add <source> <severity> "<summary>"
                                 append a validated line to incidents/inbox.md
ops wake [--force]               start the configured agent if the inbox has new pending lines
ops incident new "<title>" [--from-inbox <line>]
ops incident close <id>
ops secret list [--stale]        vault entries with owner and purpose; --stale: past rotation
ops secret search <pattern>...   match index metadata (never file contents)
ops secret view <name>           metadata plus masked snippets, lengths, sha256 prefixes
ops secret run <entry>[,..] -- '<cmd>'
                                 run `sh -c <cmd>` with the entries in env (output redacted)
ops secret insert <entry> [--var K] <target> | --all [--dry-run]
                                 write a value to host:/github:/file: targets (production WRITE)
ops secret check                 vault permissions, leak patterns, placeholders
ops secret fingerprint <name>    sha256 prefix and last 4 characters of a vault value
ops doctor                       fleet parse, vault index consistency, hook status
```

## Audit log

Every action on a remote system, provider API, the vault, the fleet, DNS, a
deployment, or production data must be in `logs/audit/` (`AGENTS.md` 1.8).
`ops` commands log automatically; other actions are logged with `ops log`.
In Claude Code, a `PostToolUse` hook (`.claude/settings.json`) runs
`bin/ops log --from-hook` and appends every Bash command, redacted, with actor
`claude`. The hook never blocks or fails a tool call.

## Unattended incident handling

`ops wake` starts the agent only when the inbox has new pending lines, so
idle intervals use no tokens. Example cron line:

```
*/5 * * * * cd /path/to/repo && bin/ops wake >> runs/wake.log 2>&1
```

The agent verifies each inbox line independently, works through the incident
folder in `incidents/`, and reports through the `notify` record in
`fleet/notify.yaml`. The autonomy level is set by the `flags` in
`ops.config.yaml`.

## Skills

| Skill | Purpose |
|---|---|
| `9router` | Install, harden, upgrade, back up, and sync a 9Router AI gateway |
| `aws-management` | AWS CLI setup and gated changes (IAM, SES, SSM) |
| `coder-remote-servers` | Coder workspaces on remote servers over a tailnet |
| `kandev` | Deploy and operate the Kandev control plane |
| `mail-server-config` | Mailu install, repair, migration, and delivery setup |
| `netdata-monitoring` | Install and harden netdata, claim to Cloud |
| `orca-remote-server` | Always-on Orca server, directly or in a Coder workspace |
| `secret-rotation` | Rotate a leaked or stale credential everywhere it is used |
| `sql-explorer` | Natural-language SQL exploration and export for one database |
| `wordpress-migration` | Migrate a WordPress site between servers |

Create a new skill by copying `.agents/skills/_template/`. See `AGENTS.md`
section 6.

## Tests and checks

CI runs on every push and pull request to `master`:

```bash
pip install pyyaml requests pytest ruff mypy types-PyYAML types-requests
pytest -q
ruff check .
mypy .
```

CI also runs `gitleaks` and `trufflehog`. The pre-commit hook requires both. They
are pinned (gitleaks 8.18.4, trufflehog 3.82.13), installed by
`ops tools install` into `.tools/bin/` (gitignored) after a sha256 check, and the
hook blocks commits while either is missing. Skill helper scripts under `.agents/`
are excluded from the lint and type gates. See `pyproject.toml`.

## License

MIT. See [LICENSE](LICENSE).
