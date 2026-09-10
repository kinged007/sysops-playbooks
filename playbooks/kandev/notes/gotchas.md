# Kandev — Gotchas (G1–G12+) — read before any run

This file is append-only. Newer entries at the bottom with a date header.
`playbook.md` links here from phases; the plan must confirm it was read.

---

## G1 — Port `38429` is preferred, not guaranteed (random fallback 10000–60000)

**Symptom:** `curl http://127.0.0.1:38429/ready` → `Connection refused` right after `kandev service install`.

**Cause:** The launcher tries `38429`; if busy it picks a random free port in `10000–60000` and logs the actual URL. `kandev service install --port <N>` is currently **overwritten** by the launcher (see `playbook.md` §7.6).

**Fix:** Read `kandev service logs --home-dir <KANDEV_HOME_DIR>` (or `--system`) — it prints the real listener. Hit that port's `/ready`. To pin a port, use a systemd drop-in:
```
# systemctl --user edit kandev.service  (or sudo systemctl edit kandev.service for system)
[Service]
Environment=KANDEV_BACKEND_PORT=<PORT>
```
then `daemon-reload` + `service restart --home-dir <KANDEV_HOME_DIR>`.

## G2 — `KANDEV_SERVER_PORT` / `--port` on `service install` does not reliably stick

Same root as G1. The flag writes `KANDEV_SERVER_PORT` into the unit, then the native launcher replaces it at startup. Until the upstream fix lands, rely on the drop-in in G1. The `systemctl cat kandev.service` line showing `Environment=KANDEV_SERVER_PORT=…` is evidence the flag is **not** effective today.

## G3 — `auth.jwtSecret` does NOT enable authentication

**Symptom:** Operator sets `auth.jwtSecret: <long-random>` in `config.yaml` expecting a login gate; `curl http://<host>:38429/api/v1/workspaces` still returns `200` and no setup wizard appears.

**Cause:** `auth.jwtSecret` is a compatibility field on the main HTTP path — the real toggle is **`KANDEV_FEATURES_AUTH=true`** (env locks it ON) or the UI `Settings → System → Feature Toggles → Authentication & users` → restart. Docs § Configuration says `auth.jwtSecret` is *accepted and validated compatibility config* and *does not add* a boundary on the main product path.

**Fix:** Set `KANDEV_FEATURES_AUTH=true` in compose env / systemd drop-in / `<KANDEV_HOME_DIR>/config.yaml` and restart. The first visitor then **must** create the admin immediately (see G9).

## G4 — Auth isolation is application-layer, not filesystem

With `KANDEV_FEATURES_AUTH=true`, Kandev isolates *data* per user (workspaces/tasks/secrets return `not found` to other users). It **does not** isolate:

- The on-disk tree under `KANDEV_HOME_DIR` (`tasks/`, `repos/`, `worktrees/`, `sessions/`) — owned by the OS user running the backend. Anyone with shell access to that OS user can read all files.
- Agent CLI logins (`gh auth`, `claude login`, provider tokens) — they authenticate as the OS user, so all Kandev users share the same on-disk agent credentials.

For hard agent-credential isolation, run a separate Kandev instance per OS user (separate `--home-dir` + separate service/port/proxy host) or use the filesystem-acl / sandboxed executor pattern.

## G5 — Config file search is first-match, not merged (and `KANDEV_HOME_DIR` cannot be moved by its own file)

`config.yaml` search: `./config.yaml` → `<KANDEV_HOME_DIR>/config.yaml` → `/etc/kandev/config.yaml`. Only the first existing file is read. Two files side-by-side are **not** merged. A home-selected file cannot set `homeDir` (it cannot relocate the directory that selected it) — pass `--home-dir <KANDEV_HOME_DIR>` at `service install` time (unit records it). After a config change, **restart** (`service restart --home-dir …` / `docker compose restart kandev`).

Isolation tip: put `config.yaml` at `<KANDEV_HOME_DIR>/config.yaml` so `rm -rf <KANDEV_HOME_DIR>` removes config too. A file at `/etc/kandev/config.yaml` **survives** home removal and must be deleted separately.

