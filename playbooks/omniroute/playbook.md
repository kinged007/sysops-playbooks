# Playbook: OmniRoute — Procedure

Canonical steps for a run. **Placeholders only** — never real IPs, hostnames,
usernames, or credentials. Real values go in the execution's `plan.md`,
`inventory.md`, and `secrets/`.

Conventions: every step that WRITES to a system is flagged **WRITE** and needs
approval per the run's permission mode (A: per-write confirm / B:
plan-as-approved). Rollback is given for every write. Reads are free.

The **SQ** marker means "ask the operator" — never assume. The **TGT** marker
means "target chosen at plan approval" (remote / local npm / Docker).

---

## 0. Pre-flight
- [ ] Read `notes/gotchas.md` (mandatory) — may change how you plan
- [ ] Confirm prerequisites (README): reachability, management credential in
      `secrets/`, permission mode
- [ ] Record the run's permission mode in the runbook (set by operator at
      approval, §3.4). **Never pick the mode yourself.**
- [ ] Confirm access (this is a READ): probe `GET <BASE_URL>/healthz` —
      expect `200`; `GET <BASE_URL>/` should not be a hard error.
      For SSH/running-local targets, verify the process/container exists.

## 1. Discover current state (reads only)
- [ ] TGT/SQ: confirm the install target and how the agent reaches it
      (public `https://` URL, SSH alias + forward, local process, Docker)
- [ ] `GET <BASE_URL>/healthz` — version/health JSON
- [ ] `GET <BASE_URL>/.well-known/agent.json` — A2A present? (confirms an
      OmniRoute-family server)
- [ ] `GET <BASE_URL>/api/mcp/status` — expect `403` anonymous (that is the
      correct secure state); `200` anonymous would be an exposure finding
- [ ] `GET <BASE_URL>/api/mcp/sse` — anonymous should NOT stream; any `200`
      with an SSE body is an exposure finding
- [ ] Record findings in the runbook: server version, whether MCP is gated,
      current public/base URL signals

## 2. Access & authentication (gather the credential)
- [ ] SQ: ask the operator how the agent authenticates to the instance:
      - Existing instance: operator provides a **Management-Access API key**
        (or the dashboard management password, entered/given by the operator
        only) stored in `secrets/<file>`. The agent never invents it.
      - Fresh install (npm/Docker you boot): the agent uses the run's generated
        `INITIAL_PASSWORD` to log in.
- [ ] Never echo secrets into the runbook or logs; reference them by filename.

## 3. Secrets generation (local files, no production write)
- [ ] Run `scripts/gen-secrets.ps1` — writes to `secrets/`:
      - `INITIAL_PASSWORD` (dashboard admin bootstrap)
      - `JWT_SECRET`  (`openssl rand -base64 48` equivalent)
      - `API_KEY_SECRET`  (`openssl rand -hex 32` equivalent)
      - `OMNIROUTE_WS_BRIDGE_SECRET`  (`openssl rand -base64 32`)
      - `MACHINE_ID_SALT` (per-deployment salt, over the default)
      - `OMNIROUTE_CLI_SALT` (rotate if login/token invalidation desired)
      - optional `STORAGE_ENCRYPTION_KEY` (`openssl rand -hex 32`) if
        encryption-at-rest is wanted
- [ ] Record a **secrets manifest** in `secrets/manifest.md`: names, file
      locations, first-8-chars prefix (to verify without leaking full values),
      generation timestamp, which were applied where.
- [ ] CRITICAL: `secrets/` is gitignored (`executions/` gitignored). Verify
      nothing is staged before any commit.

## 4. Configure base & public URLs (SQ — ask the operator)
- [ ] SQ: "Where will this instance be accessed from?" Ask exactly:
      - the **public URL** clients/agents will use (e.g.
        `https://<host>`), → `NEXT_PUBLIC_BASE_URL` /
        `OMNIROUTE_PUBLIC_BASE_URL`
      - the **internal URL** the server uses for self-fetches (loopback /
        container name), → `BASE_URL`
      - any **sub-path** (reverse-proxy `basePath`), → `OMNIROUTE_BASE_PATH`
- [ ] Record the operator's answers in the runbook. These are required before
      any MCP/URL configuration.

## 5. Deploy or wire the instance (TGT + WRITE, approval required)
Depends on the target the operator chose at approval:

### 5a. Remote instance (already running)
- [ ] **WRITE** (via authenticated API / dashboard session) set public URL
      env/settings to the values from §4 if they are not already correct.
  - Rollback: revert to the previous values recorded in §1.
- [ ] Confirm HTTPS posture: if the public URL is `https://`, ensure
      `AUTH_COOKIE_SECURE=true` is set (dashboard cookie flag). **WRITE** if not.
  - Rollback: set back to `false`.

### 5b. Local npm (fresh boot, operator-approved)
- [ ] **WRITE**: `npm install -g omniroute` (or `npx` the pinned version)
  - Rollback: `npm uninstall -g omniroute` (data in `~/.omniroute`/`%APPDATA%` kept).
- [ ] **WRITE**: create/seed `.env` from `templates/.env.example` with the §3
    secrets. Never commit.
  - Rollback: restore prior `.env`.
- [ ] **WRITE**: `omniroute` (port 20128). Verify `GET /healthz` → 200 and
    dashboard reachable.
  - Rollback: stop the process.

