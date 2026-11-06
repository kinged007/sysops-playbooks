# Bifrost gotchas — read before any run

## G1. Version drift: pin `<TAG>` and check changelogs

Snippets and hooks differ between v1.4/v1.5/v2.x (Code Mode needs
≥ v1.4.0-prerelease1; plugin hook order changed in v1.5+/v2.0). Docs mix
version lines (quickstart `v2.4.0` vs Helm examples `v1.4.11`). Fix: pin
`image.tag` / `--transport-version` in `plan.md`, confirm the tag exists
on Docker Hub, read `https://docs.getbifrost.ai/changelogs/` before any
upgrade. Never copy a snippet without its version.

## G2. `config_store` omitted ≠ file-only

Omitting `config_store` creates the default SQLite store and treats
`config.json` as DB-backed seed (content-hash reconciliation preserves
UI/API edits). File-only GitOps needs explicit
`"config_store": {"enabled": false}` (UI config edits disabled, restart to
apply). Fix: ask the operator which mode (playbook §2) and set it
explicitly. See `sources.md` → source-of-truth.

## G3. `BIFROST_ENCRYPTION_KEY` must be stable and backed up

Losing or changing it makes persisted encrypted values unreadable, across
restarts, replicas, upgrades, backups, and restores. Fix: generate once
into execution `secrets/`, reuse everywhere, snapshot alongside every DB
backup. Same for provider env-var names (`env.NAME` must exist at runtime).

## G4. Secrets in `config.json` must be `env.` references

`"value": "env.OPENAI_API_KEY"` reads env var `OPENAI_API_KEY` at runtime.
Plaintext keys in the file leak on commit/log and break secret rotation.
Fix: never write a real key into `config.json`; mount env from a `0600`
env_file / K8s secret sourced from execution `secrets/`.

## G5. SQLite hot-copy corrupts; Postgres needs UTF8 v16+

Hot-copying live `config.db`/`logs.db` risks inconsistency — prefer
`sqlite3 .backup`, container stop, or PVC snapshot. Postgres requires v16+
with `UTF8` encoding (`template0` + explicit locale); SQL_ASCII databases
fail migrations with `client_encoding=UTF8` errors. Fix: follow playbook
§9.1; verify with `SELECT datname, pg_encoding_to_char(encoding)`.

## G6. Semantic cache silently does nothing without a cache key

No `x-bf-cache-key` (or `default_cache_key`) → nothing caches. First
request always misses (async writes); VK identity scoping blocks cross-key
hits unless disabled; `dimension`/`provider`/`embedding_model` changes need
a fresh `vector_store_namespace`. A vector store is required even for
direct-only mode. Fix: send the header, check `x-bifrost-cache` /
`extra_fields.cache_debug`, keep a namespace per embedding config.

## G7. MCP auth and proxy pitfalls

`tools_to_auto_execute` is a no-op in pure gateway mode; per-request
narrowing uses `x-bf-mcp-include-tools`. Behind a proxy, set
`mcp_external_client_url` **before** connecting OAuth clients or DCR
redirect URIs break. `tool_sync_interval` bare numbers are nanoseconds —
use `"10m"`. Claude Code `SDK auth failed` on `/oauth2/register` in
`headers` mode is harmless. Fix: verify with `POST /v1/mcp/tool/execute`
before wiring agents.

## G8. Health 503, Helm no-start, and one-way migrations

`GET /health` returns `503` when a configured store check fails (toggle
`client.disableDbPingsInHealth` only to diagnose, not to hide it). Helm
chart requires `image.tag` (won't start without it). SQLite = StatefulSet
+ PVC (single replica, RWO); all-Postgres = Deployment. Migrations run at
startup under advisory lock and are **not** undone by image rollback —
read release migration notes and deploy one version at a time with
`/health` + real inference probes between hops.
