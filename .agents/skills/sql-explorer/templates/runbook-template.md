# Runbook: <RUN NAME>

Snapshot of `playbooks/sql-explorer/playbook.md` being executed, with real values
filled in. State lives here and in `logs/` — any agent session can resume from
these files alone. This folder is persistent per database
(`executions/sql-explorer-<suffix>/`); subsequent invocations append to it,
never replace it. `logs/` is append-only — each session adds timestamp-prefixed
files (e.g. `logs/2026-08-29T143000-01-discover.log`).

| Field | Value |
|---|---|
| Run | <run name> |
| Playbook | `sql-explorer` |
| Execution folder | `executions/sql-explorer-<suffix>/` |
| Started | <date> |
| Permission mode | <A / B> (set at plan approval) |

## Steps
Status values: `pending` / `in-progress` / `done` / `blocked`.

- [ ] **1. Connect** (read) — status: pending
  - Log: `logs/<timestamp>-01-connect.log` (append-only; prior logs never overwritten)
- [ ] **2. Explore** (read) — status: pending
  - Log: `logs/<timestamp>-02-explore.log`
- [ ] **3. Answer / export** (read) — status: pending
  - Log: `logs/<timestamp>-03-export.log`
- [ ] **4. Writes** (**WRITE**, only if approved) — status: pending
  - Log: `logs/<timestamp>-04-write.log`
  - Mode A note: operator confirmation required before running.

## Deviations
<Anything not in the plan → STOP, record here, ask operator. Never improvise.>

## Close-out
- [ ] Runbook complete (all steps done or blocked+explained)
- [ ] Findings appended to `notes.md` (cumulative history — do not overwrite)
- [ ] Promotion candidates proposed to operator (→ playbook `notes/`)
