# Runbook: <RUN NAME>

Snapshot of the **active branch** (`playbooks/mail-server-config/branches/<branch>.md`)
being executed, with real values filled in. Referenced `common.md` sections
are reproduced inline in the step logs. State lives here and in `logs/` — a
run can be resumed by any agent session from these files alone.

| Field | Value |
|---|---|
| Run | <run name> |
| Playbook | `mail-server-config` |
| Branch file(s) | `branches/<branch>.md` (+ `branches/common.md`) |
| Client | <client> |
| Started | <date> |
| Permission mode | <A / B> (set at plan approval) |

## Steps
Status values: `pending` / `in-progress` / `done` / `blocked`.

- [ ] **1. <step>** (read) — status: pending
  - Log: `logs/01-<short-name>.log`
- [ ] **2. <step>** (**WRITE**) — status: pending
  - Log: `logs/02-<short-name>.log`
  - Mode A note: operator confirmation required before running.

## Deviations
<Anything not in the plan → STOP, record here, ask operator. Never improvise.>

## Close-out
- [ ] Runbook complete (all steps done or blocked+explained)
- [ ] Findings recorded in `notes.md`
- [ ] Promotion candidates proposed to operator (→ playbook `notes/`)
