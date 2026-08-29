# Playbook: Netdata Monitoring — Procedure

Canonical steps for a run. **Placeholders only** — never real IPs, hostnames,
usernames, or credentials. Real values go in the execution's `plan.md`,
`inventory.md`, and `secrets/`.

Conventions: every step that WRITES to a production system is flagged
**WRITE** and needs approval per the run's permission mode (A: per-write
confirm / B: plan-as-approved). Rollback is given for every write. Reads are
free.

## 0. Pre-flight
- [ ] Read `notes/gotchas.md` (mandatory) — G1–G18 may change how you plan
- [ ] Confirm prerequisites (README): SSH alias for each target, operator's
      install command, permission mode set at plan approval
- [ ] Confirm access: `ssh -o BatchMode=yes <ALIAS> 'hostname'` — one line,
      no prompts
- [ ] Record the run's permission mode in the runbook

## 1. Discover current state (reads only)
- [ ] Agent version/status: `ssh <ALIAS> 'netdata -v; systemctl is-active netdata'`
- [ ] Repo state (G1/G2): `ssh <ALIAS> 'grep -r "^enabled" /etc/yum.repos.d/netdata*.repo 2>/dev/null; dnf repolist 2>/dev/null | grep -i netdata'`
- [ ] Claim state (G3): `ssh <ALIAS> 'cat /etc/netdata/claim.conf 2>/dev/null; ls /var/lib/netdata/cloud.d 2>/dev/null'`
- [ ] Exposure check (G8): `curl -s -m 5 -o NUL -w "%{http_code}" http://<NODE_ADDRESS>:19999/api/v1/info`
      — `200` means the web API is internet-open; hardening (§4) is mandatory
- [ ] Record findings in the runbook; note old hostname, old netdata version,
      existing claim ids for rollback reference

## 2. Hostname decision (ask the operator)
- [ ] ASK: "Do you want to define a hostname for this node? (current:
      `<CURRENT_HOSTNAME>`)"
      - If yes — **WRITE**: `ssh <ALIAS> 'sudo hostnamectl set-hostname <NEW_HOSTNAME>'`
        - Rollback: `ssh <ALIAS> 'sudo hostnamectl set-hostname <CURRENT_HOSTNAME>'`
      - If no: skip, use the current hostname
- [ ] Record the decision and the chosen name in the runbook. **Must happen
      before any claim** (G6), so the Cloud node is named correctly

## 3. Install or update netdata (operator command)
- [ ] ASK the operator for their install command and RECORD IT VERBATIM in
      the runbook (e.g. `wget -O /tmp/netdata-kickstart.sh https://get.netdata.cloud/kickstart.sh && sh /tmp/netdata-kickstart.sh --nightly-channel --claim-token <TOKEN> --claim-rooms <ROOM> --claim-url https://app.netdata.cloud`)
      - Any secret inside the command (claim token) is stored ONLY in
        `secrets/install-command-<ALIAS>.txt`; the runbook shows it redacted
- [ ] If the agent is already installed and only an update is needed (G1/G2):
      - **WRITE**: `ssh <ALIAS> 'echo 9 | sudo tee /etc/dnf/vars/releasever_major; sudo dnf config-manager --set-enabled netdata netdata-repoconfig; sudo dnf update -y netdata*'`
        - Rollback: `sudo dnf downgrade -y netdata*` (or reinstall from
          snapshot/backup; record the previous version in the runbook)
- [ ] If installing fresh: run the operator's recorded install command via
      SSH (as the operator specified — may include `sudo` or need the
      operator to run it themselves if sudo is password-gated, G5)
      - **WRITE** on the target; Rollback: `sudo dnf remove -y netdata*` and
        restore any previous install from the recorded version
- [ ] Verify: `ssh <ALIAS> 'netdata -v; systemctl is-active netdata'` — new
      version, `active`

## 4. Harden netdata access (security #1) — **WRITE**, approval required
- [ ] Check claim state FIRST (G18): `ssh <ALIAS> 'netdatacli aclk-state'` —
      bearer protection only works on claimed nodes (G17). If unclaimed:
      keep `bearer token protection = no`, skip to §6 (claim), then come back
      and enable it — or harden via firewall/IP restriction instead
