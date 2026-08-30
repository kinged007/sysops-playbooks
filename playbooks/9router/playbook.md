# Playbook: 9Router Proxy Manager — Procedure

Canonical steps for a run. **Placeholders only** — never real IPs, hostnames,
usernames, or credentials. Real values go in the execution's `plan.md`,
`inventory.md`, and `secrets/`. Repo-level rules (folder discipline, secrets,
committing): see `AGENTS.md`.

Conventions: every step that WRITES to a production system is flagged
**WRITE** and needs approval per the run's permission mode (A: per-write
confirm / B: plan-as-approved). Rollback is given for every write. Reads are
free. Execution folder is persistent per variant: `executions/9router/` or
`executions/9router-<suffix>/`; `logs/` is append-only with
timestamp-prefixed files (e.g. `logs/2026-08-29T143000-01-discover.log`).

> **Skill-first rule (non-negotiable):** before any management, verification,
> or API step in this playbook, fetch and follow the upstream skill:
> `https://raw.githubusercontent.com/decolua/9router/refs/heads/master/skills/9router/SKILL.md`
> It defines `NINEROUTER_URL` / `NINEROUTER_KEY`, the `/api/health` probe,
> and every `/v1/models/*` discovery contract. For capability tests, fetch
> the relevant capability skill listed inside it (chat, image, tts, stt,
> embeddings, web-search, web-fetch). Never improvise the API shape.

---

## 0. Pre-flight (mandatory, every run)

- [ ] Read `notes/gotchas.md` (mandatory) — G1–G12 may change how you plan
- [ ] **Fetch the 9Router skill** (live, not cached):
      `curl -s https://raw.githubusercontent.com/decolua/9router/refs/heads/master/skills/9router/SKILL.md`
      — confirm it contains `NINEROUTER_URL` and `/v1/models`; save a copy to
      `logs/<timestamp>-00-skill.md` for the record (no secrets in it)
- [ ] Confirm prerequisites (README): SSH alias `<ALIAS>` for the target,
      Docker or Node ≥22, free port `<PORT>` (default `20128`), domain/TLS
      choice if internet-exposed, operator-available secrets
- [ ] Confirm access (read): `ssh -o BatchMode=yes <ALIAS> 'hostname; whoami; ss -tlnp | head -n 20'`
      — one line, no prompts; record hostname in inventory
- [ ] Scan `executions/` for an existing `9router` / `9router-<suffix>` folder
      and legacy dated folders containing `9router`; present matches to the
      operator: reuse or create new variant with suffix `<SUFFIX>`
- [ ] Record the run's permission mode in the runbook (AGENTS.md §1.3: operator
      sets A per-write confirm / B plan-as-approved at plan approval)

## 1. Discover current state (reads only)

- [ ] Existing install — which mode, if any:
      ```bash
      ssh <ALIAS> 'docker ps -a --filter name=9router --format "{{.Names}} {{.Image}} {{.Status}} {{.Ports}}" 2>/dev/null; echo "---"; docker volume ls 2>/dev/null | grep -i 9router; echo "---"; which 9router 2>/dev/null; 9router --version 2>/dev/null; npm list -g 9router 2>/dev/null | head -n 5; echo "---"; ss -tlnp 2>/dev/null | grep -E ":20128|:8787|:20127"; echo "---"; cat /app/data/.env 2>/dev/null | head -n 30; cat ~/.9router/.env 2>/dev/null | head -n 30; ls -la ~/.9router/db/ 2>/dev/null; ls -la /app/data/db/ 2>/dev/null; cat .env 2>/dev/null | head -n 30; cat docker-compose.yml 2>/dev/null | head -n 80'
      ```
- [ ] Env & config on host (read only; do not echo secrets):
      ```bash
      ssh <ALIAS> 'grep -v "SECRET\|PASSWORD\|KEY\|TOKEN" .env 2>/dev/null | head -n 40; echo "---"; env | grep -i "9router\|DATA_DIR\|PORT\|HOSTNAME" 2>/dev/null | grep -v SECRET | head -n 20'
      ```
