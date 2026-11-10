# Skill: Bifrost AI Gateway

> **Agent: read references/` BEFORE any run.** references/gotchas.md` holds pitfalls
> that change how you plan; references/sources.md` is the documentation index —
> consult it live instead of guessing API shapes. Never skip this.

## What it does

Installs, configures, hardens, and operates a **Bifrost** instance
(`maximhq/bifrost`) — an open-source, high-performance AI gateway (Go) that
exposes one OpenAI-compatible API for 20+ upstream providers (OpenAI,
Anthropic, Bedrock, Vertex, Azure, Mistral, Groq, Ollama, …) with failover,
weighted load balancing, retries, virtual keys/budgets governance, semantic
caching, MCP gateway + Code Mode, drop-in SDK replacements (`/openai`,
`/anthropic`, `/genai`, `/bedrock`), Prometheus metrics, and tracing.

Covers the full lifecycle: zero-config start (npx/Docker), file vs DB-backed
`config.json`, provider/key setup, virtual keys and budgets, semantic cache,
MCP clients, reverse-proxy/TLS hardening, health verification, SQLite/Postgres
backup/restore, version-pinned upgrades, and source builds with custom
plugins. Enterprise-only features (clustering, guardrails, OIDC/SCIM, secret
managers) are mapped to docs, not operated here.

## When to use it

- Fresh install on a server, VM, or workstation (npx, Docker run, Compose,
  Helm/Kubernetes, Terraform).
- Adding/rotating providers, API keys, models, fallbacks, or load-balancing
  weights.
- Enforcing auth on inference (virtual keys), setting budgets/rate limits,
  enabling semantic cache or MCP tools.
- Hardening an exposed instance (dashboard password + setup token, enforced
  virtual keys, TLS reverse proxy, firewall).
- Backup/restore of `/app/data` (SQLite) or Postgres stores, encryption-key
  rotation planning, version-pinned upgrades.
- Modifying Bifrost from source (Go SDK use, custom `.so` plugin, new
  provider/store contribution) and troubleshooting (health, 4xx/5xx error
  classes, cache misses, MCP auth).

Not for: creating upstream provider accounts/billing, workload-side prompt
engineering, or non-Bifrost proxy work. Enterprise cluster/guardrail policy
design beyond doc pointers is out of scope.

## Prerequisites

- Key-based SSH access to the target host (`~/.ssh/config` alias). The
  playbook uses `<ALIAS>`; real hostnames live only in
  `runs/bifrost[-<suffix>]/inventory.md` and `secrets/`.
- Target tooling per mode: Docker Engine + Compose v2 (Docker/Compose/Helm
  paths), or Node.js ≥ 20 + npx (npx path), or Go 1.27.x + Node 25 (source
  builds; plugins require same Go version, Linux/macOS only, no
  cross-compilation).
- A free TCP port (default `8080`). Confirmed with `ss -tlnp`.
- Operator-supplied secrets at plan time: `BIFROST_ENCRYPTION_KEY` (stable,
  backed up — losing it makes persisted encrypted values unreadable),
  `BIFROST_SETUP_TOKEN` (first admin account only), provider API keys, and
  optionally Postgres credentials. Stored only in the execution `secrets/`.
- If internet-exposed: domain/DNS + TLS termination (Nginx/Caddy/Traefik/
  Cloudflare) and `enforce_auth_on_inference=true` decision.

## Risk level

**medium** — installs/updates a service on a production host, writes env +
volume/DB data, opens a port, optionally changes reverse-proxy/firewall rules.
Provider keys and virtual keys are secrets: never log, commit, or echo them.
DB **WRITE** steps need a fresh backup first; every write has a rollback.
Migrations are one-way (image rollback does not undo a DB migration).

## Servers involved

Single app server (`<ALIAS>`) running Bifrost on `8080` (same port serves
API, dashboard, `/health`, `/metrics`). Optionally fronted by that host's
reverse proxy, optionally backed by managed Postgres/Redis. Real values live
in the execution's `inventory.md` and `secrets/`, never here.

## Files

| Path | Purpose |
|---|---|
| `SKILL.md` | Canonical procedure (placeholders only; **WRITE**-flagged) |
| `plan-template.md` | Copied to `runs/bifrost/plan.md` on first run (or `runs/bifrost-<suffix>/plan.md`) |
| `runbook-template.md` | Copied to `runs/bifrost/runbook.md` on first run |
| `templates/docker-compose.yml` | Pinned-image compose with `./data:/app/data`, healthcheck |
| `templates/config.json.example` | Minimal DB-backed config with `env.` key references |
| `templates/nginx-bifrost.conf` | Nginx reverse-proxy vhost (TLS, streaming-safe) |
| `scripts/health-check.sh` | `/health` + `/v1/models` + chat-completion smoke probe |
| `scripts/backup.sh` | SQLite `/app/data` backup helper (stop-or-quiesce safe) |
| references/sources.md` | Documentation index — live URLs for every topic |
| references/gotchas.md` | G1–G8 pitfalls — **read before any run** |

> Execution folders are **persistent per skill variant**. The first run
> creates `runs/bifrost/` (or `runs/bifrost-<suffix>/` when the
> operator supplies a suffix like `prod`/`staging`/`personal`). All
> subsequent invocations for the same variant **reuse and append to the same
> folder** — `secrets/` and `inventory.md` persist, `logs/` is append-only.
> The agent always scans for an existing folder before creating a new one and
> confirms with the operator.

## Deployment modes (choose at plan time)

| Mode | Command | When |
|---|---|---|
| **A — npx** | `npx -y @maximhq/bifrost` | Fastest eval, workstation, no Docker |
| **B — Docker run** | `docker run -p 8080:8080 -v ./data:/app/data maximhq/bifrost:<TAG>` | One-shot server, no compose |
| **C — Docker Compose** | `templates/docker-compose.yml` | **Recommended for servers** |
| **D — Helm/Kubernetes** | `helm install bifrost bifrost/bifrost --set image.tag=<TAG> …` | K8s, HA, Postgres |
| **E — Source + systemd** | `go build ./transports/bifrost-http` | Full control, custom plugins |

Default: **C** on servers, **A** on a workstation, **D** on Kubernetes.
Always pin `image.tag` / `--transport-version` in production (unversioned
`latest` is eval-only).
