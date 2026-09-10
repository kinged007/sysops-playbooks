# Playbook: Orca Remote Server — Procedure

Canonical steps for a run. **Placeholders only** — never real IPs, hostnames,
usernames, pairing links, or credentials. Real values go in the execution's
`plan.md` / `inventory.md` / `secrets/`.
Repo-level rules (folder discipline, secrets, committing): see `AGENTS.md`.
Upstream docs (read when in doubt): Orca `Remote Orca Servers`,
`Ways to run Orca`, `SSH worktrees`, `Orca CLI reference`, `Install`,
`Mobile companion`. Orca servers are **beta** — keep server and client on a
private path you control.

---

## 1. System overview

```
Client(s) · Orca UI                    Server · Orca runtime
  laptop desktop app                     desktop app share OR orca serve
  phone (Orca Mobile)                    repos + worktrees + terminals
  browser / automation                   agent CLIs + accounts + sessions
         │                                            ▲
         │  private path ONLY (pick at §2)            │
         └──────── Tailscale tailnet ─────────────────┘
                   trusted LAN / WireGuard /
                   SSH-forward / auth tunnel
                   NEVER raw public internet
```

- The **server** owns everything: repos, worktrees, terminals, tabs,
  provider accounts, agent sessions. Agents keep running when clients
  sleep or disconnect.
- The **client** is UI only. A login on the laptop does **not** carry over
  to the server — install and authenticate every agent CLI **on the server**.
- Host modes are exclusive — **one at a time per machine**:
  - **A. Desktop app share** — best for an old laptop, Mac mini, desktop
    you can leave signed in. Setup is Settings buttons; lifetime = while
    the desktop app runs.
  - **B. `orca serve`** — best for a headless Linux box, VM, managed
    service. Setup is a terminal command / systemd service; lifetime =
    while the foreground process or service runs.
- Install destination is orthogonal to host mode — **directly on the host**
  (VPS/machine, the default path) or **inside a Coder workspace container**
  (§6 Phase 4b). Same phases; different network plumbing and lifecycle.

### Remote Orca Server vs SSH worktrees (pick correctly)

| | Remote Orca Server (this playbook) | SSH worktrees (different docs) |
|---|---|---|
| Runtime owner | Server (Orca desktop or `orca serve`) | Laptop Orca |
| Survives laptop close | Yes — full session state on server | Agents keep running on host; laptop reattaches per-worktree |
| Multi-client | Laptop + web + mobile + automation share one runtime | One laptop drives the host |
| Setup | Share/pair with a URL | Import SSH config, pick **Run on** per worktree |

If the operator only wants "run this worktree's agents on a bigger box"
with the laptop owning the runtime → stop, use SSH worktrees instead.

## 2. Mandatory location/access decision (ASK FIRST — never assume)

> **Gate.** Before any install work, ask the operator these three questions
> verbatim (adapt names) and record the answers in `plan.md`. Do not proceed
> on guesses — the answers decide the network path and whether Tailscale is
> required.

**Question to ask up front:**

> "1. Where does this Orca server live — same LAN as the clients (e.g. home
> LAN Mac mini), a cloud VPS with a public IP, a home server behind NAT, or
> somewhere else? 2. How should clients reach it — Tailscale tailnet, LAN
> only, existing WireGuard/VLAN, SSH-forwarding, or an authenticated tunnel?
> 3. Should the server run as the desktop app (screen-attached machine) or
> headless `orca serve`? 4. Directly on the host, or inside a Coder
> workspace container on shared infrastructure (§6 Phase 4b)? If the server
> is not on a private LAN path the clients share, I strongly recommend
> Tailscale and will not expose the Orca port to the public internet."

### Decision table (apply, don't improvise)

| Server location | Clients | Required path |
|---|---|---|
| Same LAN, clients never leave it | LAN devices only | Trusted LAN is acceptable; Tailscale still recommended (roaming phones, ACLs) |
| Home server behind NAT / CGNAT | Roaming laptop + phone | **Tailscale REQUIRED** (suggested by this playbook) — NAT traversal + private `100.x.y.z` address |
| Cloud VPS with public IP | Anywhere | **Tailscale REQUIRED** — bind/pair over tailnet only; public forward **forbidden** |
| Already on WireGuard / trusted VLAN / auth tunnel | Members of that path | That private path is acceptable; Tailscale is the suggested alternative |
| Inside a Coder workspace (container) | Tailnet clients | **Tailscale REQUIRED**, direct-dial via host publish (§6 Phase 4b). The workspace is not a tailnet node — tunnel/loopback links are rejected by the app, so a published port is mandatory, not optional |
| "Just forward the port publicly" | — | **REFUSE.** Offer Tailscale, WireGuard, trusted LAN, SSH-forward, or an authenticated tunnel instead |

