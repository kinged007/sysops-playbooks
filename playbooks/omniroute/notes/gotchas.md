# OmniRoute gotchas (G1–G?)

Lessons from real runs. **Read before planning any run.** Every run must check
for the conditions below before writing anything.

## G1 — `/api/mcp/*` is LOCAL_ONLY by default (verified)
The MCP HTTP surface (`/api/mcp/status|tools|sse|stream|audit`) is in the
LOCAL_ONLY route tier. Anonymous and non-manage-scope callers get `403` even on
a fully healthy public instance. To reach it from outside loopback you MUST
present a Bearer API key carrying the `manage` scope (or the narrower
`mcp:connect` scope since v3.8.2). This is the expected secure state, not a bug:
an anonymous `200` on `/api/mcp/status` is an exposure finding.
- Confirm secure: `curl -s -o /dev/null -w "%{http_code}" https://<host>/api/mcp/status` → `403`
- Access: `curl -s -H "Authorization: Bearer <key>" https://<host>/api/mcp/status` → `200`

## G2 — MCP is OFF until enabled in settings
Both `/api/mcp/sse` and `/api/mcp/stream` return `400` with a hint until
`mcpEnabled=true` AND `mcpTransport` matches the endpoint you hit
(`sse` vs `streamable-http`). Enable via dashboard (MCP page) or
`PATCH /api/settings` (management session). `mcpEnabled` is NOT
password-gated server-side, but the settings route still requires management
auth (session cookie or manage-scope key).

## G3 — SSE transport vs Streamable HTTP
- `/api/mcp/sse` — GET/POST, long-lived event stream. A bounded probe
  (`curl -N --max-time 5`) should get HTTP 200 and an SSE body; do NOT hold a
  full session open in a probe.
- `/api/mcp/stream` — streamable HTTP, `mcp-session-id` header, DELETE to end.
  Preferred by Claude Code (`--type http`) and most multi-session clients.
- Switching `mcpTransport` closes sessions on the other transport.

## G4 — the manage key's plaintext is shown ONCE
`POST /api/keys` returns the full key exactly once; it is stored hashed
server-side. Capture it straight into `secrets/mcp-key-<tag>.txt` at creation.
Never echo it into logs/runbook. `GET /api/keys` returns only masked values.

## G5 — "I have it installed already" can mean "running elsewhere"
An operator saying OmniRoute is already installed is NOT an instruction to skip
discovery. The agent must still probe `healthz` + `agent.json` + MCP gating
before writing anything, and ask where the instance is reachable. Never assume
a target (local/Docker/VPS/remote) — the operator picks it at plan approval.

## G6 — Windows tooling gotchas
- PowerShell `Invoke-WebRequest` is fine for bounded probes; for the SSE
  handshake prefer a `curl.exe --max-time` bounded call (PowerShell may buffer
  an open stream indefinitely).
- `netstat -ano | findstr <port>` on Windows needs care with quotes; use
  `Get-NetTCPConnection -LocalPort <port>` instead.
- `npx omniroute` with no local package cancels with a prompt — never run it
  non-interactively to "check version"; use the real binary or probe the URL.

## G7 — secrets are per-variant (persistent)
Secrets (INITIAL_PASSWORD, JWT_SECRET, API_KEY_SECRET, WS_BRIDGE_SECRET, salts)
are generated into `executions/omniroute/secrets/` (or `executions/omniroute-<suffix>/secrets/`)
and **persist across invocations** of the same variant (repo AGENTS.md §1.4/§4). Each
variant is isolated — never copy secrets between variants without explicit operator
approval. A public instance's existing secrets are never read/rotated without
explicit operator approval.

## G8 — public URL env vars
- `NEXT_PUBLIC_BASE_URL` — canonical public origin (OAuth redirects, dashboard
  links, generated public URLs). Required behind a reverse proxy.
- `BASE_URL` — internal server-to-server URL; keep it loopback/container, never
  a public hostname for credential-bearing self-fetches.
- `OMNIROUTE_PUBLIC_BASE_URL` — highest-priority browser-facing origin when a
  relay reaches OmniRoute internally but the browser must fetch from public.
- `AUTH_COOKIE_SECURE=true` required when the public URL is HTTPS.
- `OMNIROUTE_BASE_PATH` — subpath behind a proxy (e.g. `/omniroute`); Next.js
  basePath is baked at build for Docker, but prebuilt images patch at startup.

## G9 — route guard carve-out scope
Since v3.8.2 the `/api/mcp/*` LOCAL_ONLY carve-out accepts a Bearer key with
`manage` OR the additive narrow scope `mcp:connect` (authorizes ONLY the
`/api/mcp/` bypass — no other management routes). Prefer `mcp:connect` for a
remote MCP-only caller to keep least privilege; `manage` is the dashboard
"Management Access" toggle. `/api/cli-tools/runtime/*` is NOT bypassable.

