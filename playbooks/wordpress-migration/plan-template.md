# Plan: <RUN NAME>

| Field | Value |
|---|---|
| Client | <client> |
| Playbook | `wordpress-migration` |
| Execution folder | `executions/wordpress-migration/` or `executions/wordpress-migration-<suffix>/` |
| Permission mode | **UNSET — set by operator at approval** (A: per-write confirm / B: plan-as-approved) |
| Status | draft → approved → executing → closed |

## Servers involved (THIS variant only)
| Alias (ssh config) | Role | Purpose | Access key |
|---|---|---|---|
| <alias> | <source/prod/dest> | <what it does in this run> | `~/.ssh/<key>` |

## Credentials / secrets (THIS variant only)
<Files in `secrets/` of this execution folder; never inline values here>
Secrets persist in this folder across invocations — update in place when rotating.

## Steps
Numbered steps mirroring `runbook.md`, with **WRITE** flags:

1. <step> (read)
2. <step> (**WRITE** — describe exactly what changes on which host)
3. ...

## Risk assessment
<What could go wrong; what is the blast radius; rollback plan>

## Approval
- [ ] Operator reviewed plan and set permission mode: <A or B>
- [ ] Operator approved execution on <date>