Rules:

- If the answer is anything other than "shared private LAN / existing
  private path", **suggest Tailscale** and proceed on Tailscale unless the
  operator explicitly picks another private path with justification.
- Record in `plan.md`: `server_location`, `access_path`,
  `host_mode (desktop | serve)`, `host_type (direct | coder-workspace)`,
  `pairing_address`, `fixed_port?`,
  `tailscale_required? (yes/no + why)`.
- Any later discovery that the network differs from the recorded answers →
  **DEVIATION**: stop, re-ask, get re-approval (AGENTS.md §3.4/§3.6).

## 3. Roles

| Task | Who | Why |
|---|---|---|
| Create/own Tailscale tailnet, approve devices, set ACLs/grants | **User** | Owns the identity |
| Provide SSH access (`ssh-copy-id`, keys) | **User** | Agent must never handle passwords |
| Desktop-app clicks (Advertise → New Link → Generate), copying the access link over a private channel | **User** (or agent over screen-shared session only if operator approves) | Link is a password-equivalent |
| `claude login` / `codex login` device flows, provider OAuth on the server | **User** | Interactive auth |
| Everything else (install, verify, `orca serve`, systemd, firewall checks, pairing on the client UI when credentials are already present) | **Agent** | Technical work |

**The agent's golden rule: never ask for (or accept) a password or a pairing
link in chat/logs.** Pairing links travel user→client over a private channel
and land in the execution's `secrets/`; passwords never leave the user.
If a step needs privilege the agent lacks, use scoped NOPASSWD sudoers (§5)
or hand the user the exact command.

## 4. Prerequisites

Before any SSH work:

1. **SSH alias for the server** — user runs `ssh-copy-id <user>@<host>`;
   agent gets `<alias>` (from `~/.ssh/config`). Record alias + key path in
   `plan.md`. No passwords, keys only.
2. **Tailscale account + tailnet** (when §2 requires it). Auth method:
   - **Reusable pre-auth key** (hands-off): Admin → Settings → Keys →
     Generate (Reusable=on, Ephemeral=off, no tags). Agent uses
     `sudo tailscale up --auth-key=<KEY>`. Keys expire (90d default) —
     store in the execution's `secrets/`, never in chat.
   - **Interactive**: each device prints an approval URL the user opens.
3. **Orca installers reachable** — GitHub Releases (macOS `.dmg` Apple
   Silicon/Intel, Windows `.exe`, Linux AppImage/`.deb`/`.rpm`) or
   `brew install --cask stablyai/orca/orca`. Note: the Linux CLI is named
   `orca-ide` (avoids the GNOME Orca screen-reader clash) — verify with
   `command -v orca || command -v orca-ide`.
4. **Client inventory** — which desktops/phones pair to this server, all on
   the same tailnet/path (§8 matrix depends on it).
5. **Notes read** — `notes/security.md`, `notes/client-connections.md`,
   `notes/gotchas.md` (+ `notes/coder-workspace.md` when §2 recorded
   `host_type=coder-workspace`).
6. **Coder path only** (`host_type=coder-workspace`): template with a
   published Orca port (§6 Phase 4b B1), workspace created + autostop set
   to manual, `coder` CLI authenticated, tailnet grant + host firewall
   slots reserved for the external port.

## 5. Access & privilege model (the sudo problem)

Production hosts often disable root SSH and require a password for every
`sudo`. The agent works around that without ever seeing a password:

```bash
# EVERY server (tailscale + firewall checks need privilege):
echo '<user> ALL=(root) NOPASSWD: /usr/bin/tailscale' | sudo tee /etc/sudoers.d/orca-setup
echo '<user> ALL=(root) NOPASSWD: /usr/sbin/ufw'     | sudo tee -a /etc/sudoers.d/orca-setup
sudo chmod 0440 /etc/sudoers.d/orca-setup
sudo visudo -c        # must print "parsed OK"
```

