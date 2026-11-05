# Gotchas — 9Router Proxy Manager (G1–G12)

Read BEFORE any run (mandated by README §0). Real pitfalls from setup
experience + upstream docs; each with symptom → cause → fix.

---

**G1 — `DATA_DIR` mismatch between env and mount (silent data loss)**

Symptom: 9Router starts but loses providers/combos after a restart or
`data.sqlite` is 0 bytes; `docker logs` shows `ENOENT` or a fresh DB.
Cause: `DATA_DIR` inside the container is always `/app/data` (Dockerfile),
but the host mount is e.g. `~/.9router`. If `.env` says `DATA_DIR=/var/lib/9router`
while compose mounts `~/.9router:/app/data`, the app writes to `/app/data`
(the volume) but the operator backs up the wrong host path.
Fix: keep `DATA_DIR=/app/data` in container env, mount the same host dir
everywhere (`env_file` + `volumes` agree), and record the chosen `HOST_DATA_DIR`
in `plan.md`. The playbook's §3.2 forces this.

---

**G2 — `9router-app` is a private npm package; source mode is clone+build, not `npm install 9router`**

Symptom: `npm install` inside a git clone fails with `403` or `package not found`
when trying to `npm install 9router` from the repo root.
Cause: the repo's `package.json` name is `9router-app` (private). The *published*
CLI is the separate `9router` package (the `cli/` subpackage). Source execution
means `git clone decolua/9router && npm install && npm run build && npm run start`.
Fix: follow the playbook's Mode D steps exactly; do not `npm install -g 9router`
from the repo root.

---

**G3 — `better-sqlite3` is optional; falls back to `sql.js`**

Symptom: `npm install` warns about `better-sqlite3` failing to compile (missing
Python/make/g++ / linux-headers) but the app still starts.
Cause: `better-sqlite3` is in `optionalDependencies` — `sql.js` (WASM) is the
fallback. The Dockerfile builder installs `python3 make g++ linux-headers` to
get the native addon, but a plain `npm install` without build tools is still
usable.
Fix: on build hosts, install build tools or accept the `sql.js` fallback; do
not treat the warning as a fatal failure. In Docker, the published image already
has the native addon built.

---

**G4 — Port mismatch: 20127 (dev) vs 20128 (production/Docker)**

Symptom: `curl http://localhost:20128/api/health` refuses to connect while the
dev server is on `20127`, or vice versa.
Cause: `package.json` dev script defaults to `20127`; Dockerfile + compose +
`custom-server.js` production default is `20128`. `PORT` in `.env` wins at
runtime.
Fix: always set `PORT=20128` explicitly in `.env` / compose `environment` /
systemd unit, and probe the port recorded in `plan.md` (`<PORT>`). The
`scripts/health-check.sh` takes `--url` so the probe matches the real port.

---

**G5 — `REQUIRE_API_KEY` defaults to `false` — internet-exposed must be `true`**

Symptom: `/v1/*` is reachable without a Bearer token from the public internet;
anyone can burn your provider quota.
Cause: upstream default is `REQUIRE_API_KEY=false` (safe for localhost-only).
The playbook's §2/§5.2 forces a decision: `true` when `Exposure=internet-exposed`.
Fix: set `REQUIRE_API_KEY=true` (and `AUTH_COOKIE_SECURE=true` behind HTTPS)
before exposing via Nginx/Traefik/Caddy. Verify: unauth `curl /v1/models` →
`401`, auth → `200`.

---

**G6 — `AUTH_COOKIE_SECURE=true` over plain HTTP breaks the dashboard session**

Symptom: after setting `AUTH_COOKIE_SECURE=true`, the dashboard login
succeeds but immediately redirects back to login (cookie never set).
Cause: `Secure` cookies are only sent over HTTPS; localhost HTTP with
`AUTH_COOKIE_SECURE=true` drops the session.
Fix: `AUTH_COOKIE_SECURE=false` for localhost/HTTP; `true` only when the
client reaches 9Router over HTTPS (reverse proxy or `https://` `BASE_URL`).

