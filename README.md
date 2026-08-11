# SysOps Playbook Repository

A publishable repository of **reusable server procedures** ("playbooks") —
Coder remote workspace fleets, WordPress migrations, mail server
configuration, and more — each executed against real servers with strictly
segregated, per-run state.

```
playbooks/              ← static, reusable procedures (committed)
  _playbook-template/      skeleton for new playbooks
  coder-remote-servers/    Coder workspaces across remote servers (Tailscale + mTLS)
  wordpress-migration/     scaffolded
  mail-server-config/      scaffolded
executions/             ← per-run state (GITIGNORED)
  <date>-<client>-<playbook>-<tag>/
    plan.md  runbook.md  inventory.md  notes.md  secrets/  logs/
```

## How it works

- **Playbooks are static.** Each playbook is one subject: a canonical
  procedure (`playbook.md`, placeholders only), templates, scripts, and a
  `notes/` folder of lessons learned. Playbooks are never edited during a run.
- **Executions are self-contained.** Every run gets one gitignored folder
  holding its plan, runbook (the playbook being executed, with real values and
  step statuses), inventory of the servers it touches, credentials, and logs.
  Runs for different clients never mix.
- **Safety doctrine.** Production servers are read-only by default; every
  write — including any non-`SELECT` database query — requires explicit
  permission; permission mode (per-write confirm or plan-as-approved) is set
  at plan approval; agents never assume, always confirm, and are strictly
  obedient. See `AGENTS.md` §1.

## Starting a run

1. Create `executions/<YYYY-MM-DD>-<client>-<playbook>-<tag>/`
2. Copy the playbook's `plan-template.md` + `runbook-template.md` into it;
   fill in real hosts and credentials
3. Read the playbook's `notes/` (mandatory)
4. Present the plan for approval; the operator sets the permission mode
5. Execute against the runbook, capture logs, record findings
6. Close out: mark steps done, write `notes.md`, propose lesson promotion

## Repository layout

| Path | What it is |
|------|------------|
| `playbooks/_playbook-template/` | Skeleton for authoring new playbooks |
| `playbooks/coder-remote-servers/` | Coder workspace fleet: remote `docker:dind` daemons, Tailscale, mTLS, wildcard app subdomains |
| `playbooks/wordpress-migration/` | (scaffolded) WordPress site migration between servers |
| `playbooks/mail-server-config/` | (scaffolded) mail server configuration |
| `executions/` | **Private** per-run state — gitignored, never committed |
| `AGENTS.md` | Full admin guide: doctrine, lifecycle, folder discipline |
| `docs/` | Plans, specs, design docs |

## Security rules

1. **Never commit execution state.** `executions/` is gitignored; real IPs,
   hostnames, and credentials live only there.
2. **Placeholders only in committed files.** Real values use
   `<PLACEHOLDER>` tokens.
3. **Production is read-only by default.** Writes require explicit permission
   (see `AGENTS.md` §1).
4. **Per-run secrets.** Credentials are generated per run, never shared
   across runs.

## Contributing a playbook

Copy `playbooks/_playbook-template/`, fill in README (what/why/risk level),
`playbook.md` (procedure with `WRITE` flags), templates, scripts. Promote
lessons from past runs into `notes/`. See `AGENTS.md` §6.
