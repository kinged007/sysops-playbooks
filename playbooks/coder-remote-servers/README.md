# Playbook: Coder Remote Servers

> **Agent: read `notes/` BEFORE any run.** The notes contain lessons learned
> from previous executions (G1–G12 + wildcard subdomain traps) that may change
> how you plan. Never skip this.

## What it does
Provisions Coder development workspaces across multiple remote servers from a
single Coder host — private Tailscale tailnet, mutual TLS on every Docker API
connection (2376 bound to tailnet IPs only). Includes onboarding new remotes,
Coder template pushes, and exposing workspace app previews via wildcard
subdomains.

## When to use it
- Onboarding a new remote workspace server into the fleet
- Pushing/updating the unified Coder template for a target (local or remote)
- Setting up or repairing wildcard app subdomains (`.coder.<domain>` previews)
- TLS/ACL troubleshooting for remote daemons

## Prerequisites
- Coder host (Dokploy-managed) with `coder` CLI installed and authenticated
- Tailscale account + tailnet (free Personal: ≤6 users, unlimited devices)
- Key-based SSH access to the Coder host and each remote
- Management UI (Dokploy or Coolify) on each remote, or direct compose access

## Risk level
**medium** — touches production Docker daemons (via TLS) and live Coder
configuration. Never binds 2376 to a public interface; that is an incident.

## Servers involved
One Coder host + one or more remotes (each running a `docker:dind` container).
Real values live in the execution's `inventory.md`, never here.

## Files
| Path | Purpose |
|---|---|
| `playbook.md` | Canonical procedure (placeholders only) |
| `plan-template.md` | Copied to `executions/coder-remote-servers/plan.md` on first run (or `executions/coder-remote-servers-<suffix>/plan.md`) |
| `runbook-template.md` | Copied to `executions/coder-remote-servers/runbook.md` on first run |
| `templates/workspace-docker.yml` | Canonical dind compose (bind IP + `DOCKER_TLS_SAN` = placeholders) |
| `templates/docker-devcontainer/` | Unified Coder template (local + remote via vars) — includes `gh`, `uv`, `go`, `rust` by default like `npm`/`python` |
| `templates/gvisor-docker/` | gVisor-sandboxed workspaces (shared isolated daemon) — includes `gh`, `uv`, `go`, `rust` by default |
| `templates/remote-docker-workspace.hcl` | Simpler standalone remote template (code-server only) — includes `gh`, `uv`, `go`, `rust` by default |
| `templates/scripts/install-*.sh` | Shared helpers: `install-gh.sh`, `install-uv.sh`, `install-go.sh`, `install-rust.sh` (apt or binary to `~/.local/bin`/`~/.cargo`/`~/.local/go`) — used by all Coder templates; handles `runsc` (no sudo) |
| `scripts/setup-wildcard-cert.sh` | acme.sh + Cloudflare DNS-01 wildcard cert installer |
| `notes/gotchas.md` | G1–G12: real pitfalls hit on the fleet, with fixes |
| `notes/wildcard-subdomains.md` | Wildcard preview routing/TLS traps and fixes |

> **Default workspace tooling:** all Coder templates (`docker-devcontainer`, `gvisor-docker`, `remote-docker-workspace`) now install **GitHub CLI (`gh`), `uv`, `Go`, and `Rust` by default** on every workspace start if missing — like `npm` and `python` (baked into `codercom/enterprise-node:ubuntu`). `gh` tries apt then binary; `uv` via `pipx`/astral installer; `Go` via tarball to `~/.local/go`; `Rust` via `rustup` to `~/.cargo`. All fall back to `~/.local/bin`/`~/.cargo/bin`/`~/.local/go/bin` so they work without `sudo` (primary for `runsc`/gVisor). Authenticate `gh` with `gh auth login` or via Coder's `coder external-auth` (GitHub).
