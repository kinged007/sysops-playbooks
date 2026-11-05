---
name: netdata-monitoring
description: Install or update the netdata agent on servers, harden its web API (bearer token protection and MCP API key), optionally claim it to Netdata Cloud, record a per-node MCP config, and run fleet alert checks with a remedy plan. Use for onboarding a server into netdata, fixing a netdata install that will not update, closing an exposed :19999 API, or checking all nodes for alerts. Not for non-netdata monitoring stacks.
---

# Netdata Monitoring

> Read `references/gotchas.md` BEFORE any run. G1-G18 are lessons from earlier
> runs and may change how you plan. Never skip this.

Risk level: medium. Installs packages and changes netdata config on production
servers (all **WRITE**-flagged, approval-gated, rollback documented). The
default `:19999` exposure is treated as a vulnerability and hardened on every
run.

## When to use

- Onboarding a new server into netdata monitoring.
- Updating an existing netdata install that will not update or install.
- Hardening a node whose netdata web API (`:19999`) is exposed.
- Routine fleet alert checks ("check all the nodes for alerts"): reads only, then an operator-approved plan before any write.
- Not for: monitoring stacks other than netdata.

Prerequisites:

- Key-based SSH access to each target (`ops ssh <server>`).
- The operator's install command (for example the netdata kickstart script with a claim token), recorded in the runbook at run time.
- A Netdata Cloud account only if claiming (free plan is fine; Cloud MCP needs a paid plan, the local agent MCP does not).
- Permission mode set at plan approval (A: confirm before each write, B: plan-as-approved).

## Fleet refs needed

- `fleet/servers.yaml`: one record per target node (ssh alias, node address, OS family). `<ALIAS>` below is the server's ssh alias; `<NODE_ADDRESS>` is its address from the record.
- `fleet/services.yaml`: service `netdata` per node (port `19999`, health endpoint), if recorded.

## Vault entries needed

Names follow `<client>-<provider>-<purpose>`. Values are never printed or logged.

- `<client>-netdata-claim-token`: Netdata Cloud claim token or full install command, only when claiming.
- `<client>-netdata-mcp-key-<alias>`: the node's MCP API key (read from the node in step 4).
- `ssh/<client>-<server>`: ssh key from the server's fleet record.

## Procedure

Rules for every step:

- Reads need no flag. Every step that changes a production system is flagged **WRITE** and needs approval per the run's permission mode (A: per-write confirm / B: plan-as-approved).
- Every destructive **WRITE** (config overwrite, unclaim, downgrade, removal) is preceded by a **Backup** step.
- Every **WRITE** has a **Rollback** line.
- Every fix is followed by a **Verify** step.
- Commands use placeholders (`<ALIAS>`, `<NODE_ADDRESS>`, `<KEY>`); real values come from fleet records and the vault.

### 0. Pre-flight

- [ ] Read `references/gotchas.md` (mandatory)
- [ ] Resolve the fleet records and vault entries listed above; confirm the operator's install command and the permission mode
- [ ] Confirm access: `ssh -o BatchMode=yes <ALIAS> 'hostname'` (one line, no prompts)
- [ ] Record the run's permission mode in the runbook

### 1. Discover current state (reads only)

- [ ] Agent version/status: `ssh <ALIAS> 'netdata -v; systemctl is-active netdata'`
- [ ] Repo state (G1/G2): `ssh <ALIAS> 'grep -r "^enabled" /etc/yum.repos.d/netdata*.repo 2>/dev/null; dnf repolist 2>/dev/null | grep -i netdata'`
- [ ] Claim state (G3): `ssh <ALIAS> 'cat /etc/netdata/claim.conf 2>/dev/null; ls /var/lib/netdata/cloud.d 2>/dev/null'`
- [ ] Exposure check (G8): `curl -s -m 5 -o NUL -w "%{http_code}" http://<NODE_ADDRESS>:19999/api/v1/info`. `200` means the web API is internet-open; hardening (step 4) is mandatory
- [ ] Record findings in the runbook: old hostname, old netdata version, existing claim ids for rollback reference

### 2. Hostname decision (ask the operator)

- [ ] ASK: "Do you want to define a hostname for this node? (current: `<CURRENT_HOSTNAME>`)". If no, skip and use the current hostname
- [ ] **Backup**: record `<CURRENT_HOSTNAME>` in the runbook
- [ ] **WRITE**: `ssh <ALIAS> 'sudo hostnamectl set-hostname <NEW_HOSTNAME>'`
  - Rollback: `ssh <ALIAS> 'sudo hostnamectl set-hostname <CURRENT_HOSTNAME>'`