- [ ] Reverse-proxy state (if exposed):
      ```bash
      ssh <ALIAS> 'cat /etc/nginx/sites-enabled/* 2>/dev/null | grep -A5 -i 9router | head -n 60; echo "---"; cat /etc/dokploy/traefik/traefik.yml 2>/dev/null | head -n 60; echo "---"; caddy list 2>/dev/null | head -n 20; ss -tlnp 2>/dev/null | grep -E ":80|:443"'
      ```
- [ ] Live health (if already running) — per the skill (read):
      ```bash
      curl -s http://<HOST>:<PORT>/api/health
      # expected: {"ok":true}
      curl -s http://<HOST>:<PORT>/v1/models -H "Authorization: Bearer <KEY>" | head -c 2000
      # expected: { "object":"list", "data":[ ... ] }
      ```
      For an internet-exposed host, also probe:
      `curl -s https://<DOMAIN>/api/health` (read)
- [ ] Record findings in the runbook: current mode (A/B/C/D/none), running
      version/image tag, listening ports, DATA_DIR location, health result,
      proxy presence. Note previous `JWT_SECRET` / `DATA_DIR` / `PORT` values
      for rollback reference (do not log secret values)

## 2. Deployment-mode decision (ask the operator)

Ask explicitly; never assume. Present the four modes:

| Mode | Operator chooses when |
|---|---|
| **A — npm global** | Local workstation / single-user; `npm install -g 9router` |
| **B — Docker run** | One-shot server without compose; `docker run` published image |
| **C — Docker Compose** | **Recommended for servers**; with or without Headroom sidecar |
| **D — Source + systemd/pm2** | VPS without Docker or need for source builds |

- [ ] ASK: "Which deployment mode for `<ALIAS>` — A (npm), B (docker run),
      C (compose), or D (source)? Will it be internet-exposed (needs
      `REQUIRE_API_KEY=true` + TLS), or localhost-only?"
- [ ] ASK: "Should Headroom token saver run as a sidecar (`C+Headroom`)?"
      (`HEADROOM_URL=http://headroom:8787` inside compose network;
      `http://host.docker.internal:8787` if Headroom is on the host)
- [ ] ASK: "Domain / reverse-proxy choice if exposed (Nginx / Dokploy
      Traefik / Caddy / Cloudflare Tunnel)?"
- [ ] Record the chosen mode + exposure + proxy + Headroom decision in the
      runbook and `plan.md`. **Must happen before any WRITE.**

## 3. Prepare host (reads + gated writes)

### 3.1 Host prerequisites (read)

- [ ] Verify OS / arch: `ssh <ALIAS> 'uname -a; cat /etc/os-release 2>/dev/null | head -n 5'`
- [ ] Verify Docker (if mode B/C):
      `ssh <ALIAS> 'docker --version; docker compose version 2>/dev/null || docker-compose --version 2>/dev/null'`
- [ ] Verify Node (if mode A/D):
      `ssh <ALIAS> 'node --version; npm --version'`
- [ ] Check ports free: `ssh <ALIAS> 'ss -tlnp | grep -E ":<PORT>|:8787" || echo "ports free"'`
- [ ] Check disk for volume: `ssh <ALIAS> 'df -h /home 2>/dev/null; df -h /var/lib 2>/dev/null | head -n 5'`

### 3.2 Data directory & secrets prep (WRITE, approval required)

- [ ] Decide `DATA_DIR` (per `.env.example` / DOCKER.md):
      - Docker (B/C): `/app/data` **inside** container, bind-mounted to
        `<HOST_DATA_DIR>` (default `~/.9router` or `/var/lib/9router` on
        servers). Compose volume `9router-data` or bind `~/.9router:/app/data`.
      - npm/source (A/D): `~/.9router` (Linux/macOS) or `%APPDATA%\9router`
        (Windows), or explicit `DATA_DIR=/var/lib/9router`.
      - Record the chosen value in `plan.md` — it must match `.env` **and**
        the mount/volume.