- Scoped to exactly the binaries the playbook needs; **removable after the
  run** (re-locks everything).
- Agent check: `sudo -n -l` must show the entries. `sudo -n whoami`
  failing is **expected** — that is the point of scoping.
- If the agent already has root SSH, no sudoers needed.

## 6. Procedure — Phases 0–8

### Phase 0 — Repo prep (read)

- [ ] Read `notes/` (mandatory — security invariants may change the plan).
- [ ] Scan `executions/orca-remote-server*/` for an existing variant; confirm
  reuse vs new `-<suffix>` with the operator (AGENTS.md discovery gate).
- [ ] Fill `plan.md` §2 answers (location / access path / host mode). Plan
  stays draft until approved + permission mode (A/B) recorded.

### Phase 1 — Tailscale on server (+ clients when required)

Skip only when §2 recorded "shared LAN / existing private path, Tailscale
explicitly declined" — otherwise **WRITE**:

```bash
# - [ ] **WRITE** install Tailscale on <alias>
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --auth-key=<TAILSCALE_AUTH_KEY> --hostname=<SERVER_TAILNET_NAME>
# or interactive: sudo tailscale up --hostname=<SERVER_TAILNET_NAME>  (user approves URL)

# - [ ] verify (read)
tailscale ip          # expect 100.x.y.z — record as <SERVER_TAILSCALE_IP>
tailscale status      # both server + clients online, same tailnet
tailscale ping <CLIENT_TAILNET_NAME>   # expect pong
```

- Rollback: `sudo tailscale logout` removes the node from the tailnet;
  delete the node in the admin console if the run is abandoned.
- If the Orca connection-address picker later lacks the `100.x` address:
  confirm `tailscale status` shows connected, click the refresh button in
  Settings → Remote Orca Servers. Both sides must share the tailnet.
- Name nodes **at auth time**: server = `<SERVER_TAILNET_NAME>`
  (e.g. `orca-server`), clients keep recognizable names. Never reuse names.

### Phase 2 — Install Orca on the server (**WRITE**)

Pick the installer for the server OS. Verify after install.

```bash
# - [ ] **WRITE** install Orca on <alias> (choose ONE)

# macOS (server with desktop):
brew install --cask stablyai/orca/orca

# Linux headless (AppImage = self-updating; .deb/.rpm = package-manager updates):
# download from https://github.com/stablyai/orca/releases then install per OS docs

# - [ ] verify (read)
command -v orca || command -v orca-ide
orca status --json        # or: orca-ide status --json
```

- Keep **server and client on the same Orca version** (protocol mismatches
  show as incompatible-version / disconnected — update both sides).
- Linux server terminals need a compiler toolchain for the Orca relay's
  native modules, else files/git work but terminals don't:
  - Debian/Ubuntu: `sudo apt-get install -y build-essential python3`
  - Fedora/RHEL: `sudo dnf install -y make gcc gcc-c++ python3`
  - Alpine: `sudo apk add build-base python3`
  - Arch: `sudo pacman -S --needed base-devel python`
- Rollback: uninstall via the same channel (brew cask uninstall / package
  remove / delete AppImage). No system state besides the app + `~/.orca`.

### Phase 3 — Server-side tooling: repos, agent CLIs, accounts, skills

Orca sessions use the **server's** `PATH`, home directory, and credentials.

```bash
# - [ ] verify (read): git + provider CLIs present on <alias>
git --version
command -v claude; command -v codex; command -v opencode

# - [ ] **WRITE** install + authenticate missing CLIs on <alias>
# install per vendor docs, then (USER runs the interactive login):
orca account add --agent claude
orca account add --agent codex
orca account list          # (read) both accounts registered

# - [ ] **WRITE** install/refresh skills on <alias> (no Settings UI on headless)
orca skills install --skill orca-cli --skill orchestration
orca skills update --all
```

- The remote client **disables Add account** — accounts must be registered
  from the server shell. Run these on the machine that owns the accounts,
  not through a client-only remote session.
- Clone/place the repos the agents will work in on the server now; note
  absolute server paths in `inventory.md` (remote selectors prefer
  `path:<absolute-server-path>`).
