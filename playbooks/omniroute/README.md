# Playbook: OmniRoute — Setup, Configure & Secure

> **Agent: read `notes/` BEFORE any run.** The notes contain lessons learned
> from previous executions that may change how you plan. Never skip this.

## What it does
Deploys or connects to an OmniRoute AI-gateway instance (the MIT gateway from
`diegosouzapw/OmniRoute`), hardens it, wires up its public/base URLs, enables
the remote MCP server, and issues a **Management-Access API key** so an agent
can drive the gateway over MCP. Also generates and records all required secrets
(`INITIAL_PASSWORD`, `JWT_SECRET`, `API_KEY_SECRET`, WS-bridge secret, salts)
into the run's `secrets/` folder where the operator can review them.

Covers multiple install targets (see below). **This playbook is generic** —
it has no preferences for any one instance. Real values for a specific variant
(URLs, hosts, credentials) live only in that variant's `executions/omniroute/`
(or `executions/omniroute-<suffix>/`) folder, never here.

## When to use it
- Standing up a fresh OmniRoute gateway (Docker or npm) and doing the first-run
  hardening properly
- Onboarding an existing remote OmniRoute instance behind a public hostname
  (base/public URLs, HTTPS cookie flags, remote MCP access)
- Enabling `/api/mcp/sse` (streaming SSE) or `/api/mcp/stream` and minting a
  `manage`-scope API key so a remote agent can configure the gateway
- Auditing a public instance's exposure and locking it down

## When NOT to use it
- Non-OmniRoute gateways (use the netdata/wordpress/etc. playbooks) — this is a
  hard scope boundary
- Token/credential rotation only, without any install or config change — that
  is a different, smaller run

## Risk level
**medium** — every step WRITES to a live, possibly internet-exposed service:
secrets are written to env/config, the MCP server can be enabled (widening the
attack surface), and a management API key is created. All writes are
**WRITE**-flagged, approval-gated, and rollback-documented.

## Install targets (pick at plan approval — never assumed)
| Target | Path | Notes |
|---|---|---|
| Remote instance (HTTP/HTTPS) | reach directly via public URL, or SSH alias + forward | Connect and configure over the REST/dashboard API |
| Local npm | `npm install -g omniroute`, run `omniroute` on `:20128` | Port 20128, data in `~/.omniroute` (or `%APPDATA%\omniroute` on Windows) |
| Docker container | `docker run … diegosouzapw/omniroute` or compose | Volume on `/app/data`, port 20128; add Caddy for TLS |
| Existing-but-unconfigured | whatever is already running | Discover first, then harden |

The operator chooses the target at the plan-approval gate (§3.4). If the target
is "already running elsewhere", the agent must **discover and confirm access**
before proposing any write.

## Prerequisites (run-specific)
- Reachability from the operator machine to the target: public URL, `~/.ssh/config`
  alias to tunnel through, or a local process/Docker install
- For an existing instance: the dashboard **management password** OR a
  pre-issued **Management-Access API key** placed in the run's `secrets/`. The
  agent never handles the password directly — the operator installs/enters it.
- Permission mode set at plan approval (A = confirm before each write / B =
  plan-as-approved). The agent always asks; it never picks the mode.
- Docker CLI only if the target is a container.

## Servers involved
Either one public host (the OmniRoute instance), a container target, or the
local machine. Real values live in the execution's `inventory.md` and
`secrets/`, never here.

## Files
| Path | Purpose |
|---|---|
| `playbook.md` | Canonical procedure (placeholders only) |
| `plan-template.md` | Copied to `executions/omniroute/plan.md` on first run (or `executions/omniroute-<suffix>/plan.md`) |
| `runbook-template.md` | Copied to `executions/omniroute/runbook.md` on first run |
| `templates/.env.example` | Full env template with `<PLACEHOLDER>` secrets |
| `templates/docker-compose.yml` | Optional Docker Compose with HTTPS front (Caddy) |
| `scripts/gen-secrets.ps1` | Generates all secrets + salts, writes them to `secrets/` |
| `scripts/test-mcp.ps1` | Probes `/api/mcp/sse` + `/api/mcp/status` with the key |
| `notes/gotchas.md` | Pitfalls hit on real runs, with fixes |

## MCP access artifact (per variant)
When the MCP server is confirmed reachable, the run writes
`executions/omniroute/mcp/<alias>.mcp.json` (or `executions/omniroute-<suffix>/mcp/<alias>.mcp.json`) describing the endpoint, transport, and
the env var (`OMNIROUTE_MCP_KEY_<TAG>`) that references the key stored in
`secrets/`. The key value itself never appears in committed files. The artifact
persists in the same variant folder across invocations.