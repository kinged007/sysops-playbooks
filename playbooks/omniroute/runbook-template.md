# Runbook: <RUN NAME>

Snapshot of `playbooks/omniroute/playbook.md` being executed, with real values
filled in. State lives here and in `logs/` — any agent session can resume from
these files alone. This folder is persistent per playbook variant
(`executions/omniroute[/-<suffix>]/`); subsequent invocations append to it,
never replace it. `logs/` is append-only — each session adds timestamp-prefixed
files (e.g. `logs/2026-08-29T143000-01-discover.log`).

| Field | Value |
|---|---|
| Run | <run name> |
| Playbook | `omniroute` |
| Execution folder | `executions/omniroute/` or `executions/omniroute-<suffix>/` |
| Client | <client> |
| Started | <date> |
| Permission mode | <A / B> (set at plan approval) |
| Install target | <remote-instance / local-npm / docker / existing-unconfigured> |
| Base URL (client) | <https://host> |
| Internal URL | <http://localhost:<port>> |
| MCP transport | <sse / streamable-http> |

## Secrets manifest (pointer — values live in `secrets/`)
| Secret file | Purpose | Applied where | Prefix |
|---|---|---|---|
| `secrets/<file>` | <e.g. manage API key> | <dashboard / env / container> | `<first8>` |

## Steps
Status values: `pending` / `in-progress` / `done` / `blocked`.

- [ ] **0. Pre-flight: confirm access, permission mode** (read) — status: pending
  - Log: `logs/<timestamp>-00-preflight.log`
- [ ] **1. Discover current state** (read) — status: pending
  - Log: `logs/<timestamp>-01-discover.log`
- [ ] **2. Access & auth: operator-provided key** (read) — status: pending
- [ ] **3. Generate secrets → `secrets/`** (local) — status: pending
  - Log: `logs/<timestamp>-03-secrets.log`
- [ ] **4. Base/public URLs** (SQ — ask operator) — status: pending
- [ ] **5. Deploy/wire instance** (**WRITE**) — status: pending
  - Mode A note: operator confirmation required before running.
- [ ] **6. First-login bootstrap** (fresh only; **WRITE**) — status: pending
- [ ] **7. Harden the instance** (**WRITE**) — status: pending
  - Mode A note: operator confirmation required before running.
- [ ] **8. Enable remote MCP + create manage key** (**WRITE**) — status: pending
  - Mode A note: operator confirmation required before running.
- [ ] **9. Test MCP reachability** (read) — status: pending
  - Log: `logs/<timestamp>-09-mcp-test.log`
- [ ] **10. Build MCP access artifact** (local) — status: pending
- [ ] **11. Verification & rollback** (read) — status: pending

## Deviations
<Anything not in the plan → STOP, record here, ask operator. Never improvise.>

## Close-out
- [ ] Runbook complete (all steps done or blocked+explained)
- [ ] Findings appended to `notes.md` (cumulative history — do not overwrite)
- [ ] Promotion candidates proposed to operator (→ playbook `notes/`)
