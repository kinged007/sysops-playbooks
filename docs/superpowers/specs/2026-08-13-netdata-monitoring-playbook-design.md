# Design: Netdata Monitoring Playbook (Agent-Readable Fleet Observability)

Date: 2026-08-13
Status: approved (operator) → implemented per this spec
Repo: `sysops-playbooks`

## 1. Problem

The operator runs netdata on multiple servers and wants the agent to be able to:

1. Check every node for raised alerts ("check all the nodes for alerts and plan a remedy")
2. Summarize severity and propose a remedy plan that the operator approves before any write
3. Keep all node access **contained inside the runbook execution folder** — no global or
   project-level MCP registration
4. Record per-node MCP config as an artifact of each run, for the operator to install later
   (e.g. into a dedicated/remote agent)

Constraints from prior sessions (recalled from the Aug 11-12 netdata session):

- Netdata Cloud MCP requires a **Paid plan** — operator is on the free plan. Blocked.
- Local agent MCP (`http://<node>:19999/mcp`) works on the free plan; both fleet nodes
  answered `initialize` with tools incl. `list_raised_alerts`, `list_running_alerts`,
  `list_alert_transitions`, `query_metrics`, `execute_function`, etc.
- `:19999` is **open to the internet** by default on both nodes (verified: anonymous
  `POST /mcp` initialize succeeded). Hardening is a production WRITE needing approval.
- dnf 4.14 on Rocky 9 does not substitute `$releasever_major` → netdata repo 404s.
- Stale cloud claim state (`/var/lib/netdata/cloud.d/cloud.conf`) survives re-claims.

## 2. Approach chosen

**Approach A — playbook-only.** A new playbook `playbooks/netdata-monitoring/` containing the
canonical procedure (placeholders only), plan/runbook templates, an MCP config template, and
gotchas. No project-level opencode config. Per-run state (real IPs, secrets, generated MCP
configs, logs) lives only in `executions/<run>/`, which is gitignored by repo policy.

Rejected alternatives:
- **B — repo-scoped MCP registration** (`.opencode/opencode.json`): always-on within the
  repo; needs restart to toggle. Operator wants explicit opt-in per run.
- **C — custom local MCP bridge server**: real code to maintain, duplicates netdata's own
  MCP server. Not worth it; netdata ships the MCP server.

## 3. Playbook layout

```
playbooks/netdata-monitoring/
├── README.md              — purpose, when to use, prerequisites, risk level, servers involved,
│                             mandatory "read notes/ BEFORE any run" line
├── playbook.md            — canonical procedure; placeholders only; WRITE flags; rollbacks
├── plan-template.md       — copied to executions/<run>/plan.md
├── runbook-template.md    — copied to executions/<run>/runbook.md
├── templates/
│   └── mcp-config.json    — per-node MCP server config template (placeholders)
├── scripts/               — (kept empty unless a run proves a script is needed)
└── notes/
    └── gotchas.md         — G1..G9 lessons learned (see §6)
```

## 4. Run flow (seven gates)

### Bootstrap / Prep
- Operator creates `executions/<YYYY-MM-DD>-<client>-netdata-<tag>/`
- Copies `plan-template.md` → `plan.md`, `runbook-template.md` → `runbook.md`
- Fills `inventory.md` with SSH aliases (only), never raw hostnames/IPs in committed files
- Creates `secrets/` (gitignored by repo policy)

### NOTE-READ (mandatory before any plan)
- Agent reads `notes/gotchas.md` + `playbook.md`, proposes `plan.md` content
- Every production **WRITE** flagged; permission mode (A per-write / B plan-as-approved)
  set by operator at approval gate

### Install phase steps (from playbook.md)
1. Pre-flight: read notes, confirm prereqs, confirm SSH access (`ssh -o BatchMode=yes <alias>`)
2. Gather current state (reads): netdata version, service status, repo config, claim state
3. **Ask operator: "Do you want to define a hostname for this node?"**
   - If yes: `hostnamectl set-hostname <NAME>` (**WRITE**, before claiming so the Cloud
     node is named correctly)
4. **Record the operator's install command verbatim** into the runbook (e.g. the kickstart
   URL with claim token) — token goes to `secrets/`, never inline in committed files
5. Install/update per operator command (**WRITE**; rollback documented in playbook)
6. **Harden access** (**WRITE**, approved):
   - Enable netdata web bearer token protection (netdata.conf `[web] bearer token
     protection = yes`) + restart
   - Read MCP API key (`/var/lib/netdata/mcp_dev_preview_api_key`) → `secrets/`
   - Verify anonymous MCP access now fails, keyed access works