- [ ] Verify: `ssh <ALIAS> 'hostname'` returns the chosen name
- [ ] Record the decision and chosen name in the runbook. This must happen before any claim (G6), so the Cloud node is named correctly

### 3. Install or update netdata (operator command)

- [ ] ASK the operator for their install command and RECORD IT VERBATIM in the runbook (for example `wget -O /tmp/netdata-kickstart.sh https://get.netdata.cloud/kickstart.sh && sh /tmp/netdata-kickstart.sh --nightly-channel --claim-token <TOKEN> --claim-rooms <ROOM> --claim-url https://app.netdata.cloud`)
  - Any secret inside the command (claim token) is stored ONLY in vault entry `<client>-netdata-claim-token`; the runbook shows it redacted
- [ ] **Backup**: record the installed version (`netdata -v`) and package list (`ssh <ALIAS> 'dnf list installed "netdata*"'` or `dpkg -l | grep netdata`) in the runbook; copy `/etc/netdata` to a dated backup path on the node
- [ ] If the agent is installed and only an update is needed (G1/G2):
  - **WRITE**: `ssh <ALIAS> 'echo 9 | sudo tee /etc/dnf/vars/releasever_major; sudo dnf config-manager --set-enabled netdata netdata-repoconfig; sudo dnf update -y netdata*'`
    - Rollback: `sudo dnf downgrade -y netdata*` (or reinstall from snapshot/backup; use the previous version recorded in the runbook)
- [ ] If installing fresh: run the operator's recorded install command via SSH (as the operator specified; it may include `sudo`, or the operator may need to run it if sudo is password-gated, G5)
  - **WRITE** on the target.
    - Rollback: `sudo dnf remove -y netdata*` and restore any previous install from the recorded version
- [ ] Verify: `ssh <ALIAS> 'netdata -v; systemctl is-active netdata'` shows the new version and `active`

### 4. Harden netdata access (security #1) - **WRITE**, approval required

- [ ] Check claim state FIRST (G18): `ssh <ALIAS> 'netdatacli aclk-state'`. Bearer protection only works on claimed nodes (G17). If unclaimed: keep `bearer token protection = no`, go to step 6 (claim), then come back and enable it; or harden via firewall/IP restriction instead
- [ ] **Backup**: `ssh <ALIAS> 'sudo cp -a /etc/netdata/netdata.conf /etc/netdata/netdata.conf.bak-<DATE>'`
- [ ] Enable bearer token protection:
  - **WRITE**: `ssh <ALIAS> 'sudo sed -i "s/^#\? *bearer token protection *= *.*/bearer token protection = yes/" /etc/netdata/netdata.conf'`
    - If the `[web]` section or key is absent, add it under `[web]`: `[web]\n    bearer token protection = yes`
    - Rollback: set the value back to `no` (original recorded in the runbook), or restore `netdata.conf.bak-<DATE>`
- [ ] **WRITE**: `ssh <ALIAS> 'sudo systemctl restart netdata'`
  - Rollback: `ssh <ALIAS> 'sudo systemctl restart netdata'` (after reverting the config)
- [ ] Read the MCP API key (G9): `ssh <ALIAS> 'cat /var/lib/netdata/mcp_dev_preview_api_key'`; store it in vault entry `<client>-netdata-mcp-key-<alias>`; never in logs or the runbook
- [ ] Verify hardened (G8):
  - Anonymous must fail: `curl -s -m 5 -o NUL -w "%{http_code}" -X POST http://<NODE_ADDRESS>:19999/mcp -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"probe\",\"version\":\"1.0\"}}}'`. Expected: `401` or `403`
  - Keyed must succeed: same call with `-H "Authorization: Bearer <KEY>"`. Expected: `200`
- [ ] Note in the runbook: key vault entry name, and how to set the env var (`NETDATA_MCP_KEY_<ALIAS>`) for future agent configs

### 5. Generate the per-node MCP config artifact (local file, no production write)

- [ ] Copy `templates/mcp-config.json` to `runs/netdata-monitoring/mcp/<ALIAS>.mcp.json` (or `runs/netdata-monitoring-<suffix>/mcp/<ALIAS>.mcp.json` for a named variant)
- [ ] Fill in real values: server key `netdata-<ALIAS>`, `url` `http://<NODE_ADDRESS>:19999/mcp`, env var name `NETDATA_MCP_KEY_<ALIAS>`
- [ ] Validate: `python -m json.tool runs/netdata-monitoring/mcp/<ALIAS>.mcp.json`
- [ ] Note in the runbook how to install the artifact later: merge the `"mcp"` block into an agent's `opencode.json` and set the env var to the key in the vault entry. The file is gitignored (inside `runs/`); the key value never appears in committed files