## G10 — combos can only fail over to providers inside the combo
A combo's fallback never leaves the providers listed in its `models[]`. If a
combo lists only `opencode-go` targets and that provider's models hit
429/403/401, the combo fails 100% — it cannot reach another provider's credits
that aren't in the combo.
- Check: `GET /api/combos` and read each combo's `models[].providerId`.
- Fix: add at least one cross-provider fallback model to the combo
  (e.g. `ollamacloud/deepseek-v4-flash`, `opencode-zen/*`).

## G11 — model 429/403 is often model/account-level, not key-level
Multiple API-key connections under the SAME provider share the provider's
account quota. Rotating to another key of the same provider does NOT bypass a
"Monthly usage limit reached" 429 or a "China-hosted requires opt-in" 403.
- Per-connection cooldown (baseCooldown 3s, backoff 5) rotates KEYS on per-key
  rate limits, but not account-wide caps.
- Check real model behavior with a tiny completion before diagnosing key
  rotation: `POST /v1/chat/completions {model: "<provider>/<model>"}` and read
  the error body (429 quota / 403 region opt-in / 401 auth).
- Region-gated models (e.g. deepseek China-hosted) 403 until the operator
  enables them in the provider dashboard ("China servers" toggle).

## G12 — strategy semantics for "prefer my top model, fall back when exhausted"
- `priority` = always target[0], fall to next on error/quota. THE choice when a
  specific preferred model must go first.
- `cache-optimized` = pin to same account for prompt-cache hits; it AVOIDS
  switching targets and can look like failover is broken. Not a preference
  strategy.
- `auto` = 9-factor scoring (cost/latency/quota/circuit); cost-optimal but may
  NOT honor a preferred top model.
- `reset-window` = order by quota-reset recency; can't express preference.
- Recommendation: `priority` with preferred model as target[0], then other
  same-provider models, then a cross-provider safety net. Cache savings still
  come from provider-side prompt caching.

## G13 — PATCH vs PUT on combo/API routes
On the deployed 3.8.49 line, `PATCH /api/combos/[id]` returns **405**; use
`PUT /api/combos/[id]` (the route source aliases PATCH→PUT on newer lines, but
3.8.49 served 405). Same for provider detail routes. Use PUT for combo updates
against this build.

## G14 — MCP server can drive routing config (REST mirror)
The MCP tools (`omniroute_list_combos`, `omniroute_set_routing_strategy`,
`omniroute_simulate_route`, `omniroute_explain_route`) are the intended agent
interface, but they ride the same management auth as the REST surface
(`/api/combos`, `/api/combos/metrics`, `/api/monitoring/health`). For scripting
and reproducibility the REST endpoints are deterministic and easier to
authenticate with a manage-scope Bearer key; the skill docs live at
`skills/omni-combos-routing/SKILL.md` in the upstream repo and should be fetched
when the operator references them.

## G15 — "shield my prompts, terse my replies": compression config
OmniRoute's compression is a GLOBAL profile written ONLY via MCP tools
(`omniroute_set_compression_engine`, `omniroute_compression_configure`, scope
`write:compression`) — there is NO REST route to change the active profile
(`/api/compression/engines` is GET-only; `/api/settings` has no compression
object in its schema).
- The engines that can cut/rewrite a USER PROMPT (`inputScope:"messages"`) are:
  `aggressive` (summarizer, default 2048 tokens/msg), `llmlingua` (semantic
  prune, default ON minTokens 2000), `caveman` (rule prose, compressRoles
  includes "user"), `ccr` (block→retrieve marker), `ultra`, `llm`.
- To guarantee a long prompt is NEVER cut: set `engine="rtk"` via
  `omniroute_set_compression_engine` — this flips ALL input engines off and
  leaves only tool-output compression. Keep `autoTriggerTokens=0` so nothing
  auto-fires. `preserveSystemPrompt` stays true.
- To minimize REPLIES without touching code: enable `outputMode:true`
  (Caveman OUTPUT mode) and the `terse-prose`/`less-code`/`ponytail` output
  styles. `rtk.applyToCodeBlocks=false` keeps code byte-perfect.
- Driving MCP writes over SSE is blocked once any earlier probe left the SSE
  transport "already initialized" (`-32600`). Workaround that works: flip
  `mcpTransport` sse→streamable-http (fresh session via `mcp-session-id`),
  do the MCP calls, then flip back to sse. Each mcpTransport switch closes
  existing sessions.

---
(Template notes: add G-numbers as real runs produce lessons. Promote via the
operator after a run, never mid-run.)