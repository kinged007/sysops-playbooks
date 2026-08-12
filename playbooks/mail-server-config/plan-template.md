# Plan: <RUN NAME>

| Field | Value |
|---|---|
| Client | <client> |
| Playbook | `mail-server-config` |
| Branch | <setup \| repair \| migrate \| ops> |
| Scale | <small \| medium-large \| n/a> (setup branch) |
| Existing stack | <postfix \| exim \| mailcow \| mailu \| poste.io \| other \| n/a> (repair/migrate) |
| Date | <YYYY-MM-DD> |
| Execution folder | `executions/<YYYY-MM-DD>-<client>-<playbook>-<tag>/` |
| Permission mode | **UNSET — set by operator at approval** (A: per-write confirm / B: plan-as-approved) |
| Status | draft → approved → executing → closed |

## Servers involved (THIS run only)
| Alias (ssh config) | Role | Purpose | Access key |
|---|---|---|---|
| <alias> | <source/mailserver/dest> | <what it does in this run> | `~/.ssh/<key>` |

## Credentials / secrets (THIS run only)
<Files in `secrets/` of this execution folder; never inline values here>

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
