---
name: bifrost
description: Deploy, configure, harden, and operate a Bifrost AI gateway (OpenAI-compatible LLM/MCP gateway) on Docker, Dokploy, or Kubernetes. Use for fresh installs, provider and virtual-key setup, domain/TLS, backup/restore, pinned upgrades, source builds, and health checks. Not for creating upstream provider accounts or Enterprise SSO/guardrail design.
---

# Skill: Bifrost AI Gateway — Procedure

Canonical steps for a run. **Placeholders only** — never real IPs, hostnames,
usernames, or credentials. Real values go in the execution's `plan.md`,
`inventory.md`, and `secrets/`. Repo rules (folder discipline, secrets,
committing): see `AGENTS.md`.

Conventions: every step that WRITES to a production system is flagged
**WRITE** and needs approval per the run's permission mode (A: per-write
confirm / B: plan-as-approved). Rollback is given for every write. Reads are
free. Execution folder is persistent per variant: `executions/bifrost/` or
`executions/bifrost-<suffix>/`; `logs/` is append-only with
timestamp-prefixed files.

> **Docs-first rule:** Bifrost docs move fast and versions matter (snippets
> differ between v1.4/v1.5/v2.x). Before any config, verify, or API step,
> consult references/sources.md` and fetch the live page (never improvise schema).
> Pin the Bifrost version in `plan.md` and check changelogs before upgrades:
> `https://docs.getbifrost.ai/changelogs/`.

---

## 0. Pre-flight (mandatory, every run)

- [ ] Read references/gotchas.md` (G1–G8 may change how you plan) and
  references/sources.md` (docs index for this run's topics)
- [ ] Confirm prerequisites (README): SSH alias `<ALIAS>`, tooling for the
  chosen mode, free port `<PORT>` (default `8080`), domain/TLS choice if
  exposed, operator-available secrets
- [ ] Confirm access (read):
  `ssh -o BatchMode=yes <ALIAS> 'hostname; whoami; ss -tlnp | head -n 20'`
- [ ] Scan `executions/` for `bifrost` / `bifrost-<suffix>` folders and legacy
  dated folders containing `bifrost`; present matches to the operator: reuse
  or create new variant with suffix `<SUFFIX>`
- [ ] Pin the Bifrost version for this run (e.g. `<TAG>` like `v2.4.0`;
  check `https://docs.getbifrost.ai/changelogs/`). Record in plan + runbook
- [ ] Record the run's permission mode in the runbook (AGENTS.md §1.3:
  operator sets A per-write confirm / B plan-as-approved at plan approval)

## 1. Discover current state (reads only)

- [ ] Existing install — which mode, if any:
  ```bash
  ssh <ALIAS> 'docker ps -a --filter name=bifrost --format "{{.Names}} {{.Image}} {{.Status}} {{.Ports}}" 2>/dev/null; echo "---"; which bifrost 2>/dev/null; npx -y @maximhq/bifrost --version 2>/dev/null | head -n 5; echo "---"; ss -tlnp 2>/dev/null | grep -E ":8080"; echo "---"; ls -la ~/.config/bifrost/ 2>/dev/null; ls -la /app/data/ 2>/dev/null; ls -la ./data/ 2>/dev/null; cat docker-compose.yml 2>/dev/null | head -n 60; echo "---"; helm list -A 2>/dev/null | grep -i bifrost; kubectl get statefulset,deployment,svc,pvc -l app.kubernetes.io/name=bifrost -A 2>/dev/null | head -n 20'
  ```
- [ ] Config and env on host (read only; never echo secrets):
  ```bash
  ssh <ALIAS> 'ls -la <APP_DIR>/ 2>/dev/null; echo "---"; cat <APP_DIR>/config.json 2>/dev/null | head -n 60; echo "---"; env | grep -i "BIFROST\|APP_PORT\|APP_HOST\|APP_DIR\|LOG_LEVEL" 2>/dev/null | grep -v TOKEN | head -n 20'
  ```
  (`<APP_DIR>`: npx default `~/.config/bifrost`; Docker `/app/data` mount)
