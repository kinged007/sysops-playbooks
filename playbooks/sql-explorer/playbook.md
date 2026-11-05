# Playbook: SQL Explorer — Procedure

Canonical steps for a run. **Placeholders only** — never real hosts,
database names, usernames, or credentials. Real values go in the execution's
`secrets/db.env`.

## 0. Pre-flight
- [ ] Read `notes/` for lessons that affect this run
- [ ] Confirm which database: new variant (`executions/sql-explorer-<suffix>/`)
  or reuse an existing folder — ask the operator, never auto-pick
- [ ] New variant: copy `templates/db.env.example` to
  `<exec>/secrets/db.env` and have the operator fill it in
- [ ] `scripts/db.py` is executable (`chmod +x scripts/db.py`); first run
  resolves its `uv` dependencies automatically
- [ ] Run the self-check once after script changes: `python3 scripts/test_db.py`

## 1. Connect (read)
- [ ] Smoke test: `scripts/db.py --exec <exec> tables`
- [ ] If it fails, check `notes/gotchas.md` (host/port, SSL, grants) before asking

## 2. Explore (read)
- [ ] `scripts/db.py --exec <exec> schema` — all tables and columns
- [ ] `scripts/db.py --exec <exec> schema <table>` — one table
- [ ] Translate the operator's question to SQL; sample first
  (`... LIMIT 5`) before full result sets
- [ ] `scripts/db.py --exec <exec> q "<SELECT ...>"`

## 3. Answer and export (read)
- [ ] Show small results inline (table output)
- [ ] Large results: `scripts/db.py --exec <exec> q "<SELECT ...>" --csv <file>`
  (write the CSV under `<exec>/`, e.g. `<exec>/exports/answer.csv`)
- [ ] Counts before dumps: `SELECT COUNT(*)` first so the operator knows the size

## 4. Writes (only with approval)
- [ ] Every write must be in the approved plan, flagged **WRITE**, and covered
  by the run's permission mode (per-write confirm or plan-as-approved)
- [ ] Dry-run the predicate first: run the `WHERE` clause as a `SELECT`
  and show the affected rows/count before the write
- [ ] **WRITE** `scripts/db.py --exec <exec> exec "<UPDATE|INSERT|CREATE ...>" --yes`

## N. Verification
- [ ] Re-`SELECT` the affected rows after a write; record before/after counts
- [ ] Rollback: restore from the pre-write `SELECT ... --csv` snapshot, or
  reverse the statement (DELETE the inserted rows, restore old values).
  DDL (`CREATE`/`ALTER`/`DROP`) rolls back by dropping/renaming — state this
  in the plan since there is no undo beyond backups.

---

## Authoring rules
- Steps must be copy-paste executable with placeholders filled.
- Flag every step that WRITES with **WRITE** in bold. Reads need no flag.
- Add rollback instructions for every write step.
- After each run, promote lessons into `notes/` (via the operator, never mid-run).