## G6 — Bind-mount `/data` permission repair is slow or fails on some storage

The base `ghcr.io/kdlbs/kandev` image starts as root, `chown -R 1000 /data`, then drops to `kandev` (UID 1000) via `gosu`. On a large bind mount this `chown` is **slow**. On root-squashed NFS it can **fail** (ownership not applied). The `universal` flavor runs as `kandev` directly and does **not** do this repair — you must pre-create the host directory `install -d -o 1000 -g 1000 /srv/kandev`.

For fast/remote storage, prefer a **named volume** (`kandev-data`) — the volume is owned inside the container and avoids host `chown`. If you need host-inspectable bind mounts, pre-create with `id kandev` (or `1000:1000`) and verify with `ls -ld /srv/kandev` before `docker compose up -d`.

## G7 — Mounting `/var/run/docker.sock` into the Kandev container is NOT a working Docker executor

**Symptom:** `Settings → Executors → Docker` build succeeds, but every Docker task fails with missing `agentctl` helper / session bind-mount errors in `docker logs kandev`.

**Cause:** The Local Docker executor asks the *daemon* to bind-mount (a) the `agentctl` helper at `/app/...` and (b) per-execution dirs under the control plane's `KANDEV_HOME_DIR` (`/data/agent-sessions`, `/data/tasks`, etc.). When the control plane itself is containerized, the daemon resolves those paths on the **daemon host**, not inside the Kandev container — the helper path doesn't exist there. No compose manifest for full `host-path == container-path` mirroring is shipped.

**Fix:** For reliable Local Docker tasks, run the Kandev control plane **on the Docker host** (Service mode, `KANDEV_DOCKER_ENABLED=true` default). If the control plane must stay containerized, either accept the limitation and use SSH/Sprites executors, or build a custom mirrored deployment that puts every required source at identical absolute host/container paths (advanced, not covered by the default compose).

## G8 — User service disappears after logout/reboot (lingering)

`kandev service install` (user scope) creates a `systemd --user` unit. On Linux it starts at boot **only if lingering is enabled**:
```
sudo loginctl enable-linger "$USER"
systemctl --user enable kandev.service   # plan does this via service install --now
```
`--no-boot-start` on install keeps the pre-existing enabled state. `kandev service logs` warning about disappearance after logout = lingering missing. System services (`--system`) do not need lingering. On macOS, a LaunchAgent belongs to the logged-in GUI user; use a LaunchDaemon for host-wide boot without login.

## G9 — `KANDEV_TRUSTED_PROXIES` gates two things — get the peer wrong and everything breaks silently

`KANDEV_TRUSTED_PROXIES` (or `server.trustedProxies:` in `config.yaml`) controls **both** `X-Forwarded-For` (client IP auditing + rate-limiter key) and `X-Forwarded-Host` (port-scoped cookie host). Rules:

- List the **proxy peer IP** Kandev sees over TCP (e.g. Caddy/Nginx local `127.0.0.1` or Dokploy's `10.x` peer), not the browser network.
- Exact IP is preferred when stable; narrow CIDR (`10.0.0.0/28`) only when the proxy network is dynamic.
- Set it in the **same** place as the rest of config (compose `env_file`, `<KANDEV_HOME_DIR>/config.yaml`, or a systemd drop-in); the unit's fixed env does **not** inherit the shell's.

**Symptoms of a wrong value:** either `journalctl --user-unit kandev | grep "ignoring X-Forwarded-Host from untrusted peer"` (and port-scoped session cookies clash when multiple instances share a host), or `curl -I https://<DOMAIN>/ws` → `403` (Origin gate rejected `X-Forwarded-Host`), or `X-Forwarded-For` spoofing defeats the login rate-limiter.

**Fix:** set the peer shown in the warning as the trusted value, restart, and confirm the warning is gone.

## G10 — Reverse proxy must forward the entire root, preserve WebSocket upgrades, and NOT use a subpath

Kandev is one origin (`:38429`) serving `SPA + /api + /ws + /mcp + /health + /ready`. Subpath deployments (`/kandev/`) are not documented and break SPA/WS/MCP. Use a dedicated host (`kandev.<DOMAIN>`) and proxy `/` with:

- Caddy: `reverse_proxy kandev:38429` (auto WS, auto `X-Forwarded-*`).
- Nginx: `proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; proxy_set_header X-Forwarded-For …; X-Forwarded-Proto …;` + long `proxy_read_timeout`.

Missing `Upgrade` headers → `/ws` and `/mcp` WebSocket connections never upgrade; missing `X-Forwarded-Proto: https` → `Secure` session cookies may not mark correctly over TLS.

## G11 — `/ready` is NOT `/health`; use the right one

- `/health` → `200` as soon as the TCP listener accepts (even mid-startup) — use for `livenessProbe` / process-supervisor.
- `/ready` → `503` until routes + agent registry are wired, then `200` — use for `readinessProbe` / Compose `healthcheck` / `depends_on: condition: service_healthy`.
- `/api/v1/system/health` → diagnostic JSON (healthy + issue list, usually `200` even when `healthy:false`) — not a probe.

Compose example uses `test: ["CMD","curl","-f","http://localhost:38429/ready"]`.

## G12 — SQLite DB continuity: two defaults, snapshot adoption, and when startup refuses to start

No explicit `KANDEV_DATABASE_PATH` / `database.path` → startup checks **both**:

- `<KANDEV_HOME_DIR>/data/kandev.db` (current) and
- `<KANDEV_HOME_DIR>/kandev.db` (legacy).

If **only legacy exists and is valid**, Kandev copies it to the current path as a validated `VACUUM INTO`-style snapshot and leaves legacy files in place for manual recovery. If **both contain task history**, Kandev keeps the current database and does **not** merge. If **current has no task history but legacy has task history**, startup **stops** and names both paths — it will not modify either DB. Fix: stop other writers, preserve both files + `-wal`/`-shm`, and set `database.path: <intended>` or `KANDEV_DATABASE_PATH=<path>` explicitly, then restart.

Custom path rule: `backups/` is always the **sibling of the DB file's parent directory** (`<db-parent>/backups/`). When you set a custom `KANDEV_DATABASE_PATH` (e.g. `/srv/kandev-data/kandev.db`), the UI's Backups page reads/writes `/srv/kandev-data/backups/` (not `<home>/data/backups/`). Kandev does **not** move old snapshots automatically. Also, `<home>/data/master.key` (0600) **never** moves with the DB — a snapshot without the matching key cannot decrypt stored secrets.

## G13 — System service: pre-create the home; installer refuses to `chown` it for you

```
sudo install -d -o <USER> -g <GROUP> -m 0700 <KANDEV_HOME_DIR> <KANDEV_HOME_DIR>/logs
sudo "$(command -v kandev)" service install --system --run-as <USER> --home-dir <KANDEV_HOME_DIR>
```
If the directory is missing, a symlink, or owned by a different user than `--run-as`, `service install --system` fails with guidance (it does not recurse `chown`). Reinstalling without `--run-as` preserves the account stored in the existing managed unit — supply `--run-as` only for an intentional account migration (and reconcile filesystem ownership yourself first).

## G14 — Setup mode race: first visitor after `KANDEV_FEATURES_AUTH=true` becomes admin

Auth ON via **env** locks the toggle ON and boots into setup mode on the next restart. Whoever reaches the origin (proxy `https://<DOMAIN>` or direct `http://127.0.0.1:<PORT>`) **first** creates the admin. Complete the wizard immediately after deploying — especially via env. With auth ON, the instance is authenticated **after** the admin exists; until then the setup pages are intentionally public (like `/health`/`/ready` always are).

## G15 — SQLite's master key is separate from the DB file

`data/master.key` (`0600`, AES-256) lives at `<KANDEV_HOME_DIR>/data/master.key` even when `KANDEV_DATABASE_PATH` points elsewhere. Every `manual-*.db` (SQLite) or `*.dump` (Postgres dump) is undecryptable for stored secrets without its matching key. Back up key + snapshot **together**, test restore together. `scripts/backup.sh` prints this warning and `scripts/restore.sh` checks it.

## G16 — Postgres moves rows only; removal/backup still needs the home

Switching to `driver: postgres` moves **only DB rows** off the Kandev volume. These remain on `/data` (inside `KANDEV_HOME_DIR` or the mounted volume): `tasks/`, `worktrees/`, `repos/`, `sessions/`, `agent-sessions/`, `.npm-global/`, `home/`, `logs/`, `data/master.key`. System `Backups` page becomes SQLite-only. Removal must delete **both** the volume/home **and** have a `pg_dump` retention policy (see `scripts/backup.sh --postgres`).

## G17 — Switching drivers does NOT migrate rows; use §16.4

Setting `KANDEV_DATABASE_DRIVER=sqlite↔postgres` does **not** convert rows — it just opens a different (empty when fresh) database. Real migrations use the three auditable paths in `playbook.md` §16.4:

- **A.** SQLite custom-path move (`.backup` — no driver change),
- **B.** SQLite→Postgres via `pgloader` (verified row counts),
- **C.** Postgres→SQLite reverse (converter tool + table-by-table verification),

each preceded by a **verified** snapshot/dump + a maintenance window (all backends stopped). `scripts/migrate-db.sh` wraps these with `--dry-run` and `--assume-stopped`.

## G18 — One isolated home = one clean `rm -rf`

For removable Service installs, the plan chooses **one** `<KANDEV_HOME_DIR>` and records it in `plan.md` §1.1 (plus inventory and runbook). `kandev service uninstall --home-dir <KANDEV_HOME_DIR>` removes the **unit** only; the isolated home (`<KANDEV_HOME_DIR>`, and if applicable `<CUSTOM_DB_DIR>` and `/etc/kandev/config.yaml` when a shared config was used) stays until an explicit `rm -rf <home>` after an off-host snapshot is verified. This is intentional — never surprise-delete data at uninstall time.

## G19 — Docker executor shows “No compatible agent profiles for ‘Docker’” — check WORKSPACE Default Agent Profile

**Symptom:** `Settings → Executors → Docker` profile built successfully, but `New Task → Executor: Docker` shows **`No compatible agent profiles for "Docker"`** and the agent dropdown is empty — no agent can be selected.

**Cause:** The *workspace* has no usable Default Agent Profile. Kandev filters agents by executor compatibility, and the workspace setting **`Settings → Workspaces → <workspace> → Default Agent Profile`** is still `Default` (the placeholder, not a real profile). `Default` is not an installed agent (Claude/Codex/OpenCode/Copilot/Pi) and has no Docker-compatible runtime mapping. The API therefore returns zero compatible profiles even though `Settings → Agents` shows installed agents.

**Fix:** In the workspace that will own the task, open **`Settings → Workspaces → <workspace> → Default Agent Profile`** and change it from `Default` to a real installed profile — e.g. `Claude`, `Codex`, `OpenCode`, `Copilot`, or `Pi` (the ones installed via `npm install -g @anthropic-ai/claude-code` etc.). Save. Return to `New Task` — the Docker executor now shows the compatible agents. If you use multiple workspaces, set the Default Agent Profile **per workspace** (it is not global). Verify with a throwaway task: `New Task → Executor: Docker` → agent list populated → `docker ps --filter label=kandev.managed=true` shows the task container.

*Seen 2026-09-01 on `agents.munyard.biz` (v0.92.2) after global installs — global `npm install -g` made agents visible in `Settings → Agents`, but tasks remained blocked until the workspace default was switched.*

---

## History

- 2026-09-01: Initial G1–G18 captured from Kandev docs (run-as-a-service, docker, authentication, configuration, executors, operations) and adapted for this playbook's isolated `--home-dir` + DB-path layout.
- 2026-09-01: G19 added — Docker “No compatible agent profiles” caused by workspace Default Agent Profile still set to placeholder `Default`.

