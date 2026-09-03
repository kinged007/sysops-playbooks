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
| `scripts/model-inventory.py` | Multi-provider inventory fetcher (google/opencode/cloudflare/ollama/openrouter/command_code) → `models.csv` with `supports_vision`/`supports_image_generation` |
| `scripts/model-inventory-cron.sh` | Cron wrapper for `model-inventory.py` — weekly Mon 15:00, logs to `executions/…/logs/`, optional `9router-sync` |
| `scripts/9router-sync.py` | Syncs `model-inventory` → 9Router (`/api/models/custom`, `/api/combos`) + regenerates `generated/` configs |
| `scripts/9router-sync-cron.sh` | Cron wrapper for `9router-sync.py` — weekly Mon 16:00, logs to `executions/…/logs/`, standalone (inventory already fetched at 15:00) |
| `templates/cron-9router-sync` | Crontab fragment — two jobs: 15:00 inventory + 16:00 sync (copy-paste for `crontab -e`) |
| `templates/systemd-9router-sync.service` | systemd unit for weekly sync (oneshot, calls `9router-sync-cron.sh`) |
| `templates/systemd-9router-sync.timer` | systemd timer — every Monday 16:00 (`OnCalendar=Mon *-*-* 16:00:00`, `Persistent=true`) |
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

## Automation: 9Router Sync

`playbooks/9router/scripts/9router-sync.py` keeps 9Router in sync with `model-inventory`.

- Source: `executions/9router/model-inventory/models.{json,csv}` (generated by `model-inventory.py`)
- Config: `executions/9router/9router-sync.config.yaml` (copy from `templates/9router-sync.config.example.yaml`; gitignored)
- Run: `python playbooks/9router/scripts/9router-sync.py --dry-run --verbose` (local) or cron/systemd
- What it does: global filter -> provider-mapped routed ids -> diff sync `/api/models/custom` + `/api/models/disabled` + `/api/combos` (only if diff) -> regenerate `generated/` CLI configs.
- Discovery: processes **every** `executions/*9router*/**/9router-sync*.yaml` found, writing outputs alongside each config.

## Automation: Model inventory weekly refresh (cron)

`playbooks/9router/scripts/model-inventory-cron.sh` is the cron-friendly wrapper for `model-inventory.py` (and `9router-sync.py` if present). It resolves the repo root, picks `python` (`.venv` preferred), handles locks, and logs to the execution folder so it works unattended from `crontab`.

- **Schedule:** every Monday at 15:00 (3pm) — `0 15 * * 1`
- **Script:** `playbooks/9router/scripts/model-inventory-cron.sh` (`chmod +x` on the host)
- **Config discovery:** auto-finds `executions/*9router*/**/model-inventory*.yaml` (prefers `executions/9router/model-inventory.config.yaml`); override with `--config PATH`
- **Logs:** `executions/9router/logs/<ISO>-model-inventory-cron.log` (append-only, one file per run) plus stdout for cron mail
- **Lock:** `flock /tmp/model-inventory-cron.lock` when available, else `mkdir` lock — prevents overlapping runs

**Install (host):**
```bash
# 1. make executable (once, on the Linux host — not needed on Windows checkout)
chmod +x /opt/sysops-playbooks/playbooks/9router/scripts/model-inventory-cron.sh

# 2. edit crontab (host time = Monday 15:00 local)
crontab -e
# add:
0 15 * * 1 /opt/sysops-playbooks/playbooks/9router/scripts/model-inventory-cron.sh >> /var/log/model-inventory-cron.log 2>&1

# 3. verify (dry-run, no writes):
/opt/sysops-playbooks/playbooks/9router/scripts/model-inventory-cron.sh --dry-run --verbose
ls -lh /opt/sysops-playbooks/executions/9router/logs/*model-inventory-cron.log
cat /opt/sysops-playbooks/executions/9router/model-inventory/models.csv | head -n 5
```

Other examples:
```bash
# explicit config + keep 9router untouched
./playbooks/9router/scripts/model-inventory-cron.sh --config executions/9router-prod/model-inventory.config.yaml --no-sync

# force verbose sync after inventory
./playbooks/9router/scripts/model-inventory-cron.sh --verbose
```

