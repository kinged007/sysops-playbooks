---
name: 9router
description: Install, configure, harden, upgrade, back up, and operate a 9Router instance (OpenAI-compatible AI gateway in front of 40+ providers). Use for a fresh 9Router install, upgrade, API-key and TLS hardening, provider and combo management, SQLite backup and restore, weekly model-inventory sync, and health checks. Not for creating provider accounts or non-9Router reverse-proxy work.
---

# 9Router Proxy Manager

> Read `references/gotchas.md` BEFORE any run (G1-G12 can change how you plan).
>
> Fetch the upstream 9Router skill BEFORE any management, verification, or API
> step (see `references/skill.md`):
> `https://raw.githubusercontent.com/decolua/9router/refs/heads/master/skills/9router/SKILL.md`
> It defines `NINEROUTER_URL` / `NINEROUTER_KEY`, the `/api/health` probe, and
> every `/v1/models/*` contract. For capability tests, fetch the capability
> skill listed inside it (chat, image, tts, stt, embeddings, web-search,
> web-fetch). Never improvise the API shape.

Risk level: medium. Installs or updates a service on a production host, writes
env and volume data, opens a port, and optionally changes reverse-proxy and
firewall rules. The database holds provider tokens: never log, commit, or echo
them.

9Router is an OpenAI-compatible gateway between CLI tools (Claude Code, Codex,
Cursor, Cline, OpenCode, Copilot, Antigravity, OpenClaw) and 40+ upstream
providers (Anthropic, OpenAI, Gemini, GLM, MiniMax, Kimi, OpenRouter, Vertex,
self-hosted whisper/Kokoro/llama-server). Features covered: 3-tier fallback
(subscription, cheap, free), RTK / Headroom / Caveman / Ponytail token savers,
quota tracking, format translation, multi-account sync, bearer-key protection,
request logging, Cloud Sync, and Cloudflare/Dokploy/Traefik/Nginx fronting.

## When to use

- Fresh install on a new or existing server (local VM, VPS, Dokploy/Coolify host, bare metal).
- Upgrade (Docker tag bump or `npm install -g 9router`).
- Hardening an internet-exposed instance (`REQUIRE_API_KEY`, `AUTH_COOKIE_SECURE=true`, TLS, firewall).
- Adding or rotating providers, API keys, OAuth accounts, or rebuilding fallback combos.
- Migrating `$DATA_DIR/db/data.sqlite` between hosts or restoring a backup.
- Ongoing ops: health checks, token-saver tuning, quota/cost triage, cloud-sync repair, log inspection, weekly model-inventory sync.

Not for: creating upstream provider accounts, workload-side prompt engineering,
or non-9Router reverse-proxy work.

## Fleet refs needed

- `fleet/services.yaml`: service `9router` (compose path, health endpoint, host).
- `fleet/servers.yaml`: the server record named by that service's `host` (connect via `ops ssh <server>`; `<ALIAS>` below is that server's ssh alias).
- `fleet/sites.yaml`: the domain record, only if internet-exposed.
- `fleet/providers.yaml`: DNS/Cloudflare account, only if the proxy or tunnel is Cloudflare.

Prerequisites on the target:

- Docker mode (recommended): Docker Engine + Compose v2 (`docker compose version`), or `docker run`.
- npm mode: Node.js >= 22, npm >= 10.
- Source mode: Node.js >= 22, `git`, `npm`, and `pm2` or `systemd`.
- A free TCP port (default `20128`; Headroom sidecar `8787`), confirmed with `ss -tlnp`.
- If internet-exposed: domain/DNS record, TLS termination (Dokploy Traefik, Caddy, Nginx, or Cloudflare), and an operator decision on `REQUIRE_API_KEY` (must be `true` for public exposure).

## Vault entries needed

Names follow `<client>-<provider>-<purpose>`. Values are never printed or logged.

| Vault entry | Used for |
|---|---|
| `<client>-9router-jwt-secret` | `JWT_SECRET` (32+ random bytes, base64) |
| `<client>-9router-initial-password` | `INITIAL_PASSWORD` (first dashboard login) |
| `<client>-9router-dashboard-password` | dashboard password after first-login rotation |
| `<client>-9router-api-key` | `NINEROUTER_KEY` (Dashboard -> Keys) |
| `<client>-9router-api-key-secret` | `API_KEY_SECRET` |
| `<client>-9router-machine-id-salt` | `MACHINE_ID_SALT` |
| `<client>-gcp-vertex-sa` | Vertex service-account JSON, only if used |
| `ssh/<client>-<server>` | ssh key from the server's fleet record |

Upstream provider API keys are pasted into the Dashboard and stored by 9Router
in its own database, not in the vault.

## Deployment modes (choose at plan time)

