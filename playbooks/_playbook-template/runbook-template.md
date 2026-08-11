# Runbook: <RUN NAME>

Snapshot of `playbooks/<name>/playbook.md` being executed, with real values
filled in. State lives here and in `logs/` — a run can be resumed by any agent
session from these files alone.

| Field | Value |
|---|---|
| Run | <run name> |
| Playbook | <playbook-name> |
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
