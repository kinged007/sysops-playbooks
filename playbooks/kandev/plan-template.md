# Plan: <RUN NAME> — Kandev

| Field | Value |
|---|---|
| Client | <client> |
| Playbook | `kandev` |
| Execution folder | `executions/kandev/` or `executions/kandev-<suffix>/` |
| Permission mode | **UNSET — set by operator at approval** (A: per-write confirm / B: plan-as-approved) |
| Status | draft → approved → executing → closed |
| Kandev image tag | `ghcr.io/kdlbs/kandev:<X.Y.Z>` (pinned, not `latest`) or `n/a (Service)` |

## 1. Servers involved (THIS variant only)

| Alias (ssh config) | Role | Purpose | OS / Access | Home path |
|---|---|---|---|---|
| <ALIAS> | app | Kandev control plane (`:38429`) + reverse proxy (`:80/:443`) | `<OS>` / `~/.ssh/<key>` | `<KANDEV_HOME_DIR>` |
| <ALIAS_SSH_1> | executor-ssh | Remote SSH executor (if F3) | `<OS>` / ssh-agent or key | `~/.kandev` (remote) |
| <ALIAS_DOCKER> | executor-docker | Local Docker daemon host (may be same as app) | Docker Engine / `unix:///var/run/docker.sock` | `n/a` |

## 1.1 Home & DB layout — the removal contract (THIS variant only)

> This section is the source of truth for backups, migration, and `uninstall` + `rm -rf` cleanup. Every path must be mirrored in `inventory.md` Section 1.1 and `plan.md` §9.4.

| Item | Value |
|---|---|
| **KANDEV_HOME_DIR** | `<KANDEV_HOME_DIR>` — e.g. `/srv/kandev` (system isolated) or `~/srv/kandev` (user isolated) or `~/.kandev` (default, scattered) |
| Isolated home? | **yes** (`--home-dir <KANDEV_HOME_DIR>` everywhere) / **no** (accepts scattered defaults) |
| System vs user service | user (`systemd --user` / LaunchAgent) / system (`--system --run-as <USER>`) / `n/a (Docker)` |
| Config file chosen | `<KANDEV_HOME_DIR>/config.yaml` (preferred, co-located) **or** `/etc/kandev/config.yaml` (shared, survives home removal) **or** `secrets/env` (compose `env_file`) |
| Database driver | `sqlite` (default) / `postgres` |
| SQLite DB path | `<KANDEV_HOME_DIR>/data/kandev.db` (inside home) **or** `<CUSTOM_DB_PATH>` via `KANDEV_DATABASE_PATH` (outside home, needs separate removal) — `n/a` if Postgres |
| Backups sibling dir | `<KANDEV_HOME_DIR>/data/backups/` **or** `<CUSTOM_DIR>/backups/` **or** `n/a (Postgres → pg_dump at <PG_DUMP_PATH>)` |
| `master.key` location | `<KANDEV_HOME_DIR>/data/master.key` (0600, required with any DB backup to decrypt secrets) |
| Postgres tuple (if driver=postgres) | host=`<PGHOST>` port=`<PGPORT>` user=`<PGUSER>` db=`<PGDB>` sslMode=`<PG_SSLMODE>` password in `secrets/kandev-db-password` (`0600`, `valueFrom.secretKeyRef` in compose) |
| Outside-home extras needing separate `rm` | e.g. `<CUSTOM_DB_DIR>`, `/etc/kandev/config.yaml`, `<COMPOSE_DIR>`, `/srv/kandev/Caddyfile.kandev`, bundle path |
| Lingering (user service) | `enable-linger=yes` (boot-without-login) / `no` |

**Removal map (copy to §16.6):**

```bash
# User isolated:
kandev service uninstall --home-dir <KANDEV_HOME_DIR> && rm -rf <KANDEV_HOME_DIR>
# System isolated:
sudo "$(command -v kandev)" service uninstall --system --home-dir <KANDEV_HOME_DIR> && sudo rm -rf <KANDEV_HOME_DIR>
# + if custom DB outside home:  rm -rf <CUSTOM_DB_DIR>
# + if shared config:           sudo rm -f /etc/kandev/config.yaml
# + bundle (choose one):        npm uninstall -g kandev | brew uninstall kandev | sudo rm -rf /opt/kandev
# Docker isolated:
docker compose -f <COMPOSE_DIR>/docker-compose.yml down   # retain volumes
docker volume rm kandev-data              # purge only after off-host snapshot
rm -rf <COMPOSE_DIR>                       # compose file itself
```