| Mode | Command | When |
|---|---|---|
| A: npm global | `npm install -g 9router && 9router` | Local single-user, fastest |
| B: Docker run | `docker run -d -p 20128:20128 -v <DATA_DIR>:/app/data -e DATA_DIR=/app/data decolua/9router:latest` | One-shot, no compose |
| C: Docker Compose | `templates/docker-compose.yml` (or `.headroom.yml`) | Recommended for servers; Headroom sidecar supported |
| D: Source + systemd/pm2 | `git clone ... && npm install && npm run build && npm run start` | Full control, VPS without Docker |

Default recommendation: C on servers, A on a developer workstation.

## Procedure

Rules for every step:

- Reads need no flag. Every step that changes a production system is flagged **WRITE** and needs approval per the run's permission mode (AGENTS.md section 1.3).
- Every destructive **WRITE** is preceded by a **Backup** step.
- Every **WRITE** has a **Rollback** line.
- Every fix is followed by a **Verify** step.
- Placeholders only: `<ALIAS>`, `<PORT>`, `<HOST>`, `<DOMAIN>`, `<DATA_DIR>`, `<COMPOSE_DIR>`, `<APP_DIR>`.
- Planned work is tracked from `templates/plan-template.md` and `templates/runbook-template.md` in `runs/9router[-<suffix>]/`; logs there are append-only and timestamp-prefixed.

### 0. Pre-flight (every run)

- [ ] Read `references/gotchas.md`.
- [ ] Fetch the upstream 9Router skill live (not cached):
      `curl -s https://raw.githubusercontent.com/decolua/9router/refs/heads/master/skills/9router/SKILL.md`
      Confirm it contains `NINEROUTER_URL` and `/v1/models`. Save a copy to `logs/<timestamp>-00-skill.md` (no secrets in it).
- [ ] Resolve `fleet/services.yaml` service `9router` and its `fleet/servers.yaml` record. Confirm the vault entries above exist.
- [ ] Confirm access (read): `ssh -o BatchMode=yes <ALIAS> 'hostname; whoami; ss -tlnp | head -n 20'`
- [ ] Record the run's permission mode in the runbook (A per-write confirm / B plan-as-approved).

### 1. Discover current state (reads only)

- [ ] Existing install, which mode if any:
      ```bash
      ssh <ALIAS> 'docker ps -a --filter name=9router --format "{{.Names}} {{.Image}} {{.Status}} {{.Ports}}" 2>/dev/null; echo "---"; docker volume ls 2>/dev/null | grep -i 9router; echo "---"; which 9router 2>/dev/null; 9router --version 2>/dev/null; npm list -g 9router 2>/dev/null | head -n 5; echo "---"; ss -tlnp 2>/dev/null | grep -E ":20128|:8787|:20127"; echo "---"; ls -la ~/.9router/db/ 2>/dev/null; ls -la /app/data/db/ 2>/dev/null; cat docker-compose.yml 2>/dev/null | head -n 80'
      ```
- [ ] Env and config on the host, secrets excluded:
      ```bash
      ssh <ALIAS> 'grep -v "SECRET\|PASSWORD\|KEY\|TOKEN" .env 2>/dev/null | head -n 40; echo "---"; env | grep -i "9router\|DATA_DIR\|PORT\|HOSTNAME" 2>/dev/null | grep -v SECRET | head -n 20'
      ```
- [ ] Reverse-proxy state, if exposed:
      ```bash
      ssh <ALIAS> 'cat /etc/nginx/sites-enabled/* 2>/dev/null | grep -A5 -i 9router | head -n 60; echo "---"; cat /etc/dokploy/traefik/traefik.yml 2>/dev/null | head -n 60; echo "---"; caddy list 2>/dev/null | head -n 20; ss -tlnp 2>/dev/null | grep -E ":80|:443"'
      ```
- [ ] Live health, if already running (per the upstream skill):
      ```bash
      curl -s http://<HOST>:<PORT>/api/health            # expected: {"ok":true}
      curl -s http://<HOST>:<PORT>/v1/models -H "Authorization: Bearer <KEY>" | head -c 2000
      curl -s https://<DOMAIN>/api/health                # if internet-exposed
      ```
- [ ] Record in the runbook: current mode (A/B/C/D/none), version or image tag, listening ports, `DATA_DIR`, health result, proxy presence. Note previous `DATA_DIR` / `PORT` values for rollback (no secret values).

### 2. Deployment-mode decision (ask the operator)

Ask explicitly; never assume.

