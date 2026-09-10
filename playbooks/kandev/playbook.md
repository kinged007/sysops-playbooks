# Playbook: Kandev — Procedure

Canonical steps for a run. **Placeholders only** — never real IPs, hostnames,
usernames, or credentials. Real values go in the execution's `plan.md`.
Repo-level rules (folder discipline, secrets, committing): see `AGENTS.md`.

> **Read `notes/gotchas.md` before anything.** Every phase below has traps
> hit on real installs (auth lock, port fallback, Docker executor, proxy).
> **Fetch the live Kandev docs at the start of the run** — they are the
> source of truth for flags, paths, and env names:
> `https://kandev.ai/docs/run-as-a-service`, `/docker`, `/authentication`,
> `/executors`, `/automation-and-mcp`, `/configuration`, `/operations`.

---

## 1. System overview

```
                  ┌─────────────────────────────────────────┐
                  │         Kandev control plane            │
                  │  SPA + API + WS (/ws) + MCP (/mcp)     │
                  │  health (/health) / ready (/ready)     │
                  │              :38429                     │
                  └───────────┬──────────────┬──────────────┘
                              │              │
                    ┌─────────┴──────┐  ┌────┴─────────────┐
                    │ Reverse proxy  │  │  Auth (opt-in)   │
                    │ Caddy/Nginx/   │  │  KANDEV_FEATURES │
                    │ Traefik (TLS)  │  │  _AUTH=true      │
                    └──────┬─────────┘  └──────────────────┘
                           │ :443 https://<DOMAIN>
                  ┌────────┴────────┐
                  │  Executors      │
                  │  Local/Worktree │  Docker (local daemon)
                  │  SSH (remote)   │  Sprites (optional)
                  └─────────────────┘
```

- **Control plane** = one process serving the SPA/API/WS/MCP on a single port (default `38429`, fallback `10000–60000` if busy — see G2).
- **Persistence** = `<KANDEV_HOME_DIR>/data/kandev.db` (SQLite, default) or external Postgres; plus `/data/repos`, `/tasks`, `/worktrees`, `/sessions`, `/agent-sessions`, `/data/.npm-global`, `/data/home`. `KANDEV_HOME_DIR` is the single root that determines where **all** data lives.
- **Service mode (A)** = native binary managed by `systemd --user` / `systemd --system` / `launchd`. **Docker mode (B)** = `ghcr.io/kdlbs/kandev:X.Y.Z` with a mounted `/data` volume.
- **MCP** = external clients (Claude Code, Cursor, OpenCode) talk to `https://<DOMAIN>/mcp` with a PAT (`kandev_pat_…`) when auth is ON.
- **Executors** = where agent sessions run. `Local Docker` and `SSH` are the playbook defaults (asked, enabled unless operator opts out).

### Key design decisions (do not "improve" without re-reading these)

1. **Auth is a runtime feature toggle**, not a config file. `KANDEV_FEATURES_AUTH=true` (or UI `Settings > System > Feature Toggles → Authentication & users` → restart) boots into **setup mode**; the **first visitor creates the admin**. If you set it via env, the UI toggle is locked ON.
2. **TLS ≠ auth.** TLS terminates in the reverse proxy; auth is separate. An `0.0.0.0` bind without auth logs a warning and must never be internet-exposed.
3. **Config file search is first-match, not merged:** `config.yaml` in CWD → `<KANDEV_HOME_DIR>/config.yaml` → `/etc/kandev/config.yaml`. The service unit carries the selected file; env overrides file.
4. **Docker control plane ≠ Docker executor.** Giving the Kandev *container* a Docker socket (`/var/run/docker.sock`) is **not a complete Local Docker config** — the daemon resolves bind-mount sources on the *daemon host*, not inside the Kandev container. Prefer running the control plane on the Docker host for reliable Docker tasks (see §12 / G7).
5. **Ports lie.** `--port`/`KANDEV_SERVER_PORT` on a `service install` is currently **overwritten by the launcher's auto-selection** (G2). Pin with a systemd drop-in `KANDEV_BACKEND_PORT` if you need a fixed port.
6. **Pros/cons must be shown and choice asked.** Never assume Service vs Docker or Auth ON vs OFF — present the tables from the README and record the operator's choice in `plan.md`.
7. **Service installs must be removable with one command.** Native installs scatter state across `~/.kandev`, `/etc/kandev`, `/var/lib/kandev`, `~/.config/systemd/user`, and the npm/brew prefix unless you choose an **isolated `KANDEV_HOME_DIR`** and record it. This playbook always offers `--home-dir <isolated-path>` so the entire Kandev tree (DB, worktrees, repos, `master.key`, logs, `service/install.json`) lives in one place that `kandev service uninstall` + `rm -rf <home-dir>` removes cleanly. The same principle applies to Docker: one named volume or one bind-mounted host directory — never a mix.

---

## 2. Roles

| Task | Who | Why |
|------|-----|-----|
| Choose deployment mode (Service vs Docker vs mention others) | **Operator (with Agent advice)** | Cost, persistence, host ownership |
| Choose auth mode (ON recommended vs OFF single-user) | **Operator** | Security boundary decision |
| Choose isolated home path + DB driver (SQLite vs Postgres, removal plan) | **Operator** | Determines future `rm -rf` scope and migration complexity |
| Provide SSH access (`ssh-copy-id` + `~/.ssh/config` alias) | **Operator** | Agent never handles passwords |
| Create DNS record + decide TLS method (Caddy auto-TLS vs ACME DNS-01) | **Operator** | Owns the domain |
| Approve Cloudflare API token (if DNS-01) and any PAT scope | **Operator** | Secret ownership |
| Approve each **WRITE** (mode A per-write confirm, or mode B plan-as-approved) | **Operator** | AGENTS.md §1.3 |
| Everything else (install, config, proxy, verify, executor plumbing) | **Agent** | Technical work |

**The agent's golden rule: never ask for (or accept) a password.** If a step needs privilege the agent doesn't have, hand the operator the exact command or use a scoped `NOPASSWD` helper.

### Permission model note (the `sudo` problem)

Some hosts disable `root` SSH and require a password for `sudo`. For **system-service** installs the agent needs passwordless `systemctl`/`install` only if the operator wants agent-driven install — otherwise the operator runs the `sudo` lines. User-service and Docker mode require no `sudo`. When using `--home-dir` with a system service, the directory must be pre-created and `chown`ed to `--run-as <USER>` before `service install` (the installer refuses to `chown` for you and will fail with guidance).

---

## 3. Prerequisites (verify before SSH work)

- [ ] **T1 — Target host decided:** ask *"Where should Kandev run? Which machine/VPS will host the control plane?"* Record `<ALIAS>` + chosen `<KANDEV_HOME_DIR>`:
  - Service (removable): isolated path via `--home-dir` — e.g. `/srv/kandev` or `/opt/kandev/data` (system service) or `$HOME/.kandev-isolated` / `$HOME/srv/kandev` (user service) — so `uninstall` + `rm -rf` cleans everything. Default fallback is `~/.kandev` (user) or `/var/lib/kandev` (system) if operator accepts scattering.
  - Docker: `/data` inside container → host volume `<HOST_DATA_PATH>` (`/srv/kandev` bind mount) or `kandev-data` named volume — single source of truth.
  - Record the chosen path in `plan.md` and `inventory.md` Section 1.1 (Home & DB layout).
- [ ] **T2 — SSH alias:** operator runs `ssh-copy-id <user>@<host>` and adds `Host <ALIAS>` to `~/.ssh/config`. Agent verifies with `ssh <ALIAS> 'echo ok; uname -a'`.
- [ ] **T3 — OS + tool check:** `ssh <ALIAS> 'systemctl --version; docker --version; docker compose version; caddy version; nginx -v'` (whichever path applies). For Service mode: `node --version` + `npm --version` (≥22 / ≥7) or `brew --version`. Check `sqlite3 --version` (for local SQLite sanity) and `pg_isready` if Postgres is under consideration.
- [ ] **T4 — Domain + DNS:** operator confirms `<DOMAIN>` (e.g. `kandev.example.com`) and where DNS is hosted (Cloudflare / registrar / other).
- [ ] **T5 — Reverse-proxy choice:** ask which proxy the host already uses (Dokploy Traefik, standalone Caddy, Nginx, none). Ship the matching template from `templates/`.
- [ ] **T6 — Port availability:** `ssh <ALIAS> 'ss -tlnp | grep -E "38429|443|80"'` — must show `38429` free (or plan the fallback/drop-in).
- [ ] **T7 — DB driver decision staged:** ask P1/P2 (§4.4) *before* install so `--home-dir` and compose `volumes:` already match the chosen storage layout (SQLite path vs Postgres separation). Never assume SQLite.

---

## 4. Phase 0 — Discovery: questions to ask before anything

> Gather answers from the operator **and** by inspection. Record in the execution's `inventory.md`. Mark each answer as *operator-answered* vs *verified by inspection*. **Do not skip the two branching questions (D1, D2).**

### 4.1 The critical decisions first (ask before anything else)

| # | Question | Why it matters | Default proposal |
|---|----------|----------------|------------------|
| **D1** | **Where should Kandev run, and which deployment path?** (A) Run as a Service (`kandev service install` → systemd/launchd) on this host, **or** (B) Docker / Docker Compose (`ghcr.io/kdlbs/kandev`) on this host? Mention others (CLI foreground, Desktop App, Kubernetes) and their trade-offs, then ask. | Selects the entire install branch (Phase 7 vs Phase 8). Never assume. | **B (Docker Compose + Caddy)** for servers; **A (user systemd service with `--home-dir`)** for a workstation — but **always ask** and show the pros/cons table from the README. |
| **D2** | **Authentication:** single-user without authentication (requires network-level protection) **or** with authentication (`KANDEV_FEATURES_AUTH=true`, **preferred**, especially if publicly accessible)? | Auth ON vs OFF changes every hardening step — PATs, proxy, bind address, trustedProxies, setup-mode admin. | **Auth ON** (`true`). Require explicit sign-off to stay OFF on a non-loopback/public host. |

**Script to read aloud / paste:**

> "Kandev can run in a few ways — the two we recommend are (A) **Run as a Service** — a native `systemd`/`launchd` service on the host (`kandev service install`) — and (B) **Docker / Docker Compose** — a pinned `ghcr.io/kdlbs/kandev` image with a persistent `/data` volume. There are also other options — a plain `kandev --headless` foreground process, the Desktop App, or Kubernetes (experimental, single-replica) — but A and B are the ones that give you long-lived, restart-safe operation *and* reliable Docker-based task execution.
>
> **(A) Service pros:** no container layer, fastest cold-start, direct host Docker/SSH executors; with `--home-dir <isolated>` the whole tree removes cleanly. **Cons:** host toolchain needed, needs `loginctl enable-linger` for user units, and the `--port` flag doesn't reliably pin the listener (needs a drop-in).
>
> **(B) Docker pros:** reproducible image-pinned deploys, pairs cleanly with a Caddy/Nginx sidecar for TLS, easy to move between hosts. **Cons:** mounting the Docker socket alone isn't enough for Local Docker tasks (the daemon resolves bind-mount paths on the daemon host — so reliable Docker tasks normally need the control plane *on* the Docker host).
>
> Which would you prefer for **where** it runs, and do you want it on an **isolated path** (so uninstall is `service uninstall` + `rm -rf <home-dir>`) or the default scattered layout?
>
> Then: authentication is off by default (single-user). For any host that other users or the internet can reach, we **strongly recommend** `KANDEV_FEATURES_AUTH=true` — each person gets their own account/workspaces, and MCP/external clients use personal access tokens. Without auth, anyone who can reach the listener controls everything, so we'd have to lock it behind loopback/VPN/Tailscale and a proxy. Do you want **auth ON (recommended)** or stay single-user OFF (and if so, how will you shield it)?"

