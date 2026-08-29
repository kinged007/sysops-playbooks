# Runbook: <RUN NAME>

Snapshot of `playbooks/coder-remote-servers/playbook.md` being executed, with
real values filled in. State lives here and in `logs/` — any agent session can
resume from these files alone. This folder is persistent per playbook variant
(`executions/coder-remote-servers[/-<suffix>]/`); subsequent invocations append
to it, never replace it. `logs/` is append-only — each session adds
timestamp-prefixed files (e.g. `logs/2026-08-29T143000-01-discover.log`).

| Field | Value |
|---|---|
| Run | <run name> |
| Playbook | `coder-remote-servers` |
| Execution folder | `executions/coder-remote-servers/` or `executions/coder-remote-servers-<suffix>/` |
| Client | <client> |
| Started | <date> |
| Permission mode | <A / B> (set at plan approval) |

## Steps
Status values: `pending` / `in-progress` / `done` / `blocked`.

- [ ] **1. <step>** (read) — status: pending
  - Log: `logs/<timestamp>-01-<short-name>.log` (append-only; prior logs never overwritten)
- [ ] **2. <step>** (**WRITE**) — status: pending
  - Log: `logs/<timestamp>-02-<short-name>.log`
  - Mode A note: operator confirmation required before running.

## Deviations
<Anything not in the plan → STOP, record here, ask operator. Never improvise.>

## Close-out
- [ ] Runbook complete (all steps done or blocked+explained)
- [ ] Findings appended to `notes.md` (cumulative history — do not overwrite)
- [ ] Promotion candidates proposed to operator (→ playbook `notes/`)