- [ ] **WRITE** — Generate secrets (operator approval; store only in
      `executions/9router[-<suffix>]/secrets/`):
      ```bash
      # Generate JWT_SECRET (32+ random bytes, base64)
      openssl rand -base64 48 > executions/9router/secrets/jwt-secret.txt
      # Generate API_KEY_SECRET and MACHINE_ID_SALT similarly
      openssl rand -base64 32 > executions/9router/secrets/api-key-secret.txt
      openssl rand -base64 16 > executions/9router/secrets/machine-id-salt.txt
      ```
      - Never inline secret values in `plan.md` / `runbook.md` — reference the
        `secrets/` file path only.
      - `INITIAL_PASSWORD` — ask operator, store in
        `secrets/initial-password.txt`. If reusing an existing install, keep
        the current password.
      - Rollback: keep previous secret files as `*.prev-<timestamp>` in the
        same `secrets/` folder; revert = restore previous files + restart.

- [ ] **WRITE** — Prepare the env file on the target from
      `templates/env.example` (placeholders filled from `secrets/` and
      `plan.md` decisions). Required keys:
      `JWT_SECRET`, `INITIAL_PASSWORD`, `DATA_DIR`, `PORT`, `NODE_ENV`,
      `BASE_URL`, `CLOUD_URL` (or compat `NEXT_PUBLIC_*`), `API_KEY_SECRET`,
      `MACHINE_ID_SALT`, `REQUIRE_API_KEY`, `AUTH_COOKIE_SECURE`.
      See §5 for the hardening rule on `REQUIRE_API_KEY` /
      `AUTH_COOKIE_SECURE`. Store the filled file as `.env` on the host
      (mode D) or compose `env_file` path (mode C); do not commit or log it.
      - Rollback: keep previous `.env` as `.env.prev-<timestamp>` before
        overwriting.

## 4. Install 9Router (WRITE, approval required — branch on mode from §2)

### 4A. Mode A — npm global (local / single-user)

- [ ] **WRITE**: `ssh <ALIAS> 'npm install -g 9router'`
      — Rollback: `npm uninstall -g 9router` or `npm install -g 9router@<PREV_VERSION>`
- [ ] **WRITE**: `ssh <ALIAS> 'mkdir -p <DATA_DIR> && cat > <DATA_DIR>/.env <<EOF
      JWT_SECRET=<from secrets/jwt-secret.txt>
      INITIAL_PASSWORD=<from secrets/initial-password.txt>
      DATA_DIR=<DATA_DIR>
      PORT=<PORT>
      ... (see templates/env.example)
      EOF
      '`
- [ ] Start (foreground test then background):
      `ssh <ALIAS> 'nohup 9router > <DATA_DIR>/9router.log 2>&1 & echo $! > <DATA_DIR>/9router.pid; sleep 3; cat <DATA_DIR>/9router.log | tail -n 50'`
      - Rollback: `kill $(cat <DATA_DIR>/9router.pid); rm <DATA_DIR>/9router.pid`
- [ ] Verify: `curl -s http://<HOST>:<PORT>/api/health` → `{"ok":true}` (see §7)

### 4B. Mode B — Docker run (one-shot)

- [ ] **WRITE**: `ssh <ALIAS> 'docker pull decolua/9router:latest'`
      — Rollback: `docker pull decolua/9router:<PREV_TAG>`
- [ ] **WRITE**: `ssh <ALIAS> 'mkdir -p <HOST_DATA_DIR> && docker rm -f 9router 2>/dev/null; docker run -d \
        -p <PORT>:20128 \
        -v <HOST_DATA_DIR>:/app/data \
        -e DATA_DIR=/app/data \
        --env-file <HOST_ENV_PATH> \
        --name 9router \
        decolua/9router:latest'`
      — Rollback: `docker rm -f 9router; docker run ... decolua/9router:<PREV_TAG>`