### 4.2 Feature defaults — ask, but assume wanted unless operator opts out

| # | Question | Default | Why |
|---|----------|---------|-----|
| **F1** | **MCP access** — should your AI assistant (Claude Code / Cursor / OpenCode) manage projects/tasks via `https://<DOMAIN>/mcp`? | **Yes** — enabled + verified | Primary reason many operators self-host; requires PAT when auth ON and a proxy that forwards `/mcp` + WebSocket upgrades. |
| **F2** | **Docker executor (Local Docker)** — tasks in repeatable containers? | **Yes** | Repeatable boundary; needs `docker.host` reachable and `KANDEV_DOCKER_ENABLED=true` (host-native) or acknowledged container limitation. |
| **F3** | **Remote SSH executor(s)** — tasks on remote hosts via SSH/SFTP? | **Yes** — ask how many hosts, get `<ALIAS_SSH_*>` | Requires target fingerprint pinning, `bash`/`zsh`, `AllowTcpForwarding yes`, agent binary probe. |

If any of F1–F3 is declined, record the opt-out and skip the matching section — but **plan must ensure each requested feature is clearly achievable** (MCP endpoint reachable, Docker build succeeds, SSH `Test Connection` passes).

### 4.3 Host & domain

| # | Question | Why |
|---|----------|-----|
| H1 | Host OS: Linux distro + version / macOS version? | Service vs Docker path changes; systemd vs launchd. |
| H2 | Is Docker already on this host, or should we install it? Which storage driver/volume path? | Docker mode + Docker executor need it. |
| H3 | What is `<DOMAIN>` and where is its DNS (Cloudflare / registrar / other)? Can you create an `A`/`CNAME` for it? | DNS + TLS. |
| H4 | Existing reverse proxy on this host? (Dokploy Traefik / Caddy / Nginx / none) | Which template to use; whether `:80/:443` already bound. |
| H5 | TLS preference: **Caddy auto-TLS (HTTP-01, simplest)** vs **DNS-01** (wildcard / origin behind firewall) vs **existing cert**? | Determines ACME flow and whether a Cloudflare API token is needed. |
| H6 | For a Service install: do you want an **isolated `KANDEV_HOME_DIR`** (recommended for clean uninstall: e.g. `/srv/kandev` or `$HOME/srv/kandev`) or the default `~/.kandev` / `/var/lib/kandev`? | Determines `uninstall` + `rm -rf` scope and whether scattering is accepted. |

### 4.4 Persistence & database — storage layout is a plan decision, not an afterthought

| # | Question | Why | Default |
|---|----------|-----|---------|
| **P1** | **SQLite (default, embedded, WAL)** or **PostgreSQL (external, operator-managed)**? See §9.4 for the full matrix: SQLite is one-file + one `master.key`, simplest + fastest for single-host; Postgres moves DB off-volume, needs `pg_dump`/PITR, keeps `/data` still required for worktrees/repos. Which do you prefer *now*, and what might you want *later* (so migration can be planned)? | DB driver changes compose/env, backup, and migration steps (§16.4). Never assume. | **SQLite** (single-host default) unless operator says Postgres |
| **P2** | **Where should the DB file live?** SQLite options: (i) default `<KANDEV_HOME_DIR>/data/kandev.db` (inside the isolated home — removal is `rm -rf <home-dir>`), (ii) custom absolute path via `KANDEV_DATABASE_PATH` / `database.path` (e.g. `/srv/kandev-data/kandev.db` on its own subvolume/mount), (iii) legacy `<KANDEV_HOME_DIR>/kandev.db` only if migrating an old install (see §9.4 / G11). Postgres options: host/DB/user/password/sslMode + `backups/` sibling dir consideration. | Path determines `backups/` location, snapshot wiring, and whether `rm -rf` is sufficient or deliberate. | (i) `<KANDEV_HOME_DIR>/data/kandev.db` — co-located, simplest |
| P3 | Host volume for Docker/service: **named volume** (`kandev-data`) or **bind mount** (`/srv/kandev` → `/data`)? If bind, is `chown 1000:1000` feasible and not root-squashed (NAS)? | Permissions + portability (G6) and whether the K8s/container `fsGroup` dance is needed. | Named volume unless operator needs host inspection |

> **Rule:** the DB location and `KANDEV_HOME_DIR` must be complementary — the plan records a single **home + DB layout** (e.g. `home=/srv/kandev, db=<home>/data/kandev.db` *or* `home=/srv/kandev, db=/srv/kandev-data/kandev.db` with explicit `KANDEV_DATABASE_PATH`) so future `kandev service uninstall` + `rm -rf <home>` + (if custom DB path outside home) `rm <db> <backups>` is auditable and complete.

### 4.5 Executors — details if F2/F3 accepted

| # | Question | Why |
|---|----------|-----|
| E1 | For Docker executor: which image to pin for tasks? Default `node:22-slim` + `kandev/multi-agent:latest` equivalent, or a custom Dockerfile? | Image build runs with daemon authority — admin operation. |
| E2 | For SSH: for each `<ALIAS_SSH_*>`, hostname/IP, port, user, auth (ssh-agent vs key file), and can you share the expected SHA256 fingerprint out-of-band? | Pinning + verification; bastion `ProxyJump` if needed. |
| E3 | Any Sprites.dev sandboxes needed? Provider token available as secret? | Optional. |

---

## 5. Phase 1 — Decide method and record the plan

- [ ] Present **both** tables (deployment modes + auth modes) from the README verbatim.
- [ ] Record operator choice for **D1** (A vs B, plus isolated home path vs default) and **D2** (auth ON vs OFF + shielding if OFF).
- [ ] Record choices for **F1–F3** (MCP / Docker / SSH — default all ON).
- [ ] Record `<ALIAS>`, `<KANDEV_HOME_DIR>` (isolated or default), `<DOMAIN>`, reverse-proxy choice, TLS choice.
- [ ] Record **P1–P3**: SQLite vs Postgres, exact DB path (`<KANDEV_HOME_DIR>/data/kandev.db` vs custom `KANDEV_DATABASE_PATH`), volume type (named vs bind). Include the **removal map**: which paths `uninstall` + `rm -rf` will delete and which are outside the home (secrets, custom DB, compose file).
- [ ] Record DB migration intent if operator says "start SQLite, move to Postgres later" (or vice-versa) → park a migration step (§16.4) without blocking Day-1.
- [ ] Write the chosen branch into `plan.md` (steps below are the master list; mark the non-chosen branch as *parked*).
- [ ] Record permission mode per AGENTS.md §1.3 (ask: *"Should I confirm before each production write, or is it OK to execute the plan as approved?"* → **A per-write confirm** (default) or **B plan-as-approved**) and save it in `plan.md`.

### 5.1 Branch summary (for `plan.md`)

| Branch | Meaning |
|--------|---------|
| **Branch A — Service** | §§7 + 9 + 10 + 11 + 12 + 13 + 15.2 + 16 (this page) |
| **Branch B — Docker** | §§8 + 9 + 10 + 11 + 12 + 13 + 15.1 + 16 |

Other install options (CLI foreground / Desktop / Kubernetes) are **parked** unless operator explicitly opts in — note them as alternatives in `plan.md` so the decision is auditable.

---

## 6. Phase 2 — Prerequisites & access (both branches)

- [ ] `ssh <ALIAS> 'echo ok; id; pwd; ls -la'` — reachable via alias, no password.
- [ ] Create/confirm the execution folder `executions/kandev/` (or `executions/kandev-<suffix>/`) with `secrets/` + `logs/`; `git status` must show no `executions/` (AGENTS.md §7).
- [ ] Record the **Home & DB layout** in `inventory.md` §1.1 (template below) — this is the contract for later removal/migration:
  ```markdown
  ## 1.1 Home & DB layout (this variant)
  - KANDEV_HOME_DIR: <KANDEV_HOME_DIR>   # e.g. /srv/kandev or /var/lib/kandev or ~/.kandev or /srv/kandev/docker-data
  - Database driver: sqlite | postgres
  - Database path: <KANDEV_HOME_DIR>/data/kandev.db  # or KANDEV_DATABASE_PATH=/srv/kandev-data/kandev.db
  - Backups dir: <backups-dir>  # <db-parent>/backups  (sibling of the DB file) or <home>/data/backups
  - master.key: <KANDEV_HOME_DIR>/data/master.key (owner-only 0600, required to decrypt secrets)
  - Outside-home extras: <list any custom DB path / bind mount host path / compose file location>
  ```