## Automation: 9Router weekly sync (cron — every Monday 16:00)

`playbooks/9router/scripts/9router-sync-cron.sh` is the standalone cron wrapper for `9router-sync.py`. It runs **one hour after** the inventory fetch (15:00 → 16:00) so the fresh `model-inventory` is already on disk. It also works standalone — if inventory is already fresh, it just syncs.

- **Schedule:** every Monday at 16:00 (4pm) — `0 16 * * 1` (see `templates/cron-9router-sync` and `templates/systemd-9router-sync.timer`)
- **Script:** `playbooks/9router/scripts/9router-sync-cron.sh` (`chmod +x` on the host)
- **Config discovery:** auto-finds `executions/*9router*/**/9router-sync*.yaml` (prefers `executions/9router/9router-sync.config.yaml`); override with `--config PATH`
- **What it does:** global filter → provider-mapped `oc`/`ocg`/`ollama`/`openrouter`/`cmc`/`gemini` ids → diff-guarded `POST/DELETE /api/models/custom` + `PUT/POST /api/combos` + regenerates `executions/<variant>/generated/` and `executions/<variant>/combos/*.json|*.csv`
- **Logs:** `executions/9router/logs/<ISO>-9router-sync-cron.log` (append-only) plus stdout for cron mail
- **Lock:** `flock /tmp/9router-sync-cron.lock` (fallback `mkdir`)

**Install — cron (host):**
```bash
# 1. make executable
chmod +x /opt/sysops-playbooks/playbooks/9router/scripts/9router-sync-cron.sh

# 2. edit crontab (host time = Monday 16:00 local)
crontab -e
# add (both jobs — 15:00 inventory + 16:00 sync):
0 15 * * 1 /opt/sysops-playbooks/playbooks/9router/scripts/model-inventory-cron.sh >> /var/log/model-inventory-cron.log 2>&1
0 16 * * 1 /opt/sysops-playbooks/playbooks/9router/scripts/9router-sync-cron.sh >> /var/log/9router-sync-cron.log 2>&1
# or use the fragment:
cat /opt/sysops-playbooks/playbooks/9router/templates/cron-9router-sync

# 3. verify (dry-run, no writes to 9Router):
/opt/sysops-playbooks/playbooks/9router/scripts/9router-sync-cron.sh --dry-run --verbose
ls -lh /opt/sysops-playbooks/executions/9router/logs/*9router-sync-cron.log
cat /opt/sysops-playbooks/executions/9router/combos/free.csv | head -n 10
ls -lh /opt/sysops-playbooks/executions/9router/generated/opencode.json
```

**Install — systemd timer (preferred on modern hosts):**
```bash
sudo cp /opt/sysops-playbooks/playbooks/9router/templates/systemd-9router-sync.service /etc/systemd/system/9router-sync.service
sudo cp /opt/sysops-playbooks/playbooks/9router/templates/systemd-9router-sync.timer /etc/systemd/system/9router-sync.timer
# Edit <USER> and <REPO_ROOT> in /etc/systemd/system/9router-sync.service
sudo systemctl daemon-reload
sudo systemctl enable --now 9router-sync.timer
systemctl list-timers 9router-sync.timer
journalctl -u 9router-sync -f

# Manual trigger:
sudo systemctl start 9router-sync.service
# Dry-run:
sudo -u <USER> /opt/sysops-playbooks/playbooks/9router/scripts/9router-sync-cron.sh --dry-run --verbose
```

Other examples:
```bash
# explicit config
./playbooks/9router/scripts/9router-sync-cron.sh --config executions/9router-prod/9router-sync.config.yaml --verbose

# cron on Windows (Task Scheduler) — run weekly Monday 16:00:
#   schtasks /create /tn "9Router Sync" /tr "powershell.exe -File C:\path\to\9router-sync-cron.sh" /sc weekly /d MON /st 16:00
```

Systemd timer alternative: call the same script from `ExecStart=`; it is timer-friendly (no TTY, no secrets on CLI — keys stay in `executions/…/secrets/`).
