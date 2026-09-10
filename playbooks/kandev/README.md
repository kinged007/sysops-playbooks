# Playbook: Kandev — Self-Hosted AI Task Orchestration

> **Agent: read `notes/` BEFORE any run.** The notes contain lessons learned
> from previous executions (auth pitfalls, Docker executor limitations,
> port binding, reverse-proxy traps) that may change how you plan. Never skip this.
>
> **Agent: fetch the Kandev docs BEFORE any management step.** Docs are the
> source of truth for terms, flags, and paths — do not improvise:
> - https://kandev.ai/docs/run-as-a-service (service mode)
> - https://kandev.ai/docs/docker (container mode)
> - https://kandev.ai/docs/authentication (auth toggle + PATs)
> - https://kandev.ai/docs/executors (Docker / SSH / Sprites)
> - https://kandev.ai/docs/automation-and-mcp (external MCP + `/mcp`)
> - https://kandev.ai/docs/configuration (env / `config.yaml` reference)

## What it does

Deploys the **Kandev** control plane (backend + SPA + API + WebSocket + `/mcp`) on a server the operator controls, so tasks can be orchestrated persistently and reached from a custom domain over HTTPS. Two deployment branches are supported — **Run as a Service** (native systemd/launchd via `kandev service install`) and **Docker / Docker Compose** (`ghcr.io/kdlbs/kandev`) — with a hardened default of **authentication ON** (`KANDEV_FEATURES_AUTH=true`), **MCP access** (external MCP at `/mcp` via PAT), and **remote executors** (Local Docker + SSH) enabled and verified. Also configures reverse-proxy TLS termination, DNS, persistence, health checks, backups, and upgrades.

## When to use it

- Operator wants Kandev available after logout/reboot (`systemd`/`launchd` service, or `restart: unless-stopped` container) rather than a foreground `kandev` process.
- Operator needs Docker-based agent execution (repeatable container boundary per task).
- Operator needs remote execution (SSH hosts) and AI-assistant access via **MCP** (Claude Code, Cursor, OpenCode connecting to `/mcp`).
- Hardening an existing install that is currently unauthenticated, loopback-only, or `0.0.0.0` without a proxy.

Not for: upstream agent CLI installation inside Kandev (done via Kandev UI `Settings > Agents`), workload prompt engineering, or Kubernetes production rollout (see experimental `k8s/` manifests in Kandev docs — mentioned as alternative, not executed by this playbook unless operator explicitly asks).

## Prerequisites

- Key-based SSH access to the target host (`~/.ssh/config` alias `<ALIAS>`). Real hostnames/IPs live only in `executions/kandev[-<suffix>]/inventory.md` and `secrets/`, never here.
- On the target:
  - **Service mode (A):** Linux with `systemd` (or macOS with `launchd`), `curl`/`tar`, Node ≥ 22 + npm ≥ 7 *or* Homebrew *or* a release archive; `sudo` for system-service installs.
  - **Docker mode (B):** Docker Engine + Compose v2 (`docker compose version`), a free TCP port (default `38429`), and a writable volume path (`/srv/kandev` or named volume `kandev-data`).
- A domain (or subdomain) you control + ability to create an `A`/`CNAME` record (e.g. `kandev.example.com`). For TLS: Cloudflare **or** a reverse proxy that can do ACME DNS-01/HTTP-01 (Caddy, Nginx + certbot, Dokploy Traefik).
- Reverse proxy choice for HTTPS: **Caddy** (simplest, auto-TLS), **Nginx**, **Traefik/Dokploy**, or Cloudflare-proxied edge. The playbook ships templates for all three and asks which you want.
- Operator-supplied secrets at plan time (stored only in `executions/kandev[-<suffix>]/secrets/`):
  - Whether auth will be **ON** (recommended) or **OFF** (single-user, private network only).
  - For Docker + Postgres (optional): `KANDEV_DATABASE_PASSWORD`.
  - For TLS DNS-01 (optional): Cloudflare API token (`Zone → DNS → Edit`).
  - For SSH executors: target SSH host fingerprints + key/ssh-agent choice.
