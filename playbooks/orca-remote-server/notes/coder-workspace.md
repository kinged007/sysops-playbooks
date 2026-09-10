# Coder-workspace hosts — nuances, helpers, hardening list

Companion to `playbook.md` §6 Phase 4b. Read BEFORE any workspace run
(mandated by §4). Placeholders only — no real IPs, names, or links.

## N1 — A workspace is not a tailnet node

Coder workspaces have no Tailscale identity of their own; they ride the
*host's* networking (and Coder's own internal `fd7a:...` range on the
dashboard→agent leg, which is normal — not an error, not dialable for
Orca). Consequences:

- There is no workspace tailnet IP to advertise. Clients always dial the
  **host's** tailnet address + the published external port.
- Anything that assumes "the server is a node" (grants to the workspace,
  `tailscale` CLI in the container) does not apply. Grants target the
  **host node** (`tcp:<EXT-PORT>`); the container has no `tailscale`
  binary and needs none.

## N2 — The publish crosses netns boundaries; respect them

- A flat daemon (workspace containers on the host daemon): publish with
  `ip = <HOST-TAILSCALE-IP>` — constrained bind, tailnet-only.
- A nested daemon (workspace → dind container → host): the inner netns
  lacks host IPs, so a host-IP bind fails with "cannot assign requested
  address". Bind `0.0.0.0` there and DNAT on the host
  (`tailscale0:<EXT-PORT>` → `<INNER-IP>:<EXT-PORT>`). Discover the inner
  IP live (`docker inspect <dind-container>`) — never assume it.
- `docker port <workspace-container>` (asked of the *owning* daemon)
  is the ground truth for what is actually published.

## N3 — The three host rules and why each exists

Tailnet-dialed packets die in three different places; each rule fixes
exactly one (diagnose with counters before adding rules):

1. **DNAT** (`nat/PREROUTING`): rewrites host `<EXT-PORT>` to the inner
   publish. Discriminator: `PREROUTING` counters — 0 during dials means
   the tailnet filter ate them (fix the grant, not the host).
2. **MASQUERADE** (`nat/POSTROUTING`): return-path source NAT. Without
   it the handshake never completes even though every filter accepts —
   the inner hops can't route the tailnet source back.
3. **`DOCKER-USER` ACCEPT**: Docker's documented admin hook, evaluated
   first in `FORWARD`, before Docker's own chains (which know nothing
   about inner publishes and drop the packets in `DOCKER-BRIDGE`).
   Prefer it over editing Docker-managed chains. The `ufw route allow`
   pinhole is belt (currently shadowed — keep for defense in depth).
4. All three are **ephemeral** (`iptables` resets on reboot; inner IPs
   shift when infra containers are recreated). Experiment debt —
   harden via `before.rules`/template (Phase 2 list below).

## N4 — Bind ≠ advertise (the expensive lesson)

`orca serve --port` sets bind AND advertised port together;
`--pairing-address` overrides the advertised host and accepts
`host:port`. The only consistent shape with a port mapping:

```bash
orca serve --port <INT-PORT> --pairing-address <HOST-TAILSCALE-IP>:<EXT-PORT>
```

Binding the external port inside the container serves nowhere (proxy
accepts, backend refuses — looks alive from the outside). Always read
back both lines: `Bound endpoint` (must be the mapped container port)
and `Advertised endpoint` (must be what clients dial).

## N5 — Loopback links are rejected, tunnels can't pair

The desktop app refuses `127.0.0.1` links for remote entries. A
port-forward + loopback link therefore transports fine but never
pairs — direct-dial is mandatory. (The one legitimate loopback: a
tunnel that makes "self" mean the server is still useful for *other*
tools, just not for Orca pairing.)

## N6 — Lifecycle: autostop, rebuild, users, no systemd

- `coder schedule stop <WORKSPACE> manual`. Autostop = dead server =
  dead agents + stale terminal handles. A blank schedule display has
  meant "no stop armed" so far — treat as observed-not-proven until an
  idle stretch survives.
- Rebuild wipes the system layer (reinstall Orca); `$HOME`
  (`~/.config/orca`, skills, projects) persists (grants survive); the
  host tailnet IP may change (Edit host, token survives).
- One runtime user (the workspace user). Split users = permission pain.
- No systemd in containers: `nohup` for experiments, template
  `startup_script`/`startup_command` when hardening, baked image last.

## N7 — Dev servers: bind `127.0.0.1`, always

`localhost` is a coin flip between stacks. `[::1]`-only breaks Orca's
server-side browser AND Coder's agent proxy with the identical
"connection refused" symptom — check `ss -tln` first, not the proxy.
`npm run dev -- --host 127.0.0.1` (or `server.host` in config).

## N8 — Preview URLs and the terminal-link gap

- Coder preview URLs need no definition: dashboard Ports hands out
  `https://<port>--<agent>--<workspace>--<owner>.<CODER-DOMAIN>` per
  detected port (Coder-authenticated). Bake stable ones with
  `coder_app(subdomain=true)` when hardening. Framework allow-lists
  (Vite `allowedHosts`) must include `<CODER-DOMAIN>`.
- Orca honors **no** `VSCODE_PROXY_URI` equivalent (verified: set with
  no effect, absent from the binary, no setting). Terminal
  `localhost:port` links open client-local. Bridge the gap with:

```sh
# ~/.bashrc (workspace) — mints the Coder preview URL for a port.
# Portable: derives names from the var Coder already provides.
preview() { echo "${VSCODE_PROXY_URI//'{{port}}'/$1}"; }
```

- File upstream: "support `VSCODE_PROXY_URI` for terminal link
  rewriting" — the day that lands, delete the helper.

## N9 — Diagnostic ladder (workspace path)

`ss` in container → `docker port` on owning daemon → DNAT counters →
`tcpdump -i tailscale0` (0 packets = filter) → `DOCKER-USER` counters
→ MASQUERADE present → backend `wget` from the publishing netns
(reset = alive, refused = dead backend). Never `pkill -f` with a
pattern that also matches your own remote command line — it kills
your shell first (kill by pid, or start fresh when nothing runs).

## Phase-2 hardening list (when the experiment graduates)

1. Bake Orca + t64 libs + build tools into the workspace image.
2. `startup_script` ensure-serve block (+ `preview()` into
   dotfiles/skel).
3. `coder_app` entries for stable app URLs; decide `share` levels.
4. Persist host rules (`before.rules`, pinned inner IPs or a stable
   forwarder) or flatten the daemon topology to delete them.
5. Autostop policy per workspace purpose; sizing guide
   (Orca + CLIs + docker wants real RAM/CPU).
6. Mobile-link minting from the workspace (`--mobile-pairing` restart;
   verify desktop grant survives).
