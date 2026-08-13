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
