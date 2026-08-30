# Playbook: 9Router Proxy Manager

> **Agent: read `notes/` BEFORE any run.** The notes contain lessons learned
> from previous executions that may change how you plan. Never skip this.
>
> **Agent: fetch the 9Router management skill BEFORE any management step:**
> `https://raw.githubusercontent.com/decolua/9router/refs/heads/master/skills/9router/SKILL.md`
> — this skill is the canonical gateway for all 9Router operations (health,
> model discovery, chat/image/TTS/embeddings/web-search). The playbook's
> verification and management phases depend on it; do not improvise the API
> shapes.

## What it does

Installs, configures, hardens, and operates a **9Router** instance — an
OpenAI-compatible AI gateway / proxy that sits between local CLI tools (Claude
Code, Codex, Cursor, Cline, OpenCode, Copilot, Antigravity, OpenClaw…) and
40+ upstream providers (Anthropic, OpenAI, Gemini, GLM, MiniMax, Kimi,
OpenRouter, Vertex, self-hosted whisper/Kokoro/llama-server, …). Features
managed by the playbook: smart 3-tier fallback (subscription → cheap → free),
RTK / Headroom / Caveman / Ponytail token savers, quota tracking,
format translation, multi-account sync, bearer-key protection, request
logging, Cloud Sync, and Cloudflare/Dokploy/Traefik/Nginx fronting.

Covers the full lifecycle: fresh install, configuration & provider/combo
setup, connectivity verification via the skill's `/api/health` and
`/v1/models/*` contracts, backup/restore of the local SQLite store,
upgrade, reverse-proxy hardening, and decommission.

## When to use it

- Fresh install of 9Router on a new or existing server (local VM, VPS,
  Dokploy/Coolify host, bare metal).
- Upgrading an existing 9Router installation (Docker tag bump or
  `npm install -g 9router` update).
- Hardening an internet-exposed 9Router (enable `REQUIRE_API_KEY`,
  `AUTH_COOKIE_SECURE=true`, reverse-proxy TLS, firewall).
- Adding / rotating providers, API keys, OAuth accounts, or rebuilding
  fallback combos ("subscription → cheap → free").
- Migrating 9Router data (`$DATA_DIR/db/data.sqlite`) between hosts or
  restoring from a backup.
- Ongoing ops: health checks, token-saver tuning, quota/cost triage,
  cloud-sync repair, log inspection.

Not for: upstream provider account creation (done on the provider's site),
workload-side LLM prompt engineering, or non-9Router reverse-proxy work
(handled by the host's existing proxy playbooks).

## Prerequisites

- Key-based SSH access to the target host (`~/.ssh/config` alias). The
  playbook references `<ALIAS>` everywhere; real hostnames live only in
  `executions/9router[-<suffix>]/inventory.md` and `secrets/`.
- On the target:
  - **Docker mode** (recommended): Docker Engine + Compose v2
    (`docker compose version`), or single `docker run` capability.
  - **npm mode** (local/single-user): Node.js ≥ 22, npm ≥ 10.
  - **Source mode** (VPS/systemd): Node.js ≥ 22, `git`, `npm`, `pm2` or
    `systemd` for process supervision.
- A free TCP port for 9Router (default `20128`; Headroom sidecar `8787`
  if used). Confirmed free via `ss -tlnp`.
- If internet-exposed: a domain/DNS record + TLS termination (Dokploy
  Traefik, Caddy, Nginx, or Cloudflare) and an operator decision on
  `REQUIRE_API_KEY` (must be `true` for public exposure).
- Operator-supplied secrets at plan time: `JWT_SECRET` (long random),
  `INITIAL_PASSWORD` (dashboard first login), `API_KEY_SECRET`,
  `MACHINE_ID_SALT`, and any upstream provider API keys / OAuth intent.
  Stored only in `executions/9router[-<suffix>]/secrets/`.

## Risk level

**medium** — installs/updates a service on a production host, writes env +
volume data, opens a port, and optionally changes reverse-proxy / firewall
rules. All production **WRITE** steps are flagged and approval-gated per
AGENTS.md §1.3. Rollback is documented per write (container/image revert,
env restore, volume restore from SQLite backup, proxy config revert). The
database path contains no customer PII beyond provider tokens, but those
tokens are secrets — never log, commit, or echo them.

## Servers involved

Single app server (`<ALIAS>`) running 9Router. Optionally fronted by that
same host's reverse proxy (Traefik/Dokploy, Caddy, or Nginx) — no second
server required. Real values live in the execution's `inventory.md` and
`secrets/`, never here.

## Files

| Path | Purpose |
|---|---|
| `playbook.md` | Canonical step-by-step procedure (placeholders only; **WRITE**-flagged) |
| `plan-template.md` | Copied to `executions/9router/plan.md` on first run (or `executions/9router-<suffix>/plan.md`) |
| `runbook-template.md` | Copied to `executions/9router/runbook.md` on first run |
| `templates/env.example` | Env file template (mirrors upstream `.env.example` with operator guidance) |
| `templates/docker-compose.yml` | Single-service compose (published image, persistent volume, env_file) |
| `templates/docker-compose.headroom.yml` | Compose with Headroom sidecar (`headroom:8787`) + `HEADROOM_URL` wiring |
| `templates/nginx-9router.conf` | Nginx reverse-proxy vhost template (TLS, headers, `/v1` + `/api` + `/dashboard`) |
| `templates/systemd-9router.service` | systemd unit for source/pm2-less deploys |
| `scripts/health-check.sh` | Health + model-discovery probe (uses the 9Router skill contracts) |
| `scripts/backup.sh` | SQLite hot-copy / volume backup helper |
| `scripts/restore.sh` | SQLite restore helper (with pre-restore backup) |
| `scripts/update.sh` | Update helper (Docker pull / npm update branch) |
| `notes/gotchas.md` | G1–G12: real pitfalls, with fixes — **read before any run** |
| `notes/skill.md` | Pointer to the upstream skill (fetched live each run, not bundled) |

> Execution folders are **persistent per playbook variant**. The first run
> creates `executions/9router/` (or `executions/9router-<suffix>/` when the
> operator supplies a suffix like `prod`/`staging`/`personal`). All
> subsequent invocations for the same variant **reuse and append to the
> same folder** — `secrets/` and `inventory.md` persist, `logs/` is
> append-only. The agent always scans for an existing folder before
> creating a new one and confirms with the operator.

## Deployment modes (choose at plan time)

| Mode | Command | When |
|---|---|---|
| **A — npm global** | `npm install -g 9router && 9router` | Local single-user, fastest |
| **B — Docker run** | `docker run -d -p 20128:20128 -v <DATA_DIR>:/app/data -e DATA_DIR=/app/data decolua/9router:latest` | One-shot, no compose |
| **C — Docker Compose** | `templates/docker-compose.yml` (or `.headroom.yml`) | Recommended for servers; Headroom sidecar supported |
| **D — Source + systemd/pm2** | `git clone … && npm install && npm run build && npm run start` | Full control, VPS without Docker |

The playbook's Phase 4 branches on this choice. Default recommendation:
**C (Docker Compose)** on servers; **A** on a developer workstation.
