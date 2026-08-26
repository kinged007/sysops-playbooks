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

## G10 — nightly + ML on by default = chronic CPU burn (the #1 tune)
v2.x **nightly** builds with ML enabled (default) train on EVERY collected
dimension. A busy docker host with ~2–4k dimensions runs the main netdata
process at **20–40% of one core permanently**, plus apps.plugin ~10%.
- Diagnose: `ps -eo pcpu,comm --sort=-pcpu | head` — the netdata main process
  is the top consumer; `curl -s localhost:19999/api/v1/ml_info` shows
  `ml-running: 1`; count dimensions via `/api/v1/charts`
- Fix: `[ml] enabled = no` in `/etc/netdata/netdata.conf` + restart
- Verify: `ml_info` returns empty and no `anomaly*` charts exist in
  `/api/v1/charts` (this is the fastest red/green signal that ML is off)
- Expected effect on one 6-core VPS: ~30% → ~20% of a core (before the other
  trims below)

## G11 — network-viewer disable lives under `[plugins]`, not `[plugins:netdata]`
The network-viewer plugin enumerates ALL sockets via NETLINK_INET_DIAG on
every cycle — pure overhead on container hosts. The correct netdata.conf
section is `[plugins]`:
```
[plugins]
    network-viewer = no
```
- `[plugins:netdata]` is NOT accepted for this in v2.x — the plugin stays up
- Verify: after restart the `NETWORK-VIEWER` process is gone
  (`ps -eo comm | grep -i network`)

## G12 — go.d `docker` collector fail-loops against a slow docker store
go.d polls the docker API every second. When the docker store is huge/slow
(100+ GB of volumes, heavy overlay churn), each `images/json` call takes >1s:
- journald spams `skipping data collection: previous run is still in progress`
  (go.d collector=docker)
- dockerd CPU climbs and its log fills with `request cancelled by client ...
  status=499` on `/v1.55/images/json`
- Fix: `/etc/netdata/go.d/go.d.conf` (create if absent):
  ```
  modules:
    docker: no
  ```
  The rest of go.d keeps running; container CPU/mem still comes from the
  cgroups plugin — only the docker-engine API metrics are lost.

## G13 — virtual interface chart explosion (docker hosts)
Netdata creates ~10+ charts per network interface. Docker hosts accumulate
15–20+ virtual interfaces (`veth*`, `br-*`, `docker0`, `docker_gwbridge`,
`tailscale0`) = hundreds of wasted charts and ML/health work.
- Fix in netdata.conf:
  ```
  [plugin:proc:/proc/net/dev]
      disable by default interfaces matching = lo fireqos* *-ifb veth* br-* docker* tailscale*
  ```
- Keep `eth0`/real NICs monitored. Verified drop on one host: 1976 → 1302
  charts (~34% less work). Interface traffic charts for the host's real NIC
  are unaffected.

## G14 — channel switch on native installs = REPO PACKAGE swap, not the updater conf
`CHANNEL` in `/etc/netdata/netdata-updater.conf` only matters for tarball
installs. On apt (Ubuntu/Debian) the channel is WHICH repo package is
installed: `netdata-repo-edge` = nightly, `netdata-repo` = stable.
- Swap to stable: `apt-get install netdata-repo`, `apt-get update`
- Then pin the WHOLE package set, not just `netdata` — pinning only
  `netdata=2.11.0` fails with "held broken packages" because the plugin
  packages (`netdata-plugin-apps`, `-go`, `-network-viewer`, ...) stay at
  nightly and conflict:
  `apt-get install --allow-downgrades netdata=2.11.0 netdata-plugin-*=2.11.0 ...`
  (list them from `dpkg -l | grep netdata-plugin`)
- On Rocky/dnf the same logic applies: repo channel file swap, then
  `dnf downgrade netdata*`
- Verify: `netdata -V` — stable shows NO `-nightly` suffix (e.g. `v2.11.0`)

## G15 — netdata-updater.sh jitter makes it look hung
Non-interactive runs sleep 1–3600s before doing anything. The script
HARDCODES `NETDATA_UPDATER_JITTER=3600` and clobbers env values — the only
bypass is `NETDATA_NOT_RUNNING_FROM_CRON=1`:
```
NETDATA_NOT_RUNNING_FROM_CRON=1 /usr/libexec/netdata/netdata-updater.sh
```
- On apt installs it then shells to `apt` and can end with a confusing
  `NETDATA WAS NOT UPDATED` when the repo channel is edge but you expected
  stable — that's G14, not an updater bug

## G16 — ACLK/cloud link churn burns main-process CPU
A flapping netdata-cloud connection shows in `/var/log/netdata/access.log` as
repeated `ACLK DISCONNECTED` / `ACLK CONNECTED` plus
`HEALTH ... Processed N entries, queued M` — the main process eats 10–25% of
a core just syncing state. Local dashboard keeps working.
- Check: `grep -c "ACLK DISCONNECTED" /var/log/netdata/access.log` (high =
  churn) and the queued-entry counts
- Options: fix the path to app.netdata.cloud, or unclaim/disable the cloud
  link (`claim.conf`; re-claim is kickstart-only, see G9). Ask the operator
  before disconnecting — some teams use the cloud dashboard.
