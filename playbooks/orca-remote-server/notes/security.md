# Security notes — Orca Remote Server

Why this playbook is strict. Read BEFORE any run (mandated by README).

Upstream stance (Orca docs, `Remote Orca Servers`): servers are **beta** —
keep server and client on a **private network path you control** (same
Tailscale tailnet or LAN). Do **not** forward the Orca port to the public
internet; prefer Tailscale, WireGuard, trusted LAN, SSH-forwarding, or an
authenticated tunnel. Keep Tailscale ACLs/grants as narrow as the setup
allows. A pairing URL grants access to the runtime — treat it like a
password.

## S1 — The location question is the security decision

Ask where the server lives and how it is reached (§2) because the answer
selects the threat model:

- Shared LAN the clients never leave → LAN path is defensible; Tailscale
  still recommended (roaming phones break LAN-only on day one).
- Home behind NAT / VPS with public IP / roaming clients → Tailscale (or
  equivalent private path) is **required**, not optional. NAT traversal and
  the `100.x.y.z` identity are the point.
- "Just expose the port" is never accepted. The Orca port serves a full
  agent runtime (shell, files, credentials) — a public forward turns any
  token leak or auth gap into remote compromise. Refuse and offer the
  private-path list instead.

## S2 — Pairing links are passwords

- One grant per client (server lists them under **Shared Server Access**,
  each revocable via the trash button; revocation drops active sessions at
  once).
- Generating another link replaces the previous **unused** link; paired
  clients keep theirs until revoked — so a leaked-but-unused link still
  dies on regeneration, a leaked-and-used one needs explicit revocation.
- Handoff over a private channel only, into `executions/.../secrets/`
  (one file per client). Never chat, logs, tickets, or screenshots.
- Wrong recipient → revoke first, ask questions later, then issue fresh.

## S3 — Addresses that lie

- `127.0.0.1` in a connection address / `--pairing-address` works only on
  the server itself. A remote client dialing it connects to itself and
  reports a confusing failure — always advertise a reachable tailnet / LAN /
  tunnel address.
- Wildcard / `0.0.0.0` binds on a public box plus a permissive firewall is
  the incident this playbook exists to prevent. Verify with
  `ss -tlnp | grep <PORT>` (must show the private address) and an off-path
  `Test-NetConnection <PUBLIC_IP> -Port <PORT>` that must fail.

## S4 — One host mode per machine

Desktop share **xor** `orca serve`. Two runtimes on one box fight over
state and double the pairing-link attack surface. The playbook verifies
only the recorded mode is running.

## S5 — The server owns credentials

Laptop logins don't transfer. `orca account add` (Claude/Codex device
flows), provider CLIs, `git` auth, and skills (`orca skills install /
update`) are server-side facts — re-verify after every rebuild, and never
exfiltrate server credentials to "fix" a client.

## S6 — Version parity is a security control

Client and server on different Orca versions can fail open into confusing
protocol-mismatch states. Update both sides together; treat
incompatible-version warnings as stop-and-update, not click-through.