- Permission mode set at plan approval (AGENTS.md §1.3): **A** = confirm before each **WRITE**, **B** = plan-as-approved.

## Risk level

**medium** — installs/updates a service on a production host, writes systemd units or compose files, opens/exposes a port, changes reverse-proxy / firewall / DNS, and optionally migrates SQLite. All production **WRITE** steps are flagged and approval-gated per AGENTS.md §1.3. Rollback is documented per write (unit/plist revert, compose down, volume snapshot restore, proxy config revert). Secrets (`*.pem`, PATs, `master.key`, `KANDEV_DATABASE_PASSWORD`) are never committed — see AGENTS.md §7.

## Servers involved

Single app server (`<ALIAS>`) running Kandev. Optionally fronted by that same host's reverse proxy (Caddy/Nginx/Traefik) — no second server required. Remote executor hosts (Docker daemon host, SSH targets) may be the same machine or separate; each is an additional `<ALIAS_SSH_*>` / `<ALIAS_DOCKER>` entry in the execution's `inventory.md`. Real values live only in the execution folder.

## Deployment modes (choose at plan time — always ask)

| Mode | How | When | Pros | Cons |
|------|-----|------|------|------|
| **A — Run as a Service** (native) | `kandev service install --home-dir <KANDEV_HOME_DIR>` → systemd user/system unit *or* launchd plist (isolated tree, one `rm -rf` removal) | Persistent workstation, single-tenant VPS, admin owns the OS, wants minimal Docker dependency, wants clean uninstall | No container layer; fastest cold-start; isolated `<KANDEV_HOME_DIR>` holds DB/`master.key`/worktrees/logs — `service uninstall --home-dir <KANDEV_HOME_DIR>` + `rm -rf <KANDEV_HOME_DIR>` removes everything; direct host Docker/SSH executors work without volume-mirroring hacks; native `service logs/status/config` | Host toolchain required (Node/Homebrew/archive); lingering needed for user units; port-flag limitation (`KANDEV_BACKEND_PORT` drop-in); not portable across hosts; bundle path (`/opt/kandev`/`npm root -g`/`brew --cellar`) removed separately |
| **B — Docker / Docker Compose** (recommended for servers) | `ghcr.io/kdlbs/kandev:X.Y.Z` + volume `/data` + `restart: unless-stopped` (one named volume or one bind-mount dir) | Server fleet, Dokploy/Coolify host,want image-pinned deploys + compose-managed TLS companion | One-line image pin + digest; named-volume persistence; pairs cleanly with Caddy/Nginx sidecar; reproducible across hosts; removal is `docker compose down` + `docker volume rm kandev-data` (or `rm -rf /srv/kandev`) | **Local Docker executor limitation** — mounting `/var/run/docker.sock` alone is insufficient for task containers (helper/session bind-mount paths must match on daemon host; prefer host-native control plane for reliable Docker tasks); entrypoint `chown /data` can be slow on large bind mounts |

Other install options (mentioned, not default):
- **CLI foreground** (`kandev` / `kandev --headless`) — ephemeral, dies with the shell; useful for quick tests only.
- **Desktop App** (Tauri) — packaged WebView + native runtime; laptop/single-user.
- **Kubernetes** (`k8s/` manifests) — experimental, single-replica only (`Recreate`), not HA; mentioned as an alternative if operator explicitly asks.
- **Windows / WSL** — foreground or service wrapper; `kandev service` is not supported on Windows.

Default recommendation the playbook proposes: **B (Docker Compose + Caddy)** for internet-facing servers (clean TLS + pin), **A (user systemd service with `--home-dir ~/srv/kandev`, `--system --home-dir /srv/kandev` only if boot-without-login required)** for a developer workstation. **Always confirm with the operator** — the plan never picks without asking.

