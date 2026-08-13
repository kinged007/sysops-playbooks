# Netdata Monitoring Playbook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the `playbooks/netdata-monitoring/` playbook in `sysops-playbooks` so any future run can install, harden, and monitor netdata on operator-provided servers — with per-node MCP config artifacts recorded in the run's execution folder, generalized (placeholders only).

**Architecture:** A new playbook folder following the repo's existing conventions (`_playbook-template`, `coder-remote-servers`): README, canonical `playbook.md` (install + harden + claim + ops phases, every production WRITE flagged with rollback), plan/runbook templates, an MCP config template, and `notes/gotchas.md` (G1–G9 lessons learned from the Aug 11–12 netdata sessions). No project-level opencode config; real values only ever appear in `executions/<run>/`.

**Tech Stack:** Markdown playbooks, JSON template, curl JSON-RPC recipes against netdata's local agent MCP endpoint (`http://<NODE_ADDRESS>:19999/mcp`), SSH for production access.

**Spec:** `docs/superpowers/specs/2026-08-13-netdata-monitoring-playbook-design.md`

---

## File Structure

| Path | Responsibility |
|---|---|
| `playbooks/netdata-monitoring/README.md` | Purpose, when to use, prerequisites, risk level, files table |
| `playbooks/netdata-monitoring/playbook.md` | Canonical procedure: pre-flight, state discovery, hostname ask, install/update (operator command recorded), hardening, MCP artifact generation, claim, ops (check-all-nodes), verification/rollback |
| `playbooks/netdata-monitoring/plan-template.md` | Per-run plan skeleton (copied to `executions/<run>/plan.md`) |
| `playbooks/netdata-monitoring/runbook-template.md` | Per-run runbook skeleton (copied to `executions/<run>/runbook.md`) |
| `playbooks/netdata-monitoring/templates/mcp-config.json` | Placeholder-only per-node MCP server config (source for the generated artifact) |
| `playbooks/netdata-monitoring/notes/gotchas.md` | G1–G9 lessons learned (mandatory read before any run) |

---

### Task 1: Scaffold folder + plan/runbook templates

**Files:**
- Create: `playbooks/netdata-monitoring/plan-template.md`
- Create: `playbooks/netdata-monitoring/runbook-template.md`

- [ ] **Step 1: Create the folder**

Run:
```powershell
New-Item -ItemType Directory -Path "D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring\notes" -Force
New-Item -ItemType Directory -Path "D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring\templates" -Force
New-Item -ItemType Directory -Path "D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring\scripts" -Force
```
Expected: three directories created, no errors.

- [ ] **Step 2: Copy the generic plan template**

Run:
```powershell
Copy-Item "D:\Data\git\sysops-playbooks\playbooks\_playbook-template\plan-template.md" "D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring\plan-template.md"
Get-Content "D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring\plan-template.md" | Select-Object -First 3
```
Expected: file copied; first lines show `# Plan: <RUN NAME>` and the fields table.

- [ ] **Step 3: Copy the generic runbook template**

Run:
```powershell
Copy-Item "D:\Data\git\sysops-playbooks\playbooks\_playbook-template\runbook-template.md" "D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring\runbook-template.md"
Get-Content "D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring\runbook-template.md" | Select-Object -First 3
```
Expected: file copied; first lines show `# Runbook: <RUN NAME>`.

- [ ] **Step 4: Commit**

```bash
git add playbooks/netdata-monitoring/plan-template.md playbooks/netdata-monitoring/runbook-template.md
git commit -m "feat(netdata-monitoring): scaffold playbook with plan/runbook templates"
```

---

### Task 2: README.md

**Files:**
- Create: `playbooks/netdata-monitoring/README.md`

- [ ] **Step 1: Write the README**

Create `D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring\README.md` with EXACTLY this content:

```markdown
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
```

- [ ] **Step 2: Verify the README contains the mandatory notes line**

Run:
```powershell
Select-String -Path "D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring\README.md" -Pattern "read ``notes/`` BEFORE any run"
```
Expected: exactly one match.

- [ ] **Step 3: Commit**

```bash
git add playbooks/netdata-monitoring/README.md
git commit -m "feat(netdata-monitoring): add README"
```

---

### Task 3: MCP config template

**Files:**
- Create: `playbooks/netdata-monitoring/templates/mcp-config.json`

- [ ] **Step 1: Write the template**

Create `D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring\templates\mcp-config.json` with EXACTLY this content (placeholders only — valid JSON):

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

- [ ] **Step 2: Verify it parses as valid JSON**

Run:
```powershell
python -m json.tool "D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring\templates\mcp-config.json"
```
Expected: the JSON pretty-printed back, no error. Placeholders inside strings are fine.

- [ ] **Step 3: Verify no real values leaked**

Run:
```powershell
Select-String -Path "D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring\templates\mcp-config.json" -Pattern "207\.180\.216\.129|62\.171\.191\.174|my-tech-vps|contabo"
```
Expected: NO output (zero matches).

