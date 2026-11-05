# Plan: <RUN NAME>

| Field | Value |
|---|---|
| Client | <client> |
| Skill | `orca-remote-server` |
| Run folder | `runs/orca-remote-server/` or `runs/orca-remote-server-<suffix>/` |
| Permission mode | **UNSET — set by operator at approval** (A: per-write confirm / B: plan-as-approved) |
| Status | draft → approved → executing → closed |

## Server location / access decision (THIS run — mandatory, never assumed)

| Question | Answer |
|---|---|
| Where does the server live? (same LAN / home behind NAT / cloud VPS w/ public IP / other) | <answer> |
| How do clients reach it? (Tailscale tailnet / LAN-only / WireGuard-VLAN / SSH-forward / auth tunnel) | <answer> |
| Host mode? (desktop-app share / headless `orca serve`) | <answer> |
| Host type? (direct-on-host / coder-workspace container — Phase 4b) | <direct / coder-workspace> |
| [workspace only] Template / workspace / publish mapping | `<template> / <workspace> / <INT-PORT>→<HOST-TAILSCALE-IP>:<EXT-PORT>, autostop=<manual?>` |
| Tailscale required? (yes unless shared private LAN — why) | <yes/no + why> |
| Pairing address clients dial | `<100.x.y.z / LAN IP / tunnel hostname>` |
| Fixed port needed? (only if firewall/tunnel/service requires it) | `<port or "no — default">` |
| Clients pairing in this run (desktop/mobile/automation) | <list> |

> If the server is not on a private LAN path the clients share, Tailscale
> is the skill default. A public port-forward is never an approved
> answer — re-ask instead.

## Fleet refs (THIS variant only)

| Fleet record | Role | Purpose |
|---|---|---|
| `fleet/servers.yaml`: <server name> | orca-server | <always-on runtime; desktop or serve> |
| `fleet/servers.yaml`: <client name> | client-<n> | <desktop/mobile pairing in this run> |

## Vault entries (THIS variant only)

<Vault entry names `<client>-<provider>-<purpose>`; never inline values here>
Vault entries persist across invocations — rotate them in place.
Expected: Tailscale pre-auth key (`<client>-tailscale-authkey`), pairing links
(`<client>-orca-pairing-<device>` — one entry per client device, delete after
use or on revoke). Pairing links are password-equivalent.

## Steps

Numbered steps mirroring `runbook.md`, with **WRITE** flags:

1. Record the location/access decision + confirm reuse/new variant (read)
2. **WRITE** — Tailscale join on server (+ clients if required)
3. **WRITE** — install Orca on server, verify version parity
4. **WRITE** — server tooling: agent CLIs, `orca account add` (user logins), skills
5. **WRITE** — start runtime (Mode A user clicks / Mode B `orca serve` + systemd; workspace variant Phase 4b B2–B4)
6. **WRITE** — grants + firewall (+ host DNAT/MASQUERADE/`DOCKER-USER` for workspace variant); negative public-reachability check (read)
7. Pair client(s) — private link handoff (**WRITE**-adjacent, per-client grant)
8. Verify end-to-end (read) + notes/inventory update

## Risk assessment

<What could go wrong; what is the blast radius; rollback plan>
Blast radius: one Orca server (repos, agent creds, sessions) + its network
path. Leaked pairing link or public port-forward = full-runtime compromise:
revoke grant immediately, remove forward, rotate Tailscale key if exposed.
Rollback per SKILL.md phase (tailscale logout, uninstall, disable service,
remove firewall/grant rules, revoke grants).

## Approval

- [ ] Operator reviewed plan and set permission mode: <A or B>
- [ ] Operator approved execution on <date>
