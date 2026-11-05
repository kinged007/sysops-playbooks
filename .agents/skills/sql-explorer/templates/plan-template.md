# Plan: <RUN NAME>

| Field | Value |
|---|---|
| Client | <client> |
| Playbook | `sql-explorer` |
| Execution folder | `executions/sql-explorer-<suffix>/` (suffix identifies the database, e.g. `acme`) |
| Permission mode | **UNSET — set by operator at approval** (A: per-write confirm / B: plan-as-approved) |
| Status | draft → approved → executing → closed |

## Database (THIS variant only)
| Field | Value |
|---|---|
| Suffix | <suffix> |
| DB_TYPE | <postgres \| mysql \| sqlite> |
| Secrets | `secrets/db.env` (copied from playbook `templates/db.env.example`, filled by operator) |

Secrets persist in this folder across invocations — update in place when rotating.

## Question / goal
<What the operator wants to know or export>

## Steps
Numbered steps mirroring `runbook.md`, with **WRITE** flags:

1. <step> (read)
2. <step> (**WRITE** — exact statement + affected rows from dry-run SELECT)
3. ...

## Risk assessment
<Reads are safe. For writes: what could go wrong; blast radius; rollback plan>

## Approval
- [ ] Operator reviewed plan and set permission mode: <A or B>
- [ ] Operator approved execution on <date>