## 2. Deployment & feature choices (ask, never assume)

### 2.1 Deployment branch (D1)

| Option | Chosen? | Notes |
|---|---|---|
| **A — Run as a Service** (`kandev service install` → systemd/launchd, isolated `--home-dir <KANDEV_HOME_DIR>`) | `[ ]` | User vs system, lingering, `--home-dir` |
| **B — Docker / Docker Compose** (`ghcr.io/kdlbs/kandev:<X.Y.Z>` + volume `/data`) | `[ ]` | Named volume `kandev-data` vs bind `/srv/kandev` |
| Alternatives parked (CLI foreground / Desktop / Kubernetes `k8s/` single-replica) | `[ ]` | Mentioned, not executed unless operator opts in |

Showed README pros/cons table to operator: `[ ] yes`

### 2.2 Authentication (D2)

| Option | Chosen? | Shielding if OFF |
|---|---|---|
| **Auth ON** (`KANDEV_FEATURES_AUTH=true`, setup mode → first visitor creates admin, PATs `kandev_pat_…` for MCP) — **preferred if public** | `[ ]` | — |
| **Auth OFF** (single-user, loopback/VPN only — `127.0.0.1` + proxy/Tailscale) | `[ ]` | `server.host=127.0.0.1` + tailnet/firewall/proxy shielding documented: `<shielding>` |

Shielding plan if OFF on non-loopback host (mandatory): `<shielding detail>`

### 2.3 Default features (F1–F3 — defaults ON unless operator opted out)

| Feature | Wanted? | Verified via |
|---|---|---|
| **F1 — MCP external** (`https://<DOMAIN>/mcp` + PAT + proxy root passthrough) | `[ ] yes` / `[ ] no (opt-out)` | `curl -H "Authorization: Bearer <PAT>" https://<DOMAIN>/mcp initialize` + client `tools/list` |
| **F2 — Docker executor** (`KANDEV_DOCKER_ENABLED`, daemon reachable, profile built) | `[ ] yes` / `[ ] no` | `docker info` + Docker profile Build Image + throwaway task → `docker ps --filter label=kandev.managed=true` |
| **F3 — SSH executor(s)** (`<ALIAS_SSH_*>` pinning, `AllowTcpForwarding yes`) | `[ ] yes` / `[ ] no` | `Test Connection` + fingerprint pinning + throwaway task |

Opt-out reasons (if any): `<reasons>`

### 2.4 Host & domain (H1–H6, P1–P3, E1–E3)

| Field | Value |
|---|---|
| H1 OS | `<OS>` |
| H2 Docker on host? | yes / needs install (`<notes>`) |
| H3 Domain + DNS host | `<DOMAIN>` @ `<DNS_HOST>` (A/CNAME → `<ALIAS>`) |
| H4 Existing proxy | Caddy / Nginx / Dokploy Traefik / none |
| H5 TLS method | Caddy auto-TLS HTTP-01 / DNS-01 via Cloudflare (`<TOKEN_REF>`) / existing cert |
| H6 Isolated home preference | isolated (`--home-dir <KANDEV_HOME_DIR>`) / default scattered |
| **P1 DB driver (now)** | `sqlite` / `postgres` |
| **P2 DB path** | `<SPAN>` — see §1.1 |
| P3 Volume (Docker) | `kandev-data` named / `/srv/kandev` bind (`chown 1000:1000`) |
| Future DB intent (migration parked?) | stay / start sqlite → postgres later (§16.4 B) / postgres → sqlite later (§16.4 C) |
| E1 Docker image for tasks | `kandev/multi-agent:latest` / `node:22-slim` / custom `<Dockerfile>` |
| E2 SSH hosts | `<ALIAS_SSH_1>: host=<HOST> port=<PORT> user=<USER> auth=ssh-agent|key fingerprint=<SHA256>` |
| E3 Sprites token | `n/a` / `secrets/sprites-token` |
| KANDEV image tag (Docker) | `<X.Y.Z>` |
| Reverse-proxy choice | Caddy / Nginx / Traefik (isolated snippet `import`/`include`) |
| `KANDEV_TRUSTED_PROXIES` | `<PROXY_PEER_IP_OR_CIDR>` |

