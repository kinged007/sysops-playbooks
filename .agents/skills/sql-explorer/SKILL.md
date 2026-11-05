---
name: sql-explorer
description: Explore and export data from one SQL database (postgres, mysql, sqlite) by translating natural-language questions to SQL and running them through scripts/db.py. Use for schema discovery, finding rows, answering data questions, CSV exports, and small approved writes. Not for schema migrations, bulk data moves between servers, or production writes without an approved plan.
---

# SQL Explorer

> Read `references/` before any run. It holds lessons that change how you query.

**Production databases are SELECT-only.** Any other statement (INSERT, UPDATE,
DELETE, ALTER, DROP, TRUNCATE, GRANT, CREATE) is a production write. It needs
an approved plan, a **WRITE** flag, the run's permission mode, and `--yes`.

Risk level: medium. Reads are safe. `exec` writes to production data. Reads run
by default; writes need plan approval plus `--yes`.

## When to use

- Exploring an unfamiliar database: tables, columns, sample rows.
- Finding rows, joining across tables, answering data questions.
- Exporting result sets to CSV.
- Small writes (UPDATE/CREATE/INSERT) when the operator approves them.
- Not for: schema migrations (use the project's migration tool), bulk data
  moves between servers, production writes without an approved plan.

Prerequisites: `uv` (installs `psycopg[binary]` and `pymysql` on first run);
sqlite uses the standard library; the database is reachable from this machine
with valid credentials.

## Fleet refs needed

One database per run variant.

- `fleet/services.yaml`: the database service record (type, host, port, database name).
- `fleet/servers.yaml`: the server hosting the database, if it is reached through an ssh tunnel (`ops ssh <server>`).

## Vault entries needed

Names follow `<client>-<provider>-<purpose>`. Values are never printed or logged.

- `<client>-<db>-db-env`: the `DB_*` values (see `templates/db.env.example`). The script reads them from `<run>/secrets/db.env`; the file is created from the vault entry and never printed.

## Procedure

Rules for every step:

- Reads need no flag. Every step that changes a production system is flagged **WRITE** and needs approval per the run's permission mode.
- Every destructive **WRITE** is preceded by a **Backup** step.
- Every **WRITE** has a **Rollback** line.
- Every write is followed by a **Verify** step.
- Production databases: `SELECT` only unless the step is flagged **WRITE** and approved.
- Commands use placeholders; never write real hosts, database names, usernames, or credentials in this file.

`<run>` is the run folder `runs/sql-explorer-<suffix>/`.

### 0. Pre-flight

- [ ] Read `references/` for lessons that affect this run
- [ ] Confirm which database: new variant (`runs/sql-explorer-<suffix>/`) or reuse an existing folder. Ask the operator, never auto-pick
- [ ] New variant: build `<run>/secrets/db.env` from `templates/db.env.example` and the vault entry, and have the operator fill it in
- [ ] `scripts/db.py` is executable (`chmod +x scripts/db.py`); first run resolves its `uv` dependencies
- [ ] After script changes, run the self-check: `python3 scripts/test_db.py`

### 1. Connect (read)

- [ ] Smoke test: `scripts/db.py --exec <run> tables`
- [ ] If it fails, check `references/gotchas.md` (host/port, SSL, grants) before asking

### 2. Explore (read)

- [ ] `scripts/db.py --exec <run> schema` for all tables and columns
- [ ] `scripts/db.py --exec <run> schema <table>` for one table
- [ ] Translate the operator's question to SQL; sample first (`... LIMIT 5`) before full result sets
- [ ] `scripts/db.py --exec <run> q "<SELECT ...>"`

### 3. Answer and export (read)

- [ ] Show small results inline (table output)
- [ ] Counts before dumps: `SELECT COUNT(*)` first so the operator knows the size
- [ ] Large results: `scripts/db.py --exec <run> q "<SELECT ...>" --csv <file>`; write the CSV under `<run>/`, for example `<run>/exports/answer.csv`

### 4. Writes (only with approval)

- Every write must be in the approved plan, flagged **WRITE**, and covered by the run's permission mode (per-write confirm or plan-as-approved).
- [ ] Dry-run the predicate: run the `WHERE` clause as a `SELECT` and show the affected rows and count
- [ ] **Backup**: `scripts/db.py --exec <run> q "SELECT * FROM <table> WHERE <predicate>" --csv <run>/exports/pre-write-<table>.csv`
- [ ] **WRITE**: `scripts/db.py --exec <run> exec "<UPDATE|INSERT|CREATE ...>" --yes`
  - Rollback: restore from the pre-write CSV, or reverse the statement (DELETE the inserted rows, restore old values). DDL (`CREATE`/`ALTER`/`DROP`) rolls back by dropping or renaming. State this in the plan, since there is no undo beyond backups.
- [ ] Verify: re-`SELECT` the affected rows; record before and after counts

## Rollback

Per write: use the pre-write CSV snapshot or the reverse statement from the
step 4 rollback line. If the affected row count differs from the dry-run, stop
and ask the operator before any further write.

## Verify

- [ ] Re-`SELECT` the affected rows after every write and compare with the dry-run
- [ ] Before and after counts are recorded in `logs/`

## Gotchas

Details in `references/gotchas.md`.

- `q` accepts only reads (SELECT/WITH/VALUES/TABLE/EXPLAIN/SHOW/DESCRIBE); anything else exits non-zero.
- `exec` refuses without `--yes`, and `--yes` needs plan approval first.
- Preset environment variables win over `db.env`; unset `DB_*` when debugging "wrong database".
- Empty tables print only `0 row(s)` on stderr: the table exists but is empty.

## Files

| Path | Purpose |
|---|---|
| `scripts/db.py` | Query CLI (uv script: postgres/mysql/sqlite; tables/schema/q/exec/--csv) |
| `scripts/test_db.py` | Self-check for `db.py` (stdlib sqlite only) |
| `templates/db.env.example` | Connection values template |
| `templates/plan-template.md`, `templates/runbook-template.md` | Copied to `runs/sql-explorer-<suffix>/` on first run |
| `references/gotchas.md` | Query and connection pitfalls from past runs |