- [ ] Enable bearer token protection:
      - **WRITE**: `ssh <ALIAS> 'sudo sed -i "s/^#\? *bearer token protection *= *.*/bearer token protection = yes/" /etc/netdata/netdata.conf'`
        - If the `[web]` section or key is absent, add it under `[web]`:
          `[web]\n    bearer token protection = yes`
        - Rollback: set the value back to `no` (record original in runbook)
- [ ] **WRITE**: `ssh <ALIAS> 'sudo systemctl restart netdata'`
      - Rollback: `ssh <ALIAS> 'sudo systemctl restart netdata'` (after
        reverting the config)
- [ ] Read the MCP API key (G9): `ssh <ALIAS> 'cat /var/lib/netdata/mcp_dev_preview_api_key'`
      → store in `secrets/netdata-mcp-key-<ALIAS>.txt`; never in logs/runbook
- [ ] Verify hardened (G8):
      - Anonymous must fail:
        `curl -s -m 5 -o NUL -w "%{http_code}" -X POST http://<NODE_ADDRESS>:19999/mcp -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"probe\",\"version\":\"1.0\"}}}'`
        — expected: `401` or `403`
      - Keyed must succeed: same call with
        `-H "Authorization: Bearer <KEY>"` — expected: `200`
- [ ] Note in the runbook: key location, how to set the env var
      (`NETDATA_MCP_KEY_<ALIAS>`) for future agent configs

## 5. Generate the per-node MCP config artifact (local file, no production write)
- [ ] Copy `templates/mcp-config.json` to `executions/netdata-monitoring/mcp/<ALIAS>.mcp.json` (or `executions/netdata-monitoring-<suffix>/mcp/<ALIAS>.mcp.json` for a named variant)
- [ ] Fill in real values: server key `netdata-<ALIAS>`, `url`
       `http://<NODE_ADDRESS>:19999/mcp`, env var name `NETDATA_MCP_KEY_<ALIAS>`
- [ ] Validate: `python -m json.tool executions/netdata-monitoring/mcp/<ALIAS>.mcp.json`
- [ ] Note in the runbook: how to install this artifact later (merge into an
      agent's `opencode.json`; set the env var to the key in `secrets/`)

## 6. Claim to Netdata Cloud (only if the operator provides a token)
- [ ] If the operator gives a claim token/command: store the command in
      `secrets/`, run it via SSH
      - If the node was previously claimed (G3): **WRITE** full unclaim first:
        `sudo systemctl stop netdata; rm -f /etc/netdata/claim.conf; rm -rf /var/lib/netdata/cloud.d; sudo systemctl start netdata`
        - Rollback: re-run the old claim command if known, or re-claim after
      - **WRITE**: run the operator's claim/kickstart command
- [ ] Verify: query the agent API `claim_id` — must be a NEW id; node shows
      online in the target Cloud room (may take a minute)

## 7. Ops phase — check all nodes for alerts (reads only)
For EACH node in inventory:
- [ ] Initialize an MCP session (G7):
      `curl -s -X POST http://<NODE_ADDRESS>:19999/mcp -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "Authorization: Bearer <KEY>" -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"sysops-agent\",\"version\":\"1.0\"}}}'`
      — capture `mcp-session-id` header
- [ ] `tools/list` — confirm the three alert tools exist
- [ ] `tools/call` `list_raised_alerts` — active WARNING/CRITICAL
- [ ] `tools/call` `list_running_alerts` — full picture incl. cleared
- [ ] `tools/call` `list_alert_transitions` — recent state changes
- [ ] Summarize per node: alert name, status, current value + units, last
      transition time, summary text, affected context
- [ ] Produce a severity table: CRITICAL / WARNING / informational; include
      duration and trend (rising/easing) where visible

## 8. Remedy plan → operator approval (never improvise)
- [ ] For each raised alert propose: context, likely cause, the exact fix
      command (**WRITE**-flagged, with rollback), and priority order
- [ ] STOP. Present the remedy plan. Execute ONLY after the operator approves
      (per the run's permission mode). Deviations from the approved plan are
      a stop-and-ask (repo AGENTS.md §6)

## 9. Verification & rollback
- [ ] Re-run `list_raised_alerts` — raised set matches expectation (empty or
      approved remaining)
- [ ] Confirm every **WRITE** executed this run has a rollback recorded in the
      runbook (hostname, install, hardening config, restart, claim)
- [ ] Findings → run `notes.md`; propose lesson promotion to `notes/gotchas.md`
      (operator approves promotion, never mid-run)
