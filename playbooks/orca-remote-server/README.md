# Playbook: Orca Remote Server

> **Agent: read `notes/` BEFORE any run.** The notes contain security
> invariants and client-connection pitfalls that may change how you plan.
> Never skip this. This playbook's pairing links grant full runtime access —
> treat them like passwords.

## What it does

Provisions one always-on Orca server (desktop app share **or** headless
`orca serve`, directly on a host **or** inside a Coder workspace container)
and pairs desktop / mobile / automation clients to it over a
private path — Tailscale tailnet preferred, trusted LAN / SSH-forward /
authenticated tunnel otherwise. Covers the mandatory location/access
decision, secure install, tailnet + firewall hardening, server-side tooling
(agent CLIs, accounts, skills), pairing, per-client connection notes, and
revocation. Never exposes the Orca port to the public internet.

## When to use it

- Setting up a new always-on Orca runtime (old laptop, Mac mini, home
  server, cloud VPS, team box) so agents survive laptop sleep/disconnect
- Adding another client (desktop, mobile, browser/automation) to an
  existing Orca server
- Moving a server between networks (LAN → Tailscale, home → VPS) or
  switching host mode (desktop app ↔ `orca serve`)
- Repairing pairing, ACL, or "server disconnected" failures

NOT covered: SSH worktrees where the laptop owns the runtime (see Orca
`Ways to run` / `SSH worktrees` docs instead), per-workspace Cloud VM
recipes (`orca.yaml`), or Orca-managed VPS hosting (Orca sells none — you
bring the machine).

## Prerequisites

- One server machine you control (Linux headless/VM, macOS, or Windows)
  with key-based SSH access (`ssh-copy-id`; agent never handles passwords)
- Orca installed on every client; Tailscale account + tailnet when the
  server is not LAN-only (free Personal: ≤6 users, unlimited devices)
- Server owner available for interactive steps (desktop clicks, Tailscale
  approval, `coder`/`claude`/`codex` logins, pairing-link handoff over a
  private channel)
- Decision inputs (asked at Phase 1, never assumed): where the server
  lives, how clients reach it, desktop-app vs `orca serve` host mode,
  direct-on-host vs Coder-workspace install destination

## Risk level

**medium** — installs packages and configures a long-lived network
service holding repos, agent credentials, and session state. A leaked
pairing link or a publicly forwarded Orca port is a full-runtime-compromise
incident (see §7 security invariants).

## Servers involved

One Orca server + one or more clients (laptop/desktop/phone/automation).
Real values live in the execution's `inventory.md`, never here.

## Files

| Path | Purpose |
|---|---|
| `playbook.md` | Canonical procedure (placeholders only) |
| `plan-template.md` | Copied to `executions/orca-remote-server/plan.md` on first run (or `executions/orca-remote-server-<suffix>/plan.md`) |
| `runbook-template.md` | Copied to `executions/orca-remote-server/runbook.md` on first run |
| `templates/orca-serve.service` | systemd unit for headless `orca serve` (`<PLACEHOLDER>`s for user, address, port) |
| `templates/tailscale-grants.example.json` | Minimal tailnet grants skeleton (Orca server ↔ clients only) |
| `scripts/install-orca-server.sh` | Headless-Linux helper: Tailscale + Orca CLI presence check, build tools for the Orca relay |
| `notes/security.md` | Security invariants + location/access decision rationale |
| `notes/coder-workspace.md` | Coder-workspace variant nuances: netns plumbing, bind-vs-advertise, lifecycle, preview helper |
| `notes/client-connections.md` | Per-setup client connection matrix (desktop, mobile, SSH-forward, tunnel) |
| `notes/gotchas.md` | Real pitfalls (from Orca docs + runs), with fixes |

> Execution folders are **persistent per playbook variant**. The first run creates
> `executions/orca-remote-server/` (or `executions/orca-remote-server-<suffix>/` when the operator
> supplies a suffix like `personal`/`company`/`prod`). All subsequent invocations
> for the same variant **reuse and append to the same folder** — `secrets/` and
> `inventory.md` persist, `logs/` is append-only. The agent always scans for an
> existing folder before creating a new one and confirms with the operator.
