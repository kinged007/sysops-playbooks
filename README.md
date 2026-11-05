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
| `runs/` | Planned-work state per skill variant (`executions` is a symlink to it) | no |
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
ops inventory [--stale]          list fleet records; --stale lists vault entries past rotation
ops ssh <server> [--via V] [cmd] connect with the server's connect block (ssh, coder, docker-context)
ops exec <service> <cmd>         run a command with the service's vault entries in env (output redacted)
ops log "<action>" [--target X] [--result ok|fail]
                                 append an audit log line
ops inbox add <source> <severity> "<summary>"
                                 append a validated line to incidents/inbox.md
ops wake [--force]               start the configured agent if the inbox has new pending lines
ops incident new "<title>" [--from-inbox <line>]
ops incident close <id>
ops secret check                 vault permissions, leak patterns, placeholders
ops secret fingerprint <name>    sha256 prefix and last 4 characters of a vault value
ops doctor                       fleet parse, vault index consistency, hook status
```

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

CI also runs `gitleaks` and `trufflehog`. Skill helper scripts under `.agents/`
are excluded from the lint and type gates. See `pyproject.toml`.

## License

MIT. See [LICENSE](LICENSE).