### 5c. Docker (fresh boot, operator-approved)
- [ ] **WRITE**: `docker run -d --name <name> --restart unless-stopped
      -p 20128:20128 -v <vol>:/app/data -e ... <env> diegosouzapw/omniroute:latest`
    (prefer `templates/docker-compose.yml` with Caddy for TLS, §7).
  - Rollback: `docker stop <name> && docker rm <name>` (volume kept).
- [ ] **WRITE**: if a reverse proxy (Caddy) is used, point it at the container
    and set `NEXT_PUBLIC_BASE_URL` + `AUTH_COOKIE_SECURE=true` + `BASE_URL`
    (container-internal URL).
  - Rollback: remove the proxy route / revert env.

## 6. First-login bootstrap (fresh installs only)
- [ ] SQ: confirm the operator wants the agent to log in with the generated
      `INITIAL_PASSWORD`, or whether the operator will set the password in the
      dashboard themselves.
- [ ] **WRITE**: log in to the dashboard (management session cookie), then force
      a password change / verify `INITIAL_PASSWORD` was applied.
  - Rollback: n/a (authentication only).
- [ ] Note: after login, the stored `INITIAL_PASSWORD` in `secrets/` should be
      marked "usеd once, rotate in dashboard" if extended password life is
      wanted. (The playbook never stores a rotated password that it generated
      for use; the operator rotates.)

## 7. Harden the instance (security) — WRITE, approval required
- [ ] **WRITE** set hardening settings via authenticated API:
      - `AUTH_COOKIE_SECURE=true` (HTTPS public URL)
      - `INPUT_SANITIZER_MODE=block` (prompt-injection force-block; optional,
        SQ first — default `warn`)
      - Keep `LOCAL_ONLY` gating on `/api/mcp/*` (do NOT disable the carve-out
        kill-switch); allow remote MCP only via a `manage`/`mcp:connect` key.
  - Rollback: revert the keys changed (record originals in §1/runbook).
- [ ] **WRITE** confirm/verify `REQUIRE_API_KEY` posture for `/v1/*` proxy if the
      operator wants all calls authenticated. SQ first.
  - Rollback: set back to `false`.
- [ ] Verify by reading back the settings — confirm the flags took.

## 8. Enable the remote MCP server (WRITE, approval required)
- [ ] SQ: confirm the MCP transport the operator wants:
      - `sse` → `/api/mcp/sse` (GET/POST, streaming event transport)
      - `streamable-http` → `/api/mcp/stream` (multi-session, preferred by many
        clients; SSE may have client-side caveats)
- [ ] **WRITE** set `mcpEnabled=true` and `mcpTransport=<chosen>` via the
      authenticated settings API (`PATCH /api/settings`; `mcpEnabled` is not
      password-gated server-side).
  - Rollback: set `mcpEnabled=false`.
- [ ] **WRITE** create the **Management-Access API key**:
      `POST /api/keys` with `{ "name": "<tag>-mcp-agent", "scopes": ["manage"] }`
      (or `["mcp:connect"]` for a lower-privilege remote-MCP-only key — SQ).
      The plaintext key is returned once; store it immediately in
      `secrets/mcp-key-<tag>.txt` and note the id/prefix in the manifest.
  - Rollback: revoke the key (`DELETE /api/keys/<id>` or dashboard).
- [ ] Never log the full key. Prefer `mcp:connect` over `manage` where the MCP
      tools permit, to keep the key least-privilege. (Say which scope was used.)

## 9. Test MCP reachability (reads after the writes)
- [ ] `GET <BASE_URL>/api/mcp/status` with `Authorization: Bearer <KEY>` → `200`
- [ ] `GET <BASE_URL>/api/mcp/tools` with the key → tool catalog JSON
- [ ] **SSE:** `GET <BASE_URL>/api/mcp/sse` with the key → expect `200` and an
      SSE-compatible body/stream. Note: SSE is long-lived; use a bounded probe
      (`curl -N --max-time 5`) and confirm the handshake, not a full session.
- [ ] Streamable HTTP: `POST <BASE_URL>/api/mcp/stream` with an `initialize`
      MCP JSON-RPC payload + key → expect `200` and `mcp-session-id` header.
- [ ] Anonymous re-check: without a key, `/api/mcp/status` and `/api/mcp/sse`
      must remain `403`/blocked — confirms the carve-out still gates.
- [ ] Write results to `logs/` after each probe.

## 10. Build the MCP access artifact (local file, no production write)
- [ ] `scripts/test-mcp.ps1` also emits
      `executions/<run>/mcp/<tag>.mcp.json` with:
      - server key suffix, `url = <BASE_URL>/api/mcp/<transport>`,
        transport, and the env var name `OMNIROUTE_MCP_KEY_<TAG>`
- [ ] Validate the JSON.
- [ ] Note in the runbook: how a future agent consumes it (merge the `mcp`
      block into an agent config; set the env var to the key in `secrets/`).

## 11. Verification & rollback
- [ ] Re-read the four reachability checks from §9 — all consistent.
- [ ] Confirm every **WRITE** has a rollback recorded in the runbook (URL set,
      HTTPS flags, hardening, MCP enable, key create).
- [ ] Confirm `secrets/manifest.md` lists every secret and its file, and that
      `git status` shows no `secrets/`, no `executions/`.
- [ ] Findings → run `notes.md`; propose lesson promotion to `notes/gotchas.md`
      (operator approves promotion, never mid-run).

---

## Authoring rules
- Steps must be copy-paste executable with placeholders filled.
- Flag every WRITE with **WRITE**; give rollback for each.
- `SQ` = ask operator; `TGT` = target chosen at plan approval.
- Promote lessons to `notes/` only via the operator, after the run.