## Storage & database — the removable layout (ask at plan time)

The playbook always proposes an **isolated `KANDEV_HOME_DIR`** so uninstall is reviewable and data is deletable with one `rm -rf` (see `playbook.md` §1 key decision 7, §6–§8, §16.6). `<KANDEV_HOME_DIR>` is the single root for `data/kandev.db` (WAL + `-shm`), `data/master.key` (`0600`, AES-256 — backup together), `data/backups/` (`manual-*.db` never pruned, auto `kandev-*.db` retain-2), `logs/backend-logs.log` (256 MiB ring, 3-day max), `service/install.json`, `repos/`, `tasks/`, `worktrees/`, `sessions/`.

| Driver | DB file / connection | `backups/` sibling | When |
|--------|---------------------|---------------------|------|
| **SQLite inside home** — default | `<KANDEV_HOME_DIR>/data/kandev.db` (auto WAL, legacy `<KANDEV_HOME_DIR>/kandev.db` adoption once) | `<KANDEV_HOME_DIR>/data/backups/` — holds snapshots; `master.key` stays at `<KANDEV_HOME_DIR>/data/master.key` | Single-host (all modes) — simplest, fastest, one `rm -rf <KANDEV_HOME_DIR>` removal |
| **SQLite custom path outside home** | `KANDEV_DATABASE_PATH=/srv/kandev-data/kandev.db` (`database.path` alias) | `<custom-dir>/backups/` (not `<home>/data/backups/`, not auto-moved) — `master.key` still at `<home>/data/master.key` | Dedicated DB subvolume/mount (separate quotas); removal needs `rm -rf <KANDEV_HOME_DIR> <CUSTOM_DB_DIR>` |
| **PostgreSQL (external)** | `KANDEV_DATABASE_DRIVER=postgres` + `HOST/PORT/USER/PASSWORD/DBNAME/SSLMODE` (see `templates/env.example`) | **none built-in** — use `pg_dump --format=custom` + verified restore; System Backups UI becomes SQLite-only | External DB HA/replication for the DB layer ( `/data` still required for worktrees/`master.key` — not HA for tasks) |

All three can be migrated later via the three auditable paths in `playbook.md` §16.4: **A** SQLite path move (`.backup`), **B** SQLite→Postgres (`pgloader`), **C** Postgres→SQLite (reverse converter) — each with snapshot → driver flip → `/ready` verify. `scripts/migrate-db.sh` wraps them with `--dry-run`.

## Authentication modes (choose at plan time — always ask)

| Mode | Flag | When | Pros | Cons |
|------|------|------|------|------|
| **Auth ON** — **preferred, default** | `KANDEV_FEATURES_AUTH=true` (or UI `Settings > System > Feature Toggles → Authentication & users` → restart) | Shared server, any public/internet-reachable host, multi-user, MCP over the internet | Per-user isolation (workspaces/tasks/secrets private), session + 30-day sliding expiry, per-user Global secrets, PATs for MCP/scripts (`kandev_pat_…`), revocation/disable per user | First visitor must create admin immediately (setup mode); shared filesystem/agent credentials still OS-user-scoped (see docs Limitations); requires HTTPS + reverse proxy |
| **Auth OFF** — single-user, private only | (default) `KANDEV_FEATURES_AUTH` unset/false | Single-user laptop bound to `127.0.0.1`, or VPN/Tailscale-only access with no other users | Simplest; no login; works for `ssh -L` tunnels and tailnet | **No access control** — anyone who can reach the listener (default `0.0.0.0`) controls all workspaces; must be shielded by loopback/VPN/firewall + TLS proxy; startup logs a warning on non-loopback binds |

The playbook defaults to **Auth ON** and requires explicit operator sign-off to stay OFF on a non-loopback host. If OFF is chosen for a public host, the plan includes mandatory shielding (loopback bind + authenticated reverse proxy or tailnet, never `0.0.0.0` unauthenticated).