- [ ] Verify: `ssh <ALIAS> 'docker logs --tail 50 9router; docker ps --filter name=9router'`

### 4C. Mode C — Docker Compose (recommended, servers)

- [ ] Copy `templates/docker-compose.yml` (or `docker-compose.headroom.yml` if
      Headroom chosen) to the host as `<COMPOSE_DIR>/docker-compose.yml`.
      Fill `<PORT>` and `<HOST_DATA_DIR>` / env_file path.
      — **WRITE**: `scp templates/docker-compose.yml <ALIAS>:<COMPOSE_DIR>/docker-compose.yml`
      — Rollback: restore previous compose file as `docker-compose.yml.prev-*`.
- [ ] Place the env file: `scp secrets/.env <ALIAS>:<COMPOSE_DIR>/.env`
      (or bind-mount path referenced by compose `env_file`).
- [ ] **WRITE**: `ssh <ALIAS> 'cd <COMPOSE_DIR> && docker compose pull && docker compose up -d'`
      — Rollback: `docker compose down; docker compose up -d` with previous
        image tag / compose file.
- [ ] If Headroom sidecar:
      - Compose includes `headroom` service (`ghcr.io/chopratejas/headroom:latest`)
        and sets `HEADROOM_URL=http://headroom:8787` on the 9router service.
      - On Linux with Headroom on the host (not sidecar): add
        `extra_hosts: ["host.docker.internal:host-gateway"]` and use
        `HEADROOM_URL=http://host.docker.internal:8787` — see DOCKER.md.
      - Verify: `ssh <ALIAS> 'docker compose ps; docker logs --tail 30 headroom 2>/dev/null'`
- [ ] Verify: `ssh <ALIAS> 'docker compose ps; docker logs --tail 50 9router'`

### 4D. Mode D — Source + systemd / pm2 (VPS without Docker)

- [ ] **WRITE**: `ssh <ALIAS> 'git clone https://github.com/decolua/9router.git <APP_DIR> || (cd <APP_DIR> && git fetch --all && git checkout master && git pull)'`
      — Rollback: `cd <APP_DIR> && git checkout <PREV_SHA>`
- [ ] **WRITE**: `ssh <ALIAS> 'cd <APP_DIR> && cp .env.example .env && npm install'`
      — then overwrite `.env` with the filled env from `secrets/` (same as §3.2).
      Note: the repo package is `9router-app` (private); source execution is
      the expected local-dev path — not `npm install 9router` from the repo root.
- [ ] **WRITE**: Build: `ssh <ALIAS> 'cd <APP_DIR> && npm run build'`
      — Rollback: keep previous `.next/` as `.next.prev-*`.
- [ ] **WRITE** (choose one):
      - **systemd** (template `systemd-9router.service`):
        `scp templates/systemd-9router.service <ALIAS>:/etc/systemd/system/9router.service`
        (fill `<APP_DIR>`, `<DATA_DIR>`, `<PORT>`, env), then
        `ssh <ALIAS> 'sudo systemctl daemon-reload && sudo systemctl enable --now 9router && systemctl is-active 9router'`
        — Rollback: `sudo systemctl disable --now 9router; sudo rm /etc/systemd/system/9router.service`
      - **pm2**: `ssh <ALIAS> 'pm2 start npm --name 9router -- start -- --port <PORT> && pm2 save && pm2 startup'`
        — Rollback: `pm2 delete 9router`
- [ ] Verify: `ssh <ALIAS> 'systemctl status 9router 2>/dev/null || pm2 status 2>/dev/null; curl -s http://127.0.0.1:<PORT>/api/health'`

## 5. Configure & harden (WRITE where noted)

### 5.1 Dashboard first-login (read + WRITE via UI/API)

