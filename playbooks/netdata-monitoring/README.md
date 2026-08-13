# Playbook: Netdata Monitoring

> **Agent: read `notes/` BEFORE any run.** The notes contain lessons learned
> from previous executions (G1–G9) that may change how you plan. Never skip
> this.

## What it does
Installs or updates the netdata agent on one or more servers, hardens its web
API access (bearer token protection + MCP API key), claims it to Netdata Cloud
(optional, operator-provided token), and records a per-node MCP config artifact
in the run's execution folder so the operator can later grant an agent access.
Also covers the ongoing ops flow: "check all nodes for alerts and plan a
remedy" — reads only, then an operator-approved plan before any write.

## When to use it
- Onboarding a new server into netdata monitoring
- Updating an existing netdata install that won't update or install
- Hardening a node whose netdata web API (`:19999`) is exposed
- Routine fleet alert checks ("check all the nodes for alerts")

## Prerequisites
- Key-based SSH access to each target (`~/.ssh/config` alias per server)
- The operator's preferred install command (e.g. the netdata kickstart script
  with claim token) — recorded verbatim into the runbook at run time
- Netdata Cloud account **only if** claiming (free plan is fine; Cloud MCP
  needs a paid plan, but the local agent MCP does not)
- Permission mode set at plan approval (§3.4 of repo AGENTS.md): A = confirm
  before each write, B = plan-as-approved

## Risk level
**medium** — installs packages and changes netdata config on production
servers (all **WRITE**-flagged, approval-gated, rollback documented). The
default `:19999` exposure is treated as a vulnerability and hardened on every
run.

## Servers involved
One or more servers running (or to receive) the netdata agent. Real values
live in the execution's `inventory.md` and `secrets/`, never here.

## Files
| Path | Purpose |
|---|---|
| `playbook.md` | Canonical procedure (placeholders only) |
| `plan-template.md` | Copied to `executions/<run>/plan.md` |
| `runbook-template.md` | Copied to `executions/<run>/runbook.md` |
| `templates/mcp-config.json` | Per-node MCP server config template (placeholders) |
| `notes/gotchas.md` | G1–G9: real pitfalls hit on the fleet, with fixes |

## MCP config artifact (per node, per run)
When a node is confirmed connected, the run writes
`executions/<run>/mcp/<alias>.mcp.json` from `templates/mcp-config.json` with
real values filled in. It is gitignored (inside `executions/`). To use it
later — e.g. in a dedicated or remote agent — merge the `"mcp"` block into
that agent's `opencode.json` and set the referenced env var
(`NETDATA_MCP_KEY_<ALIAS>`) to the key stored in the run's `secrets/`. The
key value itself never appears in committed files.