- [ ] ASK: "Which deployment mode for `<ALIAS>`: A (npm), B (docker run), C (compose), or D (source)? Internet-exposed (needs `REQUIRE_API_KEY=true` + TLS) or localhost-only?"
- [ ] ASK: "Should Headroom run as a sidecar (`C+Headroom`)?" (`HEADROOM_URL=http://headroom:8787` inside the compose network; `http://host.docker.internal:8787` if Headroom is on the host.)
- [ ] ASK: "Domain and reverse-proxy choice if exposed (Nginx / Dokploy Traefik / Caddy / Cloudflare Tunnel)?"
- [ ] Record mode, exposure, proxy, and Headroom decision in the runbook and plan. Must happen before any WRITE.

### 3. Prepare host

#### 3.1 Host prerequisites (reads)

- [ ] OS and arch: `ssh <ALIAS> 'uname -a; cat /etc/os-release 2>/dev/null | head -n 5'`
- [ ] Docker (mode B/C): `ssh <ALIAS> 'docker --version; docker compose version 2>/dev/null || docker-compose --version 2>/dev/null'`
- [ ] Node (mode A/D): `ssh <ALIAS> 'node --version; npm --version'`
- [ ] Ports free: `ssh <ALIAS> 'ss -tlnp | grep -E ":<PORT>|:8787" || echo "ports free"'`
- [ ] Disk for the volume: `ssh <ALIAS> 'df -h /home 2>/dev/null; df -h /var/lib 2>/dev/null | head -n 5'`

#### 3.2 Data directory and secrets (WRITE, approval required)

- [ ] Decide `DATA_DIR`. It must match `.env` and the mount or volume.
      - Docker (B/C): `/app/data` inside the container, bind-mounted to `<HOST_DATA_DIR>` (default `~/.9router` or `/var/lib/9router`).
      - npm/source (A/D): `~/.9router`, or explicit `DATA_DIR=/var/lib/9router`.
- [ ] **Backup**: if a vault entry already exists, keep the previous value as `<entry>.prev-<timestamp>`.
- [ ] **WRITE**: generate secrets into the vault entries listed above:
      ```bash
      openssl rand -base64 48   # <client>-9router-jwt-secret
      openssl rand -base64 32   # <client>-9router-api-key-secret
      openssl rand -base64 16   # <client>-9router-machine-id-salt
      ```
      `INITIAL_PASSWORD`: ask the operator and store in `<client>-9router-initial-password`. If reusing an existing install, keep the current password. Never inline secret values in plan or runbook; reference vault entry names only.
      - Rollback: restore the `.prev-<timestamp>` values and restart.
- [ ] **Backup**: if `.env` exists on the host, copy it to `.env.prev-<timestamp>`.
- [ ] **WRITE**: prepare the env file on the target from `templates/env.example`. Required keys: `JWT_SECRET`, `INITIAL_PASSWORD`, `DATA_DIR`, `PORT`, `NODE_ENV`, `BASE_URL`, `CLOUD_URL` (or compat `NEXT_PUBLIC_*`), `API_KEY_SECRET`, `MACHINE_ID_SALT`, `REQUIRE_API_KEY`, `AUTH_COOKIE_SECURE` (see section 5). Store as `.env` on the host (mode D) or the compose `env_file` path (mode C). Do not commit or log it.
      - Rollback: restore `.env.prev-<timestamp>`.

### 4. Install (WRITE, approval required; branch on mode from section 2)

#### 4A. Mode A: npm global

- [ ] **WRITE**: `ssh <ALIAS> 'npm install -g 9router'`
      - Rollback: `npm uninstall -g 9router` or `npm install -g 9router@<PREV_VERSION>`
- [ ] **WRITE**: write `<DATA_DIR>/.env` on the host from `templates/env.example` (values from the vault entries; see section 3.2).
- [ ] **WRITE**: start (foreground test, then background):
      `ssh <ALIAS> 'nohup 9router > <DATA_DIR>/9router.log 2>&1 & echo $! > <DATA_DIR>/9router.pid; sleep 3; tail -n 50 <DATA_DIR>/9router.log'`
      - Rollback: `kill $(cat <DATA_DIR>/9router.pid); rm <DATA_DIR>/9router.pid`
- [ ] Verify: `curl -s http://<HOST>:<PORT>/api/health` returns `{"ok":true}`.

#### 4B. Mode B: Docker run

- [ ] **WRITE**: `ssh <ALIAS> 'docker pull decolua/9router:latest'`
      - Rollback: `docker pull decolua/9router:<PREV_TAG>`
- [ ] **Backup**: record the current image tag and back up the data dir (section 9.1) if a container exists.
- [ ] **WRITE**:
      ```bash
      ssh <ALIAS> 'mkdir -p <HOST_DATA_DIR> && docker rm -f 9router 2>/dev/null; docker run -d \
        -p <PORT>:20128 \
        -v <HOST_DATA_DIR>:/app/data \
        -e DATA_DIR=/app/data \
        --env-file <HOST_ENV_PATH> \
        --name 9router \
        decolua/9router:latest'
      ```
      - Rollback: `docker rm -f 9router`, then `docker run ...` with `decolua/9router:<PREV_TAG>`.
