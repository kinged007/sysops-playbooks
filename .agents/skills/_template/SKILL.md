---
name: <skill-name>
description: <One sentence saying what this skill does and when to use it. Name the trigger signals and what it does not cover.>
---

# <Skill title>

> Read `references/` before any run. It holds lessons learned from earlier runs
> that can change how you plan.

Risk level: <low | medium | high> - <one-line justification, for example
"touches production Docker daemons", "moves live data between servers",
"changes live email delivery">.

## When to use

- <Signal that triggers this skill>
- Not for: <what this skill does not cover>

## Fleet refs needed

Records from `fleet/` this skill reads. Real hosts, IPs, and domains are never
written in this file.

- `fleet/services.yaml`: service `<name>` (compose path, health endpoint)
- `fleet/servers.yaml`: server record hosting the service (connection via `ops ssh <server>`)
- `fleet/sites.yaml` / `fleet/providers.yaml`: <only if used>

## Vault entries needed

Names follow `<client>-<provider>-<purpose>`. Values are never printed or
written to logs or committed files.

- `<client>-<provider>-<purpose>`: <what it is used for, minimum scope>

## Procedure

Rules for every step:

- Reads need no flag. Every step that changes a production system is flagged
  **WRITE** and needs approval per the run's permission mode.
- Every destructive **WRITE** (overwrite, delete, restart with data impact,
  schema change) is preceded by a **Backup** step.
- Every **WRITE** has a **Rollback** line.
- Every fix is followed by a **Verify** step.
- Commands are copy-paste executable with placeholders filled from fleet
  records. Placeholders only; no real values.
- Production databases: `SELECT` only unless the step is flagged **WRITE**
  and approved.

### 0. Pre-flight

- [ ] Read `references/`
- [ ] Resolve the fleet records and vault entries listed above
- [ ] Confirm access with a read-only command

### 1. <Step group>

- [ ] Read: `<command>`
- [ ] **Backup**: `<command that saves the current state>`
- [ ] **WRITE**: `<command>`
  - Rollback: `<command>`
- [ ] Verify: `<command>` expects `<result>`

## Rollback

Summary of how to return to the state before the run: which backups exist, in
what order the rollback lines are applied, and when to stop and ask.

## Verify

Final read-only checks that confirm the run succeeded.

- [ ] <Check and expected result>

## Gotchas

Short list of known pitfalls, each with a pointer to `references/` for detail.

## Files

| Path | Purpose |
|---|---|
| `scripts/` | Scripts the procedure uses |
| `templates/` | Config, compose, and unit file templates; `plan-template.md` and `runbook-template.md` for planned work |
| `references/` | Lessons learned, upstream contracts, baselines |
