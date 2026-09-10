# Runbook: <RUN NAME> — Kandev

Snapshot of `playbooks/kandev/playbook.md` being executed, with real values
filled in. State lives here and in `logs/` — any agent session can resume from
these files alone. This folder is persistent per playbook variant
(`executions/kandev[/-<suffix>]/`); subsequent invocations append to it,
never replace it. `logs/` is append-only — each session adds timestamp-prefixed
files (e.g. `logs/2026-09-01T120000-01-discover.log`).

| Field | Value |
|---|---|
| Run | <run name> |
| Playbook | `kandev` |
| Execution folder | `executions/kandev/` or `executions/kandev-<suffix>/` |
| KANDEV_HOME_DIR | `<KANDEV_HOME_DIR>` (isolated via `--home-dir` or default) |
| Database driver / path | `<sqlite|postgres>` / `<KANDEV_HOME_DIR>/data/kandev.db` or `<CUSTOM_DB_PATH>` |
| Kandev image tag (Docker) | `ghcr.io/kdlbs/kandev:<X.Y.Z>` or `n/a (Service)` |
| Started | <date> |
| Permission mode | <A per-write confirm / B plan-as-approved> (set at plan approval) |

## Steps

Status values: `pending` / `in-progress` / `done` / `blocked` / `parked`.

- [ ] **1. Discover** (read) — present deployment+auth pros/cons, record D1/D2+F1–F3+H1–H6/P1–P3/E1–E3 — status: pending
  - Log: `logs/<timestamp>-01-discover.log`
- [ ] **2. Pre-flight** (read) — read `notes/gotchas.md`, fetch live Kandev docs, confirm `ssh <ALIAS>` — status: pending
  - Log: `logs/<timestamp>-02-preflight.log`
- [ ] **3. Prerequisites** (read / **WRITE** isolated dir if chosen) — create `executions/kandev[-<suffix>]/`, record Home & DB layout §1.1, pre-create `<KANDEV_HOME_DIR>` — status: pending
  - Log: `logs/<timestamp>-03-prereqs.log`
  - Mode A note: operator confirmation required before `install -d -o <USER> <KANDEV_HOME_DIR>` if `--system`
- [ ] **4. [Branch A] Install binary** (**WRITE**) — `npm install -g kandev@latest` / `brew install` / archive; record bundle path — status: pending / parked
  - Log: `logs/<timestamp>-04-install-binary.log`
  - Mode A note: operator confirmation required before writing to production host.
- [ ] **5. [Branch A] Service install** (**WRITE**) — `kandev service install --home-dir <KANDEV_HOME_DIR>` (or `--system --run-as …`), verify `service config --home-dir` + `install.json` + `/ready` — status: pending / parked
  - Log: `logs/<timestamp>-05-service-install.log`
  - Rollback: `kandev service uninstall --home-dir <KANDEV_HOME_DIR>`
- [ ] **6. [Branch A] Fixed-port drop-in (if needed)** (**WRITE**) — `systemctl --user edit kandev.service` → `KANDEV_BACKEND_PORT` + `daemon-reload` + `restart` — status: pending / parked
  - Log: `logs/<timestamp>-06-fixed-port.log`
  - Parked if no pinned port required
- [ ] **7. [Branch B] Persistence & compose** (**WRITE**) — volume / bind mount, copy `docker-compose.yml` (pinned `:<X.Y.Z>`), optional `docker-compose.postgres.yml`, `docker compose up -d` + `/ready` — status: pending / parked
  - Log: `logs/<timestamp>-07-compose-up.log`
  - Rollback: `docker compose down` (volume retained)
- [ ] **8. Configure** (**WRITE**) — write `<KANDEV_HOME_DIR>/config.yaml` or compose env (`KANDEV_FEATURES_AUTH`, `server.host`, `KANDEV_TRUSTED_PROXIES`, DB driver/path), restart, no `X-Forwarded-Host from untrusted` warning — status: pending
  - Log: `logs/<timestamp>-08-configure.log`
- [ ] **9. Auth provisioning** (**WRITE**) — setup mode → admin `<ADMIN_EMAIL>`, invite/PAT (`secrets/kandev-pat-*.txt` `0600`) — status: pending
  - Log: `logs/<timestamp>-09-auth.log`
  - Skipped if auth OFF (record shielding instead)
- [ ] **10. Proxy + DNS + TLS** (**WRITE**) — deploy isolated `Caddyfile.kandev`/`nginx-kandev.conf` `import`/`include`, reload, `https://<DOMAIN>/ready` + `/health` over TLS — status: pending
  - Log: `logs/<timestamp>-10-proxy-tls.log`
- [ ] **11. Executors** (**WRITE**) — Docker profile Build Image + SSH `Test Connection` + throwaway task — status: pending
  - Log: `logs/<timestamp>-11-executors.log`
- [ ] **12. MCP** (**WRITE**) — `https://<DOMAIN>/mcp initialize` via PAT, client `mcpServers` config — status: pending
  - Log: `logs/<timestamp>-12-mcp.log`
- [ ] **13. DB hygiene** (read / **WRITE** snapshot) — `ls <home>/data/kandev.db* + master.key + backups/`, off-host `manual-*.db` + `master.key` (or `*.dump`) — status: pending
  - Log: `logs/<timestamp>-13-db-hygiene.log`
- [ ] **14. Verification** (read) — probe matrix (§15 playbook) + throwaway task + MCP `create_task_kandev` — status: pending
  - Log: `logs/<timestamp>-14-verification.log`
- [ ] **15. Harden + close** (read / **WRITE** off-host snapshot) — verified removal map in `inventory.md`, snapshot saved to `secrets/off-host/`, append `notes.md` — status: pending
  - Log: `logs/<timestamp>-15-close.log`

## Home & DB layout (copy from plan / inventory — the removal contract)

```
KANDEV_HOME_DIR: <KANDEV_HOME_DIR>
Driver: <sqlite|postgres>
DB: <KANDEV_HOME_DIR>/data/kandev.db | <CUSTOM_DB_PATH>
Backups: <backups-dir>
master.key: <KANDEV_HOME_DIR>/data/master.key
Postgres tuple (if postgres): host=<PGHOST> port=<PGPORT> db=<PGDB> user=<PGUSER>
Outside-home extras: <list>
Lingering: <yes|no>
```

## Removal map (copy from plan — verbatim commands for future `rm -rf`)

```bash
# Paste the four-line removal map from plan.md §1.1 here so any future operator
# can restore the host to pre-Kandev without hunting docs.
```

## Deviations

<Anything not in the plan → STOP, record here, ask operator. Never improvise.>

## Close-out

- [ ] Runbook complete (all steps done or parked/blocked+explained)
- [ ] Verified removal map present above and in `inventory.md` §1.1
- [ ] Off-host backup verified: `manual-*.db` + `master.key` (SQLite) or `*.dump` (Postgres) saved to `secrets/off-host/` and test-restored
- [ ] Findings appended to `notes.md` (cumulative history — do not overwrite)
- [ ] Promotion candidates proposed to operator (→ playbook `notes/`)