- Rollback: `orca account` removals per CLI docs; `orca skills update`
  is additive (no rollback needed beyond noting versions).

### Phase 4 — Start the server runtime (ONE host mode only)

#### Mode A — Desktop app share (screen-attached server; USER clicks)

No command — the user, on the server:

1. Open the Orca desktop app → **Settings → Remote Orca Servers**.
2. Under **Advertise this app as a server** → **New Link**.
3. **Connection address**: select the **Tailscale address** (`100.x.y.z`).
   Never `127.0.0.1` (server-local only), never a wildcard.
4. **Generate Access Link** → copy the link under **Pair another Orca
   client** and hand it to the intended client over a **private channel**.
5. Keep the app running, machine awake and online.

Agent verifies (read): server app open, tailnet online, address matches
`<SERVER_TAILSCALE_IP>`. Do **not** also start `orca serve` on this machine.

#### Mode B — Headless `orca serve` (**WRITE**)

```bash
# - [ ] **WRITE** start orca serve on <alias> (foreground test first)
orca serve --pairing-address <SERVER_TAILSCALE_IP_OR_HOSTNAME>
# prints the bound endpoint + a runtime pairing URL — USER copies it privately

# fixed port only when a firewall/tunnel/service definition requires it:
orca serve --port <PORT> --pairing-address <SERVER_TAILSCALE_IP_OR_HOSTNAME>

# mobile clients on a headless server (QR + link in terminal):
orca serve --pairing-address <SERVER_TAILSCALE_IP_OR_HOSTNAME> --mobile-pairing
```

- `--pairing-address` is the address **clients dial** — must be reachable
  (Tailscale IP/hostname, LAN IP, or tunnel hostname). Never `127.0.0.1`,
  never a wildcard. Wrong address → stop (`Ctrl-C`) and restart with the
  reachable one.
- Foreground run ends on `Ctrl-C`. For persistence install the service
  (`templates/orca-serve.service`):

```bash
# - [ ] **WRITE** persist orca serve via systemd on <alias>
sudo cp orca-serve.service /etc/systemd/system/orca-serve.service  # filled from template
sudo systemctl daemon-reload
sudo systemctl enable --now orca-serve
systemctl status orca-serve --no-pager   # (read) active (running)
```

- Rollback: `sudo systemctl disable --now orca-serve` (+ remove the unit
  file if the run is abandoned); foreground test ends with `Ctrl-C`.
- **Never run Mode A and Mode B simultaneously** on the same machine.

### Phase 4b — Variant: Orca inside a Coder workspace (container)

Use when the server should live in an isolated dev container with Docker
access (DinD) instead of directly on a host. Same phases; different
plumbing and lifecycle. Proven against a `docker-devcontainer`-family
template (experiment copy with the ports block:
`playbooks/coder-remote-servers/templates/docker-devcontainer-orca`).

**B1. Template (once per template).** Workspaces are containers, not
tailnet nodes — clients cannot dial them directly. Publish the serve port
on the Docker host's tailnet IP only (constrained bind; never public).
Terraform docker provider:

```hcl
variable "orca_publish_ip" {
  default     = ""
  description = "Docker-host IP for the workspace Orca publish (host Tailscale IP). Empty = no published port."
  type        = string
}
# inside resource "docker_container" "workspace":
dynamic "ports" {
  for_each = var.orca_publish_ip != "" ? [1] : []
  content {
    internal = <INT-PORT>    # what serve binds in the container (default 6768)
    external = <EXT-PORT>    # what clients dial on the host (e.g. 6769 — avoids host clashes)
    ip       = var.orca_publish_ip
    protocol = "tcp"
  }
}
```

- If the daemon is itself nested (workspace → dind container → host),
  the publish binds the *inner* daemon's interfaces — a host IP there
  fails with "cannot assign requested address". Bind `0.0.0.0` in that
  case and DNAT on the host (B5). Prefer a flat daemon (workspace
  containers on the host daemon) when you have the choice.
- Push as a **separate template** (never mutate the stable one for an
  experiment): `coder templates push <TEMPLATE>-orca ...` with the
  template's normal remote vars plus `--var orca_publish_ip=<HOST-TAILSCALE-IP>`.