---

**G7 — `HEADROOM_URL` network scoping (compose vs host)**

Symptom: Headroom status in Dashboard shows "unreachable" despite the container
running.
Cause:
- Inside compose, 9Router must use `http://headroom:8787` (service name).
- From the host or when Headroom runs as a host process, the container must
  use `http://host.docker.internal:8787` + compose `extra_hosts:
  ["host.docker.internal:host-gateway"]` (Linux requirement).
Fix: pick one wiring and keep it; the playbook's `docker-compose.headroom.yml`
documents both. Confirm in Dashboard → Endpoint → Token Saver → Headroom →
recheck.

---

**G8 — Self-hosted embedding `baseUrl` must include `/v1`**

Symptom: `POST /v1/embeddings` with `provider: self-hosted-embedding` returns
`501` or `404`.
Cause: the adapter appends `/embeddings`, so `http://host:8080` becomes
`http://host:8080/embeddings` (missing `/v1` prefix that llama-server expects).
The correct `baseUrl` is `http://host:8080/v1` (or full `.../v1/embeddings`,
which is also accepted).
Fix: set `providerSpecificData.baseUrl` per the README table — embedding must
include `/v1`. STT wants the full `.../v1/audio/transcriptions` URL; TTS wants
the server root.

---

**G9 — SQLite hot-backup vs live file copy**

Symptom: a `scp`'d `data.sqlite` from a running 9Router fails integrity checks
or shows stale providers after restore.
Cause: copying a live SQLite file while it is being written can produce a
torn page. The safe path is `sqlite3 data.sqlite ".backup backup.sqlite"`
(hot, consistent) or stop-then-copy.
Fix: `scripts/backup.sh` prefers `sqlite3 .backup` when `sqlite3` is on the
host; otherwise it does `docker compose stop → cp → start` for a consistent
snapshot. Install `sqlite3` on the host when possible.

---

**G10 — Dashboard "cost" is a tracking estimate, not a bill**

Symptom: Dashboard shows "$290 total cost" while using Kiro free models (50
credits/mo) — operator panics about a bill.
Cause: 9Router never charges; cost panels display what the same tokens would
have cost on paid APIs directly — a savings tracker.
Fix: reassure the operator; verify actual spend on the upstream provider's
own dashboard. The playbook's §9.4 calls this out.

---

**G11 — Reverse-proxy must forward `/v1`, `/api`, and `/dashboard`**

Symptom: dashboard loads but `POST /v1/chat/completions` returns `404` or
`502`, or streaming stops mid-response.
Cause: proxy only matched `/dashboard` or buffered SSE; 9Router serves
`/v1/*` and `/api/*` as well, and streams with `text/event-stream`.
Fix: Nginx `location /` (all paths) with `proxy_buffering off; proxy_cache off;`
and `Upgrade`/`Connection` headers (see `templates/nginx-9router.conf`).
For Traefik/Dokploy: one router for `/` (or all 9Router paths) on the right
entrypoint. Increase `proxy_read_timeout` to `300s` for long streams.

---

**G12 — Cloud Sync hang and env var precedence**

Symptom: dashboard hangs when cloud DNS is down; or cloud sync uses the wrong
base URL after a move.
Cause:
- `NEXT_PUBLIC_BASE_URL` / `NEXT_PUBLIC_CLOUD_URL` are UI/compat vars;
  server runtime prefers `BASE_URL` / `CLOUD_URL`. If only the public vars
  are set, the sync scheduler's internal callback may use a stale URL.
- Sync requests use timeout+fail-fast; an unresolvable `CLOUD_URL` should
  fail fast, but operator should confirm sync logs rather than wait.
Fix: set **both** `BASE_URL` and `CLOUD_URL` (server-side) in production;
keep `NEXT_PUBLIC_*` only if the UI build needs them. Verify with
`docker logs 9router | grep -i cloud` after a change.

---

*Append new lessons at the top with the next G-number, date, and operator
approval reference. Never use confidential values in this file — describe
patterns with `<PLACEHOLDERS>` only.*
