# Playbook: SQL Explorer

> **Agent: read `notes/` BEFORE any run.** Lessons there change how you query.

## What it does
Explores and exports data from one SQL database (postgres, mysql, sqlite)
using natural-language requests translated to SQL by the agent. Connection
parameters live in the execution folder's `secrets/db.env`; the agent runs
all queries through `scripts/db.py`, which reads the secrets file without
printing it.

## When to use it
- Exploring an unfamiliar database: tables, columns, sample rows
- Finding rows, joining across tables, answering data questions
- Exporting result sets to CSV
- Small writes (UPDATE/CREATE/INSERT) when the operator approves them

Not for: schema migrations (use the project's migration tool), bulk
data moves between servers, production writes without an approved plan.

## Prerequisites
- `uv` (installs `psycopg[binary]` and `pymysql` automatically on first run)
- sqlite3 support is stdlib, no install needed
- Database reachable from this machine with valid credentials

## Risk level
**medium** — reads are safe; `exec` writes to production data. Reads run by
default, writes need plan approval plus `--yes`, per the safety doctrine.

## Servers involved
None directly — one database per execution variant. Real values live in the
execution folder's `secrets/db.env`, never here.

## Files
| Path | Purpose |
|---|---|
| `playbook.md` | Canonical procedure (placeholders only) |
| `plan-template.md` | Copied to `executions/sql-explorer-<suffix>/plan.md` on first run |
| `runbook-template.md` | Copied to `executions/sql-explorer-<suffix>/runbook.md` on first run |
| `templates/db.env.example` | Secrets template (copy to `<exec>/secrets/db.env`, fill in) |
| `scripts/db.py` | Query CLI (uv script: postgres/mysql/sqlite, tables/schema/q/exec/--csv) |
| `scripts/test_db.py` | One self-check for `db.py` (stdlib sqlite only) |
| `notes/gotchas.md` | Query and connection pitfalls from past runs |

> Execution folders are **persistent per database**. First run for a database
> creates `executions/sql-explorer-<suffix>/` (e.g. `executions/sql-explorer-acme/`)
> with `secrets/db.env` copied from the template. Reuse the same folder for
> follow-up questions against that database — `secrets/` persists, `logs/`
> is append-only. Never copy `db.env` between variants without operator approval.
