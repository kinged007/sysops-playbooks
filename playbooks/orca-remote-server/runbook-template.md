# Runbook: <RUN NAME>

Snapshot of `playbooks/orca-remote-server/playbook.md` being executed, with
real values filled in. State lives here and in `logs/` — any agent session can
resume from these files alone. This folder is persistent per playbook variant
(`executions/orca-remote-server[/-<suffix>]/`); subsequent invocations append
to it, never replace it. `logs/` is append-only — each session adds
timestamp-prefixed files (e.g. `logs/2026-08-29T143000-01-discover.log`).

| Field | Value |
|---|---|
| Run | <run name> |
| Playbook | `orca-remote-server` |
| Execution folder | `executions/orca-remote-server/` or `executions/orca-remote-server-<suffix>/` |
| Client | <client> |
| Started | <date> |
| Permission mode | <A / B> (set at plan approval) |

## Steps

Status values: `pending` / `in-progress` / `done` / `blocked`.

- [ ] **1. Location/access decision recorded** (read) — status: pending
  - Log: `logs/<timestamp>-01-decision.log` (append-only; prior logs never overwritten)
  - Gate: server location, access path, host mode, host type (direct / coder-workspace), pairing address, Tailscale-required-why.
- [ ] **2. Tailscale join** (**WRITE**) — status: pending
  - Log: `logs/<timestamp>-02-tailscale.log`
  - Mode A note: operator confirmation required before running.
- [ ] **3. Orca install + version parity** (**WRITE**) — status: pending
  - Log: `logs/<timestamp>-03-install.log`
  - Mode A note: operator confirmation required before running.
- [ ] **4. Server tooling (agent CLIs, accounts, skills)** (**WRITE**) — status: pending
  - Log: `logs/<timestamp>-04-tooling.log`
  - Mode A note: operator confirmation required before running. Interactive logins are the user's.
- [ ] **5. Start runtime (desktop share / orca serve + systemd)** (**WRITE**) — status: pending
  - Log: `logs/<timestamp>-05-serve.log`
  - Mode A note: operator confirmation required before running.
  - Workspace variant: note template/workspace/publish mapping + autostop state here (§6 Phase 4b).
- [ ] **6. Grants + firewall + negative public check** (**WRITE**) — status: pending
  - Log: `logs/<timestamp>-06-harden.log`
  - Mode A note: operator confirmation required before running.
- [ ] **7. Pair client(s)** (per-client grant; link = secret) — status: pending
  - Log: `logs/<timestamp>-07-pair-<client>.log`
  - Link handoff is user-private; agent never pastes links into chat/logs.
- [ ] **8. Verify end-to-end + record** (read) — status: pending
  - Log: `logs/<timestamp>-08-verify.log`

## Deviations

<Anything not in the plan → STOP, record here, ask operator. Never improvise.>

## Close-out

- [ ] Runbook complete (all steps done or blocked+explained)
- [ ] Findings appended to `notes.md` (cumulative history — do not overwrite)
- [ ] Promotion candidates proposed to operator (→ playbook `notes/`)