## Default feature set (ask, but enable unless operator opts out)

Unless the operator says otherwise, the plan assumes **all three** will be wanted and makes them achievable:

- **MCP access (external MCP):** `https://<domain>/mcp` proxied from the Kandev origin root, authenticated via PAT when auth is ON. Verified with a `POST /mcp` / `initialize` probe.
- **Docker executor (Local Docker):** `KANDEV_DOCKER_ENABLED=true` + `docker.host` reachable, with a built profile `kandev/multi-agent:latest` equivalent. When the control plane itself is containerized, the limitation (§ Docker) is called out and SSH/Sprites alternatives are offered.
- **Remote SSH executor:** per-host profile with host-key pinning, `bash`/`zsh`, `MaxSessions`/`AllowTcpForwarding yes`, agent binary probe.

Sprites.dev is offered as an optional remote sandbox executor (provider token as secret) but is not assumed.

## Files

| Path | Purpose |
|---|---|
| `playbook.md` | Canonical step-by-step procedure (placeholders only; **WRITE**-flagged) — incl. isolated `--home-dir` removal (§1·7, §6–§8, §16.6) and DB matrix + migrations (§9.4, §16.4) |
| `plan-template.md` | Copied to `executions/kandev/plan.md` on first run (or `executions/kandev-<suffix>/plan.md`) — records Home & DB layout + removal map |
| `runbook-template.md` | Copied to `executions/kandev/runbook.md` on first run — mirrors plan steps, logs one file per step |
| `templates/docker-compose.yml` | Compose for Kandev + optional Caddy sidecar (loopback publish, `/data` volume, healthcheck on `/ready`) |
| `templates/docker-compose.postgres.yml` | Overlay: Kandev + Postgres 16 (SQLite → Postgres migration) |
| `templates/Caddyfile` | Caddy reverse-proxy — isolated snippet `import /srv/kandev/Caddyfile.kandev` for one-`rm` removal |
| `templates/nginx-kandev.conf` | Nginx vhost — isolated `include /srv/kandev/nginx-kandev.conf` for one-`rm` removal |
| `templates/config.yaml.example` | Minimal `config.yaml` (server.host, trustedProxies, database matrix, docker, logging) |
| `templates/env.example` | Env file template (KANDEV_HOME_DIR, KANDEV_FEATURES_AUTH, KANDEV_SERVER_HOST/TRUSTED_PROXIES, DB vars incl. `KANDEV_DATABASE_PATH`) |
| `scripts/health-check.sh` | Health + readiness probe (`/health` vs `/ready`) + MCP + home/DB check (`--home-dir`) |
| `scripts/backup.sh` | SQLite (`sqlite3 .backup`, `manual-*.db` + `master.key`) + Postgres (`pg_dump`) + cold home archive (`--archive`) |
| `scripts/restore.sh` | SQLite (quarantine → stage `.new` → install) + Postgres (`pg_restore`) — interactive `RESTORE` gate |
| `scripts/migrate-db.sh` | DB migrations: **A** SQLite path move / **B** SQLite→Postgres (`pgloader`) / **C** Postgres→SQLite reverse (`--dry-run` supported) |
| `notes/gotchas.md` | G1–G18: real pitfalls (port fallback, `auth.jwtSecret` trap, Docker executor, proxy, SQLite continuity, `master.key` coupling, isolated removal) — **read before any run** |

> Execution folders are **persistent per playbook variant**. The first run creates
> `executions/kandev/` (or `executions/kandev-<suffix>/` when the operator
> supplies a suffix like `prod`/`staging`/`personal`). All subsequent invocations
> for the same variant **reuse and append to the same folder** — `secrets/` and
> `inventory.md` persist, `logs/` is append-only. The agent always scans for an
> existing folder before creating a new one and confirms with the operator.
