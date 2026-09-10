# Plan: <RUN NAME>

| Field | Value |
|---|---|
| Client | <client> |
| Playbook | `orca-remote-server` |
| Execution folder | `executions/orca-remote-server/` or `executions/orca-remote-server-<suffix>/` |
| Permission mode | **UNSET — set by operator at approval** (A: per-write confirm / B: plan-as-approved) |
| Status | draft → approved → executing → closed |

## Server location / access decision (THIS run — mandatory, never assumed)

| Question | Answer |
|---|---|
| Where does the server live? (same LAN / home behind NAT / cloud VPS w/ public IP / other) | <answer> |
| How do clients reach it? (Tailscale tailnet / LAN-only / WireGuard-VLAN / SSH-forward / auth tunnel) | <answer> |
| Host mode? (desktop-app share / headless `orca serve`) | <answer> |
| Host type? (direct-on-host / coder-workspace container — §6 Phase 4b) | <direct / coder-workspace> |
| [workspace only] Template / workspace / publish mapping | `<template> / <workspace> / <INT-PORT>→<HOST-TAILSCALE-IP>:<EXT-PORT>, autostop=<manual?>` |
| Tailscale required? (yes unless shared private LAN — why) | <yes/no + why> |
| Pairing address clients dial | `<100.x.y.z / LAN IP / tunnel hostname>` |
| Fixed port needed? (only if firewall/tunnel/service requires it) | `<port or "no — default">` |
| Clients pairing in this run (desktop/mobile/automation) | <list> |

> If the server is not on a private LAN path the clients share, Tailscale
> is the playbook default. A public port-forward is never an approved
> answer — re-ask instead.

## Servers involved (THIS variant only)

| Alias (ssh config) | Role | Purpose | Access key |
|---|---|---|---|
| <alias> | orca-server | <always-on runtime; desktop or serve> | `~/.ssh/<key>` |
| <alias> | client-<n> | <desktop/mobile pairing in this run> | `~/.ssh/<key>` (desktop only) |

## Credentials / secrets (THIS variant only)

<Files in `secrets/` of this execution folder; never inline values here>
Secrets persist in this folder across invocations — update in place when rotating.
Expected: Tailscale pre-auth key (`secrets/tailscale-authkey`), pairing links
(`secrets/pairing-<client>-<date>.txt` — one file per client, delete after use
or on revoke). Pairing links are password-equivalent.

## Steps

Numbered steps mirroring `runbook.md`, with **WRITE** flags:

1. Record §2 decision + confirm reuse/new variant (read)
2. **WRITE** — Tailscale join on server (+ clients if required)
3. **WRITE** — install Orca on server, verify version parity
4. **WRITE** — server tooling: agent CLIs, `orca account add` (user logins), skills
5. **WRITE** — start runtime (Mode A user clicks / Mode B `orca serve` + systemd; workspace variant §6 Phase 4b B2–B4)
6. **WRITE** — grants + firewall (+ host DNAT/MASQUERADE/`DOCKER-USER` for workspace variant); negative public-reachability check (read)
7. Pair client(s) — private link handoff (**WRITE**-adjacent, per-client grant)
8. Verify end-to-end (read) + notes/inventory update

## Risk assessment

<What could go wrong; what is the blast radius; rollback plan>
Blast radius: one Orca server (repos, agent creds, sessions) + its network
path. Leaked pairing link or public port-forward = full-runtime compromise:
revoke grant immediately, remove forward, rotate Tailscale key if exposed.
Rollback per playbook.md phase (tailscale logout, uninstall, disable service,
remove firewall/grant rules, revoke grants).

## Approval

- [ ] Operator reviewed plan and set permission mode: <A or B>
- [ ] Operator approved execution on <date>