**B2. Workspace (per workspace).** `coder create <WORKSPACE> --template
<TEMPLATE>-orca ...`; `coder schedule stop <WORKSPACE> manual` —
autostop kills the server *and its agents* (indistinguishable from
pulling the plug). Size honestly (Orca + agent CLIs + docker builds
want real RAM/CPU). One runtime user: the workspace user (e.g. `coder`)
owns install + serve + projects — never split across users.

**B3. Install (same flow, container notes).** The Phase 2 `.deb` flow +
t64 libs + build tools apply unchanged; passwordless sudo is usually
present. Differences: **no systemd in containers** — run serve via
`nohup` for the experiment, graduate to the template's
`startup_script`/`startup_command` hook (runs every start) when
hardening; bake Orca into the image when hardening (the system layer
wipes on rebuild, `$HOME` persists).

**B4. Serve flags — bind vs advertise (the lesson).** `--port` sets BOTH
the bind port and the advertised port; `--pairing-address` overrides the
advertised host AND accepts `host:port`. Rule: **bind = container mapped
port, advertise = host tailnet IP + external port**:

```bash
# mapping <INT-PORT> → host <EXT-PORT>, e.g. 6768 → 6769:
orca serve --port <INT-PORT> --pairing-address <HOST-TAILSCALE-IP>:<EXT-PORT>
# verify (read): Bound endpoint ws://0.0.0.0:<INT-PORT>,
#                Advertised endpoint ws://<HOST-TAILSCALE-IP>:<EXT-PORT>
```

Binding the external port in the container serves nowhere (proxy
accepts, backend refuses). And the desktop app **rejects loopback links
for remote entries** — the tunnel shape (port-forward + `127.0.0.1`
link) cannot pair, so direct-dial is required, not optional.

**B5. Host network path (only when the publish lands in a nested
netns).** If `Test-NetConnection <HOST-TAILSCALE-IP> -Port <EXT-PORT>`
fails while serve is up, trace inward (reads first, fix last):

```bash
ss -tln | grep <INT-PORT>                                  # serve listening in the container?
docker port <workspace-container>                          # publish registered? (ask the owning daemon)
sudo iptables -t nat -L PREROUTING -n -v | grep <EXT-PORT> # DNAT counters rise on dial? 0 = tailnet filter, >0 = downstream
sudo tcpdump -i tailscale0 -n tcp port <EXT-PORT>          # decisive: 0 packets during dials = filtered upstream
```

Fixes, in the order they were needed (all **WRITE**, all
reboot-fragile — document as experiment debt, harden via
`before.rules`/template later):

```bash
# - [ ] **WRITE** DNAT tailnet → inner publish (host)
sudo iptables -t nat -A PREROUTING -i tailscale0 -p tcp --dport <EXT-PORT> -j DNAT --to-destination <INNER-IP>:<EXT-PORT>
# - [ ] **WRITE** return-path NAT (without it the handshake never completes)
sudo iptables -t nat -A POSTROUTING -o <BRIDGE> -p tcp -d <INNER-IP> --dport <EXT-PORT> -j MASQUERADE
# - [ ] **WRITE** FORWARD accept in DOCKER-USER (Docker's admin hook — first in FORWARD, before its own chains)
sudo iptables -I DOCKER-USER -i tailscale0 -o <BRIDGE> -p tcp -d <INNER-IP> --dport <EXT-PORT> -j ACCEPT
# - [ ] **WRITE** UFW route pinhole (belt; Docker chains shadow it today — keep for defense in depth)
sudo ufw route allow in on tailscale0 to <INNER-IP> port <EXT-PORT> proto tcp
```

Plus tailnet grant `tcp:<EXT-PORT>` to the host node (user console).
Rollback: `-D` each iptables rule, `ufw route delete ...`, revoke
the grant.

**B6. Pair + verify (same as Phases 6–7).** Link handoff identical
(operator fetches from the workspace shell, pastes into Add Server).
Rebuild semantics: system layer wipes → reinstall; `$HOME`
(`~/.config/orca`, skills, projects) persists → grants survive; the
tailnet IP may change → update the saved host address via Edit host
(token survives, no re-pair).