- [ ] **Step 4: Commit**

```bash
git add playbooks/netdata-monitoring/templates/mcp-config.json
git commit -m "feat(netdata-monitoring): add per-node MCP config template"
```

---

### Task 4: notes/gotchas.md

**Files:**
- Create: `playbooks/netdata-monitoring/notes/gotchas.md`

- [ ] **Step 1: Write the gotchas**

Create `D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring\notes\gotchas.md` with EXACTLY this content:

```markdown
# Netdata gotchas (G1–G9)

Lessons from real runs. **Read before planning any run.** Every run must
check for the conditions below before writing anything.

## G1 — dnf `$releasever_major` not substituted (Rocky 9)
dnf 4.14 on Rocky 9 does NOT substitute `$releasever_major` in repo baseurls —
the literal string goes to the server → 404s. The built-in variable only
landed in dnf 4.21.
- Fix: `echo 9 | sudo tee /etc/dnf/vars/releasever_major` (generic dnf var
  substitution, survives repo-file updates)
- `dnf --setopt=releasever_major=9` does NOT work on 4.14 — don't waste time
- Symptom: `dnf update` finds no netdata packages, or repo metadata 404

## G2 — netdata repos silently disabled
Repos can be left `enabled=0` after a previous 404 incident — then update and
install both do nothing.
- Check: `grep -r "^enabled" /etc/yum.repos.d/netdata*.repo`
- Fix: `sudo dnf config-manager --set-enabled netdata netdata-repoconfig`

## G3 — stale cloud claim state survives re-claims
A kickstart re-claim writes new config, but the running agent keeps serving
the OLD claim from `/var/lib/netdata/cloud.d/cloud.conf` (and `claimed_id`).
The node never appears in the new workspace.
- Fix: stop netdata, remove `claim.conf` + the whole `cloud.d` dir, re-run the
  claim, then verify via the API that `claim_id` CHANGED
- Verify claim id: query the agent API `claim_id` field before/after

## G4 — Windows PowerShell mangles quotes in ssh args
Inner quotes in `ssh <alias> 'cmd "with" quotes'` get stripped by PowerShell
arg concatenation — commands fail silently or do the wrong thing.
- Fix: prefer quote-free patterns (`grep -v ^#` over `grep -v '^#'`), or scp a
  script and run it, or write the remote command to a file first

## G5 — password-gated sudo (no root SSH)
Some hosts expose only a non-root user whose sudo needs a password. We never
handle passwords.
- Fix: prepare the exact commands and ask the operator to run them, or have
  the operator add a scoped NOPASSWD sudoers line (see repo AGENTS.md §5)

## G6 — set hostname BEFORE claiming
If you claim before `hostnamectl set-hostname`, the Cloud node keeps the old
name and renaming it in the Cloud UI is manual. Order matters: hostname
first, then claim.

## G7 — agent MCP protocol details
- Endpoint: `POST http://<NODE_ADDRESS>:19999/mcp`
- Headers: `Content-Type: application/json`,
  `Accept: application/json, text/event-stream`
- Sequence: `initialize` → capture the `mcp-session-id` response header →
  `notifications/initialized` → `tools/list` → `tools/call`
- Alert tools: `list_raised_alerts` (WARNING/CRITICAL only),
  `list_running_alerts` (all), `list_alert_transitions` (history)
- Responses may be SSE events (`data: {...}` lines) or plain JSON — parse both
- OpenCode supports streamable-HTTP remote MCP (`type: "remote"`); SSE has
  known issues — use the HTTP endpoint, not SSE

## G8 — `:19999` is internet-open by default
Fresh installs answer anonymous requests on the public interface (verified:
anonymous `POST /mcp` initialize succeeds). Anyone can read metrics/alerts.
- Always run the hardening step after install (bearer token protection + MCP
  API key), and verify anonymous access now fails

## G9 — v2 claim is kickstart-only; Cloud MCP needs a paid plan
- netdata v2 has no built-in claim CLI flag — the kickstart script handles
  claiming (running it on an existing install just claims/updates it)
- Netdata Cloud MCP (`app.netdata.cloud/api/v1/mcp`) requires a **paid** plan;
  the local agent MCP (`:19999/mcp`) works on the free plan — prefer it
- The MCP API key file is `/var/lib/netdata/mcp_dev_preview_api_key`
```

- [ ] **Step 2: Verify no real values leaked**

Run:
```powershell
Select-String -Path "D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring\notes\gotchas.md" -Pattern "207\.180\.216\.129|62\.171\.191\.174|my-tech-vps|contabo|tskey-"
```
Expected: NO output (zero matches).

- [ ] **Step 3: Commit**

```bash
git add playbooks/netdata-monitoring/notes/gotchas.md
git commit -m "feat(netdata-monitoring): add G1-G9 gotchas notes"
```

---

### Task 5: playbook.md (canonical procedure)

**Files:**
- Create: `playbooks/netdata-monitoring/playbook.md`

- [ ] **Step 1: Write the playbook**

Create `D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring\playbook.md` with EXACTLY this content:

```markdown
# Playbook: Netdata Monitoring — Procedure

