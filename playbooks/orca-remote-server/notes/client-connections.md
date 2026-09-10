# Client connections — Orca Remote Server

How each client type connects **given the server setup**. Check the row that
matches the recorded `access_path` + `host_mode` — do not mix rows.

## Desktop client (all setups)

1. Orca → **Settings → Remote Orca Servers → Add Server**.
2. Display name (e.g. `<SERVER_DISPLAY_NAME>`), paste the access link,
   **Add Server** → **Connect** if Disconnected.
3. **Advanced → Active Server**: set only when server-routed projects,
   terminals, provider checks, and browser/mobile handoff should default to
   this server. Otherwise leave unset — new projects stay local.
4. Shared servers: sidebar filter **Hide other-client workspaces** so the
   device lists only its own workspaces.
5. Adding a server saves it without migrating existing projects — open a
   server project (or set Active Server) to actually use it.

| Server setup | What the pasted link contains | Reachability requirement |
|---|---|---|
| Tailscale + desktop share | Tailscale `100.x.y.z` address (Orca lists it first in the picker) | Client on the same tailnet |
| Tailscale + `orca serve` | Printed runtime pairing URL (`--pairing-address 100.x.y.z`, optional `--port`) | Client on the same tailnet; service still running |
| LAN-only | LAN address link/URL | Client on the same LAN — roaming breaks this; migrate to Tailscale |
| SSH-forward / auth tunnel | Tunnel-local dial address per tunnel docs; server side still advertises its reachable address | Forward established first; exact command recorded in `plan.md` |

## Mobile client

- Phone must share the path: same tailnet (Tailscale setups) or same LAN
  (LAN-only). There is no "pair over the public internet" row.
- Headless servers: start serve with `--mobile-pairing`, open Orca Mobile →
  **Pair**, scan the terminal QR or paste the printed link.
- Desktop-share servers: use the desktop pairing flow (relay or LAN path);
  keep phone + server Orca updated — version skew blocks pairing with an
  update prompt. After updating, refresh; if the error persists, remove the
  host and re-pair.
- Same-display-name hosts: the New-Workspace host picker shows endpoints —
  pick by endpoint, not just name.
- Server address moved (home LAN → Tailscale)? Edit the saved host's address
  (host card **⋯ → Edit host**) instead of re-pairing; the token survives.

## Browser / automation clients

- Automation targets the **server runtime** (its `orca` CLI, selectors, and
  server-side absolute paths — `path:<absolute-server-path>` — because the
  caller's cwd may not exist on the server). See the Orca CLI reference.
- `orca serve` must be running (foreground or `orca-serve.service`) for the
  whole automation window; desktop-share servers need the app open.
- Prefer `--json` CLI output for automation; reacquire terminal handles via
  `orca terminal list --json` after any runtime restart (handles are
  runtime-scoped).

## Shared-server behavior (all clients)

- Agents survive client sleep/disconnect; reconnecting returns the same
  workspace/tab/pane state without duplicating paired tabs.
- The server needs the repo, tools, and credentials — a login on one client
  never fixes another client's missing server-side auth.
- Projects deleted on the server vanish from every paired client (no ghost
  rows) — expected, not data loss on the clients.
- Server must stay awake, online, and running Orca; mobile push/desktop
  notifications only arrive while the path is up.