**B7. Dev servers + preview URLs.** Bind dev servers to `127.0.0.1`
explicitly — `localhost` is a coin flip between stacks and `[::1]`-only
breaks BOTH Orca's server-side browser and Coder's agent proxy (same
symptom, two places). Coder preview URLs need no definition: the
dashboard Ports tab hands out
`https://<port>--<agent>--<workspace>--<owner>.<CODER-DOMAIN>` per
detected port; bake stable ones with `coder_app(subdomain=true)` when
hardening. Framework allow-lists (e.g. Vite `allowedHosts`) must
include `<CODER-DOMAIN>`. Terminal `localhost:port` links open
client-local — Orca honors no `VSCODE_PROXY_URI` equivalent (verified
absent from the binary); use the `preview()` helper in
`notes/coder-workspace.md`.

Rollback (whole variant): delete the workspace, `-D` the host iptables
rules, remove the UFW/grant rules, revoke pairing grants, optionally
delete the experiment template. The template copy itself is inert until
pushed.

### Phase 5 — Harden the path (**WRITE** where it changes the server)

1. Tailnet grants — narrowest possible in the admin console (skeleton:
   `templates/tailscale-grants.example.json`). Server ↔ paired clients
   only; no `0.0.0.0` rules for the Orca port.
2. Host firewall — default-deny posture; allow the Orca port **only** on the
   private path:

```bash
# - [ ] **WRITE** firewall on <alias> (example: UFW)
sudo ufw default deny incoming
sudo ufw allow in on tailscale0 to any port <PORT> proto tcp   # Tailscale path
sudo ufw enable
sudo ufw status verbose   # (read) verify
```

3. Negative checks (read, every run):
   - No port-forward / NAT rule / security-group ingress sending the Orca
     port (`<PORT>`, default `6768`) from the public internet to the
     server. Cloud console + `ss -tlnp | grep <PORT>` must show the
     listener on the tailnet/LAN address, never `0.0.0.0` for a public box.
   - From an off-path host, `Test-NetConnection <PUBLIC_IP> -Port <PORT>`
     must fail/timeout.
   - Workspace variant: the same checks apply to `<EXT-PORT>`, plus the
     §6 Phase 4b B5 chain (DNAT counters, `DOCKER-USER`, MASQUERADE).
4. Rollback: remove the added firewall/grant rules; re-check status output.

### Phase 6 — Pair clients (per client; link handling is **WRITE**-adjacent)

Pairing links are password-equivalent: private channel only, one link per
client, revoke-after-use hygiene per §7. The agent never pastes a link into
chat/logs — it lands in `executions/.../secrets/`.

**Desktop client** (USER clicks, agent verifies):

1. Client Orca → **Settings → Remote Orca Servers → Add Server**.
2. Name it recognizably (e.g. `<SERVER_DISPLAY_NAME>`), paste the access
   link, **Add Server** → **Connect** if it shows Disconnected.
3. Only set **Advanced → Active Server** when server-routed projects,
   terminals, provider checks, and browser/mobile handoff should default
   to this server. Otherwise leave unset so new projects stay local.
4. Multi-client sidebar: enable **Hide other-client workspaces** when the
   device should list only its own workspaces.

**Mobile client:** phone on the **same tailnet/path** → Orca Mobile →
**Pair** → scan the `--mobile-pairing` QR or paste the printed link.
(Desktop-relay mobile pairing is a different flow — headless servers use
the `orca serve --mobile-pairing` link. Keep phone + server Orca updated;
protocol mismatches block pairing.)

**SSH-forward / tunnel clients** (no Tailscale on the client): forward a
local port over the private path, then pair to `127.0.0.1` **on the client
side only** as the dial address per the tunnel docs — the server's
`--pairing-address` itself must still be the reachable server-side address.
Record the exact forward command in `plan.md`. Prefer Tailscale over this.

- Generating another server link replaces the previous **unused** link;
  already-paired clients keep their own grants until revoked.
- Rollback per client: server → **Shared Server Access** → trash button
  beside the grant (active sessions on that grant drop immediately) → client
  **Remove** host entry.

### Phase 7 — Verify end-to-end + record

```bash
# - [ ] (read) from the server shell
orca status --json
orca host list --json        # server + SSH targets + paired servers visible
orca account list
```

- [ ] From each paired client: server shows **Connected**; open one of its
  projects and use Orca normally (terminal + agent + file + worktree all
  live on the server).