- [ ] Verify: `ssh <ALIAS> 'docker logs --tail 50 9router; docker ps --filter name=9router'`

#### 4C. Mode C: Docker Compose (recommended for servers)

- [ ] **Backup**: if a compose file exists, copy it to `docker-compose.yml.prev-<timestamp>`.
- [ ] **WRITE**: copy `templates/docker-compose.yml` (or `docker-compose.headroom.yml` if Headroom) to `<COMPOSE_DIR>/docker-compose.yml`; fill `<PORT>`, `<HOST_DATA_DIR>`, and the env_file path:
      `scp templates/docker-compose.yml <ALIAS>:<COMPOSE_DIR>/docker-compose.yml`
      - Rollback: restore `docker-compose.yml.prev-<timestamp>`.
- [ ] **WRITE**: place the env file at `<COMPOSE_DIR>/.env` (or the path in compose `env_file`), written from the vault values over scp as a `0600` file.
- [ ] **WRITE**: `ssh <ALIAS> 'cd <COMPOSE_DIR> && docker compose pull && docker compose up -d'`
      - Rollback: `docker compose down; docker compose up -d` with the previous image tag and compose file.
- [ ] If Headroom sidecar:
      - Compose includes the `headroom` service (`ghcr.io/chopratejas/headroom:latest`) and sets `HEADROOM_URL=http://headroom:8787` on the 9router service.
      - Linux with Headroom on the host: add `extra_hosts: ["host.docker.internal:host-gateway"]` and use `HEADROOM_URL=http://host.docker.internal:8787` (see upstream DOCKER.md).
      - Verify: `ssh <ALIAS> 'docker compose ps; docker logs --tail 30 headroom 2>/dev/null'`
- [ ] Verify: `ssh <ALIAS> 'docker compose ps; docker logs --tail 50 9router'`

#### 4D. Mode D: Source + systemd/pm2

- [ ] **Backup**: record the current commit (`git -C <APP_DIR> rev-parse HEAD`) and keep the previous `.next/` as `.next.prev-<timestamp>`.
- [ ] **WRITE**: `ssh <ALIAS> 'git clone https://github.com/decolua/9router.git <APP_DIR> || (cd <APP_DIR> && git fetch --all && git checkout master && git pull)'`
      - Rollback: `cd <APP_DIR> && git checkout <PREV_SHA>`
- [ ] **WRITE**: `ssh <ALIAS> 'cd <APP_DIR> && cp .env.example .env && npm install'`, then overwrite `.env` with the filled env (section 3.2). The repo package is `9router-app` (private); source execution is the expected path, not `npm install 9router` from the repo root.
- [ ] **WRITE**: build: `ssh <ALIAS> 'cd <APP_DIR> && npm run build'`
      - Rollback: restore `.next.prev-<timestamp>`.
- [ ] **WRITE** (choose one):
      - systemd (`templates/systemd-9router.service`): `scp templates/systemd-9router.service <ALIAS>:/etc/systemd/system/9router.service` (fill `<APP_DIR>`, `<DATA_DIR>`, `<PORT>`, env), then `ssh <ALIAS> 'sudo systemctl daemon-reload && sudo systemctl enable --now 9router && systemctl is-active 9router'`
        - Rollback: `sudo systemctl disable --now 9router; sudo rm /etc/systemd/system/9router.service`
      - pm2: `ssh <ALIAS> 'pm2 start npm --name 9router -- start -- --port <PORT> && pm2 save && pm2 startup'`
        - Rollback: `pm2 delete 9router`
- [ ] Verify: `ssh <ALIAS> 'systemctl status 9router 2>/dev/null || pm2 status 2>/dev/null; curl -s http://127.0.0.1:<PORT>/api/health'`

### 5. Configure and harden

#### 5.1 Dashboard first login

- [ ] Open `http://<HOST>:<PORT>/dashboard` (or `https://<DOMAIN>/dashboard` if proxied). Log in with `INITIAL_PASSWORD`.
- [ ] **WRITE**: change the dashboard password immediately (Dashboard -> Settings). Store the new password in `<client>-9router-dashboard-password`.
      - Rollback: reset via `INITIAL_PASSWORD` + `JWT_SECRET` rotation if needed.
- [ ] Record the `BASE_URL` decision. Prefer server-side `BASE_URL` / `CLOUD_URL` in production (`NEXT_PUBLIC_*` is UI-only). Set `BASE_URL=http://<HOST>:<PORT>` (or `https://<DOMAIN>` when proxied) so the internal sync scheduler can call back.

