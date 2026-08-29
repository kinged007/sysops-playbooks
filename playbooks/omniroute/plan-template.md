# Plan: <RUN NAME>

| Field | Value |
|---|---|
| Client | <client> |
| Playbook | `omniroute` |
| Date | <YYYY-MM-DD> |
| Execution folder | `executions/<YYYY-MM-DD>-<client>-omniroute-<tag>/` |
| Permission mode | **UNSET — set by operator at approval** (A: per-write confirm / B: plan-as-approved) |
| Status | draft → approved → executing → closed |

## Install target (chosen by operator at approval)
<remote-instance / local-npm / docker / existing-unconfigured>
- How the agent reaches it: <public URL / SSH alias+forward / localhost / container>

## Servers involved (THIS run only)
| Alias (ssh config) | Role | Purpose | Access key |
|---|---|---|---|
| <alias-or-url> | <remote/prod/local> | <OmniRoute host / container / local> | `~/.ssh/<key>` or n/a |

## Credentials / secrets (THIS run only)
<Files in `secrets/` of this execution folder; never inline values here>
- `<file>` — <what it holds, e.g. management API key, INITIAL_PASSWORD>
- `<file>` — <...>

## Base/public URLs (operator-provided at §4)
- Public URL: <https://host>
- Internal URL: <http://localhost:<port> or container name>
- Base path (if any): <subpath or root>

## Steps
Numbered steps mirroring `runbook.md`, with **WRITE** flags:

1. <step> (read)
2. <step> (**WRITE** — describe exactly what changes on which host)
3. ...

## Risk assessment
<What could go wrong; blast radius; rollback plan. Public instance → note that
MCP enablement and key creation widen exposure; the LOCAL_ONLY carve-out must
stay intact.>

## Approval
- [ ] Operator reviewed plan and set permission mode: <A or B>
- [ ] Operator approved execution on <date>