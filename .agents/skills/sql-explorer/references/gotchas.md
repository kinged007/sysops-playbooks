# Notes: SQL Explorer gotchas

Read before any run. Newest at bottom with date header.

## 2026-10-05 — initial
- `q` accepts only reads (SELECT/WITH/VALUES/TABLE/EXPLAIN/SHOW/DESCRIBE).
  Anything else exits non-zero — use `exec --yes` for writes.
- `exec` refuses without `--yes`, and `--yes` needs plan approval first.
- Preset environment variables win over `db.env`; unset `DB_*` before
  debugging "wrong database" confusion.
- First `uv` run downloads dependencies — slow once, fast after.
- Empty tables print no grid, only `0 row(s)` on stderr — that means the
  table exists but is empty, not that the query failed.