## 3. Credentials / secrets (THIS variant only)

> Files in `secrets/` of this execution folder; never inline values here. Mode `0600` for anything bearing tokens/keys. Secrets persist in this folder across invocations — update in place when rotating.

| Secret file | Purpose |
|---|---|
| `secrets/kandev-pat-<user>.txt` | PAT (`kandev_pat_…`) for `<ADMIN_EMAIL>` — shown once at creation |
| `secrets/kandev-db-password` | `KANDEV_DATABASE_PASSWORD` (Postgres only, `0600`, `${VAR:?set …}` in compose) |
| `secrets/cf-token` | Cloudflare API token (`Zone → DNS → Edit`) for DNS-01 (if H5=DNS-01) |
| `secrets/env` (or compose `env_file`) | `KANDEV_FEATURES_AUTH`, `KANDEV_TRUSTED_PROXIES`, `KANDEV_LOG_LEVEL` |
| Off-host snapshots | `secrets/off-host/manual-*.db` + `secrets/off-host/master.key` (SQLite) or `secrets/off-host/*.dump` (Postgres) after verification |

No real values appear in `plan.md`; this table lists **filenames** only.

## 4. Steps

Numbered steps mirroring `runbook.md`, with **WRITE** flags. The non-chosen deployment branch is parked after approval — steps keep their numbers so `logs/*-NN-*.log` remain stable.

1. **Discover** — present deployment+auth pros/cons, record D1/D2 + F1–F3 + H1–H6/P1–P3/E1–E3 into `inventory.md` §1.1 (Home & DB layout). (read)
2. **Pre-flight** — read `notes/gotchas.md` + fetch live Kandev docs; confirm `ssh <ALIAS>` alias + permission mode (A/B). (read)
3. **Prerequisites — access & home layout** — create/confirm `executions/kandev[-<suffix>]/` (`secrets/` + `logs/`), record Home & DB layout §1.1, pre-create isolated `<KANDEV_HOME_DIR>` (`install -d -m 0700`), DNS + firewall checks. (read / **WRITE** pre-create isolated dir)
4. **[Branch A] Install binary** — `npm install -g kandev@latest` / `brew install kdlbs/kandev/kandev` / archive to `/opt/kandev`; note bundle path for removal. (**WRITE** — host package)
5. **[Branch A] Service install** — `kandev service install --home-dir <KANDEV_HOME_DIR>` (user) or `--system --run-as <USER> --home-dir <KANDEV_HOME_DIR>` (system) after `install -d -o <USER>` pre-create; verify `service config --home-dir` + `install.json` + `/ready`. (**WRITE** — systemd unit/plist + `KANDEV_HOME_DIR` tree)
6. **[Branch A] Fixed port drop-in (if pinned port required)** — `systemctl --user edit kandev.service` → `Environment=KANDEV_BACKEND_PORT=<PORT>` + `daemon-reload` + `restart`. (**WRITE** — unit drop-in)
7. **[Branch B] Persistence & compose** — `docker volume create kandev-data` or `install -d -o 1000 -g 1000 /srv/kandev`; copy `templates/docker-compose.yml` (pinned `:<X.Y.Z>`), optional `docker-compose.postgres.yml`, wire `KANDEV_DATABASE_PATH` if custom path, verify `docker compose up -d` + `/ready` + `ls /data/data/kandev.db`. (**WRITE** — volume + compose file + container)
8. **Configure — auth + bind + trustedProxies + DB** — write `<KANDEV_HOME_DIR>/config.yaml` (or `/etc/kandev/config.yaml` + note surviving path) or compose env; set `KANDEV_FEATURES_AUTH`, `server.host=127.0.0.1` behind proxy, `KANDEV_TRUSTED_PROXIES=<PEER>`, DB driver/path (§9.4); restart; tail `X-Forwarded-Host from untrusted` warning must be absent. (**WRITE** — config.yaml / compose env)
9. **Auth provisioning (if ON)** — restart → setup mode → create first admin `<ADMIN_EMAIL>` immediately; create invite/PAT (`secrets/kandev-pat-*.txt` `0600`), test `curl -H "Authorization: Bearer <PAT>" https://<DOMAIN>/api/v1/workspaces` (expect 401 without). (**WRITE** — user/PAT creation)
10. **Reverse proxy + DNS + TLS** — deploy `templates/Caddyfile` (isolated snippet `import /srv/kandev/Caddyfile.kandev`) or `nginx-kandev.conf` (isolated `include`), issue cert (HTTP-01/DNS-01), reload; verify `https://<DOMAIN>/health` & `/ready` over TLS, no `403` on `/ws`. (**WRITE** — proxy Caddyfile/vhost)
11. **Executors** — Docker profile (Build Image, pinned `image_tag`) + SSH profiles (`Test Connection` + fingerprint pin + `AllowTcpForwarding`/`MaxSessions` pre-flight), throwaway task per executor reaches `agent_message`. (**WRITE** — executor profiles)
12. **MCP** — proxy root passthrough + `POST https://<DOMAIN>/mcp initialize` via PAT; wire Claude/Cursor/OpenCode `mcpServers.kandev` and verify `tools/list`. (**WRITE** — MCP client config, if local)
13. **DB hygiene check** — `ls -lh <KANDEV_HOME_DIR>/data/kandev.db* <KANDEV_HOME_DIR>/data/master.key || ls <CUSTOM_DB_DIR>/kandev.db*` + `ls <backups>/`; note off-host snapshot requirement. (read / **WRITE** initial manual snapshot)
14. **Verification** — full probe matrix (§15 of `playbook.md`: `/health`/`/ready` local + via `https://<DOMAIN>`, TLS dates, `/api/v1/features`, PAT `401` gate, MCP `initialize`, executor `docker ps --filter label=kandev.managed=true`, SSH `~/.kandev/bin/agentctl` checks) + throwaway task + MCP `create_task_kandev`. (read)
15. **Harden + close** — record verified removal map in `inventory.md`, off-host snapshot `manual-*.db`+`master.key` (or `*.dump`), `notes.md` appendix. (**WRITE** — off-host snapshot copy)