### 6. Claim to Netdata Cloud (only if the operator provides a token)

- [ ] Store the operator's claim token or command in vault entry `<client>-netdata-claim-token`
- [ ] If the node was previously claimed (G3):
  - **Backup**: `ssh <ALIAS> 'sudo cp -a /etc/netdata/claim.conf /etc/netdata/claim.conf.bak-<DATE>; sudo cp -a /var/lib/netdata/cloud.d /var/lib/netdata/cloud.d.bak-<DATE>'`; record the old claim id (`netdatacli aclk-state`)
  - **WRITE** full unclaim: `sudo systemctl stop netdata; rm -f /etc/netdata/claim.conf; rm -rf /var/lib/netdata/cloud.d; sudo systemctl start netdata`
    - Rollback: restore the `.bak-<DATE>` copies and restart netdata, or re-run the old claim command if known
- [ ] **WRITE**: run the operator's claim/kickstart command
  - Rollback: unclaim as above and restore the backups
- [ ] Verify (G18): `ssh <ALIAS> 'netdatacli aclk-state'` shows `Claimed:` yes, `Online:` yes, and a NEW claim id; the node shows online in the target Cloud room (may take a minute)

### 7. Ops phase: check all nodes for alerts (reads only)

For EACH node in the fleet records:

- [ ] Initialize an MCP session (G7): `curl -s -X POST http://<NODE_ADDRESS>:19999/mcp -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "Authorization: Bearer <KEY>" -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"sysops-agent\",\"version\":\"1.0\"}}}'`; capture the `mcp-session-id` header
- [ ] `tools/list`: confirm the three alert tools exist
- [ ] `tools/call` `list_raised_alerts`: active WARNING/CRITICAL
- [ ] `tools/call` `list_running_alerts`: full picture including cleared
- [ ] `tools/call` `list_alert_transitions`: recent state changes
- [ ] Summarize per node: alert name, status, current value and units, last transition time, summary text, affected context
- [ ] Produce a severity table: CRITICAL / WARNING / informational, with duration and trend (rising/easing) where visible

### 8. Remedy plan and operator approval (never improvise)

- [ ] For each raised alert propose: context, likely cause, the exact fix command (**WRITE**-flagged, with **Backup** and Rollback), and priority order
- [ ] STOP. Present the remedy plan. Execute ONLY after the operator approves (per the run's permission mode). A deviation from the approved plan is a stop-and-ask (repo AGENTS.md section 6)

### 9. Verification

- [ ] Re-run `list_raised_alerts`: the raised set matches expectation (empty or approved remaining)
- [ ] Confirm every **WRITE** executed this run has a rollback recorded in the runbook (hostname, install, hardening config, restart, claim)
- [ ] Findings go to the run `notes.md`; propose lesson promotion to `references/gotchas.md` (operator approves promotion, never mid-run)

## Rollback

Apply the per-step rollback lines in reverse order: claim, hardening config
(restore `netdata.conf.bak-<DATE>` and restart), install or update (downgrade
or remove using the version recorded in step 3), hostname. If a rollback does
not return the node to the recorded state, stop and ask the operator.

## Verify

- [ ] `netdata -v` and `systemctl is-active netdata` on every touched node
- [ ] Anonymous `POST /mcp` fails and keyed `POST /mcp` returns `200` (claimed nodes)
- [ ] `netdatacli aclk-state` matches the intended claim state
- [ ] `list_raised_alerts` is empty or matches the approved remaining set

## Gotchas

Details for each in `references/gotchas.md`.

- G1/G2: dnf `$releasever_major` not substituted on Rocky 9; netdata repos can be silently disabled.
- G3/G18: stale claim state survives re-claims; verify claims with `netdatacli aclk-state`, not the API.
- G6: set the hostname before claiming.
- G8/G17: `:19999` is open by default; bearer protection needs a claimed agent. Order for new installs: install, tune, claim, enable bearer protection, verify.
- G10-G13: nightly with ML on burns CPU; network-viewer, go.d docker, and virtual interface charts add overhead on container hosts.
- G14/G15: channel switch is a repo package swap; the updater sleeps up to an hour unless `NETDATA_NOT_RUNNING_FROM_CRON=1`.

## Files

| Path | Purpose |
|---|---|
| `templates/mcp-config.json` | Per-node MCP server config template (placeholders) |
| `templates/plan-template.md`, `templates/runbook-template.md` | Copied to `runs/netdata-monitoring[-<suffix>]/` on first run |
| `references/gotchas.md` | G1-G18: pitfalls hit on the fleet, with fixes |
