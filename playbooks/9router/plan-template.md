# Plan: <RUN NAME>

| Field | Value |
|---|---|
| Client | <client> |
| Playbook | `9router` |
| Execution folder | `executions/9router/` or `executions/9router-<suffix>/` |
| Permission mode | **UNSET — set by operator at approval** (A: per-write confirm / B: plan-as-approved) |
| Status | draft → approved → executing → closed |

## Servers involved (THIS variant only)

| Alias (ssh config) | Role | Purpose | Access key |
|---|---|---|---|
| <alias> | app | 9Router host (single server; optionally fronted by its own reverse proxy) | `~/.ssh/<key>` |

If the run uses a reverse proxy that is the same host, note it inline
(e.g. `<alias> (also Nginx/Traefik on same host)`). A second alias is only
needed when the proxy is on a different machine — record it as a second row.

## Deployment mode (operator choice — §2 of playbook.md)

| Field | Value |
|---|---|
| Mode | <A npm global / B docker run / C docker compose / C+Headroom / D source+systemd / D source+pm2> |
| Exposure | <localhost-only / internet-exposed> |
| Reverse proxy | <none / Nginx / Dokploy Traefik / Caddy / Cloudflare Tunnel> |
| Domain (if exposed) | <DOMAIN> |
| Upstream port | <PORT> (default 20128; Headroom 8787 if sidecar) |
| DATA_DIR (host) | <HOST_DATA_DIR> (e.g. `~/.9router` or `/var/lib/9router`) |
| DATA_DIR (container) | `/app/data` (Docker B/C; must match env + mount) |
| Compose dir (if C) | <COMPOSE_DIR> |
| App dir (if D) | <APP_DIR> |
| Image tag (if B/C) | <TAG> (default `decolua/9router:latest`; pin for rollback) |
| Prev version/tag | <PREV> (for rollback) |

## Credentials / secrets (THIS variant only)

Files in `secrets/` of this execution folder; never inline values here.
Secrets persist in this folder across invocations — update in place when rotating.

| Secret | File in `secrets/` | Notes |
|---|---|---|
| JWT secret | `jwt-secret.txt` | `openssl rand -base64 48` |
| Dashboard initial password | `initial-password.txt` | rotated after first login |
| Dashboard current password | `dashboard-password.txt` | after first-login rotation |
| 9Router API key (NINEROUTER_KEY) | `9router-api-key.txt` | Dashboard → Keys; value for `Authorization: Bearer` |
| API key HMAC secret | `api-key-secret.txt` | `API_KEY_SECRET` |
| Machine ID salt | `machine-id-salt.txt` | `MACHINE_ID_SALT` |
| Vertex SA JSON (if used) | `vertex-sa.json` | GCP service-account JSON; gitignored |
| Tailscale / proxy token (if any) | `<token>.txt` | only if tailnet or CF tunnel used |
| Prev secrets | `*.prev-<timestamp>` | kept on rotation for rollback |

Env file on the host (`<COMPOSE_DIR>/.env` or `<APP_DIR>/.env` or
`<DATA_DIR>/.env`) is built from `templates/env.example` + these secrets.
The env file itself is never committed or logged (redact `SECRET/PASSWORD/KEY/TOKEN`).

## Steps

Numbered steps mirroring `runbook.md`, with **WRITE** flags. The operator
reviews this list at approval and sets the permission mode.

1. Pre-flight: fetch 9Router skill + read `notes/gotchas.md` (read)
2. Discover current state on `<alias>` — existing install, ports, health (read)
3. Decide deployment mode + exposure + proxy + Headroom (ask operator; read)
4. Prepare host: verify Docker/Node/ports/disk (read)
5. Prepare DATA_DIR + generate secrets into `secrets/` (**WRITE** — local secrets + remote DATA_DIR/env prep)
6. Install — branch on mode:
   - A: npm global (**WRITE** on `<alias>`)
   - B: docker run (**WRITE** on `<alias>`)
   - C: docker compose with or without Headroom (**WRITE** on `<alias>`)
   - D: source clone + build + systemd/pm2 (**WRITE** on `<alias>`)
7. Dashboard first-login + password rotation (read + **WRITE** via UI)
8. Harden API key + auth: `REQUIRE_API_KEY`, `AUTH_COOKIE_SECURE`, create API key (**WRITE** — env + restart)
9. Token-saver tuning (RTK/Headroom/Ponytail/Caveman) (read + **WRITE** via Dashboard)
10. Reverse proxy + firewall (if exposed) — Nginx/Traefik/Caddy + UFW (**WRITE** on `<alias>`)
11. Provider & combo management — connect providers + create combos (**WRITE** via Dashboard/API)
12. Verification: `/api/health`, `/v1/models/*`, `chat/completions` probe via the skill (read)
13. Operational handover: backup path, update procedure, log locations (read + **WRITE** for initial backup artifact)
14. Verification & rollback gate (read)

## Risk assessment

What could go wrong; blast radius; rollback plan:

- **Install failure (port taken / Docker missing / build tools missing):** blast
  radius = single host, no data loss. Rollback = stop/remove container or
  `npm uninstall`; restore previous compose/env from `*.prev-*`.
- **Env / secret misconfig (`DATA_DIR` mismatch, wrong `BASE_URL`):** volume not
  mounted or sync callbacks fail. Rollback = restore previous `.env` + restart.
- **Public exposure without `REQUIRE_API_KEY=true`:** bearerless access to
  `/v1/*` (cost/abuse). Mitigation: playbook forces the question at §2; the
  plan must set `REQUIRE_API_KEY=true` when `Exposure=internet-exposed`.
- **SQLite data loss on downgrade/upgrade:** schema drift. Mitigation: mandatory
  hot backup before any upgrade; restore via `scripts/restore.sh`.
- **Reverse-proxy misconfig (TLS / `proxy_pass`):** 502/404 on `/api` or `/v1`.
  Rollback = revert `nginx-9router.conf` / Traefik labels + reload.
- **Provider token leak:** never echo secrets in logs/runbook; `scripts/*`
  redact; git leak check at close-out.

## Approval

- [ ] Operator reviewed plan and set permission mode: <A or B>
- [ ] Operator approved deployment mode + exposure + proxy choice on <date>
- [ ] Operator confirmed secrets are available or may be generated into `secrets/`
- [ ] Operator approved execution on <date>