- [ ] Reverse-proxy state (if exposed):
  ```bash
  ssh <ALIAS> 'cat /etc/nginx/sites-enabled/* 2>/dev/null | grep -A8 -i bifrost | head -n 60; echo "---"; ss -tlnp 2>/dev/null | grep -E ":80|:443"'
  ```
- [ ] Live health (if running):
  ```bash
  curl -s http://<HOST>:<PORT>/health            # 200 when ready, 503 on store failure
  curl -s http://<HOST>:<PORT>/v1/models | head -c 1000
  curl -s http://<HOST>:<PORT>/metrics | head -c 500   # telemetry plugin, default on
  ```
- [ ] Record in runbook: mode (A/B/C/D/E/none), image tag or transport
  version, `<APP_DIR>` contents (`config.json`? `config.db`? `logs.db`?),
  health result, proxy presence. Note previous tag + `<APP_DIR>` + DB paths
  for rollback (no secret values).

## 2. Deployment-mode decision (ask the operator)

Ask explicitly; never assume.

- [ ] ASK: "Which mode for `<ALIAS>` — A (npx), B (docker run), C (compose),
  D (Helm/K8s), or E (source)? Pinned version `<TAG>`? Internet-exposed
  (needs dashboard password + enforced virtual keys + TLS) or
  localhost-only?"