- [ ] Sleep/disconnect the client → agents keep running; reconnect →
  same workspace/tab/pane state, no duplicated paired tabs.
- [ ] Confirm version parity (no incompatible-protocol warnings) and that
  deleted-on-server projects disappear from clients (no ghost rows) — that
  is expected shared-state behavior, not a bug.
- [ ] Append to the execution's `notes.md`, update `inventory.md` +
  `secrets/` pointers. Never commit them (AGENTS.md §7).

## 7. Security invariants (verify every time)

1. **Private path only.** Orca traffic rides Tailscale, WireGuard, trusted
   LAN, SSH-forward, or an authenticated tunnel. Forwarding the Orca port
   to the public internet is a **security incident** — remove immediately.
2. **Pairing links are passwords.** Private channel, per-client grant,
   least privilege. A link shared with the wrong person → revoke that grant
   at once (**Shared Server Access** → trash) and issue a fresh link.
3. **Tailnet ACLs/grants narrow.** Server ↔ paired clients only; review on
   every new client.
4. **No loopback/wildcard advertise.** `--pairing-address` / connection
   address is always a reachable tailnet/LAN/tunnel address. `127.0.0.1`
   works only on the server itself; wildcards mislead clients. The
   desktop app enforces this: loopback links are rejected for remote
   entries (tunnel shapes must graduate to direct-dial — §6 Phase 4b).
5. **One host mode.** Desktop share XOR `orca serve` — never both.
6. **Credentials live on the server.** Laptop logins don't transfer; agent
   CLIs + `orca account` + skills are server-side facts. Re-verify after
   any server rebuild.
7. **No secrets in git.** Pairing links/tokens, Tailscale keys, `*.pem`,
   `*.key` live only in gitignored `executions/` — a tracked secret is an
   incident → unstage, move, rotate (AGENTS.md §7).
8. **Agent never sees a password.** Keys + pre-auth keys only.

## 8. Client connections — per-setup notes (summary; full matrix in `notes/`)

| Server setup | Desktop client dials | Mobile client | Notes |
|---|---|---|---|
| Tailscale + desktop share | Paste access link (Tailscale `100.x` address inside) via **Add Server** | Same tailnet → Pair (relay or LAN path) | Easiest; Orca lists the `100.x` address first |
| Tailscale + `orca serve` | Paste printed runtime pairing URL via **Add Server** | Same tailnet → `--mobile-pairing` QR/link | Service must stay running; `--port` fixed only if the firewall/service needs it |
| LAN-only server | LAN address link/URL via **Add Server** | Same LAN Wi-Fi → Pair | Breaks the moment a client roams — migrate to Tailscale then |
| SSH-forward / auth tunnel, no tailnet on client | Forward first, then pair per tunnel docs | Not recommended (use Tailscale) | Record the exact forward in `plan.md`; fragile, document it |
| Coder workspace (`host_type=coder-workspace`) | Paste pairing URL advertising `<HOST-TAILSCALE-IP>:<EXT-PORT>` via **Add Server** | Same tailnet → `--mobile-pairing` link (minted from the workspace) | Workspace is not a tailnet node; host publish + grant required (§6 Phase 4b). Autostop must be manual |