- [ ] DNS: operator creates `A`/`CNAME` for `<DOMAIN>` → `<ALIAS>` public IP (or tailnet IP if VPN-only). Verify propagation: `dig <DOMAIN> +short` and `curl -I http://<DOMAIN>` (expect proxy 502/308 until Kandev is up — that's OK).
- [ ] Firewall: allow `80/tcp` + `443/tcp` to the proxy (and `22/tcp` for SSH only from your IP/tailnet). If `<DOMAIN>` will be VPN-only, confirm the VPN ACL allows the operator's client.
- [ ] For isolated service homes: pre-create the directory so ownership can be verified before `service install`:
  ```bash
  # User service isolated (no sudo):
  ssh <ALIAS> 'install -d -m 0700 <KANDEV_HOME_DIR> && ls -ld <KANDEV_HOME_DIR>'

  # System service isolated (needs sudo + chown to --run-as user):
  ssh <ALIAS> 'sudo install -d -o <USER> -g <GROUP> -m 0700 <KANDEV_HOME_DIR> <KANDEV_HOME_DIR>/logs && sudo namei -l <KANDEV_HOME_DIR> | head -20'
  ```

---

## 7. Branch A — Run as a Service (`kandev service install`)

> This branch is **parked** if the operator chose Docker (Branch B).

### 7.1 Choose service scope (+ isolated home)

| Scope | Unit path | Default home if no `--home-dir` | Isolated home example | When | Needs lingering? |
|-------|-----------|----------------------------------|-----------------------|------|------------------|
| **User service** (default) | `~/.config/systemd/user/kandev.service` (Linux) / `~/Library/LaunchAgents/com.kdlbs.kandev.plist` (macOS) | `~/.kandev` (scattered alongside dotfiles) | `~/srv/kandev` or `~/.kandev-isolated` via `--home-dir ~/srv/kandev` | Personal workstation / single-user host; want removal = `uninstall` + `rm -rf ~/srv/kandev` | **Yes** on Linux for boot-without-login: `sudo loginctl enable-linger <user>` |
| **System service** (`--system`) | `/etc/systemd/system/kandev.service` / `/Library/LaunchDaemons/com.kdlbs.kandev.plist` | `/var/lib/kandev` (scattered: unit in `/etc`, data in `/var/lib`) | `/srv/kandev` via `--home-dir /srv/kandev` (pre-created, `chown <USER>`) | Boot-time, login-independent, multi-user host; want removal = `uninstall --system` + `rm -rf /srv/kandev` | No — but needs `sudo` + `--run-as <USER>` |

Ask which scope **and** whether to use an isolated `--home-dir`. Record in `plan.md`. **Recommend isolated** unless operator explicitly accepts defaults — the rest of this branch wires `--home-dir <KANDEV_HOME_DIR>` everywhere.

### 7.2 Install the Kandev binary (persistent, not `npx`)

```bash
# Choose ONE channel. Prefer global npm for a durable service:

# npm (recommended for service):
npm install -g kandev@latest
kandev --version

# Homebrew (macOS/Linux):
brew install kdlbs/kandev/kandev
kandev --version

# Release archive (if neither is available):
curl -fsSLO https://github.com/kdlbs/kandev/releases/latest/download/kandev-linux-x64.tar.gz
curl -fsSLO https://github.com/kdlbs/kandev/releases/latest/download/kandev-linux-x64.tar.gz.sha256
shasum -a 256 -c kandev-linux-x64.tar.gz.sha256
tar -xzf kandev-linux-x64.tar.gz
sudo mv kandev /opt/kandev && sudo ln -sf /opt/kandev/bin/kandev /usr/local/bin/kandev
kandev --version

# Verify: do NOT use npx for a durable service:
# npx -y kandev@latest service install  # ephemeral, cache-clean invalidation — avoid unless operator insists
```

> Archival note: `/opt/kandev` is the launch bundle; `<KANDEV_HOME_DIR>` is the runtime state. Removing the service **does not** remove the bundle — note which bundle path to delete separately if a full purge is intended (`npm root -g`, `brew --cellar kandev`, or `/opt/kandev`).

### 7.3 User service install (isolated home recommended)

```bash
# Isolated (recommended — clean removal):
ssh <ALIAS> 'kandev service install --home-dir <KANDEV_HOME_DIR>'
ssh <ALIAS> 'kandev service status --home-dir <KANDEV_HOME_DIR>'
ssh <ALIAS> 'kandev service logs --home-dir <KANDEV_HOME_DIR>'   # shows actual listener URL (may NOT be 38429 if busy — G2)
ssh <ALIAS> 'kandev service config --home-dir <KANDEV_HOME_DIR>' # diagnostic: prints OS manager, mode, home, unit path

# Default (only if operator accepted scattering):
ssh <ALIAS> 'kandev service install'
ssh <ALIAS> 'kandev service status'
ssh <ALIAS> 'kandev service logs'

# If boot-without-login is required:
ssh <ALIAS> 'sudo loginctl enable-linger $USER'
ssh <ALIAS> 'loginctl show-user $USER | grep Linger'

# Verify readiness (port from logs — may be random fallback):
ssh <ALIAS> 'curl --fail http://127.0.0.1:<PORT>/ready'
ssh <ALIAS> 'ls -l <KANDEV_HOME_DIR>/service/install.json && cat <KANDEV_HOME_DIR>/service/install.json | jq .'
# Expected layout after install (isolated):
# <KANDEV_HOME_DIR>/
#   data/kandev.db (+ -wal/-shm)  ← DB
#   data/master.key                ← owner-only 0600, decrypts secrets
#   data/backups/                  ← SQLite snapshots (if driver=sqlite)
#   logs/backend-logs.log          ← file logs (256 MiB ring)
#   service/install.json           ← install metadata (owner-only)
#   repos/ tasks/ worktrees/ sessions/ agent-sessions/ …
```

- [ ] **WRITE** — `kandev service install --home-dir <KANDEV_HOME_DIR>` (user scope) writes `~/.config/systemd/user/kandev.service` (or `~/Library/LaunchAgents/...`), does `daemon-reload` + `enable --now` / `bootstrap` + `kickstart`. The unit records `KANDEV_HOME_DIR`. Rollback: `kandev service uninstall --home-dir <KANDEV_HOME_DIR>` (or without flag if default) — removes unit, **leaves** `<KANDEV_HOME_DIR>` intact (so `rm -rf <KANDEV_HOME_DIR>` is the explicit data purge, §16.5).

### 7.4 System service install (only if chosen, isolated home required for clean removal)

```bash
ssh <ALIAS> 'KANDEV_BIN="$(command -v kandev)"; echo $KANDEV_BIN'
# Pre-create isolated home with correct ownership BEFORE install (installer refuses to chown):
ssh <ALIAS> 'sudo install -d -o <USER> -g <GROUP> -m 0700 <KANDEV_HOME_DIR> <KANDEV_HOME_DIR>/logs'
ssh <ALIAS> 'sudo namei -l <KANDEV_HOME_DIR> | head -20'

# Install (omit --run-as on reinstall to preserve recorded account):
ssh <ALIAS> 'sudo "$(command -v kandev)" service install --system --run-as <USER> --home-dir <KANDEV_HOME_DIR>'
ssh <ALIAS> 'sudo "$(command -v kandev)" service status --system --home-dir <KANDEV_HOME_DIR>'
ssh <ALIAS> 'sudo "$(command -v kandev)" service config --system --home-dir <KANDEV_HOME_DIR>'
ssh <ALIAS> 'sudo journalctl -u kandev.service -n 100 --no-pager'

# macOS daemon variant (same flags):
ssh <ALIAS> 'sudo "$(command -v kandev)" service install --system --run-as <USER> --home-dir <KANDEV_HOME_DIR>'
```

- [ ] **WRITE** — system install writes `/etc/systemd/system/kandev.service` (or `/Library/LaunchDaemons/com.kdlbs.kandev.plist`) and expects `/srv/kandev` already owed by `<USER>`. Rollback: `sudo "$(command -v kandev)" service uninstall --system --home-dir <KANDEV_HOME_DIR>`.
- [ ] Record the uninstall + removal commands verbatim in `plan.md` §16.5 so any future operator can run them without hunting (see §6 inventory snippet).

### 7.5 Environment isolation & custom DB path (Service)

```bash
# The service unit has a small fixed environment — it does NOT inherit the
# installing shell's exports. Put overrides in config.yaml OR a systemd drop-in.

# Config file placement for an isolated home (first-match wins):
# Preferred: <KANDEV_HOME_DIR>/config.yaml   (co-located, removed with rm -rf)
# Alt: /etc/kandev/config.yaml                (shared conventional path — SURVIVES rm -rf <home>, must be deleted separately)
# CWD config.yaml                             (dev-only, do not use for a service)

# Custom SQLite path OUTSIDE the home (e.g. dedicated DB subvolume):
# env:
KANDEV_DATABASE_PATH=/srv/kandev-data/kandev.db   # or database.path in config.yaml
# Backups then live beside the DB: /srv/kandev-data/backups/  (NOT <home>/data/backups)
# master.key stays at <KANDEV_HOME_DIR>/data/master.key — DB backup without matching key cannot decrypt secrets
```

- [ ] If `KANDEV_DATABASE_PATH` is outside `<KANDEV_HOME_DIR>`, record both paths in `plan.md`/`inventory.md` and note that removal requires `rm -rf <KANDEV_HOME_DIR> <CUSTOM_DB_DIR>` (§16.5).

### 7.6 Fixed-port control (only if a pinned port is required — G2)

> Do **not** rely on `kandev service install --port <N>` — the launcher overwrites it. Use the OS drop-in instead.

```bash
# Linux user service:
ssh <ALIAS> 'systemctl --user edit kandev.service'   # adds:
# [Service]
# Environment=KANDEV_BACKEND_PORT=<PORT>

ssh <ALIAS> 'systemctl --user daemon-reload; kandev service restart --home-dir <KANDEV_HOME_DIR>; kandev service logs --home-dir <KANDEV_HOME_DIR> | tail -20'

# Linux system service:
ssh <ALIAS> 'sudo systemctl edit kandev.service'     # same stanza
ssh <ALIAS> 'sudo systemctl daemon-reload; sudo "$(command -v kandev)" service restart --system --home-dir <KANDEV_HOME_DIR>'
```

- [ ] If a pinned port is required, confirm `/ready` is on `<PORT>` after restart: `curl --fail http://127.0.0.1:<PORT>/ready`.

---

## 8. Branch B — Docker / Docker Compose (recommended for servers)

> This branch is **parked** if the operator chose Service (Branch A).

### 8.1 Choose persistence & placement

- [ ] Ask **named volume** vs **bind mount** (P3). Named = portable, survives `docker compose down`; bind = host-inspectable, survives `docker volume rm`. Record choice + host path in `plan.md` §1.1.
- [ ] Named volume: `ssh <ALIAS> 'docker volume create kandev-data && docker volume inspect kandev-data'`
- [ ] Bind mount: `ssh <ALIAS> 'sudo install -d -o 1000 -g 1000 /srv/kandev && ls -ld /srv/kandev'` — `1000:1000` is the `kandev` user inside the base image; universal image runs as `kandev` directly. Verify `fsGroup`/root-squash if on NFS.

> Isolation note: the Docker variant is already removable (one volume/dir + `docker compose down`). Prefer a single location — don't mix a bind-mounted home with a named volume for backups.

### 8.2 Compose files

- [ ] Copy `templates/docker-compose.yml` → `executions/kandev/compose/docker-compose.yml` (or `<ALIAS>` subfolder), replace `<KANDEV_IMAGE_TAG>` with a **pinned** version (e.g. `0.8.3`, not `latest`) or digest. **WRITE** — `docker volume create` / `install -d` for the bind mount.
- [ ] If SQLite custom path (P2 outside home): set `KANDEV_DATABASE_PATH: /data/db-custom/kandev.db` and add an extra mount `- kandev-db:/data/db-custom` or bind `- /srv/kandev-db:/data/db-custom`. Record that removal needs both volumes/host paths.
- [ ] If Postgres (P1 = postgres): overlay `templates/docker-compose.postgres.yml` and set `KANDEV_DB_PASSWORD` via a `secrets/` file + `${KANDEV_DB_PASSWORD:?set …}` — never inline. Postgres moves **only DB rows** off-volume; `/data` (worktrees/repos/`master.key`) is still required.
- [ ] Review `templates/env.example` → execution `secrets/env` (owner-only `0600`) or compose `env_file:`.

Canonical compose (from `templates/docker-compose.yml`):

```yaml
services:
  kandev:
    image: ghcr.io/kdlbs/kandev:<KANDEV_IMAGE_TAG>
    ports:
      - "127.0.0.1:38429:38429"   # loopback only; proxy terminates TLS
    volumes:
      - kandev-data:/data        # or /srv/kandev:/data for bind
    environment:
      KANDEV_FEATURES_AUTH: "${KANDEV_FEATURES_AUTH:-true}"
      KANDEV_LOG_LEVEL: "${KANDEV_LOG_LEVEL:-info}"
      KANDEV_TRUSTED_PROXIES: "${KANDEV_TRUSTED_PROXIES:-}"  # proxy IP/CIDR
      KANDEV_DATABASE_DRIVER: "${KANDEV_DATABASE_DRIVER:-sqlite}"  # or postgres
      # KANDEV_DATABASE_PATH: /data/db-custom/kandev.db  # only if P2 outside home
      # KANDEV_DATABASE_PASSWORD: "${KANDEV_DB_PASSWORD:?set …}"  # postgres only
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:38429/ready"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s
volumes:
  kandev-data:
  # kandev-db:  # only if custom path outside /data
```

If the operator wants to expose a different **host** port, change only the left side: `"127.0.0.1:9080:38429"` and open `http://localhost:9080`. Do **not** replace the container command's internal `38429` unless you also re-publish it.

### 8.3 Bring up & verify

```bash
ssh <ALIAS> 'cd <COMPOSE_DIR> && docker compose pull kandev'
ssh <ALIAS> 'cd <COMPOSE_DIR> && docker compose up -d kandev && docker compose logs -f kandev'
ssh <ALIAS> 'docker ps --filter name=kandev'
ssh <ALIAS> 'curl --fail http://127.0.0.1:38429/ready'
ssh <ALIAS> 'curl -s http://127.0.0.1:38429/health | head'
ssh <ALIAS> 'docker exec kandev ls -lh /data/data/kandev.db /data/data/master.key 2>&1 | head'
```

- [ ] **WRITE** — `docker compose up -d` creates the container + volume. Rollback: `docker compose down` (volume persists, data retained) or `docker compose down -v` (destroys volumes — only with operator approval + snapshot, §16.5).

---

## 9. Configuration (both branches)

> Kandev load order (later wins): built-in defaults → **first existing** `config.yaml` (CWD → `<KANDEV_HOME_DIR>/config.yaml` → `/etc/kandev/config.yaml`, no merge) → **env vars** (`KANDEV_*`). Service units carry the selected file; Docker passes env. No `--config` flag. Restart after any change.

### 9.1 Auth flag (the branching toggle — §4 D2)

```bash
# Auth ON (preferred):
# Option 1 — env (fresh servers, Docker, K8s) — locks the UI toggle ON:
KANDEV_FEATURES_AUTH=true

# Option 2 — UI toggle (existing install): Settings → System → Feature Toggles
# → "Authentication & users" → Restart (comes up in setup mode).

# Auth OFF — single-user laptop / VPN-only:
# leave KANDEV_FEATURES_AUTH unset/false (do NOT set a dummy jwtSecret hoping it adds auth — it does not, G3).
```

- [ ] Set `KANDEV_FEATURES_AUTH` in the compose `environment` **or** `<KANDEV_HOME_DIR>/config.yaml` → `features.auth: true` (if using a YAML path) **or** plan the post-up UI toggle. Record which path was chosen.
- [ ] If auth is ON and `KANDEV_FEATURES_AUTH=true` was set via env, note in `plan.md` that the UI toggle is **locked** (cannot be turned off from Settings).

### 9.2 Bind address & trusted proxies

```yaml
# config.yaml minimal (templates/config.yaml.example):
server:
  host: "127.0.0.1"          # loopback when a proxy terminates TLS; use 0.0.0.0 only if auth + proxy shield it
  trustedProxies:
    - "<PROXY_PEER_IP_OR_CIDR>"  # the TCP peer of Kandev — usually 10.x / 172.16.x / 127.0.0.1

logging:
  level: "info"
  format: "text"             # json in production/K8s
```

Env equivalent:

```bash
KANDEV_SERVER_HOST=127.0.0.1
KANDEV_TRUSTED_PROXIES=10.0.0.5          # exact proxy IP if stable; narrow CIDR if the proxy network is dynamic
```

> `KANDEV_TRUSTED_PROXIES` gates both `X-Forwarded-For` (client IP for session audit + rate-limiter) and `X-Forwarded-Host` (port-scoped cookie host). Missing entry → `X-Forwarded-Host from untrusted peer` warning and spoofable `X-Forwarded-For` (G9). List the **proxy peer**, not the browser network; never trust a broad private range by default.

- [ ] **WRITE** — write/overwrite `<KANDEV_HOME_DIR>/config.yaml` (preferred for co-located removal) *or* `/etc/kandev/config.yaml` (shared — survives `rm -rf <home>`, note in `plan.md`) *or* `secrets/env` (compose `env_file:`). Prefer `<KANDEV_HOME_DIR>/config.yaml` when `--home-dir` is isolated so config dies with the home. Set `server.host` to `127.0.0.1` when a proxy is in front. Mode: `0600` if it bears secrets. Rollback: restore the `.bak` copy (service installs save `<path>.bak` when overwriting unmanaged files).
- [ ] For systemd: `systemctl --user edit kandev.service` drop-in to add `Environment=KANDEV_TRUSTED_PROXIES=…` if using env rather than YAML.

### 9.3 Persistence + Docker runtime flags

```bash
KANDEV_HOME_DIR=<KANDEV_HOME_DIR>  # e.g. /srv/kandev or ~/srv/kandev  (service --home-dir)
# Docker image internal:
KANDEV_HOME_DIR=/data              # Docker (image default, mount-controlled)
KANDEV_DOCKER_ENABLED=true         # host Service (default true); Docker image defaults false — must be flipped to enable Local Docker
KANDEV_LOG_LEVEL=info
```

Record in `inventory.md`.

### 9.4 Database storage — choose, place, and back up correctly

> The DB choice is a Day-1 layout decision because the **backup sibling rule** and the `master.key` coupling follow it everywhere.

| Driver | DB file / connection | `backups/` sibling | `master.key` | When to choose |
|--------|---------------------|---------------------|--------------|----------------|
| **SQLite — default, inside home** (recommended) | `<KANDEV_HOME_DIR>/data/kandev.db` (auto-created, WAL mode). Legacy check: `<KANDEV_HOME_DIR>/kandev.db` adopted once if `data/kandev.db` empty (G11). | `<KANDEV_HOME_DIR>/data/backups/` — holds `manual-*.db` (never pruned) + auto `kandev-*.db` pre-migration snapshots (retain-2). Kandev also uses `data/kandev.db-wal` / `-shm` transient sidecars. | `<KANDEV_HOME_DIR>/data/master.key` (AES-256, `0600`). SQLite backup **without** this key cannot decrypt stored secrets. | Single-host (desktop, service, single-replica container). Simplest, fastest, one `rm -rf` removal. **Use this unless you need external DB tooling.** |
| **SQLite — custom path outside home** | `KANDEV_DATABASE_PATH=/srv/kandev-data/kandev.db` (or `database.path` in `config.yaml`). Absolute or `~/`-expanded. | `<custom-dir>/backups/` — sibling of the custom DB file. System UI pages use *configured path sibling*, not `<home>/data/backups`. Kandev does NOT move old snapshots automatically. | Still `<KANDEV_HOME_DIR>/data/master.key` — **not** beside the custom DB. Keep them together for restores. | Dedicated DB subvolume/mount (e.g. SSD vs HDD, separate quotas, host tmpfs). Requires `install -d` + `chown` on the custom dir and recording both paths for removal. |
| **PostgreSQL — external** | `KANDEV_DATABASE_DRIVER=postgres` + `KANDEV_DATABASE_HOST/PORT/USER/PASSWORD/DBNAME/SSLMODE` (see `templates/env.example` / `docker-compose.postgres.yml`). Kandev does NOT `VACUUM INTO`; provision the DB and network/TLS before first start. | **None built-in** — Kandev's System backup/restore is SQLite-only. Use `pg_dump` / provider PITR (see `scripts/backup.sh --postgres`). | Still `<KANDEV_HOME_DIR>/data/master.key` for app secrets; DB rows remain encrypted by it. | Operator needs external DB HA/backups/replication **for the DB layer itself**. Note: `/data` is still required for worktrees/repos/`agent-sessions`; Postgres does not make Kandev horizontally scalable (1 replica only, task workspaces remain filesystem-local). |

Common settings (all modes):

```yaml
# config.yaml
database:
  driver: "sqlite"            # or "postgres"
  path: ""                    # empty → <home>/data/kandev.db ; or "/srv/kandev-data/kandev.db"
  host: "localhost"           # postgres only
  port: 5432                  # postgres only
  user: "kandev"              # postgres only
  password: ""                # postgres — prefer env KANDEV_DATABASE_PASSWORD + secret file
  dbName: "kandev"            # postgres only
  sslMode: "disable"          # postgres: disable | require | verify-ca | verify-full
```

```bash
# env equivalents (later wins over file):
KANDEV_DATABASE_DRIVER=postgres
KANDEV_DATABASE_HOST=postgres
KANDEV_DATABASE_PORT=5432
KANDEV_DATABASE_USER=kandev
KANDEV_DATABASE_PASSWORD="${KANDEV_DB_PASSWORD:?set KANDEV_DB_PASSWORD}"
KANDEV_DATABASE_DBNAME=kandev
KANDEV_DATABASE_SSLMODE=disable
KANDEV_DATABASE_PATH=/srv/kandev-data/kandev.db   # SQLite custom-path alias
```

- [ ] Record P1/P2 choice in `plan.md` §1.1 (Home & DB layout) — the migration and uninstall steps read it.
- [ ] For SQLite inside home: ensure `<KANDEV_HOME_DIR>/data` is on persistent storage (named volume or bind mount). Verify `sqlite3 <home>/data/kandev.db "PRAGMA journal_mode;"` → `wal`.
- [ ] For SQLite custom path: **WRITE** — `install -d -o <USER> -g <GROUP> -m 0700 <CUSTOM_DIR> <CUSTOM_DIR>/backups` (host or container volume), set `KANDEV_DATABASE_PATH` in the unit drop-in or compose env, restart, `curl /ready`, and `ls -l <CUSTOM_DIR>/kandev.db* <HOME>/data/master.key`.
- [ ] For Postgres: **WRITE** — create the K8s Secret or `secrets/db-password` (`0600`, `valueFrom.secretKeyRef` in compose), create the DB/role (`CREATE USER kandev; CREATE DATABASE kandev OWNER kandev;`), set the 7 `KANDEV_DATABASE_*` vars, and note that `data/backups` is now irrelevant (see §16.3 for `pg_dump` commands). Never commit the password in `config.yaml`.

---

## 10. Authentication provisioning (when auth ON — §9.1)

> With auth ON, the instance boots into **setup mode** — the setup wizard appears and the **first visitor creates the admin**. All existing (pre-auth) workspaces are assigned to that admin. Complete the wizard immediately after deploying — especially when `KANDEV_FEATURES_AUTH=true` was set via env (anyone who reaches the origin first could claim admin).

- [ ] Restart Kandev after enabling auth (UI toggle prompts it; env requires `kandev service restart --home-dir <KANDEV_HOME_DIR>` / `docker compose restart kandev`).
- [ ] `ssh <ALIAS> 'curl -s http://127.0.0.1:<PORT>/api/v1/features | jq .'` — expect `auth` feature enabled.
- [ ] **WRITE** — Open `https://<DOMAIN>` (or `http://127.0.0.1:<PORT>` via `ssh -L` if proxy not yet up), complete the setup wizard → create the first admin (`<ADMIN_EMAIL>` / password). Store the admin identity in `inventory.md` (never the password — treat as secret).
- [ ] In `Settings → System → Users` (admin only) — mint an invite link or direct-create additional users as needed. Invite links are tokenized (`/invite?token=…`), single-use, ~7-day expiry; share out of band.
- [ ] In `Settings → Account → API Tokens` — create at least one PAT (`kandev_pat_…`) for MCP/scripts. **Shown once at creation** — save to `secrets/kandev-pat-<user>.txt` (`0600`) in the execution folder. Test:
  ```bash
  curl -H "Authorization: Bearer <PAT>" https://<DOMAIN>/api/v1/workspaces
  curl "https://<DOMAIN>/api/v1/workspaces?token=<PAT>"   # WS fallback form
  ```
- [ ] Verify isolation: a `member` sees only their own workspaces; `admin` does not see others' workspaces (G4). Filesystem/agent creds are still OS-user-scoped — note this limitation for the operator.

---

## 11. Reverse proxy + DNS + TLS

> The backend serves **everything** (SPA, `/api`, `/ws`, `/mcp`, `/health`, `/ready`) on one origin. Proxy the **entire root path** and preserve WebSocket upgrades. A subpath like `/kandev/` is not supported — use a dedicated host (`kandev.<DOMAIN>`).

### 11.1 Caddy (recommended — auto-TLS, simplest)

- [ ] **WRITE** — `templates/Caddyfile` → `/etc/caddy/Caddyfile` (host) or compose sidecar volume. Replace `<DOMAIN>` + `<KANDEV_UPSTREAM>` (`kandev:38429` in compose, `127.0.0.1:38429` for Service). Prefer an **isolated Caddyfile snippet** (`/srv/kandev/Caddyfile.kandev`) `import`ed from the main `Caddyfile` so removal is deleting the snippet:
  ```
  # /srv/kandev/Caddyfile.kandev (isolated snippet)
  kandev.<DOMAIN> {
      reverse_proxy kandev:38429
  }
  # Service mode (host Caddy):
  # kandev.<DOMAIN> { reverse_proxy 127.0.0.1:<PORT> }
  ```
  Main `Caddyfile`: `import /srv/kandev/Caddyfile.kandev` (or `import /srv/kandev/*.Caddyfile`). Rollback: comment the `import` line + `systemctl reload caddy` / `docker compose restart caddy`; snippet stays for restore or is `rm`'d on purge.
- [ ] `ssh <ALIAS> 'caddy fmt --overwrite /etc/caddy/Caddyfile && caddy reload --config /etc/caddy/Caddyfile'` (or `docker compose up -d caddy`).

### 11.2 Nginx (alternative)

- [ ] **WRITE** — `templates/nginx-kandev.conf` → `/etc/nginx/sites-available/kandev.conf` → `ln -s … sites-enabled/` **or** as `/srv/kandev/nginx-kandev.conf` + `include /srv/kandev/nginx-kandev.conf;` from `nginx.conf` (isolated so removal = deleting one file). Replace `<DOMAIN>`, `<PORT>`, TLS cert paths. Must include:
  ```nginx
  location / {
      proxy_pass http://127.0.0.1:<PORT>;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto $scheme;
      proxy_read_timeout 86400;
  }
  ```
- [ ] Issue cert (if not already): `certbot --nginx -d <DOMAIN>` (HTTP-01) or `certbot --dns-cloudflare -d <DOMAIN> -d *.kandev.<DOMAIN>` (DNS-01, needs Cloudflare token). Or reuse the host's Dokploy/Traefik ACME cert store.
- [ ] `ssh <ALIAS> 'nginx -t && systemctl reload nginx'`

### 11.3 Dokploy / Traefik (if the host is Dokploy-managed)

- [ ] In Dokploy, add domain `<DOMAIN>` to the Kandev app; enable Let's Encrypt.
- [ ] Ensure Traefik forwards `X-Forwarded-Host`/`X-Forwarded-Proto` and preserves `Upgrade` headers (Dokploy does this by default for compose apps; verify `traefik.http.routers.*.middlewares` not stripping WS).
- [ ] If Cloudflare is orange-cloud fronting, set `KANDEV_TRUSTED_PROXIES` to the **Dokploy host's** IP seen by Kandev (peer), not Cloudflare's edge IP.
- [ ] For isolated removal: add labels via the compose `labels:` snippet in `templates/docker-compose.yml` rather than Dokploy UI-only state, so the proxy wiring is versioned with `<COMPOSE_DIR>/docker-compose.yml`.

### 11.4 `trustedProxies` + DNS cutover check

- [ ] Set `KANDEV_TRUSTED_PROXIES=<PROXY_PEER_IP>` (or narrow CIDR) — §9.2. Restart Kandev (drop-in or `@service --home-dir` + `service restart`).
- [ ] Tail logs for the gate warning: `ssh <ALIAS> 'journalctl --user-unit kandev --no-pager | grep -i "X-Forwarded-Host from untrusted"'` or `docker logs kandev | grep -i "X-Forwarded-Host"` — if it appears, the peer list is wrong; fix and restart.
- [ ] DNS: `dig <DOMAIN> +short` → proxy/origin IP; `curl -vk https://<DOMAIN>/health` should return `200` via TLS.
- [ ] WS gate: `curl -I https://<DOMAIN>/ws` should **not** return `403` (403 = Host/Origin gate rejected the `X-Forwarded-Host`/Origin rewrite — see `notes/gotchas.md` G9).

---

## 12. Executors — defaults: Local Docker + SSH (F2/F3)

> Executors determine *where* a task environment runs. Profiles live in `Settings → Executors`. Agent/model choices are reviewed before each task — the executor profile is reusable. If the operator opted out of either, park that section.

### 12.1 Local Docker (when F2 = yes)

**Pre-check — which control plane are we on?**

- **Service on Docker host (reliable):** `KANDEV_DOCKER_ENABLED=true` (default), `docker.host` reachable (`unix:///var/run/docker.sock` on Unix), daemon can build/pull images. This is the correct topology for Docker tasks.
- **Dockerized control plane (limited):** `KANDEV_DOCKER_ENABLED=false` by image default — flipping it to `true` and mounting `/var/run/docker.sock` is **not by itself sufficient**. The daemon will be asked to bind-mount the `agentctl` helper at `/app/.../agentctl` and per-execution dirs under `/data/agent-sessions`, plus the local clone source — those paths must exist at **identical absolute host paths** on the daemon host. No compose manifest for this full mirroring is shipped; test every path, or **prefer SSH / Sprites** for task execution when the control plane is containerized (G7).

- [ ] On the host: `ssh <ALIAS> 'docker info | head -20'` — daemon reachable.
- [ ] In Kandev UI: `Settings → Executors → Docker → Create New Profile` — `image_tag` (e.g. `kandev/multi-agent:latest` or `X.Y.Z`), Dockerfile content (`Use defaults` = `node:22-slim` + `git`/`ca-certificates`/`curl` + `WORKDIR /workspace`), **Build Image** must succeed before the profile is created. Treat Dockerfile instructions as **daemon-root** (admin operation).
- [ ] **WRITE** — Create the Docker profile (`image_tag` pinned). Rollback: delete the profile in Settings; `docker rmi <tag>` if the image was built locally.
- [ ] Prepare script note (doc § Executors): Docker profile `prepare` runs **inside the container before `agentctl`** (common 10-min limit `KANDEV_TASK_PREPARATION_TIMEOUT`); `cleanup` is not executed by the Docker runtime.
- [ ] Verify: create a throwaway task with Docker executor + a trivial prompt, confirm the agent container appears: `ssh <ALIAS> 'docker ps --filter label=kandev.managed=true'` and the task transcript reaches `agent_message`.

### 12.2 SSH (when F3 = yes, repeat per `<ALIAS_SSH_*>`)

- [ ] Target pre-flight (over SSH):
  ```bash
  ssh <ALIAS_SSH_1> 'uname -a; bash --version | head -1; zsh --version 2>&1 | head -1'
  ssh <ALIAS_SSH_1> 'command -v <AGENT_CMD>; echo $?'
  ssh <ALIAS_SSH_1> 'grep -E "AllowTcpForwarding|MaxSessions" /etc/ssh/sshd_config; sudo sshd -T | grep -E "allowtcpforwarding|maxsessions"'
  ```
  Needs: Linux `amd64`/`arm64` or macOS `amd64`/`arm64`, pubkey auth + SFTP, `bash` (Linux) or `zsh` (macOS) (or configured `ssh_shell`), `AllowTcpForwarding yes`, enough `MaxSessions`, agent binary visible to a login shell, writable `~/.kandev`.

- [ ] In Kandev UI: `Settings → Executors → SSH → Create New Profile` — enter `<ALIAS_SSH_*>` host (or SSH alias from `~/.ssh/config`), port, user, identity (ssh-agent vs key file). OpenSSH `HostName`/`Port`/`User`/`IdentityAgent`/`IdentityFile`/`ProxyJump` inheritance is honored (explicit form wins; `IdentitiesOnly` not consumed).
- [ ] Run **Test Connection**; verify the observed **SHA256 host fingerprint** independently (compare to `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on the target, or prior `ssh -o VisualHostKey=yes <alias>`); select **Trust this host** (pins the target key). For `ProxyJump` bastions, pre-populate `~/.ssh/known_hosts` — unknown bastion keys are accepted on first use otherwise.
- [ ] **WRITE** — Save the SSH profile. Rollback: delete the profile; remove `~/.kandev` entries on the target only after confirming no session needs `tasks/` (no background sweeper).
- [ ] Verify: create a throwaway task on this SSH profile, confirm the remote `agentctl` helper appears at `~/.kandev/bin/agentctl` (`agentctl.sha256` sibling) and the task reaches the agent.

### 12.3 Sprites.dev (optional)

- [ ] Only if operator asked — save provider token as a Kandev secret, create `Settings → Executors → Sprites.dev` profile with `SPRITES_API_TOKEN` mapped to that secret. Note: network policy is applied late (after credential upload/prepare/controller start) — not a security boundary.

### 12.4 Workspace sources + env secrets

- [ ] In `Settings → Executors` ensure `KANDEV_GITHUB_CREDENTIAL_BROKER_PUBLIC_BASE_URL` (or `KANDEV_GITHUB_CREDENTIAL_BROKER_PUBLIC_BASE_URL`) is `https://<DOMAIN>` when SSH/Sprites/Docker need brokered GitHub creds over HTTPS (loopback HTTP allowed only for dev).
- [ ] Workspace repos: `Settings → Workspaces → <ws> → Repositories` — map **Environment secrets** (Global or same-workspace secrets) to POSIX keys for tasks. Kandev fails the launch if a binding is missing/ambiguous.

---

## 13. MCP access — defaults ON (F1)

> MCP lets the operator's AI assistant manage Kandev. Two surfaces: **task MCP** (auto-injected into agent sessions, no setup) and **external MCP** (third-party clients hitting the backend — this section).

### 13.1 External MCP via reverse proxy

- [ ] Confirm the proxy forwards the **entire origin root** (not a subpath) and preserves WS upgrades — MCP shares port `38429` with the SPA/API (`/mcp`, `/ws`, `/health`, `/ready` all one origin). Caddy snippet in §11.1 already does this; for Nginx see §11.2 `Upgrade`/`Connection` headers.
- [ ] If auth OFF: `curl https://<DOMAIN>/mcp` should be reachable (protected only by network — tailnet/firewall/proxy ACL).
- [ ] If auth ON: every `/mcp` call needs a PAT:

  ```bash
  # Create in Settings → Account → API Tokens (shown once, kandev_pat_…):
  curl -H "Authorization: Bearer kandev_pat_..." https://<DOMAIN>/mcp \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
  ```

  Without a header the backend returns `401` (except `/health`, `/ready`, login/invite, `GET /api/v1/features`, webhook receivers, and plugin-declared public webhooks).

### 13.2 Client configuration

- [ ] **Claude Code / Cursor / OpenCode** — add to the client's MCP config (examples, replace `<DOMAIN>` + `<PAT>`):

  ```json
  {
    "mcpServers": {
      "kandev": {
        "type": "http",
        "url": "https://kandev.example.com/mcp",
        "headers": { "Authorization": "Bearer kandev_pat_..." }
      }
    }
  }
  ```

  For clients that cannot send headers over WebSocket, append `?token=<PAT>` to the WS URL. SSE transport also supported (`/mcp` serves both).

- [ ] Verify from the client: list tools (`tools/list`) should include `create_task_kandev`, `list_tasks_kandev`, `message_task_kandev`, etc. (full catalog in `https://kandev.ai/docs/automation-and-mcp`). `external` profile includes task creation/update/coordination; profile/config surfaces vary by task mode.

### 13.3 MCP policy on the executor profile (optional hardening)

- [ ] In each executor profile, the **MCP policy JSON** (`{}` checked as object) can restrict which MCP servers a spawned agent may load (stdio/HTTP/SSE allowlists, URL rewrites). Test restrictive policies with the real servers the agent needs.

---

## 14. Security invariants (verify every time)

1. **Listener never `0.0.0.0` unauthenticated.** If `KANDEV_FEATURES_AUTH` is OFF and the host is not loopback-only, the bind must be `127.0.0.1` + loopback-only publish (`127.0.0.1:38429:38429`) + proxy/TLS/VPN in front. Public `0.0.0.0:38429` without auth is an incident.
2. **TLS everywhere public.** `https://<DOMAIN>` cert is valid; `curl -vk https://<DOMAIN>/health` returns `200` over TLS; session cookie is `Secure` when `X-Forwarded-Proto: https` reaches Kandev (set `KANDEV_TRUSTED_PROXIES`).
3. **`KANDEV_TRUSTED_PROXIES` set correctly** to the proxy peer IP/CIDR (never the client network), otherwise `X-Forwarded-For` is spoofable and rate-limiter can be bypassed. Warning `ignoring X-Forwarded-Host from untrusted peer` must be absent after restart.
4. **No secrets in git.** `*.pem`/`*.key`/`*.tfvars`/`.env`/`executions/` are gitignored. A tracked secret is an incident → unstage, move to `executions/kandev/secrets/`, rotate the credential. Check before every commit:
   ```powershell
   git status
   git ls-files --cached --others --exclude-standard | ForEach-Object { if (Test-Path $_) {
     $c = Get-Content $_ -Raw
     if ($c -match 'kandev_pat_|KANDEV_|BEGIN (CERTIFICATE|PRIVATE|RSA)|tskey-') { Write-Output "LEAK: $_" }
   }}
   ```
5. **`secrets/` is `0600`** where it bears tokens/passwords/`master.key`; `~/.kandev/logs/backend-logs.log` and segments are `0600`. Home permissions checked at startup (warning if group/other readable).
6. **Pinned tags/digests.** Compose uses `ghcr.io/kdlbs/kandev:X.Y.Z` (real version, not `latest` moving tag) or a digest; `universal-weekly-YYYYMMDD` dated tags for universal flavor. Upgrades tested on a snapshot first.
7. **Docker daemon host awareness.** Never assume socket mount = working Docker executor (G7).
8. **Single-owner SQLite.** One `<KANDEV_HOME_DIR>` / one `KANDEV_DATABASE_PATH` is owned by exactly one Kandev process. Never start two backends against the same SQLite file (separate homes alone don't help when `KANDEV_DATABASE_PATH` points outside home at the same file).
9. **Master key accompanies DB backups.** A DB snapshot without `<home>/data/master.key` cannot decrypt stored secrets — back them up together and with `0600`.

---

## 15. Verification (both branches — do not skip)

```bash
# Health vs readiness (ready = can serve real traffic):
curl --fail http://127.0.0.1:<PORT>/health        # 200 as soon as listener is up
curl --fail http://127.0.0.1:<PORT>/ready         # 200 only after routes + agent registry
curl -vk https://<DOMAIN>/health                 # via proxy+TLS
curl -vk https://<DOMAIN>/ready

# DNS + TLS:
echo | openssl s_client -connect <DOMAIN>:443 -servername <DOMAIN> 2>/dev/null | openssl x509 -noout -dates -subject
curl -vk https://<DOMAIN>/api/v1/features | jq .  # shows auth flag + features

# Home & DB layout (wiring proves removal map is correct):
ssh <ALIAS> 'ls -lh <KANDEV_HOME_DIR>/data/kandev.db* <KANDEV_HOME_DIR>/data/master.key 2>&1 | head -20'
ssh <ALIAS> 'ls -lh <KANDEV_HOME_DIR>/data/backups/ 2>&1 | head -20'
ssh <ALIAS> 'ls -lh <KANDEV_HOME_DIR>/logs/backend-logs.log 2>&1 | head'
ssh <ALIAS> 'kandev service config --home-dir <KANDEV_HOME_DIR> 2>&1 | cat'  # service mode — prints home + unit path
ssh <ALIAS> 'cat <KANDEV_HOME_DIR>/service/install.json 2>&1 | jq . 2>&1 | head -20'  # service mode

# Auth (when ON):
curl -H "Authorization: Bearer <PAT>" https://<DOMAIN>/api/v1/workspaces | jq .
# expect 401 without a token

# MCP (when ON):
curl -H "Authorization: Bearer <PAT>" -H "Content-Type: application/json" \
  https://<DOMAIN>/mcp -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'

# Executors:
# Docker: Settings → Executors → Docker profile shows a successful build; throwaway task reaches agent_message
ssh <ALIAS> 'docker ps --filter label=kandev.managed=true --format "table {{.Names}}\t{{.Status}}"'
# SSH: throwaway task on each SSH profile completes agent turn; remote helper exists:
ssh <ALIAS_SSH_1> 'ls -l ~/.kandev/bin/agentctl ~/.kandev/bin/agentctl.sha256 2>&1 | head'
```

- [ ] All probes pass. **If any fail, do NOT proceed to close-out** — fix + re-verify.
- [ ] Create + delete a throwaway task on each enabled executor (Docker, SSH). Confirm the workspace `Files` panel shows the repo/worktree and the transcript shows agent output.
- [ ] From the MCP client (Claude/Cursor/OpenCode), run `list_workspaces` / `create_task_kandev` against `https://<DOMAIN>/mcp` — confirm the task appears in the Kandev UI.
- [ ] Record the **verified removal map** in `logs/` + `inventory.md`: which single `rm -rf` (plus which named volumes) restores the host to pre-Kandev.

---

## 16. Operate, backup, upgrade, migration, uninstall

### 16.1 Logs & probes

```bash
# Service — isolated home (preferred):
kandev service status --home-dir <KANDEV_HOME_DIR>
kandev service logs -f --home-dir <KANDEV_HOME_DIR>
kandev service config --home-dir <KANDEV_HOME_DIR>
systemctl --user status kandev.service; journalctl --user-unit kandev.service -n 200 --no-pager
sudo systemctl status kandev.service; sudo journalctl -u kandev.service -n 200 --no-pager  # system
# Also:
systemctl --user cat kandev.service  # or: sudo systemctl cat kandev.service
namei -l <KANDEV_HOME_DIR> | head -20

# Service — default home (only if scattering accepted):
kandev service status; kandev service logs -f

# Docker
docker ps; docker logs kandev --tail 200
docker compose -f <COMPOSE_DIR>/docker-compose.yml logs -f kandev
docker volume ls | grep kandev

# Kandev file logs (both modes — the 256 MiB ring, 3-day max):
ls -lh <KANDEV_HOME_DIR>/logs/backend-logs*.log
ls -lh /srv/kandev/logs/backend-logs*.log  # if --home-dir /srv/kandev
# Probes — use /ready for Compose healthcheck/depends_on: service_healthy (not /health)
```

### 16.2 SQLite backup & restore (driver = sqlite)

```bash
# ── Create a snapshot ───────────────────────────────────────────────
# Preferred — UI (creates manual-*.db in <db-parent>/backups/):
# Settings → System → Backups → Create snapshot → Download + copy off-host
# + separately copy <KANDEV_HOME_DIR>/data/master.key (0600) — needed to decrypt secrets.

# CLI / file backup (same VACUUM INTO as the UI; safe offline; online with care):
ssh <ALIAS> 'sqlite3 <KANDEV_HOME_DIR>/data/kandev.db ".backup <KANDEV_HOME_DIR>/data/backups/manual-$(date -u +%Y%m%dT%H%M%SZ).db"'
# Custom path:
ssh <ALIAS> 'sqlite3 <CUSTOM_DB_PATH> ".backup <CUSTOM_DIR>/backups/manual-$(date -u +%Y%m%dT%H%M%SZ).db"'
# Or via helper script (stops service for a cold copy — see scripts/backup.sh):
ssh <ALIAS> 'KDB=<CUSTOM_DB_PATH:-<KANDEV_HOME_DIR>/data/kandev.db> bash <REPO>/playbooks/kandev/scripts/backup.sh --home <KANDEV_HOME_DIR> --dest <DB_PARENT>/backups/'
# Cold home archive (user service — custom --home-dir adapted below):
ssh <ALIAS> 'kandev service stop --home-dir <KANDEV_HOME_DIR> && tar -C "$(dirname <KANDEV_HOME_DIR>)" -czf "$HOME/kandev-state-$(date -u +%Y%m%dT%H%M%SZ).tar.gz" "$(basename <KANDEV_HOME_DIR>)" && kandev service start --home-dir <KANDEV_HOME_DIR>'

# ── Restore a System snapshot (SQLite-only UI flow) ─────────────────
# 1) Stop/finish active agent sessions, preserve unpushed Git work.
# 2) Settings → System → Backups → Restore → type RESTORE → confirm.
#    Kandev stops scheduling, stages <configured-path>.new, validates checkpoint,
#    closes pool, quarantines <configured-path> + -wal/-shm, installs staged file.
# 3) Click "Restart Kandev" (or quit/relaunch manually: kandev service restart --home-dir <KANDEV_HOME_DIR>).
# 4) Verify /ready, System → Status, DB schema, secrets, tasks, worktrees.

# ── Restore outside the UI (SQLite file path) ───────────────────────
# scripts/restore.sh <snapshot> --home <KANDEV_HOME_DIR> [--db-path <CUSTOM_DB_PATH>]
# See scripts/restore.sh for quarantine/rollback handling.

# ── What snapshots do NOT contain ──────────────────────────────────
# Snapshots do NOT contain: Git worktrees/clones in <home>/tasks, <home>/repos,
# <home>/sessions, agent CLI logins outside <home> (e.g. ~/.codex, ~/.config/gh
# — but in Docker HOME=/data/home lives ON volume), provider-side objects,
# service metadata. Back those up separately if required.
```

Postgres deployments: use `pg_dump` + tested restore (next section) — Kandev's built-in SQLite backup/restore does not cover Postgres.

### 16.3 PostgreSQL backup & restore (driver = postgres)

```bash
# ── Create a verified dump ──────────────────────────────────────────
# Standard pg_dump (configure PGHOST/PGPORT/PGUSER/PGDATABASE + .pgpass):
pg_dump --host "$PGHOST" --port "${PGPORT:-5432}" \
  --username "${PGUSER:-kandev}" --format=custom \
  --file "kandev-$(date -u +%Y%m%dT%H%M%SZ).dump" \
  "${PGDATABASE:-kandev}"
# Verify:
pg_restore --list "kandev-*.dump" | head -20

# Via compose (from <ALIAS>):
ssh <ALIAS> 'docker compose -f <COMPOSE_DIR>/docker-compose.yml exec postgres pg_dump -U kandev -Fc kandev > /tmp/kandev-$(date -u +%Y%m%dT%H%M%SZ).dump'
# + still copy <KANDEV_HOME_DIR>/data/master.key + <KANDEV_HOME_DIR>/data/backups is now irrelevant

# ── Restore (destructive — stop all Kandev backends first) ──────────
# Stop every Kandev backend using this DB, then:
pg_restore --clean --if-exists --no-owner \
  --host "$PGHOST" --port "${PGPORT:-5432}" \
  --username "${PGUSER:-kandev}" --dbname "${PGDATABASE:-kandev}" \
  kandev-YYYYMMDDTHHMMSSZ.dump
# Restart ONE backend, wait for schema init (curl /ready), verify single-replica first.

# ── Recall ──────────────────────────────────────────────────────────
# Postgres moves DB rows off-volume but /data (worktrees/repos/master.key) stays
# on <KANDEV_HOME_DIR>/data. Backup both together (DB dump + home archive) for a
# restorable system. Kandev has no automatic downgrade; a restored DB must be
# paired with a compatible Kandev binary.
```

### 16.4 Database migrations — when the operator wants to change storage

> P1/P2 choice is reversible, but **has a careful order**. Never flip `driver`/`database.path`/`KANDEV_DATABASE_PATH` without a verified snapshot, a maintenance window, and a tested restore. Kandev never migrates rows between drivers — it just opens whichever file/DB the current config points at.

#### Preconditions for every migration

- [ ] **Stop or finish active sessions** and preserve unpushed Git work (worktrees live on filesystem, not in DB).
- [ ] **Take a verified backup** of BOTH the source and (if it exists) the target DB — see §16.2 (SQLite) / §16.3 (Postgres). For Postgres, `pg_dump --format=custom`; for SQLite, `sqlite3 … ".backup …"` + copy of `master.key` (`0600`).
- [ ] **Stop all Kandev backends** touching either DB (systemd: `kandev service stop --home-dir <KANDEV_HOME_DIR>`; Docker: `docker compose stop kandev`). One writer owns a SQLite file.
- [ ] Record both paths in `plan.md` so the migration is auditable.

#### A. Move SQLite file inside vs outside the home (no driver change)

This keeps `driver: sqlite`, only changes where the file lives.

```bash
# Example: default → custom directory (e.g. new SSD/subvolume):
# 1) Stop:
kandev service stop --home-dir <KANDEV_HOME_DIR>   # or: docker compose stop kandev

# 2) Copy (cold, with WAL checkpoint — use .backup, NOT cp while writers may run):
sqlite3 <KANDEV_HOME_DIR>/data/kandev.db ".backup /srv/kandev-data/kandev.db"
# also copy sidecars if they exist:
ls -l <KANDEV_HOME_DIR>/data/kandev.db*  # expect -wal/-shm (may be absent after checkpoint)
# Preserve master.key alongside the DB for future restores:
cp -a <KANDEV_HOME_DIR>/data/master.key /srv/kandev-data/master.key.backup  # reference copy, real stays in <home>/data/master.key

# 3) Point config at the new file:
# env / drop-in:
echo 'Environment=KANDEV_DATABASE_PATH=/srv/kandev-data/kandev.db' | systemctl --user edit kandev.service --stdin  # user service
# or compose env:
# KANDEV_DATABASE_PATH: /data/db-custom/kandev.db  + volume - /srv/kandev-data:/data/db-custom

# 4) Restart + verify (G11):
kandev service start --home-dir <KANDEV_HOME_DIR>   # or: docker compose up -d kandev
curl --fail http://127.0.0.1:<PORT>/ready
sqlite3 /srv/kandev-data/kandev.db "SELECT count(*) FROM tasks; SELECT count(*) FROM kandev_meta;"  # sanity

# 5) Only after verification, optionally remove the old file (or keep as rollback):
# mv <KANDEV_HOME_DIR>/data/kandev.db{,.migrated-$(date +%F)} ; mv <KANDEV_HOME_DIR>/data/kandev.db-wal{,.migrated-$(date +%F)} 2>/dev/null; true

# Reverse (custom → default): same steps in reverse; set KANDEV_DATABASE_PATH="" (or delete key) and restart.
```

**Inventory update:** change `Database path:` and `Backups dir:` to the new sibling `backups/` (e.g. `/srv/kandev-data/backups/`); note that snapshots will now appear there, old ones in `<home>/data/backups/` are NOT auto-moved.

#### B. SQLite → PostgreSQL (adopt an external DB)

```bash
# 1) Provision Postgres (host, role, DB):
# On the DB host:
createuser -h <PGHOST> -U <PG_SUPERUSER> kandev
createdb -h <PGHOST> -U <PG_SUPERUSER> -O kandev kandev
# Enforce password + sslMode per your policy.

# 2) Verified source snapshot (do NOT skip even if source is small):
sqlite3 <KANDEV_HOME_DIR>/data/kandev.db ".backup <KANDEV_HOME_DIR>/data/backups/pre-pg-migration-$(date -u +%Y%m%dT%H%M%SZ).db"
cp <KANDEV_HOME_DIR>/data/master.key <KANDEV_HOME_DIR>/data/backups/master.key.pre-pg  # keep together, 0600

# 3) Convert rows → Postgres.
# Kandev has NO built-in SQLite→Postgres row migrator — flipping driver alone
# boots an EMPTY Postgres DB (previous tasks/history will be absent).
# Pick ONE transfer method (plan must state which operator approved):

# Option B1 — pgloader (most faithful for Kandev's SQLite):
pgloader sqlite:///<KANDEV_HOME_DIR>/data/kandev.db pgsql://kandev:<PGPASS>@<PGHOST>:5432/kandev
# Verify: psql -h <PGHOST> -U kandev -c "select count(*) from tasks;" ; compare to sqlite3 source count

# Option B2 — whitespace export/import (when pgloader unavailable — less faithful for blobs):
sqlite3 <KANDEV_HOME_DIR>/data/kandev.db .dump | psql -h <PGHOST> -U kandev kandev
# (Verify carefully; WAL/committed frames must be flushed — .backup already did.)

# Option B3 — clean slate (acceptable if operator wants a fresh DB):
# Extract only what must survive (e.g. recreate workspaces); document as such.
# Flipping driver without row copy is exactly this path.

# 4) Stop Kandev, flip driver, restart:
kandev service stop --home-dir <KANDEV_HOME_DIR>   # or docker compose stop kandev
# In <KANDEV_HOME_DIR>/config.yaml or env/drop-in/compose:
#   database.driver: postgres
#   database.host/port/user/dbName/sslMode (+ password via KANDEV_DATABASE_PASSWORD)
# or compose env:
#   KANDEV_DATABASE_DRIVER: postgres
#   KANDEV_DATABASE_HOST: postgres
#   KANDEV_DATABASE_PASSWORD: "${KANDEV_DB_PASSWORD:?set KANDEV_DB_PASSWORD}"
kandev service start --home-dir <KANDEV_HOME_DIR>   # or docker compose up -d kandev
curl --fail http://127.0.0.1:<PORT>/ready
curl -s https://<DOMAIN>/api/v1/system/health | jq .  # diagnostic, not readiness

# 5) Verify tasks, secrets (master.key still at <home>/data/master.key), files,
#    and that /data (worktrees/repos) still mounts. Postgres rows are now authoritative;
#    SQLite file at <home>/data/kandev.db is inert — archive it but do NOT auto-delete.

# 6) Switch backup policy to pg_dump (§16.3); Settings → System → Backups page will now show
#    "SQLite-only" and is NOT the Postgres path.
```

**Inventory update:** `driver: postgres`, connection tuple, `Backups dir: N/A (pg_dump at <dump-path>)`, removal now needs `kandev-data` volume + `pg_dump` store.

#### C. PostgreSQL → SQLite (return to embedded)

```bash
# 1) Verified source dump:
pg_dump --host "$PGHOST" --port "${PGPORT:-5432}" --username "${PGUSER:-kandev}" --format=custom --file "/tmp/kandev-pre-sqlite-$(date -u +%Y%m%dT%H%M%SZ).dump" kandev

# 2) Stop Kandev:
kandev service stop --home-dir <KANDEV_HOME_DIR>

# 3) Empty SQLite file + restore rows there (reverse of B):
# Create an empty SQLite file the way Kandev will (it will init schema at startup):
KANDEV_DATABASE_DRIVER=sqlite KANDEV_DATABASE_PATH=<KANDEV_HOME_DIR>/data/kandev.db kandev --headless --help >/dev/null 2>&1; rm -f <KANDEV_HOME_DIR>/data/kandev.db
# Use pgloader reverse (or dump→sqlite conversion) — pgloader reverse is not always available,
# so the practical path is pg_dump → conversion. Kandev docs acknowledge driver switch does
# NOT migrate rows — plan must allocate time for this conversion and a verification query.
# Practical: use a tool (e.g. pg2sqlite, or `pg_dump --data-only --inserts` piped through adaptation)
# and compare row counts table-by-table before flipping.

# 4) Flip driver back to sqlite (remove KANDEV_DATABASE_* env or set driver: sqlite), restart:
kandev service start --home-dir <KANDEV_HOME_DIR>
curl --fail http://127.0.0.1:<PORT>/ready

# 5) Verify tasks/secrets/files; pg dump stays as rollback. Postgres DB remains reachable until operator explicitly drops it.
```

> All three migrations share one rule: **changing `driver`/`path` does not move `master.key`**. The key lives at `<KANDEV_HOME_DIR>/data/master.key` (owner-only). Moving the DB without the key makes encrypted secret values unreadable.

### 16.5 Upgrade & rollback

```bash
# Service (global npm, durable) — isolated home:
npm install --global kandev@latest
kandev service install --home-dir <KANDEV_HOME_DIR>     # preserves --system/--run-as when reinstalled
kandev service restart --home-dir <KANDEV_HOME_DIR>
kandev service status --home-dir <KANDEV_HOME_DIR>

# Service — system isolated:
sudo "$(command -v kandev)" service install --system --run-as <USER> --home-dir <KANDEV_HOME_DIR>
sudo "$(command -v kandev)" service restart --system --home-dir <KANDEV_HOME_DIR>

# Docker — pinned tag:
docker compose -f <COMPOSE_DIR>/docker-compose.yml pull kandev   # X.Y.Z pinned
docker compose -f <COMPOSE_DIR>/docker-compose.yml up -d kandev
docker compose -f <COMPOSE_DIR>/docker-compose.yml logs -f kandev
# (schema migrations run at startup; on SQLite a pre-migration snapshot is taken — keep your own backup too)

# Verify after every upgrade:
curl --fail http://127.0.0.1:<PORT>/ready; curl -vk https://<DOMAIN>/ready
```

Never mix versions against one DB (replicas: 1; redo `service install` after switching branches/checkouts). Before any schema-cutover release, read `https://kandev.ai/docs/operations` for the advisory-lock / single-replica requirement.

### 16.6 Uninstall — data retained until explicitly purged

> The playbook is designed so uninstall is reviewable **from `plan.md`** — operator sees exactly which paths disappear.

#### A. Service — isolated home (recommended)

```bash
# ── Disable & remove the unit/plist ────────────────────────────────
# User service:
kandev service uninstall --home-dir <KANDEV_HOME_DIR>
# Verify: systemctl --user cat kandev.service should now fail; ls ~/.config/systemd/user/kandev.service should be gone
systemctl --user daemon-reload  # Linux
# macOS: launchctl bootout gui/$(id -u)/com.kdlbs.kandev 2>/dev/null; true

# System service:
sudo "$(command -v kandev)" service uninstall --system --home-dir <KANDEV_HOME_DIR>
sudo systemctl daemon-reload  # Linux

# ── Data still on disk (by design) ─────────────────────────────────
ls -ld <KANDEV_HOME_DIR>                          # the isolated home
ls -lh <KANDEV_HOME_DIR>/data/kandev.db* 2>&1 | head
ls -lh <KANDEV_HOME_DIR>/data/backups/ 2>&1 | head
ls -ld <KANDEV_HOME_DIR>/logs 2>&1 | head
cat <KANDEV_HOME_DIR>/service/install.json 2>&1 | head -20  # install metadata
# If database path is custom OUTSIDE the home (§9.4 row 2):
ls -ld <CUSTOM_DB_DIR> 2>&1 | head
# Config outside home:
ls -l /etc/kandev/config.yaml 2>&1 | head
# Bundle (not auto-removed):
command -v kandev; npm root -g 2>&1 | head; brew --cellar kandev 2>&1 | head; ls -ld /opt/kandev 2>&1 | head
# Proxy snippet (if isolated):
ls -l /srv/kandev/Caddyfile.kandev /srv/kandev/nginx-kandev.conf 2>&1 | head

# ── Optional: lingering (if boot-without-login was enabled) ───────
sudo loginctl disable-linger <USER>   # only if you enabled it in §7.3 and want to revert

# ── Purge data (only after verified backup) ───────────────────────
# Stop first, verify snapshots off-host, then:
kandev service stop --home-dir <KANDEV_HOME_DIR> 2>/dev/null; true
# SQLite + home (co-located — one command):
rm -rf <KANDEV_HOME_DIR>
# If custom DB outside home (TWO paths):
rm -rf <KANDEV_HOME_DIR> <CUSTOM_DB_DIR>
# If shared config was used:
sudo rm -f /etc/kandev/config.yaml && sudo rmdir /etc/kandev 2>/dev/null; true
# Proxy snippet (if isolated):
sudo rm -f /srv/kandev/Caddyfile.kandev /srv/kandev/nginx-kandev.conf 2>&1 | head
# Bundle (choose the ONE that matches your install channel):
npm uninstall -g kandev          # npm
brew uninstall kandev            # Homebrew
sudo rm -rf /opt/kandev /usr/local/bin/kandev  # archive
# Verify host is clean:
ls -ld <KANDEV_HOME_DIR> 2>&1 | grep "No such"
docker volume ls 2>&1 | head   # if Docker was also present
```

#### B. Service — default home (scattered, only if operator accepted it)

```bash
# Same uninstall, but without --home-dir; then scattered cleanup:
kandev service uninstall               # or --system variant
rm -rf ~/.kandev                       # user
sudo rm -rf /var/lib/kandev            # system (if that was the home)
sudo rm -f /etc/kandev/config.yaml; sudo rmdir /etc/kandev 2>/dev/null; true
sudo rm -f ~/.config/systemd/user/kandev.service.bak /etc/systemd/system/kandev.service.bak 2>/dev/null; true
# + bundle + proxy snippet as above
```

#### C. Docker (isolated — one compose + one volume)

```bash
# Stop containers, keep volumes (data retained):
docker compose -f <COMPOSE_DIR>/docker-compose.yml down
docker volume inspect kandev-data 2>&1 | head -20

# Verify SQLite snapshots / master.key are inside the volume:
docker run --rm -v kandev-data:/data alpine ls -lh /data/data/kandev.db* /data/data/master.key /data/data/backups/ 2>&1 | head -20

# Purge (only after off-host snapshot):
docker volume rm kandev-data           # or: docker compose -f <COMPOSE_DIR>/docker-compose.yml down -v
# Bind-mount variant:
sudo rm -rf /srv/kandev                # host path that was /data
# Also remove any custom DB volume/path outside /data (§8.2):
docker volume rm kandev-db 2>&1 | head; sudo rm -rf /srv/kandev-db 2>&1 | head
# Compose dir itself:
rm -rf <COMPOSE_DIR>
# Proxy snippet (if isolated) + DB dump store remain until explicitly removed.
```

**Never delete without a verified restore:** download one `manual-*.db` (SQLite) or `*.dump` (Postgres) + `master.key` copy to `executions/kandev/secrets/off-host/` and test restoring into an isolated throwaway instance (see §16.2) before purging.

---

## 17. Common questions

- **Why not npx?** `npx` lives in npm's transient cache; a cache clean invalidates the recorded absolute path in the unit. Prefer `npm install -g kandev@latest` for any service; `npx` is a fragile fallback whose logs tell you to reinstall after upgrades.
- **Can I run on Windows without WSL?** `kandev service` is systemd/launchd only — Windows Service Control Manager is not supported. Run headless (`kandev --headless`) or via WSL/Docker.
- **Why does `curl 38429` fail after install?** The launcher picked a free random fallback (`10000–60000`) — check `kandev service logs --home-dir <KANDEV_HOME_DIR>` for the actual URL and hit `/ready` there (G2).
- **Does `auth.jwtSecret` add auth?** No — `KANDEV_FEATURES_AUTH=true` is the toggle; `auth.jwtSecret` is a compatibility field and does not make an unauthenticated server authenticated (G3).
- **Which DB for production?** SQLite (default, WAL) inside `<KANDEV_HOME_DIR>/data/kandev.db` is the simplest and is fine for all single-host deploys in this playbook. Choose SQLite with a custom `KANDEV_DATABASE_PATH` when you need a separate DB mount, or Postgres when you need external DB HA/replication for the **DB layer** (remember `/data` still required, and Kandev's `data/backups` UI is SQLite-only). Changing later is §16.4.
- **How do I expose work safely to the internet?** Terminate TLS in Caddy/Nginx/Traefik, set `server.host: 127.0.0.1`, put `KANDEV_FEATURES_AUTH=true`, set `KANDEV_TRUSTED_PROXIES` to the proxy peer, proxy the root `/` (not a subpath), and require PATs on `/mcp`. Never publish `38429` to `0.0.0.0` unauthenticated.
- **How do I cleanly remove a Service install?** `kandev service uninstall --home-dir <KANDEV_HOME_DIR>` (or `--system` variant) + `rm -rf <KANDEV_HOME_DIR>` (+ `<CUSTOM_DB_DIR>` if you split it, + `/etc/kandev/config.yaml` if you used a shared config, + bundle). §16.6 lists every path so the host can be returned to pre-Kandev.
- **If I split DB outside home, what must I back up together?** `<CUSTOM_DB_DIR>/kandev.db` (and its `-wal`/`-shm` at backup time) **plus** `<KANDEV_HOME_DIR>/data/master.key`. One without the other leaves secrets undecryptable.

---

## 18. Quick run checklist (branch on D1)

### 0. Pre-flight
- [ ] `notes/gotchas.md` read; Kandev docs fetched.
- [ ] `<ALIAS>` SSH alias works (`ssh <ALIAS> 'echo ok'`).
- [ ] Permission mode chosen (A vs B) and recorded in `plan.md`.

### 1. Discovery answers recorded (§4)
- [ ] D1 (Service vs Docker + isolated home vs default) — pros/cons shown, operator chose.
- [ ] D2 (Auth ON vs OFF, shielding if OFF) — pros/cons shown, operator chose.
- [ ] F1–F3 (MCP / Docker exec / SSH exec) — defaults assumed ON unless opted out.
- [ ] H1–H6 (incl. H6 isolated home question) answered and written to `inventory.md`.
- [ ] P1–P3 (SQLite vs Postgres, DB path, volume type) chosen; removal map drafted.

### 2. Prerequisites (§6)
- [ ] Execution folder created; `secrets/` + `logs/` exist.
- [ ] `inventory.md` §1.1 Home & DB layout filled; isolated directory pre-created `install -d -m 0700`.
- [ ] `<DOMAIN>` DNS created; `80/443` open to proxy.
- [ ] Port `38429` checked (or fallback/drop-in planned).

### 3. Install branch
- [ ] **A:** §7 — binary installed (not npx), `service install --home-dir <KANDEV_HOME_DIR>` (user `--system` as chosen), lingering if needed, `service config --home-dir` + `install.json` verified, `/ready` passes, layout matches `plan.md`.
- [ ] **B:** §8 — volume/dir prepared, compose pinned (`X.Y.Z`), `KDB` wiring matches P2, `docker compose up -d`, `/ready` passes, `ls /data/data/kandev.db /data/data/master.key` inside volume.

### 4. Configure (§9)
- [ ] `KANDEV_FEATURES_AUTH` set (or UI toggle planned); `server.host` = `127.0.0.1` behind proxy; `KANDEV_TRUSTED_PROXIES` = proxy peer; config file placed at `<KANDEV_HOME_DIR>/config.yaml` (or recorded shared path).

### 5. Auth (§10) — if ON
- [ ] Wizard → admin created immediately; invite/PAT minted; `curl -H "Authorization: Bearer <PAT>" …` passes; `401` without.

### 6. Proxy/TLS (§11)
- [ ] Caddy/Nginx/Traefik configured per template, `Upgrade`/`X-Forwarded-*` set; isolated snippet `import`/`include` used so removal is one file; cert valid; `https://<DOMAIN>/ready` + `/health` pass; no `403` on `/ws`; no `X-Forwarded-Host from untrusted peer`.

### 7. Executors (§12)
- [ ] Docker profile built (if F2); SSH profile pinned + Test Connection (if F3); throwaway task per executor succeeds.

### 8. MCP (§13)
- [ ] `https://<DOMAIN>/mcp` reachable; `initialize` via PAT succeeds; Claude/Cursor/OpenCode can list/create tasks.

### 9. Harden + verify (§14–15)
- [ ] All invariants pass (§14 incl. single-owner + master.key coupling); no secrets in git; tags pinned.
- [ ] Full probe matrix (§15 incl. home/DB layout checks) recorded in `logs/`; verified removal map written to `inventory.md`.

### 10. Record & close
- [ ] Update execution's `inventory.md` + `notes.md`; propose lesson promotion to playbook `notes/`.
- [ ] Verify off-host backup: one `manual-*.db` (or `*.dump`) + `master.key` copy saved to `executions/kandev/secrets/off-host/` and test-restored.

---

## Authoring rules

- Steps must be copy-paste executable with placeholders filled.
- Flag every step that WRITES to a production system with **WRITE** in bold
  (e.g. `- [ ] **WRITE** install package X on <host>`). Reads need no flag.
- Add rollback instructions for every write step.
- After each run, promote lessons into `notes/` (via the operator, never
  mid-run).