Parked if alternatives chosen: `* (parked — operator chose <BRANCH>)` appended to the non-chosen Branch steps (6 or 7).

## 5. Risk assessment

| Risk | Blast radius | Mitigation / rollback |
|---|---|---|
| `0.0.0.0:38429` unauthenticated if auth OFF + proxy missing | Full workspace takeover | Require `127.0.0.1` + tailnet/firewall + immediate auth ON if public (G3). Rollback: set `server.host: 127.0.0.1` + proxy. |
| Wrong `KANDEV_TRUSTED_PROXIES` peer → spoofed `X-Forwarded-For`, broken `X-Forwarded-Host` gate | Session/rate-limiter bypass, `403` on `/ws`/`/mcp` | Set exact proxy peer IP/CIDR, restart, tail `ignoring X-Forwarded-Host from untrusted peer` must be absent (G9). |
| Random fallback port (G2) breaks proxy/healthcheck | UI unreachable, healthcheck `503` | Check `service logs` for actual port; pin via `KANDEV_BACKEND_PORT` drop-in if pinned port required. |
| Docker executor fails under containerized control plane (G7) | Task container fails to mount `agentctl`/session bind | Prefer Service-on-docker-host for Docker tasks; SSH/Sprites fallback if containerized. |
| DB split — `master.key` not backed with DB | Encrypted secrets undecryptable after restore | Always copy `<home>/data/master.key` (`0600`) alongside any `manual-*.db`/`.dump` snapshot; test restore offline. |
| Two writers against one SQLite file | DB corruption / WAL lock | Single-owner rule: one `<home>`/one `KANDEV_DATABASE_PATH` owned by one backend; separate homes don't help when path overlaps. |
| `rm -rf <KANDEV_HOME_DIR>` purges task worktrees/repos | Unpushed Git work lost | Preserve/push work first; verify off-host snapshot restores before purge (§16.6). |

## 6. Approval

- [ ] Operator reviewed plan, saw deployment + auth pros/cons, chose placement vs isolated home, chose DB layout + removal map
- [ ] Operator set permission mode: **A per-write confirm** / **B plan-as-approved**
- [ ] Operator approved execution on <date> — plan frozen; changes need re-approval
