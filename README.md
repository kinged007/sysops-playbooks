# SysOps Playbook Repository

A publishable repository of **reusable server procedures** ("playbooks") —
from workspace fleet setup to site migrations to mail server configuration —
each executed against real servers with strictly segregated, per-run state.

## What this is

This repo stores **procedures, not state**. Each playbook captures one
subject as a canonical, copy-paste executable procedure with placeholder
values only, plus the templates, scripts, and lessons learned that go with
it. Nothing in the committed repo contains real IPs, hostnames, usernames,
or credentials.

When a procedure is run against a real client's servers, it is executed from
a **separate, gitignored execution folder** that holds the plan, the runbook
(the procedure with real values filled in), an inventory of the servers
involved, per-run credentials, and logs. Each run is fully self-contained;
runs for different clients never mix.

## Use cases

- **Scheduled or repeatable server work** — anything you do more than once
  becomes a playbook: standing up workspaces, migrating services between
  servers, configuring services, applying security hardening.
- **Operator-supervised automation** — every playbook is executed by an
  agent under a strict permission model. Production servers are read-only by
  default; every write requires explicit operator permission.
- **Segregated client work** — each run against a client's servers lives in
  its own folder with its own credentials and inventory. Nothing is shared
  between runs.
- **Institutional memory** — lessons learned from every run are captured and
  promoted back into the playbook's `notes/`, so the procedure improves over
  time without ever touching a live system mid-run.

## Repository layout

```
playbooks/              ← static, reusable procedures (committed)
  _playbook-template/      skeleton for authoring new playbooks
  <name>/                  one folder per subject: README, playbook.md,
                           plan/runbook templates, templates/, scripts/,
                           notes/
executions/             ← per-run state (GITIGNORED)
  <YYYY-MM-DD>-<client>-<playbook>-<tag>/
    plan.md  runbook.md  inventory.md  notes.md  secrets/  logs/
```

- **[`playbooks/`](playbooks/)** is the only tracked operational content.
  Each playbook folder has its own README describing what it does, when to
  use it, its prerequisites, risk level, and the servers involved — browse
  the folders for details on any specific procedure.
- **`executions/`** holds per-run state and is fully gitignored. Never
  committed.
- **`AGENTS.md`** is the full admin guide: safety doctrine, execution
  lifecycle, folder discipline, and committing rules. Agents read it before
  touching anything.

## How it works

- **Playbooks are static.** A playbook is one subject: a canonical procedure
  (`playbook.md`, placeholders only), templates, scripts, and a `notes/`
  folder of lessons learned. Playbooks are never edited during a run.
- **Executions are self-contained.** Every run gets one gitignored folder
  holding its plan, runbook (the playbook being executed, with real values
  and step statuses), inventory of the servers it touches, credentials, and
  logs.
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