7. **Generate per-node MCP config artifact** → `executions/<run>/mcp/<alias>.mcp.json`
   (template in §5), written automatically when the node is confirmed connected
8. Verify: `/api/v1/info` reachable, alerts endpoints return data, claim status correct

### Ops phase (the "check all nodes" workflow)
- Agent runs curl JSON-RPC recipes from playbook.md against each node in inventory:
  `tools/list` → `list_raised_alerts` → `list_running_alerts` → `list_alert_transitions`
- Agent produces severity summary (node, alert name, status, value, duration, context)
- Agent proposes remedy plan → **operator approval gate** before any WRITE
- Findings → run's `notes.md`; lessons → propose promotion into playbook `notes/` after run

## 5. Per-node MCP config artifact

Generated into `executions/<run>/mcp/<alias>.mcp.json` on connect:

```json
{
  "mcp": {
    "netdata-<ALIAS>": {
      "type": "remote",
      "url": "http://<NODE_ADDRESS>:19999/mcp",
      "enabled": true,
      "headers": {
        "Authorization": "Bearer {env:NETDATA_MCP_KEY_<ALIAS>}"
      }
    }
  }
}
```

- Placeholders are the ONLY form in committed files (`templates/mcp-config.json`)
- The generated file is gitignored (inside `executions/`)
- `NETDATA_MCP_KEY_<ALIAS>` value stored in run `secrets/`; operator sets it as env var
  when installing the artifact elsewhere (global config, remote agent, other machine)
- README documents: how to install (merge into `~/.config/opencode/opencode.json` or a
  remote agent's config), how to disable (`"enabled": false`)

## 6. Gotchas → notes/gotchas.md

- **G1 dnf $releasever_major**: dnf 4.14 on Rocky 9 doesn't substitute
  `$releasever_major` in repo baseurl → 404s. Fix: `/etc/dnf/vars/releasever_major=9`
  (generic dnf var substitution; `--setopt` does NOT work pre-4.21)
- **G2 disabled repos**: netdata repos may be disabled (`enabled=0`) after prior 404s;
  `dnf config-manager --set-enabled netdata netdata-repoconfig` before updates
- **G3 stale cloud claim**: `/var/lib/netdata/cloud.d/cloud.conf` + `claimed_id` survive
  kickstart re-claim; the agent keeps serving the OLD claim. Fix: stop netdata, remove
  `claim.conf` + `cloud.d`, re-claim. Verify via API that `claim_id` changed.
- **G4 PowerShell quote mangling**: Windows ssh concatenates args and strips inner
  quotes → use quote-free grep/`scp` scripts instead of nested-quote one-liners
- **G5 no root SSH**: if sudo is password-gated, prepare exact commands for the operator
  to run; never handle passwords
- **G6 hostname before claim**: set hostname BEFORE claiming or the Cloud node shows the
  old name (rename in Cloud UI is manual)
- **G7 MCP protocol details**: `POST http://<node>:19999/mcp` with
  `Accept: application/json, text/event-stream`; JSON-RPC: `initialize` → (capture
  `mcp-session-id` header) → `notifications/initialized` → `tools/list` → `tools/call`
- **G8 default exposure**: `:19999` is internet-open by default (anonymous MCP initialize
  succeeds). Always run the hardening step after install
- **G9 v2 claim is kickstart-only**: netdata v2 has no claim CLI flag; kickstart handles
  claiming. Netdata Cloud MCP needs a Paid plan; local agent MCP works on free

## 7. Safety doctrine compliance (repo AGENTS.md)

- Reads (SSH inspection, MCP `tools/call` on read endpoints) are free
- Every production WRITE (hostname, install, hardening config + restart, claim/unclaim)
  is flagged **WRITE** in plan.md and requires approval per the run's permission mode
- Real values (IPs, tokens, keys) appear ONLY in `executions/<run>/` — never in committed
  files, shell history, or logs
- Rollback documented for every WRITE step (e.g. revert netdata.conf + restart for
  hardening; re-run kickstart for claim)
- Secrets never in SSH command lines; keys/tokens via files in run `secrets/`

## 8. Out of scope (YAGNI)

- Custom MCP bridge server
- Cloud MCP (paid plan) integration
- Netdata alert action automation (agent executes fixes autonomously) — always operator
  approval gate
- Global/project-level MCP registration