#### 5.2 API key and auth hardening (WRITE, approval required)

- [ ] Decide `REQUIRE_API_KEY`: `false` is localhost-only (upstream default, safe behind a firewall). `true` is mandatory when internet-exposed. Do not expose `/v1/*` without a Bearer key. Restart required after change.
- [ ] Decide `AUTH_COOKIE_SECURE`: `false` for HTTP/localhost; `true` behind an HTTPS reverse proxy.
- [ ] **WRITE**: create or rotate the 9Router API key (Dashboard -> Keys -> Generate). Store only in `<client>-9router-api-key`. This is `NINEROUTER_KEY` for verification.
      - Rollback: previous value kept as `<entry>.prev-<timestamp>`.
- [ ] **Backup**: copy the current env file to `.env.prev-<timestamp>`.
- [ ] **WRITE**: apply env changes and restart (`docker restart 9router`, `docker compose restart 9router`, or `systemctl restart 9router`).
      - Rollback: restore `.env.prev-<timestamp>` and restart.
- [ ] Verify: unauthenticated `curl http://<HOST>:<PORT>/v1/models` returns `401` when `REQUIRE_API_KEY=true`; authenticated returns `200`.

#### 5.3 Token-saver and endpoint tuning (Dashboard, WRITE)

- [ ] Dashboard -> Endpoint -> Token Saver: RTK is ON by default (saves 20-40% input tokens). Toggle if the operator wants it off.
- [ ] Headroom (if sidecar): Dashboard -> Endpoint -> Token Saver -> Headroom -> URL `http://headroom:8787` (compose network) or `http://host.docker.internal:8787`; recheck status, then enable. It fails open if Headroom is down.
- [ ] Ponytail (Lite/Full/Ultra) and Caveman (up to 65% output savings): enable per operator preference. Stacks with RTK.
- [ ] Per-request bypass: header `X-9Router-Token-Saver: off`.
- [ ] Verify: section 8 token-saver sanity check.

### 6. Reverse proxy and firewall (WRITE, approval required; only if exposed)