- [ ] Open `http://<HOST>:<PORT>/dashboard` (or `https://<DOMAIN>/dashboard`
      if reverse-proxied). Log in with `INITIAL_PASSWORD`.
- [ ] **WRITE** — Change the dashboard password immediately (Dashboard → Settings).
      Store the new password only in `secrets/dashboard-password.txt`.
      — Rollback: reset via `INITIAL_PASSWORD` + `JWT_SECRET` rotation if needed.
- [ ] Record `BASE_URL` / `NEXT_PUBLIC_BASE_URL` decision:
      Prefer server-side `BASE_URL` / `CLOUD_URL` in production; compat
      `NEXT_PUBLIC_*` is UI-only. Set `BASE_URL=http://<HOST>:<PORT>` (or
      `https://<DOMAIN>` when proxied) so the internal sync scheduler can
      callback.

### 5.2 API key & auth hardening (WRITE, approval required)

- [ ] **Decide `REQUIRE_API_KEY`:**
      - `false` — localhost-only (default upstream; safe behind firewall).
      - **`true` — mandatory when internet-exposed** (any reverse-proxy / public
        port). Do not expose `/v1/*` without a Bearer key.
      - Set in `.env` / compose `environment`; restart required after change.
- [ ] **Decide `AUTH_COOKIE_SECURE`:**
      - `false` — HTTP / localhost.
      - `true` — behind HTTPS reverse proxy (set when TLS is terminated).
- [ ] **WRITE** — Create/rotate the 9Router API key (Dashboard → Keys →
      Generate). Store only in `secrets/9router-api-key.txt`; never in
      `runbook.md` / logs. This key becomes `NINEROUTER_KEY` for skill-based
      verification.
      — Rollback: previous key file `9router-api-key.prev-*`.
- [ ] **WRITE** — Apply env changes and restart:
      - Docker/compose: `docker restart 9router` / `docker compose restart 9router`
      - npm/source: `kill` + restart or `systemctl restart 9router`
      — Verify: unauthenticated `curl http://<HOST>:<PORT>/v1/models` → `401`
        when `REQUIRE_API_KEY=true`; authenticated → `200`.

### 5.3 Token-saver & endpoint tuning (via Dashboard, WRITE-annotated)

- [ ] Dashboard → Endpoint → Token Saver: confirm **RTK** default ON (saves
      20–40% input tokens). Toggle per run if the operator wants it off.
- [ ] Headroom (if sidecar): Dashboard → Endpoint → Token Saver → Headroom →
      URL `http://headroom:8787` (compose network) or
      `http://host.docker.internal:8787` — recheck status → enable. Fails open
      if Headroom is down.
- [ ] Ponytail (Lazy Senior Dev: Lite/Full/Ultra) + Caveman (up to 65% output
      savings): Dashboard → Endpoint → Ponytail / Caveman — enable per
      operator preference. Stacks with RTK.
- [ ] Per-request bypass if needed: `X-9Router-Token-Saver: off` header.

## 6. Reverse proxy & firewall (WRITE, approval required — only if exposed)

- [ ] Choose proxy: **Nginx** (template `nginx-9router.conf`) / **Dokploy
      Traefik** (compose labels) / **Caddy** (reverse_proxy) / **Cloudflare
      Tunnel**. Record choice in `plan.md`.
