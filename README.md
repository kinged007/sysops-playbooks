# SysOps Playbook Repository

A publishable repository of **reusable server procedures** ("playbooks") —
from workspace fleet setup to site migrations to mail server configuration —
each executed against real servers with strictly segregated, per-variant state.

## What this is

This repo stores **procedures, not state**. Each playbook captures one
subject as a canonical, copy-paste executable procedure with placeholder
values only, plus the templates, scripts, and lessons learned that go with
it. Nothing in the committed repo contains real IPs, hostnames, usernames,
or credentials.

When a procedure is run against real servers, it is executed from a
**persistent, gitignored execution folder** that holds the plan, the runbook
(the procedure with real values filled in), an inventory of the servers
involved, per-variant credentials, and an append-only log. All subsequent
invocations for the same playbook (or playbook+suffix) **append to the same
folder**, so secrets, inventory, and history are reused — the agent never
re-asks for values already known, and follow-up questions instantly regain
context.

## Use cases

- **Scheduled or repeatable server work** — anything you do more than once
  becomes a playbook: standing up workspaces, migrating services between
  servers, configuring services, applying security hardening.
- **Operator-supervised automation** — every playbook is executed by an
  agent under a strict permission model. Production servers are read-only by
  default; every write requires explicit operator permission.
- **Segregated, persistent variants** — each playbook variant lives in its
  own persistent folder (`executions/<playbook>/` by default, or
  `executions/<playbook>-<suffix>/` for a named variant like `-personal` vs
  `-company`). Secrets and inventory persist there across invocations. Variants
  and playbooks never mix.
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
executions/             ← persistent per-variant state (GITIGNORED)
  <playbook>/              default variant for a playbook
    plan.md  runbook.md  inventory.md  notes.md  secrets/  logs/
  <playbook>-<suffix>/     additional variant when a custom suffix is used
    plan.md  runbook.md  inventory.md  notes.md  secrets/  logs/
```

- **[`playbooks/`](playbooks/)** is the only tracked operational content.
  Each playbook folder has its own README describing what it does, when to
  use it, its prerequisites, risk level, and the servers involved — browse
  the folders for details on any specific procedure.
- **`executions/`** holds persistent per-variant state and is fully
  gitignored. Never committed. The agent discovers existing folders for a
  playbook on every invocation and asks whether to reuse them.
- **`AGENTS.md`** is the full admin guide: safety doctrine, execution
  lifecycle, folder discipline, and committing rules. Agents read it before
  touching anything.

## How it works

- **Playbooks are static.** A playbook is one subject: a canonical procedure
  (`playbook.md`, placeholders only), templates, scripts, and a `notes/`
  folder of lessons learned. Playbooks are never edited during a run.
- **Execution folders are persistent and append-only.** Each playbook variant
  (e.g. `coder-remote-servers` or `coder-remote-servers-personal`) gets one
  gitignored folder holding its plan, runbook, inventory, credentials, and
  logs. Logs are never deleted — each session appends timestamped files.
  Subsequent requests for the same variant reuse the same folder, updating
  `logs/` and extending `plan.md`/`runbook.md` as needed.
- **Safety doctrine.** Production servers are read-only by default; every
  write — including any non-`SELECT` database query — requires explicit
  permission; permission mode (per-write confirm or plan-as-approved) is set
  at plan approval; agents never assume, always confirm, and are strictly
  obedient. See `AGENTS.md` §1.

## Starting a run (or resuming one)

1. **Discover:** agent scans `executions/<playbook>*` for existing folders
   matching the requested playbook (including any `-<suffix>` variants and
   legacy dated folders). It presents matches and asks: *"Found previous
   execution(s) XYZ — reuse, or create new variant?"*
2. **Bootstrap:** operator confirms reuse of `executions/<playbook>[/-<suffix>]/`
   or requests a new suffix (e.g. `personal`, `company`). If new, the agent
   creates the folder and its `secrets/` + `logs/` subfolders.
3. **Prep:** if new: copy the playbook's `plan-template.md` + `runbook-template.md`
   into it; fill in real hosts/credentials. If reusing: load existing
   `plan.md` / `inventory.md` / `secrets/` / `notes.md` as context and propose
   an updated plan building on them — never overwrite existing secrets or logs.
4. Read the playbook's `notes/` (mandatory)
5. Present the plan for approval; the operator sets the permission mode
6. Execute against the runbook, capture logs (timestamp-prefixed, append-only), record findings
7. Close out: mark steps done, append to `notes.md`, propose lesson promotion

## Security rules

1. **Never commit execution state.** `executions/` is gitignored; real IPs,
   hostnames, and credentials live only there.
2. **Placeholders only in committed files.** Real values use
   `<PLACEHOLDER>` tokens.
3. **Production is read-only by default.** Writes require explicit permission
   (see `AGENTS.md` §1).
4. **Per-variant secrets.** Credentials are generated per variant, stored in
   that variant's `secrets/`, and **reused across invocations** of the same
   variant. Rotate them in place inside the same folder; never copy them
   between variants without explicit approval.

## Contributing a playbook

Copy `playbooks/_playbook-template/`, fill in README (what/why/risk level),
`playbook.md` (procedure with `WRITE` flags), templates, scripts. Promote
lessons from past runs into `notes/`. See `AGENTS.md` §6.