- [ ] Choose proxy: Nginx (`templates/nginx-9router.conf`), Dokploy Traefik (compose labels), Caddy (`reverse_proxy`), or Cloudflare Tunnel. Record in the runbook.
- [ ] **Backup**: save the current proxy config (`/etc/nginx/sites-available/9router` if present) and `sudo ufw status verbose` output.
- [ ] **WRITE**: Nginx example: copy `templates/nginx-9router.conf` to `<ALIAS>:/etc/nginx/sites-available/9router`, fill `<DOMAIN>` and `proxy_pass http://127.0.0.1:<PORT>`, `ln -s` into `sites-enabled/`, add the TLS cert (Let's Encrypt or existing), then `nginx -t && systemctl reload nginx`.
      - Rollback: `rm sites-enabled/9router; nginx -t && systemctl reload nginx`.
- [ ] **WRITE**: firewall, allow `80/443` only; keep `<PORT>` firewalled unless localhost-only is intended:
      ```bash
      ssh <ALIAS> 'sudo ufw allow 80/tcp; sudo ufw allow 443/tcp; sudo ufw deny <PORT>/tcp 2>/dev/null; sudo ufw status'
      ```
      - Rollback: `sudo ufw delete allow 80/tcp` etc.; restore the saved `ufw status`.
- [ ] Verify (reads):
      ```bash
      curl -s https://<DOMAIN>/api/health                         # {"ok":true}
      curl -s https://<DOMAIN>/v1/models -H "Authorization: Bearer <KEY>" | head -c 500
      echo | openssl s_client -connect <DOMAIN>:443 -servername <DOMAIN> 2>/dev/null | openssl x509 -noout -dates
      ```

### 7. Provider and combo management

All steps can be done in the Dashboard. The API alternative uses the upstream skill's `NINEROUTER_URL` / `NINEROUTER_KEY` contracts.

- [ ] **WRITE**: Dashboard -> Providers -> connect providers per the operator's approved list (record choices in the plan):
      - OAuth (Claude Code, Codex, GitHub Copilot, Cursor, Kimchi, Antigravity): browser OAuth with auto-refresh; no secret stored locally.
      - Free (Kiro via AWS Builder ID / Google / GitHub; OpenCode Free no-auth; Vertex via GCP service-account JSON from `<client>-gcp-vertex-sa`).
      - API-key (GLM, MiniMax, Kimi, OpenAI, Anthropic, Gemini, DeepSeek, Groq, xAI, ...): paste key; stored in `$DATA_DIR/db/data.sqlite`, not in this repo.
      - Self-hosted (STT `/v1/audio/transcriptions`, TTS `/v1/audio/speech`, Embedding `/v1/embeddings`): set `providerSpecificData.baseUrl`.
      - **Backup** first: section 9.1. Rollback: remove the connection in the Dashboard or restore the DB backup.
- [ ] For each self-hosted STT/TTS/Embedding connection, validate the `baseUrl` contract (gotcha G7): STT is the full `/v1/audio/transcriptions` URL; TTS is the server root; Embedding is the OpenAI base with `/v1`.
- [ ] **WRITE**: Dashboard -> Combos -> create combos per the operator's fallback policy (for example `premium-coding`: `cc/claude-opus-4-7` -> `glm/glm-5.1` -> `minimax/MiniMax-M2.7`; `free-forever`: `kr/claude-sonnet-4.5` -> `kr/glm-5` -> `vertex/gemini-3.1-pro-preview`). Combo names are the model IDs clients use. Baseline combo orderings are local, untracked files (`combos/`, `references/baseline*`) and are produced by `scripts/9router-sync.py`.
      - Rollback: delete the combo or restore the DB backup.
- [ ] Verify (reads), list models per kind:
      ```bash
      export NINEROUTER_URL="http://<HOST>:<PORT>"   # or https://<DOMAIN>
      export NINEROUTER_KEY="<value of <client>-9router-api-key>"
      curl -s $NINEROUTER_URL/v1/models -H "Authorization: Bearer $NINEROUTER_KEY" | head -c 3000
      curl -s $NINEROUTER_URL/v1/models/image     -H "Authorization: Bearer $NINEROUTER_KEY" | head -c 2000
      curl -s $NINEROUTER_URL/v1/models/tts       -H "Authorization: Bearer $NINEROUTER_KEY" | head -c 2000
      curl -s $NINEROUTER_URL/v1/models/embedding -H "Authorization: Bearer $NINEROUTER_KEY" | head -c 2000
      curl -s $NINEROUTER_URL/v1/models/web       -H "Authorization: Bearer $NINEROUTER_KEY" | head -c 2000
      ```
      Use `data[].id` as the `model` field in chat requests. Combos appear with `owned_by:"combo"`.

### 8. Verification (reads; per the upstream skill)

Run `scripts/health-check.sh` or manually:

- [ ] Health: `curl -s $NINEROUTER_URL/api/health` returns `{"ok":true}`.
- [ ] Auth gate (if `REQUIRE_API_KEY=true`): unauthenticated `/v1/models` returns `401`; authenticated returns `200` with a `data` list.
- [ ] Dashboard: `curl -s $NINEROUTER_URL/dashboard -o /dev/null -w "%{http_code}\n"` returns `200`.
- [ ] OpenAI-compat probe (capability skill `9router-chat`: `https://raw.githubusercontent.com/decolua/9router/refs/heads/master/skills/9router-chat/SKILL.md`):
      ```bash
      curl -s $NINEROUTER_URL/v1/chat/completions \
        -H "Authorization: Bearer $NINEROUTER_KEY" \
        -H "Content-Type: application/json" \
        -d '{"model":"<MODEL_OR_COMBO_ID>","messages":[{"role":"user","content":"ping"}]}' \
        | head -c 2000
      ```
      Expect `choices[0].message.content` to contain a reply.
- [ ] Client smoke (one the operator uses): Claude Code (`~/.claude/config.json` with `anthropic_api_base`), Codex (`OPENAI_BASE_URL=$NINEROUTER_URL`), Cursor/Cline/Continue (OpenAI-compatible base URL), OpenClaw (`~/.openclaw/openclaw.json` provider `9router`, `baseUrl` `http://127.0.0.1:<PORT>/v1`).
- [ ] Token-saver sanity: send a request with a `tool_result` containing a `git diff` payload; confirm success and usage reported; bypass once with `X-9Router-Token-Saver: off` to compare.
- [ ] Record verification outputs (keys redacted) in `logs/<timestamp>-verify.log` and the runbook.

### 9. Operational lifecycle

#### 9.1 Backup

- [ ] **WRITE** (creates the backup artifact only): SQLite backup. Do not copy a live DB without care (G9).
      ```bash
      ssh <ALIAS> 'sqlite3 <DATA_DIR>/db/data.sqlite ".backup <DATA_DIR>/db/data.sqlite.bak.$(date +%F)" && ls -lh <DATA_DIR>/db/data.sqlite.bak.*'
      # Fallback (stop-then-copy): docker compose stop 9router && cp <HOST_DATA_DIR>/db/data.sqlite <BACKUP_PATH> && docker compose start 9router
      ```
      Also capture a redacted `.env` and `docker-compose.yml` next to the DB copy. Record the backup path and timestamp in the runbook.
      - Rollback: delete the backup file (the live DB is not changed).
- [ ] Keep at least one known-good backup before any upgrade or migration. The vault entries hold the key material needed to decrypt and restore; back up the vault alongside the DB.
- [ ] Helper: `scripts/backup.sh`.

#### 9.2 Restore (WRITE, approval required)

- [ ] **Backup**: take a fresh backup of the current DB first (section 9.1) so the restore is reversible. Record both paths.
- [ ] **WRITE**: stop 9Router, restore the SQLite file, restart:
      ```bash
      ssh <ALIAS> 'cd <COMPOSE_DIR> && docker compose stop 9router || docker stop 9router || systemctl stop 9router'
      scp <BACKUP_SQLITE> <ALIAS>:<DATA_DIR>/db/data.sqlite
      ssh <ALIAS> 'cd <COMPOSE_DIR> && docker compose start 9router || docker start 9router || systemctl start 9router; sleep 3; curl -s http://127.0.0.1:<PORT>/api/health'
      ```
      - Rollback: restore the pre-restore backup.
- [ ] Verify: section 8 probes. Helper: `scripts/restore.sh` (takes a pre-restore backup itself).

#### 9.3 Update / upgrade (WRITE, approval required)

- [ ] Check current vs latest:
      ```bash
      ssh <ALIAS> 'docker inspect 9router --format "{{.Config.Image}}" 2>/dev/null; 9router --version 2>/dev/null; npm view 9router version 2>/dev/null'
      curl -s https://registry.hub.docker.com/v2/repositories/decolua/9router/tags?page_size=5 | head -c 3000
      ```
- [ ] **Backup**: section 9.1. Mandatory before any upgrade.
- [ ] **WRITE**, by mode:
      - Docker/compose: `ssh <ALIAS> 'cd <COMPOSE_DIR> && docker compose pull && docker compose up -d'` (mode B: `docker pull decolua/9router:latest && docker rm -f 9router && docker run ...`)
      - npm global: `ssh <ALIAS> 'npm install -g 9router@latest'`
      - Source: `ssh <ALIAS> 'cd <APP_DIR> && git pull && npm install && npm run build && pm2 restart 9router || systemctl restart 9router'`
      - Rollback: reinstall the previous tag or version recorded in the runbook, and restore the pre-upgrade DB backup if the new version migrated the schema.
- [ ] Verify: re-run section 8 probes; `/api/health` and at least one chat completion succeed. Helper: `scripts/update.sh`.

#### 9.4 Observability and ops

- [ ] Logs: Docker `docker logs --tail 200 9router; docker logs --tail 100 headroom 2>/dev/null`; source/pm2 `pm2 logs 9router --lines 200` or `journalctl -u 9router -n 200`. Request debug logs: `ENABLE_REQUEST_LOGS=true` in `.env` writes under `logs/` in `DATA_DIR`; enable only while triaging.
- [ ] Usage: Dashboard -> Usage / Analytics. Dashboard cost is a tracking estimate, not billing; 9Router never charges.
- [ ] Cloud Sync: if enabled, confirm server-side `BASE_URL` / `CLOUD_URL` are the public base URL; verify sync jobs do not hang on DNS/timeout.
- [ ] Migration between hosts: copy the vault entries' values via the destination's own store, the `backup.sh` artifact, `.env`, and `docker-compose.yml`; follow section 9.2 on the destination.

### 10. Verification and rollback gate

- [ ] Re-run `scripts/health-check.sh` (or section 8): health OK, auth gate correct, at least one model responds to `chat/completions`.
- [ ] Every **WRITE** this run has a rollback recorded in the runbook (previous vault values, `.env.prev-*`, compose prev, previous image tag, DB backup path, proxy/firewall revert).
- [ ] Run the leak check from AGENTS.md section 7; `git status` shows no `runs/`, `vault/`, `*.pem`, `*.key`, `.tfvars`.
- [ ] Findings go to the run's `notes.md`; propose promotion into `references/gotchas.md` (operator approves, never mid-run).
- [ ] Mark runbook steps `done` or `blocked` with a reason; close the run.

## Automation: model inventory and 9Router sync

Scripts discover config under `runs/*9router*/`.

- `scripts/model-inventory.py` fetches multi-provider inventories (google/opencode/cloudflare/ollama/openrouter/command_code) into `models.csv` with `supports_vision` / `supports_image_generation`.
- `scripts/9router-sync.py` syncs the inventory to 9Router: global filter, provider-mapped routed ids, diff-guarded `/api/models/custom`, `/api/models/disabled`, `/api/combos`, and regenerates `generated/` CLI configs and `combos/*.json|*.csv`. Config: copy `templates/9router-sync.config.example.yaml` to `<run folder>/9router-sync.config.yaml` (gitignored). Dry run: `python .agents/skills/9router/scripts/9router-sync.py --dry-run --verbose`.
- `scripts/generate-configs.py` builds CLI client configs from live `GET /v1/models`.
- Cron wrappers (`chmod +x` on the host; lock via `flock`, fallback `mkdir`; logs append-only in the run folder plus stdout for cron mail):
  - `scripts/model-inventory-cron.sh`: weekly Monday 15:00 (`0 15 * * 1`). Auto-discovers `model-inventory*.yaml`; override with `--config PATH`; `--no-sync` skips the sync.
  - `scripts/9router-sync-cron.sh`: weekly Monday 16:00 (`0 16 * * 1`), one hour after the inventory fetch; also works standalone.
- Install, **WRITE** on the host, with **Backup** of the current crontab (`crontab -l > crontab.prev-<timestamp>`) first:
  ```bash
  chmod +x <REPO_ROOT>/.agents/skills/9router/scripts/*-cron.sh
  crontab -e
  # 0 15 * * 1 <REPO_ROOT>/.agents/skills/9router/scripts/model-inventory-cron.sh >> /var/log/model-inventory-cron.log 2>&1
  # 0 16 * * 1 <REPO_ROOT>/.agents/skills/9router/scripts/9router-sync-cron.sh >> /var/log/9router-sync-cron.log 2>&1
  ```
  Or use the fragment `templates/cron-9router-sync`.
  - Rollback: `crontab crontab.prev-<timestamp>`.
- systemd timer (preferred on modern hosts), **WRITE** on the host:
  ```bash
  sudo cp <REPO_ROOT>/.agents/skills/9router/templates/systemd-9router-sync.service /etc/systemd/system/9router-sync.service
  sudo cp <REPO_ROOT>/.agents/skills/9router/templates/systemd-9router-sync.timer /etc/systemd/system/9router-sync.timer
  # edit <USER> and <REPO_ROOT> in 9router-sync.service
  sudo systemctl daemon-reload && sudo systemctl enable --now 9router-sync.timer
  ```
  - Rollback: `sudo systemctl disable --now 9router-sync.timer; sudo rm /etc/systemd/system/9router-sync.{service,timer}; sudo systemctl daemon-reload`
- Verify (reads): `systemctl list-timers 9router-sync.timer`; `<REPO_ROOT>/.agents/skills/9router/scripts/9router-sync-cron.sh --dry-run --verbose`; check the latest `*9router-sync-cron.log` in the run folder.

## Rollback

Each **WRITE** has its own rollback line. Order for a full revert of an install or upgrade:

1. Proxy and firewall: restore saved proxy config and `ufw` rules, reload.
2. Application: previous image tag or version, previous compose file and `.env.prev-<timestamp>`.
3. Data: restore the pre-change SQLite backup (section 9.2).
4. Vault: restore `<entry>.prev-<timestamp>` values, then restart.

Stop and ask the operator if a rollback step is not covered here.

## Verify

Section 8 probes: `/api/health` is `{"ok":true}`, the auth gate returns `401` without a key and `200` with one, the dashboard returns `200`, and one `chat/completions` request returns a reply.

## Gotchas

Full list G1-G12 with fixes in `references/gotchas.md`. Key points:

- Fetch the upstream skill live every run; never improvise API shapes (`references/skill.md`).
- `DATA_DIR` in `.env` must match the mount or volume.
- Self-hosted STT/TTS/Embedding `baseUrl` shapes differ (G7).
- Do not copy a live SQLite file without `.backup` or a stop (G9).
- `REQUIRE_API_KEY=true` is mandatory for any internet-exposed instance.

## Files

| Path | Purpose |
|---|---|
| `references/gotchas.md` | G1-G12 pitfalls with fixes; read before any run |
| `references/skill.md` | Pointer to the upstream 9Router skill (fetched live, not bundled) |
| `templates/plan-template.md`, `templates/runbook-template.md` | Plan and runbook for planned work |
| `templates/env.example` | Env file template |
| `templates/docker-compose.yml`, `templates/docker-compose.headroom.yml` | Compose files; Headroom sidecar wiring |
| `templates/nginx-9router.conf` | Nginx vhost (TLS, headers, `/v1`, `/api`, `/dashboard`) |
| `templates/systemd-9router.service` | systemd unit for source deploys |
| `templates/systemd-9router-sync.{service,timer}`, `templates/cron-9router-sync` | Weekly sync scheduling |
| `templates/*.config.example.yaml` | Config examples for `model-inventory.py` and `9router-sync.py` |
| `scripts/health-check.sh`, `backup.sh`, `restore.sh`, `update.sh` | Ops helpers |
| `scripts/model-inventory.py`, `9router-sync.py`, `generate-configs.py` and `*-cron.sh` | Inventory, sync, config generation, cron wrappers |
