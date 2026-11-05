# Plan: <RUN NAME>

| Field | Value |
|---|---|
| Client | <client> |
| Skill | `mail-server-config` |
| Branch | <setup \| repair \| migrate \| ops> |
| Scale | <small \| medium-large \| n/a> (setup branch) |
| Existing stack | <postfix \| exim \| mailcow \| mailu \| poste.io \| other \| n/a> (repair/migrate) |
| Run folder | `runs/mail-server-config/` or `runs/mail-server-config-<suffix>/` |
| Permission mode | **UNSET — set by operator at approval** (A: per-write confirm / B: plan-as-approved) |
| Status | draft → approved → executing → closed |

## Fleet refs (THIS variant only)
| Fleet record | Role | Purpose |
|---|---|---|
| `fleet/servers.yaml`: <alias> | <source/mailserver/dest> | <what it does in this run> |
| `fleet/services.yaml`: <service name> | service | <what it does in this run> |

## Vault entries (THIS variant only)
<Vault entry names `<client>-<provider>-<purpose>`; never inline values here>
Vault entries persist across invocations — rotate in place.

## Steps
Numbered steps mirroring the **active branch file**
(`branches/<branch>.md`) plus referenced `branches/common.md` sections, with
**WRITE** flags:

1. <step> (read)
2. <step> (**WRITE** — describe exactly what changes on which host)
3. ...

## Risk assessment
<What could go wrong; what is the blast radius; rollback plan>

## Approval
- [ ] Operator reviewed plan and set permission mode: <A or B>
- [ ] Operator approved execution on <date>