Behavioral notes (all setups): **Active Server** only when the server
should be the default; **Hide other-client workspaces** for shared servers;
server must stay awake/online with Orca running; keep both sides updated;
server deletions propagate to all clients.

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Tailscale address missing in picker | Tailscale not connected | `tailscale status` on server; both sides same tailnet; refresh button beside **Connection address** (`100.x` IPv4) |
| Server Disconnected | Asleep / Orca stopped / tailnet offline / ACL / version skew | Wake server; Orca running (`systemctl status orca-serve` for headless); `tailscale status` both online; check grants; update Orca both sides on protocol-version errors |
| Link went to the wrong person | Grant exposed | **Shared Server Access** → revoke that grant now; new link for the intended client |
| Server can't find agent CLI | Installed/authed on laptop only | Install + authenticate on the **server**; remote sessions use server `PATH`/home/creds |
| `orca serve` advertises wrong address | Unreachable `--pairing-address` / loopback / wildcard | Stop; restart with the reachable tailnet/LAN/tunnel address |
| Add account disabled on remote client | By design (remote runtime scope) | Register via server shell: `orca account add --agent claude\|codex` |
| Terminals dead on Linux server, files fine | Missing compiler toolchain for relay natives | Install build tools (§6 Phase 2), reconnect |
| Two servers fighting on one box | Desktop share + `orca serve` both running | Stop one — exactly one host mode at a time |
| App rejects link ("points back to this device") | Loopback in a remote-entry link | Direct-dial required: reachable tailnet/LAN/tunnel address (§6 Phase 4b for workspaces) |
| Workspace serve unreachable, publish registered | `--port` bound the external port in the container (bind ≠ advertise) | Bind the mapped port, advertise host:port: `--port <INT-PORT> --pairing-address <HOST-TAILSCALE-IP>:<EXT-PORT>` (§6 Phase 4b B4) |
| Workspace publish fails ("cannot assign requested address") | Host IP bound in a nested (dind) netns that lacks it | Bind `0.0.0.0` in the template + DNAT on the host (§6 Phase 4b B1/B5) |
| Tailnet dials arrive but never complete (DNAT counters rise, TCP fails) | Missing MASQUERADE / FORWARD accept past Docker chains | MASQUERADE the flow + ACCEPT in `DOCKER-USER` (Docker's admin hook, before its chains) (§6 Phase 4b B5) |
| Orca browser + Coder preview both refuse a dev server | App bound `[::1]`-only; both consumers dial IPv4 loopback | Bind dev servers to `127.0.0.1` explicitly |
| Terminal localhost links open client-local | Orca honors no `VSCODE_PROXY_URI` equivalent | `preview()` helper (`notes/coder-workspace.md`); dashboard Ports URLs for real browsers |
| Workspace went quiet, clients Disconnected | Autostop fired (agents die with the workspace) | `coder schedule stop <WORKSPACE> manual`; restart serve; expect stale terminal handles |

## 10. Quick runs

### A. New server (condensed)

- [ ] §2 answers recorded (location / path / host mode) — Tailscale
  suggested unless shared private LAN (read)
- [ ] SSH alias + scoped sudoers (user) — **WRITE**-adjacent setup
- [ ] **WRITE** Tailscale join + `tailscale ip` recorded + ping both ways
- [ ] **WRITE** Orca install + version parity + build tools (Linux)
- [ ] **WRITE** agent CLIs + `orca account add` (user logins) + skills
- [ ] **WRITE** start runtime (Mode A user clicks / Mode B `orca serve`
  + optional systemd) with reachable `--pairing-address`
- [ ] **WRITE** grants + firewall; negative public-reachability check (read)
- [ ] Pair first client (§6 Phase 6); verify §6 Phase 7; write notes/inventory

### B. New client on an existing server

- [ ] Confirm client's path (same tailnet/LAN/tunnel) + Orca updated (read)
- [ ] Server generates **fresh** link / `--mobile-pairing` URL (user hands
  over privately) — treat as secret (**WRITE**-adjacent)
- [ ] Client **Add Server** → Connect; set Active Server / Hide-other
  workspaces only if wanted
- [ ] Verify Connected + open a server project; record client in
  `inventory.md`; revoke/replace any exposed grant

### C. Workspace variant (condensed)

- [ ] §2 records `host_type=coder-workspace` + template/workspace/publish mapping (read)
- [ ] Template pushed with `orca_publish_ip` set (placeholders only in repo) — **WRITE** to Coder
- [ ] Workspace created, `schedule stop manual`, sized honestly — **WRITE** to Coder
- [ ] **WRITE** Orca install (Phase 2 flow) + serve with bind/advertise split (B4)
- [ ] **WRITE** tailnet grant + host path (UFW/DNAT/MASQUERADE/`DOCKER-USER` as needed); negative public check (read)
- [ ] Pair + verify (Phases 6–7); dev servers on `127.0.0.1`; `preview()` helper installed

---

## Authoring rules

- Steps must be copy-paste executable with placeholders filled.
- Flag every step that WRITES to a production system with **WRITE** in bold
  (e.g. `- [ ] **WRITE** install package X on <host>`). Reads need no flag.
- Add rollback instructions for every write step.
- After each run, promote lessons into `notes/` (via the operator, never
  mid-run).