- [ ] ASK: "Config mode — DB-backed Web UI (default, `config.json` seeds DB)
  or file-only GitOps (`config_store.enabled:false`, restart to apply)?"
  (see references/sources.md` → config-json)
- [ ] ASK: "Backing stores — SQLite (default, persist `/app/data`) or
  Postgres v16+ UTF8 (`config_store`/`logs_store`)? Vector store for semantic
  cache (redis/weaviate/qdrant/pinecone)?"
- [ ] Record mode + version + config mode + stores + exposure in runbook and
  `plan.md`. **Must happen before any WRITE.**

## 3. Prepare host (reads + gated writes)

### 3.1 Host prerequisites (read)

- [ ] OS/arch: `ssh <ALIAS> 'uname -a; cat /etc/os-release 2>/dev/null | head -n 5'`
- [ ] Docker (B/C): `ssh <ALIAS> 'docker --version; docker compose version'`
- [ ] Node (A): `ssh <ALIAS> 'node --version; npm --version'`
- [ ] Helm/kubectl (D): `ssh <ALIAS> 'helm version; kubectl version --client'`
- [ ] Go (E): `ssh <ALIAS> 'go version'` (must match Bifrost's pinned Go,
  currently 1.27.x — check repo `go.mod`; plugins need same version + arch)
- [ ] Ports free: `ssh <ALIAS> 'ss -tlnp | grep -E ":<PORT>" || echo "port free"'`
- [ ] Disk: `ssh <ALIAS> 'df -h /home /var/lib 2>/dev/null | head -n 5'`

### 3.2 Secrets prep (WRITE, approval required)

- [ ] **Backup**: if execution `secrets/` already holds values, keep previous
  as `<name>.prev-<timestamp>` before regenerating.
- [ ] **WRITE**: generate and store (only in
  `executions/bifrost[-<suffix>]/secrets/`, never in plan/runbook/logs):
  ```bash
  openssl rand -base64 32   # BIFROST_ENCRYPTION_KEY (stable across restarts/upgrades/restores)
  openssl rand -hex 32      # BIFROST_SETUP_TOKEN (first admin account only)
  ```
  Provider API keys come from the operator (or their vault), one file per
  key. Postgres passwords likewise.
  - Rollback: restore `.prev-<timestamp>` files.
- [ ] Record secret *names/locations* (not values) in `plan.md`.

## 4. Install (WRITE, approval required; branch on section 2)

#### 4A. npx (workstation/eval)

- [ ] **WRITE**: `ssh <ALIAS> 'npx -y @maximhq/bifrost --transport-version <TAG> -app-dir <APP_DIR> -port <PORT>'`
  (first run foreground to confirm `successfully started bifrost`, then
  background via terminal multiplexer / service manager)
  - Rollback: stop process; `rm -rf <APP_DIR>` only with operator approval
    (destroys local DB).
- [ ] Verify: `curl -s http://127.0.0.1:<PORT>/health` → `200`.

#### 4B. Docker run (one-shot server)

- [ ] **WRITE**: pull pinned tag:
  `ssh <ALIAS> 'docker pull maximhq/bifrost:<TAG>'`
  - Rollback: `docker pull maximhq/bifrost:<PREV_TAG>`.
- [ ] **Backup**: if a container/data dir exists, back it up (section 9.1).
- [ ] **WRITE**:
  ```bash
  ssh <ALIAS> 'mkdir -p <HOST_DATA_DIR> && docker rm -f bifrost 2>/dev/null; docker run -d \
    -p <PORT>:8080 -v <HOST_DATA_DIR>:/app/data \
    -e APP_PORT=8080 -e APP_HOST=0.0.0.0 \
    -e LOG_LEVEL=info -e LOG_STYLE=json \
    -e BIFROST_ENCRYPTION_KEY -e BIFROST_SETUP_TOKEN \
    --name bifrost maximhq/bifrost:<TAG>'
  ```
  (Secrets reach the container via env from the execution `secrets/` —
  never on a shared command line; prefer `--env-file <path>` with `0600`.)
  - Rollback: `docker rm -f bifrost`, re-run with `<PREV_TAG>`.
- [ ] Verify: `ssh <ALIAS> 'docker ps --filter name=bifrost; docker logs --tail 30 bifrost'`

#### 4C. Docker Compose (recommended for servers)

- [ ] **Backup**: if compose/data files exist, copy to
  `docker-compose.yml.prev-<timestamp>` and back up data (section 9.1).
- [ ] **WRITE**: copy `templates/docker-compose.yml` to
  `<COMPOSE_DIR>/docker-compose.yml`; set `image: maximhq/bifrost:<TAG>`,
  `<PORT>`, `<HOST_DATA_DIR>`, env (`APP_PORT/APP_HOST/LOG_LEVEL/LOG_STYLE`,
  `BIFROST_ENCRYPTION_KEY`, `BIFROST_SETUP_TOKEN` via env_file `0600`):
  `scp templates/docker-compose.yml <ALIAS>:<COMPOSE_DIR>/docker-compose.yml`
  - Rollback: restore `docker-compose.yml.prev-<timestamp>`.
- [ ] **WRITE**: `ssh <ALIAS> 'cd <COMPOSE_DIR> && docker compose pull && docker compose up -d'`
  - Rollback: `docker compose down; docker compose up -d` with previous tag/file.
- [ ] Verify: `ssh <ALIAS> 'cd <COMPOSE_DIR> && docker compose ps; docker logs --tail 40 bifrost'`

#### 4D. Helm/Kubernetes

- [ ] **WRITE**: create encryption-key secret (**WRITE**, approval required):
  ```bash
  ssh <ALIAS> 'kubectl create secret generic bifrost-encryption-key --from-file=encryption-key=<KEY_FILE> --dry-run=client -o yaml | kubectl apply -f -'
  ```
  (`<KEY_FILE>` holds the value from execution `secrets/`; never inline it.)
  - Rollback: `kubectl delete secret bifrost-encryption-key` (only if created this run).
- [ ] **WRITE**:
  ```bash
  helm repo add bifrost https://maximhq.github.io/bifrost/helm-charts; helm repo update
  helm install bifrost bifrost/bifrost --set image.tag=<TAG> \
    --set bifrost.encryptionKeySecret.name=bifrost-encryption-key \
    --set bifrost.encryptionKeySecret.key=encryption-key
  ```
  (`image.tag` is required — the chart will not start without it. See
  references/sources.md` → helm values/storage for Postgres, providers,
  governance, plugins.)
  - Rollback: `helm uninstall bifrost` (+ delete PVC only with operator
    approval — **destroys data**).
- [ ] Verify: `kubectl rollout status statefulset/bifrost; kubectl logs -l app.kubernetes.io/name=bifrost --tail=50`

#### 4E. Source + systemd (full control / custom plugins)

- [ ] **WRITE**: `ssh <ALIAS> 'git clone https://github.com/maximhq/bifrost.git <APP_SRC> && cd <APP_SRC> && git checkout <GIT_REF_FOR_TAG> && go build -o /usr/local/bin/bifrost ./transports/bifrost-http'`
  (default branch is `dev`; check out the ref matching `<TAG>`)
  - Rollback: `rm /usr/local/bin/bifrost`; `git -C <APP_SRC> checkout <PREV_SHA>`.
- [ ] **WRITE**: install systemd unit + env file (`0600`, values from
  execution `secrets/`), then
  `ssh <ALIAS> 'sudo systemctl daemon-reload && sudo systemctl enable --now bifrost && systemctl is-active bifrost'`
  - Rollback: `sudo systemctl disable --now bifrost`.
- [ ] Verify: `curl -s http://127.0.0.1:<PORT>/health`

## 5. Configure providers and config modes

All values with secrets use `env.` references (never plaintext keys):
`"value": "env.OPENAI_API_KEY"` → env var `OPENAI_API_KEY`. See
references/sources.md` → config-json/providers.

- [ ] Decide config mode (from section 2) and apply:
  - DB-backed (default): `config.json` seeds the SQLite/Postgres config
    store at startup; UI/API edits persist in DB. `source_of_truth:
    "split"` default; `"config.json"` only to force file-wins.
  - File-only GitOps: `"config_store": {"enabled": false}` — file is the
    only source, UI config edits disabled, restart to apply.
- [ ] **Backup**: before editing `config.json` or provider state via UI/API,
  back up `<APP_DIR>/config.json` + DB (section 9.1).
- [ ] **WRITE**: seed providers — minimal `config.json` (see
  `templates/config.json.example`):
  ```json
  {
    "$schema": "https://www.getbifrost.ai/schema",
    "encryption_key": "env.BIFROST_ENCRYPTION_KEY",
    "client": { "drop_excess_requests": false, "enable_logging": true },
    "providers": {
      "openai": { "keys": [{ "name": "openai-primary", "value": "env.OPENAI_API_KEY", "models": ["*"], "weight": 1.0 }] }
    }
  }
  ```
  Place at `<APP_DIR>/config.json` (`0600`) via scp; restart file-only
  instances. Or add via Web UI / `POST /api/providers` for DB-backed.
  - Rollback: restore previous `config.json` / DB backup; restart.
- [ ] **WRITE**: per-provider `network_config` (`max_retries` default 0 —
  set e.g. `3` with `retry_backoff_initial: 500`,
  `retry_backoff_max: 5000`), key weights (`weight: 0` = last resort;
  `models: []` = deny-all, `["*"]` = allow all; `blacklisted_models` wins).
  - Rollback: previous config/DB backup.
- [ ] **WRITE**: request fallbacks per call:
  `{"model": "openai/gpt-4o-mini", "fallbacks": ["anthropic/<model>", "bedrock/<model>"]}`
  (each fallback gets its own retry budget).
  - Rollback: remove `fallbacks` from the caller.
- [ ] Verify: `scripts/health-check.sh http://<HOST>:<PORT>` (models list
  non-empty, chat completion returns `choices[0].message.content`).

## 6. Harden (WRITE, approval required)

- [ ] **WRITE**: dashboard auth — start with `BIFROST_SETUP_TOKEN` set, then
  Web UI → Workspace → Config → Security → enable password protection,
  create admin user, paste setup token. (Token is checked only at first
  admin creation; to fix a missed token, stop and restart with it set.)
  - Rollback: disable password protection in UI (operator present).
- [ ] **WRITE**: enforce inference auth for any exposed instance:
  `client.enforce_auth_on_inference: true` in `config.json` (or UI toggle
  "Enforce Virtual Keys on Inference"); restart file-only. Create virtual
  keys (section 7) and use them as Bearer tokens.
  - Rollback: set back to `false`; restart.
- [ ] **WRITE** (only if exposed): reverse proxy — copy
  `templates/nginx-bifrost.conf` to the proxy host, set `<DOMAIN>` and
  `proxy_pass http://127.0.0.1:<PORT>`, keep streaming-safe settings (no
  buffering, long timeouts for SSE), add TLS (Let's Encrypt/existing),
  `nginx -t && systemctl reload nginx`.
  - Rollback: remove vhost; `nginx -t && systemctl reload nginx`.
- [ ] **WRITE** (only if exposed): firewall — allow `80/443` only; keep
  `<PORT>` firewalled unless localhost-only is intended:
  `ssh <ALIAS> 'sudo ufw allow 80/tcp; sudo ufw allow 443/tcp; sudo ufw deny <PORT>/tcp; sudo ufw status'`
  - Rollback: restore saved `ufw status` rules.
- [ ] Verify (reads):
  ```bash
  curl -s https://<DOMAIN>/health
  curl -s http://<HOST>:<PORT>/v1/models | head -c 300
  curl -s http://<HOST>:<PORT>/v1/models -H "Authorization: Bearer <VK>" | head -c 300
  ```

## 7. Governance: virtual keys, budgets, rate limits

Enforcement requires `enforce_auth_on_inference: true`. Keys (`sk-bf-*`)
are accepted via `Authorization: Bearer`, `x-bf-vk`, `x-api-key`,
`x-goog-api-key`, `api-key`. See references/sources.md` → governance.

- [ ] **Backup**: DB backup (section 9.1) before changing keys/budgets.
- [ ] **WRITE**: create virtual key (UI or API):
  ```bash
  curl -s -X POST http://<HOST>:<PORT>/api/governance/virtual-keys \
    -H 'Content-Type: application/json' -d '{
      "name": "<KEY_NAME>", "team_id": "<TEAM_ID>",
      "provider_configs": [{"provider": "openai", "allowed_models": ["gpt-4o-mini"], "key_ids": ["*"]}],
      "budgets": [{"max_limit": 100.0, "reset_duration": "1M"}],
      "rate_limit": {"token_max_limit": 10000, "token_reset_duration": "1h",
                     "request_max_limit": 100, "request_reset_duration": "1m"},
      "is_active": true }'
  ```
  Store the returned key only in execution `secrets/`.
  - Rollback: deactivate/delete the key in UI/API or restore DB backup.
- [ ] Verify: unauthenticated `/v1/models` → `401 virtual_key_required`;
  wrong-scope model → `403 model_blocked`; over budget → `402
  budget_exceeded`; over rate → `429`. `GET /v1/models` with a VK lists only
  allowed providers.

## 8. Semantic cache, MCP, integrations, observability

- [ ] Semantic cache (**WRITE**): requires a vector store even for
  direct-only mode. Nothing caches without `x-bf-cache-key` (or
  `default_cache_key`); writes are async (first request always misses);
  identity-scoped per VK by default. Minimal plugin config sets `provider` +
  `embedding_model` + `dimension` (changing them later needs a fresh
  `vector_store_namespace`). Invalidate via
  `DELETE /api/cache/clear/{id}` or `/api/cache/clear-by-key/{key}`.
  - Rollback: disable plugin / remove cache headers.
  - Verify: same request twice with `x-bf-cache-key` → second has
    `x-bifrost-cache: HIT` (check `extra_fields.cache_debug`).
- [ ] MCP gateway (**WRITE**): add client configs
  (`connection_type: stdio|http|sse`, `tools_to_execute`, optional
  `is_code_mode_client: true` for Code Mode). Gateway serves
  `POST /mcp` + `GET /mcp` (SSE); per-request narrowing via
  `x-bf-mcp-include-tools`; behind a proxy set `mcp_external_client_url`
  before connecting OAuth clients. Claude Desktop:
  `{"mcpServers": {"bifrost": {"url": "http://<HOST>:<PORT>/mcp"}}}`.
  - Rollback: remove client config; restart file-only.
  - Verify: `POST /v1/chat/completions` suggests tools →
    `POST /v1/mcp/tool/execute` runs with approval (auto mode via
    `tools_to_auto_execute`, gateway-only).
- [ ] Drop-in SDKs (read/verify): `/openai`, `/anthropic`, `/genai`,
  `/bedrock` base URLs + virtual key as `api_key`; include
  `server.base_path` in base_url when set; filter model listing with
  `x-bf-list-models-provider`. One-line client change, no server write.
- [ ] Observability (read; **WRITE** only to enable plugins): `GET /metrics`
  (Prometheus, default on; needs admin Basic auth or Metrics-permission key
  when `auth_config` enabled); process logs via `LOG_LEVEL`/`LOG_STYLE`;
  per-request logs in logs store (`client.logRetentionDays` default 365);
  OTel/Datadog/Kafka/BigQuery via plugin config.
  - Verify: `curl -s http://<HOST>:<PORT>/metrics | head -c 500`.

## 9. Backup, restore, upgrade

#### 9.1 Backup (WRITE — creates the artifact only)

- [ ] SQLite: back up the whole `<APP_DIR>` volume contents
  (`config.json`, `config.db`, `logs.db`) — quiesce first: prefer
  container stop or DB `.backup`; never hot-copy a live SQLite file
  without care. Helm: back up the StatefulSet PVC (`storage.persistence`,
  default 10Gi).
  ```bash
  ssh <ALIAS> 'cd <APP_DIR> && sqlite3 config.db ".backup config.db.bak-$(date +%F)" && ls -lh config.db.bak-*'
  # or: docker compose stop bifrost && cp -a <HOST_DATA_DIR> <BACKUP_PATH> && docker compose start bifrost
  ```
  Helper: `scripts/backup.sh`. Also capture redacted `config.json` (no
  secrets — secrets live in env/`secrets/`) and the image tag.
- [ ] Postgres: `pg_dump` the Bifrost database(s) (config + logs stores);
  role needs ownership; migrations run at startup under advisory lock.
- [ ] Always back up `BIFROST_ENCRYPTION_KEY` alongside the DB (same
  `secrets/` snapshot). Without it, encrypted values are unreadable.
  - Rollback: delete the backup artifact (live DB untouched).

#### 9.2 Restore (WRITE, approval required)

- [ ] **Backup**: take a fresh backup of the current DB first (section 9.1)
  so the restore is reversible. Record both paths.
- [ ] **WRITE**: stop Bifrost, restore files/DB, start:
  ```bash
  ssh <ALIAS> 'cd <COMPOSE_DIR> && docker compose stop bifrost || docker stop bifrost || systemctl stop bifrost'
  scp <BACKUP_SQLITE> <ALIAS>:<APP_DIR>/config.db
  ssh <ALIAS> 'cd <COMPOSE_DIR> && docker compose start bifrost || docker start bifrost || systemctl start bifrost; sleep 5; curl -s http://127.0.0.1:<PORT>/health'
  ```
  (Postgres: `pg_restore` into the Bifrost database, then start; startup
  runs migrations + `config.json` reconciliation by content hash.)
  - Rollback: restore the pre-restore backup.
- [ ] Verify: section 10 probes.

#### 9.3 Upgrade (WRITE, approval required)

- [ ] Read: current vs target (`docker inspect`, `helm list`, changelog
  `https://docs.getbifrost.ai/changelogs/` + release migration notes).
- [ ] **Backup**: section 9.1 (image tag + DB + encryption key). Mandatory.
- [ ] **WRITE** by mode: npx `--transport-version <NEW_TAG>`; Docker
  `pull maximhq/bifrost:<NEW_TAG>` + recreate; compose edit tag +
  `pull && up -d`; Helm `helm upgrade … --reuse-values --set
  image.tag=<NEW_TAG>`; source `git pull && go build && restart`.
  Deploy **one version at a time**; wait for `/health` 200 between hops.
  - Rollback: previous tag (`helm rollback` for Helm). **Migrations are not
    reversed by image rollback** — follow release migration notes before
    running an older binary against newer data.
- [ ] Verify: section 10 (health + non-streaming + streaming inference).

## 10. Modify from source (Go SDK, plugins, contributions)

- [ ] Go SDK (read/dev): `go get github.com/maximhq/bifrost/core`; implement
  the 3-method `Account` (`GetConfiguredProviders`, `GetKeysForProvider`,
  `GetConfigForProvider`); `bifrost.Init(ctx, schemas.BifrostConfig{...})`;
  `HTTPTransport*Hook`s never fire in Go SDK mode (use
  `PreRequestHook`/`PreLLMHook`/`PostLLMHook`).
- [ ] Custom plugin (**WRITE** on build host only): Go native `.so`
  (`go build -buildmode=plugin -o myplugin.so .`), Linux/macOS only, no
  cross-compilation, same Go version + arch as Bifrost; WASM deprecated.
  Export `Init`/`GetName` + hooks (`PreRequestHook` once per request,
  `PreLLMHook` per attempt, `PostLLMHook`, `Cleanup`, MCP hooks); set
  `placement` + `order` for sequencing.
  - Rollback: remove plugin from config; restart.
- [ ] Contribute upstream (dev workstation): see
  `https://docs.getbifrost.ai/contributing/setting-up-repo.md` (setup,
  conventions, PRs) and `adding-a-provider/configstore/logstore/
  vectorstore` pages; run `go test ./...` per `AGENTS.md` in that repo.
- [ ] Verify: plugin loads in startup logs; hook fires in request trace.

## 11. Verification and rollback gate

- [ ] Re-run `scripts/health-check.sh http://<HOST>:<PORT>` (health 200,
  auth gate correct, at least one model answers `chat/completions` over
  both non-streaming and streaming).
- [ ] Every **WRITE** this run has a rollback recorded in the runbook
  (previous image tag, `.prev-*` configs, DB backup path, proxy/firewall
  revert, vault/`secrets/` restore + restart).
- [ ] Leak check: `git status` shows no `executions/`, `secrets/`, `*.pem`,
  `*.key`, `.tfvars`, `.env`; no secret values in plan/runbook/logs.
- [ ] Findings → execution `notes.md`; propose promotion into playbook
  references/` (operator approves, never mid-run).
- [ ] Mark runbook steps `done` or `blocked` with a reason; close the run.

---

## Rollback (summary order)

1. Proxy + firewall: restore saved proxy config and `ufw` rules, reload.
2. Application: previous image tag/transport version, previous
   `config.json`/compose/manifest, restart.
3. Data: restore pre-change SQLite files or Postgres dump (section 9.2);
   restore `BIFROST_ENCRYPTION_KEY` from `secrets/` snapshot if rotated.
4. Governance: deactivate created keys / restore DB backup.

Stop and ask the operator if a rollback step is not covered here.

## Verify (summary)

`/health` is `200`; the auth gate returns `401` without a key and `200`
with one; the dashboard returns `200`; one `POST /v1/chat/completions`
(non-streaming and streaming) returns a reply; `/metrics` exposes Bifrost
series; provider/model listing reflects the intended allowlists.