Canonical steps for a run. **Placeholders only** — never real IPs, hostnames,
usernames, or credentials. Real values go in the execution's `plan.md`,
`inventory.md`, and `secrets/`.

Conventions: every step that WRITES to a production system is flagged
**WRITE** and needs approval per the run's permission mode (A: per-write
confirm / B: plan-as-approved). Rollback is given for every write. Reads are
free.

## 0. Pre-flight
- [ ] Read `notes/gotchas.md` (mandatory) — G1–G9 may change how you plan
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
- [ ] Copy `templates/mcp-config.json` to `executions/<RUN>/mcp/<ALIAS>.mcp.json`
- [ ] Fill in real values: server key `netdata-<ALIAS>`, `url`
      `http://<NODE_ADDRESS>:19999/mcp`, env var name `NETDATA_MCP_KEY_<ALIAS>`
- [ ] Validate: `python -m json.tool executions/<RUN>/mcp/<ALIAS>.mcp.json`
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
```

- [ ] **Step 2: Verify required structure elements exist**

Run:
```powershell
$p = Get-Content "D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring\playbook.md" -Raw
[PSCustomObject]@{
  WRITEFlags   = ([regex]::Matches($p, '\*\*WRITE\*\*')).Count
  Placeholders = ([regex]::Matches($p, '<[A-Z_]+>')).Count
  AskHostname  = $p -match 'Do you want to define a hostname'
  InstallCmd   = $p -match 'install command'
  Hardening    = $p -match 'bearer token protection'
  MCPArtifact  = $p -match 'mcp.config.json'
  Rollback     = ([regex]::Matches($p, 'Rollback')).Count
} | Format-List
```
Expected: `WRITEFlags` ≥ 6, `Placeholders` ≥ 10, all boolean fields `True`, `Rollback` ≥ 5.

- [ ] **Step 3: Verify no real values leaked**

Run:
```powershell
Select-String -Path "D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring\playbook.md" -Pattern "207\.180\.216\.129|62\.171\.191\.174|my-tech-vps|contabo|tskey-|nIceXcK"
```
Expected: NO output (zero matches).

- [ ] **Step 4: Commit**

```bash
git add playbooks/netdata-monitoring/playbook.md
git commit -m "feat(netdata-monitoring): add canonical playbook procedure"
```

---

### Task 6: Full validation & repo hygiene

**Files:** (none created — verification only)

- [ ] **Step 1: JSON validity of the template**

Run:
```powershell
python -m json.tool "D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring\templates\mcp-config.json" | Out-Null
if ($?) { Write-Output "JSON OK" }
```
Expected: `JSON OK`.

- [ ] **Step 2: Repo-wide no-leak check (AGENTS.md §7)**

Run:
```powershell
git status
git ls-files --cached --others --exclude-standard | ForEach-Object { if (Test-Path $_) {
  $c = Get-Content $_ -Raw
  if ($c -match 'tskey-|BEGIN (CERTIFICATE|PRIVATE|RSA)') { Write-Output "LEAK: $_" }
}}
```
Expected: `git status` shows only the new playbook files (no `executions/`,
no `secrets/`); no `LEAK:` lines.

- [ ] **Step 3: Confirm no real hostnames/IPs anywhere in the new playbook**

Run:
```powershell
Select-String -Path "D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring\*" -Pattern "207\.180\.216\.129|62\.171\.191\.174|my-tech-vps|contabo" -Recurse
```
Expected: NO output (zero matches across README, playbook, templates, notes).

- [ ] **Step 4: Final structural review — files present**

Run:
```powershell
Get-ChildItem "D:\Data\git\sysops-playbooks\playbooks\netdata-monitoring" -Recurse -File | Select-Object -ExpandProperty FullName
```
Expected: README.md, playbook.md, plan-template.md, runbook-template.md,
templates/mcp-config.json, notes/gotchas.md (scripts/ empty or .gitkeep).

- [ ] **Step 5: Commit any leftover hygiene fixes**

```bash
git status
# if anything staged/unstaged remains, commit it with a descriptive message
```

---

## Self-review notes

- **Spec coverage:** §3 (layout) → Tasks 1–5; §4 run flow (hostname ask,
  install command recorded, hardening, MCP artifact, ops phase) → playbook.md
  §0–§8; §5 artifact format → Task 3 + playbook.md §5; §6 gotchas → Task 4
  (all G1–G9); §7 doctrine compliance → WRITE flags + rollbacks in every
  task's content. No gaps.
- **Placeholder scan:** all `<PLACEHOLDER>` tokens are intentional
  (playbook-level, filled at run time); no TBD/TODO.
- **Consistency:** artifact file naming (`mcp/<alias>.mcp.json`), env var
  naming (`NETDATA_MCP_KEY_<ALIAS>`), and key file
  (`/var/lib/netdata/mcp_dev_preview_api_key`) are identical across README,
  template, playbook, and gotchas.