- [ ] **WRITE** — Nginx (example):
      - Copy `templates/nginx-9router.conf` to `<ALIAS>:/etc/nginx/sites-available/9router`,
        fill `<DOMAIN>` and `proxy_pass http://127.0.0.1:<PORT>`, enable
        `ln -s sites-available/9router sites-enabled/9router`, add TLS cert
        (Let's Encrypt / existing), `nginx -t && systemctl reload nginx`.
      - Rollback: `rm sites-enabled/9router; nginx -t && systemctl reload nginx`.
- [ ] **WRITE** — Firewall: allow `80/443` only; keep `<PORT>` firewalled
      unless localhost-only is intended.
      ```bash
      ssh <ALIAS> 'sudo ufw allow 80/tcp; sudo ufw allow 443/tcp; sudo ufw deny <PORT>/tcp 2>/dev/null; sudo ufw status'
      ```
      — Rollback: `sudo ufw delete allow 80/tcp` etc.; restore previous `ufw status`.
- [ ] Verify (read):
      ```bash
      curl -s https://<DOMAIN>/api/health                         # {"ok":true}
      curl -s https://<DOMAIN>/v1/models -H "Authorization: Bearer <KEY>" | head -c 500
      echo | openssl s_client -connect <DOMAIN>:443 -servername <DOMAIN> 2>/dev/null | openssl x509 -noout -dates
      ```

## 7. Provider & combo management (via Dashboard; API alternative per skill)

> All provider/combo steps can be done in the Dashboard UI. The API
> alternative uses the skill's `NINEROUTER_URL` / `NINEROUTER_KEY` contracts.

- [ ] Dashboard → Providers → Connect desired providers per the operator's
      approved list (record choices in `plan.md`):
      - **OAuth** (Claude Code, Codex, GitHub Copilot, Cursor, Kimchi,
        Antigravity): browser OAuth → auto-refresh (store no secret locally).
      - **Free** (Kiro via AWS Builder ID / Google / GitHub; OpenCode Free
        no-auth; Vertex via GCP service-account JSON — store JSON only in
        `secrets/vertex-sa.json`).
      - **API-key** (GLM, MiniMax, Kimi, OpenAI, Anthropic, Gemini, DeepSeek,
        Groq, xAI, … — 40+): paste key → stored in 9Router's DB under
        `$DATA_DIR/db/data.sqlite`, not in this repo.
      - **Self-hosted** (STT `/v1/audio/transcriptions`, TTS `/v1/audio/speech`,
        Embedding `/v1/embeddings`): set `providerSpecificData.baseUrl` per
        the README table; `baseUrl` must include `/v1` for embeddings.
- [ ] For each **self-hosted STT/TTS/Embedding** connection, validate the
      `baseUrl` contract (see gotcha G7): STT = full `/v1/audio/transcriptions`
      URL; TTS = server root; Embedding = OpenAI base with `/v1`.
- [ ] Dashboard → Combos → Create combos per the operator's fallback policy
      (e.g. `premium-coding`: `cc/claude-opus-4-7` → `glm/glm-5.1` →
      `minimax/MiniMax-M2.7`; `free-forever`: `kr/claude-sonnet-4.5` → `kr/glm-5` →
      `vertex/gemini-3.1-pro-preview`). Name combos explicitly; combos are the
      model IDs clients will use.
- [ ] **API alternative** (reads): list available models per kind (skill):
      ```bash
      export NINEROUTER_URL="http://<HOST>:<PORT>"   # or https://<DOMAIN>
      export NINEROUTER_KEY="$(cat executions/9router/secrets/9router-api-key.txt)"
      curl -s $NINEROUTER_URL/v1/models -H "Authorization: Bearer $NINEROUTER_KEY" | head -c 3000
      curl -s $NINEROUTER_URL/v1/models/image        -H "Authorization: Bearer $NINEROUTER_KEY" | head -c 2000
      curl -s $NINEROUTER_URL/v1/models/tts          -H "Authorization: Bearer $NINEROUTER_KEY" | head -c 2000
      curl -s $NINEROUTER_URL/v1/models/embedding    -H "Authorization: Bearer $NINEROUTER_KEY" | head -c 2000
      curl -s $NINEROUTER_URL/v1/models/web          -H "Authorization: Bearer $NINEROUTER_KEY" | head -c 2000
      ```
      Use `data[].id` as the `model` field in chat requests. Combos appear with
      `owned_by:"combo"`.

## 8. Verification (reads; per the 9Router skill)

Run via `scripts/health-check.sh` or manually:

- [ ] Health (skill §Setup):
      `curl -s $NINEROUTER_URL/api/health` → `{"ok":true}`
- [ ] Auth gate (if `REQUIRE_API_KEY=true`): unauthenticated `/v1/models` → `401`;
      authenticated → `200` with a `data` list
- [ ] Dashboard: `curl -s $NINEROUTER_URL/dashboard -o /dev/null -w "%{http_code}\n"` → `200`
- [ ] OpenAI-compat probe (skill §Setup / capability `9router-chat`):
      ```bash
      # Fetch capability skill if testing chat:
      # https://raw.githubusercontent.com/decolua/9router/refs/heads/master/skills/9router-chat/SKILL.md
      curl -s $NINEROUTER_URL/v1/chat/completions \
        -H "Authorization: Bearer $NINEROUTER_KEY" \
        -H "Content-Type: application/json" \
        -d '{"model":"<MODEL_OR_COMBO_ID>","messages":[{"role":"user","content":"ping"}]}' \
        | head -c 2000
      # expect: choices[0].message.content contains a reply (or stream if requested)
      ```
- [ ] Client integration smoke (pick one the operator uses):
      - Claude Code: `~/.claude/config.json` with `anthropic_api_base` → chat works
      - Codex: `OPENAI_BASE_URL=$NINEROUTER_URL` → `codex "ping"` works
      - Cursor / Cline / Continue: OpenAI-compatible base URL → model appears
      - OpenClaw: `~/.openclaw/openclaw.json` provider `9router` with `baseUrl` `http://127.0.0.1:<PORT>/v1`
- [ ] Token-saver sanity: send a request that includes a `tool_result` with a
      `git diff` payload; confirm the response still succeeds and usage is
      reported; bypass once with `X-9Router-Token-Saver: off` to compare.
- [ ] Record all verification outputs (redact keys) in `logs/<timestamp>-verify.log`
      and in the runbook.

## 9. Operational lifecycle (ongoing)

### 9.1 Backup (read-heavy; WRITE only for the artifact)

- [ ] **WRITE** — SQLite backup (do not copy a live DB without care; see G9):
      ```bash
      # Preferred: sqlite3 hot backup (if sqlite3 present on host/container):
      ssh <ALIAS> 'sqlite3 <DATA_DIR>/db/data.sqlite ".backup <DATA_DIR>/db/data.sqlite.bak.$(date +%F)" && ls -lh <DATA_DIR>/db/data.sqlite.bak.*'
      # Fallback (stop-then-copy for a consistent snapshot):
      # Docker: docker compose stop 9router && cp <HOST_DATA_DIR>/db/data.sqlite <BACKUP_PATH> && docker compose start 9router
      ```
      Store the backup path + timestamp in the runbook. Also capture
      `.env` (redacted) and `docker-compose.yml` alongside the DB copy.
- [ ] Keep at least one known-good backup before any upgrade or migration.
      Execution-folder artifacts: `secrets/` already contains the key material
      needed to decrypt/restore; back it up alongside the DB (gitignored).

### 9.2 Restore (WRITE, approval required)

- [ ] **WRITE** — Stop 9Router, restore the SQLite file, restart:
      ```bash
      ssh <ALIAS> 'cd <COMPOSE_DIR> && docker compose stop 9router || docker stop 9router || systemctl stop 9router'
      scp <BACKUP_SQLITE> <ALIAS>:<DATA_DIR>/db/data.sqlite
      ssh <ALIAS> 'cd <COMPOSE_DIR> && docker compose start 9router || docker start 9router || systemctl start 9router; sleep 3; curl -s http://127.0.0.1:<PORT>/api/health'
      ```
      — Pre-restore: take a fresh backup of the current DB (so the restore
        itself is reversible). Record both paths in the runbook.
      — Rollback: restore the pre-restore backup.

### 9.3 Update / upgrade (WRITE, approval required)

- [ ] Check current vs latest:
      ```bash
      ssh <ALIAS> 'docker inspect 9router --format "{{.Config.Image}}" 2>/dev/null; 9router --version 2>/dev/null; npm view 9router version 2>/dev/null'
      curl -s https://registry.hub.docker.com/v2/repositories/decolua/9router/tags?page_size=5 | head -c 3000
      ```
- [ ] **WRITE** — Take a backup first (§9.1) — mandatory before any upgrade.
- [ ] **WRITE** — Branch:
      - **Docker / compose**: `ssh <ALIAS> 'cd <COMPOSE_DIR> && docker compose pull && docker compose up -d'`  (or `docker pull decolua/9router:latest && docker rm -f 9router && docker run ...` for mode B)
      - **npm global**: `ssh <ALIAS> 'npm install -g 9router@latest'`
      - **Source**: `ssh <ALIAS> 'cd <APP_DIR> && git pull && npm install && npm run build && pm2 restart 9router || systemctl restart 9router'`
      — Rollback: re-pull / re-install the previous tag/version recorded in
        the runbook + restore the pre-upgrade DB backup if the new version
        migrated the schema.
- [ ] Verify post-upgrade: re-run §8 probes; confirm `/api/health` and at
      least one chat completion still succeed.

### 9.4 Observability & ops

- [ ] Logs:
      - Docker: `ssh <ALIAS> 'docker logs --tail 200 9router; docker logs --tail 100 headroom 2>/dev/null'`
      - Source/pm2: `pm2 logs 9router --lines 200` / `journalctl -u 9router -n 200`
      - Request debug logs: `ENABLE_REQUEST_LOGS=true` in `.env` → logs under
        `logs/` inside `DATA_DIR`; enable only when triaging (verbose + disk).
- [ ] Usage analytics: Dashboard → Usage / Analytics — token, cost, and trend
      panels. Note: dashboard "cost" is a tracking estimate, not billing;
      9Router itself never charges.
- [ ] Cloud Sync: if enabled, confirm `BASE_URL` / `CLOUD_URL` (server-side)
      are set to the public base URL; verify sync jobs are not hanging on
      DNS/timeout (logs show fail-fast behavior).
- [ ] Migrations between hosts: `scp secrets/* <NEW_ALIAS>:` + `backup.sh`
      artifact + `.env` + `docker-compose.yml`; follow §9.2 on the destination.

## 10. Verification & rollback gate

- [ ] Re-run `scripts/health-check.sh` (or §8 manual probes) — health OK,
      auth gate correct, at least one model responds to `chat/completions`
- [ ] Confirm every **WRITE** executed this run has a rollback recorded in the
      runbook (secrets `*.prev-*`, `.env.prev-*`, compose prev, image prev
      tag, DB backup path, proxy/firewall revert)
- [ ] Confirm `git status` in the repo shows no `executions/` or `*.pem` /
      `*.key` / `.tfvars` / `.crt` leaks (AGENTS.md §7 check):
      `git status; git ls-files --cached --others --exclude-standard | ForEach-Object { if (Test-Path $_) { $c=Get-Content $_ -Raw; if ($c -match "tskey-|BEGIN (CERTIFICATE|PRIVATE|RSA)") { Write-Output "LEAK: $_" } } }`
- [ ] Findings → execution's `notes.md` (append, newest at top/bottom with
      date header); propose lesson promotion to the playbook's `notes/gotchas.md`
      (operator approves promotion, never mid-run)
- [ ] Mark runbook steps `done` / `blocked+explained`; close the run

---

## Authoring rules

- Steps must be copy-paste executable with placeholders filled (`<ALIAS>`,
  `<PORT>`, `<HOST>`, `<DOMAIN>`, `<DATA_DIR>`, `<COMPOSE_DIR>`, `<APP_DIR>`).
- Flag every step that WRITES to a production system with **WRITE** in bold.
- Add rollback instructions for every write step.
- After each run, promote lessons into `notes/` (via the operator, never mid-run).
