# Design: Playbook/Execution Repo Restructure

**Date:** 2026-08-11
**Status:** Approved for implementation
**Approach:** A — Static playbooks + gitignored executions

## 1. Problem

The repo is currently a single-purpose "Coder remote workspace fleet" guide. It
will become an ops repository containing multiple reusable procedures
("playbooks") for unrelated things — Coder remote servers, WordPress
migrations, mail server configuration, and more. Playbooks run against
servers that may belong to different clients and have nothing to do with each
other. All per-run information (credentials, secrets, inventory, logs, plans,
runbooks) must be segregated so there is no drift, no conflicts, and no
cross-run mixing. The repo is publishable, so real hosts/IPs/credentials must
never be committed.

Additionally, agents will execute playbooks against production servers. A
strict safety doctrine is required: production is read-only by default, all
writes require explicit permission, agents never assume, always confirm, and
are strictly obedient.

## 2. Approach chosen

**Static playbooks + gitignored executions.**

- `playbooks/` — committed, static, the only tracked operational content.
  Never modified during a run.
- `executions/` — gitignored, one self-contained folder per run. All real
  values, credentials, logs, plans, and runbooks live inside it.
- No shared vault, no shared inventory, no cross-run references.

## 3. Target folder structure

```
coder-workspaces/
├── AGENTS.md                  ← general sysops admin guide + doctrine (rewritten)
├── README.md                  ← public overview: what this repo is, how runs work
├── .gitignore                 ← extended: executions/, keep existing secret patterns
├── .gitattributes             ← unchanged (LF enforcement stays)
│
├── playbooks/                 ← COMMITTED. Static. Never modified during a run.
│   ├── _playbook-template/    ← skeleton for authoring new playbooks
│   ├── coder-remote-servers/  ← migrated from current repo
│   ├── wordpress-migration/   ← scaffolded empty
│   └── mail-server-config/    ← scaffolded empty
│
├── executions/                ← GITIGNORED. One folder per run.
│   └── <YYYY-MM-DD>-<client>-<playbook>-<short-tag>/
│       ├── plan.md            ← per-run plan: real hosts, IPs, steps, approval
│       ├── runbook.md         ← copy of playbook with real values + checkboxes
│       ├── inventory.md       ← servers touched by THIS run
│       ├── notes.md           ← run findings (candidate for playbook notes/)
│       ├── secrets/           ← credentials for this run only
│       └── logs/              ← transcripts, command outputs
│
└── docs/
    └── superpowers/specs/     ← design docs (this process)
```

Key rules:

- `playbooks/` is the only tracked state; editing it during a run is
  forbidden — corrections go to the run's `notes.md` first, then (with
  approval, after the run) get promoted into the playbook.
- `executions/` is fully gitignored; nothing inside can ever be committed.
- Naming is date-first so runs sort chronologically and the client+playbook
  is unambiguous at a glance.
- No shared vault, no shared inventory — every run is self-contained.

## 4. Playbook anatomy

Each playbook folder is self-contained and has the same shape:

```
playbooks/<name>/
├── README.md              ← what it does, when to use, prerequisites, risk level
│                            + a mandatory line: "Agent: read notes/ BEFORE any run"
├── playbook.md            ← canonical step-by-step procedure (placeholders only)
├── plan-template.md       ← skeleton copied into executions/<run>/plan.md
├── runbook-template.md    ← skeleton copied into executions/<run>/runbook.md
├── scripts/               ← scripts the playbook uses
├── templates/             ← ALL templates: compose files, project scaffolds,
│                            config templates, Coder templates — one home
└── notes/                 ← lessons learned, gotchas, pitfalls
```

Rules:

- `playbook.md` is the source of truth — written with `<PLACEHOLDER>` tokens
  only (never real IPs/hostnames/credentials).
- `notes/` is the promotion channel — during a run, findings go to the run's
  `notes.md`; after the run ends, the operator may approve promoting them into
  `playbook.md` or `notes/` of the playbook. Nothing is ever edited in a
  playbook mid-run.
- `plan-template.md` / `runbook-template.md` are copied (not symlinked) into
  the execution folder, so each run gets its own editable snapshot — no drift.
- `_playbook-template/` contains the same skeleton with explanatory comments,
  used to scaffold new playbooks.
- Scripts/templates reference relative paths inside the playbook folder, or
  get copied into the run's `scripts/` when they need per-run values.
- Every playbook README includes a prominent "Agent: read `notes/` before any
  run" requirement — the agent reads the notes before planning an execution,
  not just before executing.
- `templates/` holds ALL templates — compose files, project scaffolds, config
  templates, Coder templates. There is no separate `compose/` folder.
- Each playbook's README declares a risk profile (e.g. coder-remote-servers:
  medium — touches production Docker daemons; wordpress-migration: high —
  moves live data between servers; mail-server-config: high — changes live
  email delivery). AGENTS.md doctrine references this risk declaration.

## 5. Execution lifecycle

Every run follows the same seven gates, enforced by AGENTS.md:

```
1. BOOTSTRAP    operator creates executions/<YYYY-MM-DD>-<client>-<playbook>-<tag>/
2. PREP         agent copies plan-template.md + runbook-template.md from the
                playbook, fills in real hosts/IPs/credentials in plan.md
3. NOTE-READ    agent reads playbook notes/ (mandatory) + playbook.md; agent
                proposes the plan.md content (step list, writes flagged)
4. APPROVAL     operator reviews plan.md, sets permission mode (§6.3),
                approves → plan is frozen (no changes without re-approval)
5. EXECUTE      agent executes, checking off runbook.md steps, capturing
                outputs into logs/ (one file per step)
6. DEVIATION    anything not in the plan → STOP, ask, get approval before
                continuing (never improvise on production)
7. CLOSE        runbook marked complete/parked; findings → notes.md;
                promotion of lessons into playbook/ notes proposed to operator
```

State tracking: each step in runbook.md has a status (`pending` /
`in-progress` / `done` / `blocked`) — the run can be resumed by any agent
session because all state lives in the execution folder. Parked runs keep
their credentials until the operator deletes the folder (nothing auto-expires
or auto-moves).

## 6. Permission & safety doctrine (non-negotiable)

These live at the top of AGENTS.md, phrased so every agent reads them first.

### 6.1 Production servers are read-only by default

- Reading (SSH commands that don't modify state, `docker ps`, log inspection,
  config viewing) is allowed freely — it is how the agent understands the
  system.
- **Writing to production is strictly prohibited without explicit
  permission.** This includes: file edits, package installs, service
  restarts, config changes, data moves, docker/compose mutations, DNS
  changes, firewall changes, credential rotation — anything that changes
  state on a live system.
- **Database queries: only `SELECT` is allowed on production databases. Any
  other query (INSERT, UPDATE, DELETE, ALTER, DROP, TRUNCATE, GRANT, etc.) is
  a production write and is strictly prohibited without explicit permission.**

### 6.2 Never assume. Always confirm.

- If a step is ambiguous, if the plan doesn't cover it, if the operator's
  intent is unclear — **stop and ask**. Asking is free; a wrong write to
  production is not.
- When in doubt, ask. There is no penalty for over-confirming.

### 6.3 Permission mode — set at plan approval, never assumed

At the APPROVAL gate, the agent asks explicitly: *"Should I confirm before
each production write, or is it OK to execute the plan as approved?"*

- **Mode A (default): per-write confirm** — every production write step gets
  its own inline `May I write X to <host>?` before it happens. Reads need no
  confirmation.
- **Mode B: plan-as-approved** — approval of the plan authorizes all listed
  steps; the agent executes them without per-step asks.
- The chosen mode is recorded in plan.md and can be changed mid-run by the
  operator at any time. The agent never picks the mode itself — it always
  asks.

### 6.4 Obedience

- If the operator says stop — stop immediately, mid-command, no finishing-up.
- The agent executes what the plan says, in order, nothing more. No bonus
  steps, no "helpful" additions.

### 6.5 Cross-run and cross-client segregation (strict)

- Never read from another execution's folder. Never reuse another run's
  credentials or host aliases. Never copy files between executions.
- Real values for THIS run live only in THIS execution folder.

### 6.6 Secrets handling

- Secrets never appear in committed files, command history, or logs. No
  passwords in SSH command lines — keys and scoped tokens only.
- Sensitive data transfers between servers use scoped methods (SCP/rsync
  over SSH keys, never piping credentials through shell).

### 6.7 Playbooks are read-only during a run

Corrections go to notes.md; promotion to the playbook happens after, with
approval.

## 7. Migration of existing content

### 7.1 Into the first playbook (`playbooks/coder-remote-servers/`)

| Current location | New location |
|---|---|
| `compose/workspace-docker.yml` | `playbooks/coder-remote-servers/templates/workspace-docker.yml` |
| `templates/docker-devcontainer/` + `templates/remote-docker-workspace.hcl` | `playbooks/coder-remote-servers/templates/` |
| `scripts/setup-wildcard-cert.sh` | `playbooks/coder-remote-servers/scripts/` |
| `docs/runbooks/onboarding-a-new-remote.md` + `wildcard-app-subdomains.md` | become content of `playbooks/coder-remote-servers/playbook.md` / `notes/` |
| `docs/plans/2026-08-07-remote-docker-onboarding.md` | **archived** to `executions/2026-08-07-coder-fleet-initial-setup/` as the historical run |
| AGENTS.md coder-specific sections | generalized into the new admin guide; coder-specific knowledge (gotchas G1–G12, topology decisions) moves into the playbook's `notes/` and `playbook.md` |

### 7.2 Existing gitignored data (`secrets/`, `servers/`)

Folded into a **handover execution**:
`executions/2026-08-11-coder-fleet-current-state/` containing the existing
inventory, audit log, secrets-pointers, and still-live keys/tokens. This
preserves continuity under the new rules (per-run secrets only) without
losing anything. The old top-level `secrets/` and `servers/` folders are then
removed.

### 7.3 New scaffolding

- `playbooks/_playbook-template/` (skeleton with explanatory comments)
- `playbooks/wordpress-migration/` and `playbooks/mail-server-config/`
  scaffolded from the template (README, empty playbook.md with placeholder
  sections, templates/)
- `.gitignore` gains `executions/` (already-covered patterns stay)
- `AGENTS.md` rewritten: doctrine (§6), repo model, run lifecycle, folder
  discipline, SSH/key setup (generalized from current §9), file map
- `README.md` rewritten as the general ops-repo overview

## 8. Out of scope

- Actual content for the wordpress-migration and mail-server-config playbooks
  (scaffolded only).
- Any changes to production servers (this restructure is repo-only).
