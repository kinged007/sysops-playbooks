# Plan: <RUN NAME>

| Field | Value |
|---|---|
| Client | <client> |
| Skill | `<skill-name>` |
| Run folder | `runs/<skill>/` or `runs/<skill>-<suffix>/` |
| Permission mode | **UNSET — set by operator at approval** (A: per-write confirm / B: plan-as-approved) |
| Status | draft → approved → executing → closed |

## Fleet refs (THIS variant only)
| Fleet record | Role | Purpose |
|---|---|---|
| `fleet/servers.yaml`: <server name> | <source/prod/dest> | <what it does in this run> |
| `fleet/services.yaml`: <service name> | <service> | <what it does in this run> |

## Vault entries (THIS variant only)
<Vault entry names `<client>-<provider>-<purpose>`; never inline values here>

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
