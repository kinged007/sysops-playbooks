# Playbook: Mail Server Configuration — Master

> **Agent: read `notes/` BEFORE any run.** The notes contain lessons learned
> from previous executions that may change how you plan. Never skip this.

**Goal:** One playbook for the full mail server lifecycle on remote servers:
fresh setup, diagnosis/repair of existing servers, mailbox migration, and
ongoing ops. **Multi-stack:** the repair branch works on any MTA (postfix,
exim, mailcow, Mailu, poste.io, ...); the setup/migrate branches use
**Mailu on Docker** as the worked example.

**Architecture:** This master file only runs **Discovery** and routes to a
branch. Procedures live in `branches/`. The agent loads `branches/<branch>.md`
— plus `branches/common.md` for setup/repair/migrate — and nothing else.

| Branch | File | Use when |
|---|---|---|
| Setup | `branches/setup.md` | Fresh mail server install (Mailu, Docker) |
| Repair | `branches/repair.md` | Diagnose/fix an EXISTING server (any stack) |
| Migrate | `branches/migrate.md` | Move mailboxes from an existing server into a new Mailu |
| Ops | `branches/ops.md` | Backup, restore, update, monitor, accounts, storage, security review |
| Common | `branches/common.md` | Shared DNS/TLS/SMTP verification — loaded BY the above, never standalone |

**Branch rule (non-negotiable):** exactly **one** branch per run. Never mix
branches. An ops run on a live server is a *separate run*. Any deviation from
the plan → **STOP, record in runbook, ask the operator** (AGENTS.md §1.4).

---

## Phase 0 — Discovery (mandatory, before any branch)

Answer every question with the operator. Record answers in the execution's
`inventory.md` with the branch they select. Mark each as *answered by
operator* or *verified by inspection*.

| # | Question | Determines |
|---|----------|------------|
| D1 | **Goal of this run:** fresh install / diagnose-repair existing / migrate mailboxes / ops run? | **Branch selection** |
| D2 | Scale: **small** (<100 mailboxes, SQLite backend) or **medium/large** (PostgreSQL backend)? | setup branch DB backend |
| D3 | Existing stack (if any): **postfix / exim / mailcow / Mailu / poste.io / other / n/a**? | repair commands, migrate source |
| D4 | Where is **DNS** hosted (registrar, Cloudflare, other)? Can **PTR** be set at the VPS provider? | DNS phase feasibility |
| D5 | **Access**: SSH alias per `~/.ssh/config` for each server, root/sudo level (access-ladder pattern, see `playbooks/wordpress-migration` §1.4). Permission mode **A/B** set at plan approval (AGENTS.md §1.3) | All branches |
| D6 | **Domains**, mailbox count, per-mailbox **quota**, disk budget, **backup target** (off-box path) | Storage provisioning, quota policy |

**Routing:**

- D1 = fresh install → load `branches/setup.md` (+ `common.md`)
- D1 = diagnose/repair → load `branches/repair.md` (+ `common.md`)
- D1 = migrate → load `branches/migrate.md` (+ `common.md`); requires setup branch §1–2 completed on the target
- D1 = ops → load `branches/ops.md`

---

## Run lifecycle

0. **DISCOVER** — agent scans `executions/mail-server-config*` for existing
   variant folders (including legacy dated folders); presents matches and asks
   the operator to reuse one or create a new `-<suffix>` variant. Never
   auto-picks.
1. **BOOTSTRAP** — operator confirms reuse of `executions/mail-server-config[/-<suffix>]/`
   or a new `executions/mail-server-config-<suffix>/` folder. If new, create it
   with `secrets/` and `logs/` subfolders.
2. **PREP** — if new: copy `plan-template.md` → `plan.md` and
   `runbook-template.md` → `runbook.md` from this folder; fill hosts/IPs/credentials.
   If reusing: load existing `plan.md` / `inventory.md` / `secrets/` / `notes.md`
   as context; propose updated plan building on them — never overwrite existing
   secrets or logs.
3. **NOTE-READ** — read `notes/` (mandatory) + the **active branch file**
   (+ `common.md`); propose the step list; flag every production **WRITE**.
4. **APPROVAL** — operator reviews `plan.md`, sets permission mode (A/B),
   approves → plan frozen.
5. **EXECUTE** — tick off `runbook.md` steps; capture outputs to `logs/` (one
   timestamp-prefixed file per step, append-only — prior logs never overwritten).
6. **DEVIATION** — anything not in the plan → STOP, ask, get approval.
7. **CLOSE** — append findings to `notes.md` (cumulative history); propose
   lesson promotion to `notes/lessons.md` (operator approves).

---

## Authoring rules

- Steps are copy-paste executable with `<PLACEHOLDER>` tokens; real values
  only in the execution folder.
- Every step that WRITES to a production system is flagged **WRITE** in bold,
  with rollback instructions.
- After each run, promote lessons into `notes/` (via the operator, never
  mid-run).
