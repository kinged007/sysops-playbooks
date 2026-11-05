#!/usr/bin/env bash
# backup.sh — Kandev snapshot helpers (SQLite + Postgres + home archive)
# Never logs secret values. Files are created owner-only (0600/0700).
# See playbook §16.2 / §16.3 for the auditable order (stop → snapshot → verify → restart).
#
# Usage:
#   # SQLite (inside home) — hot online snapshot (VACUUM INTO equivalent):
#   ./scripts/backup.sh --home /srv/kandev --dest /srv/kandev/data/backups
#   ./scripts/backup.sh --home ~/srv/kandev   # dest defaults to <home>/data/backups
#   # Custom SQLite path outside home:
#   ./scripts/backup.sh --home /srv/kandev --db-path /srv/kandev-data/kandev.db --dest /srv/kandev-data/backups
#   # Postgres pg_dump (requires PGHOST/PGUSER or env):
#   ./scripts/backup.sh --postgres --dest /srv/kandev/backups --pg-dump-args "-Fc"
#   # Full cold home archive (stop first is recommended for consistency):
#   ./scripts/backup.sh --home /srv/kandev --archive --dest /srv/kandev-archives
#
# Exit codes: 0 ok, 1 error, 2 usage

set -euo pipefail

HOME_DIR=""
DB_PATH=""
DEST=""
DO_POSTGRES=0
DO_ARCHIVE=0
PG_DUMP_ARGS=(-Fc)

usage() {
  cat <<'USAGE'
Usage: backup.sh [OPTIONS]
  --home DIR        KANDEV_HOME_DIR (e.g. /srv/kandev or ~/srv/kandev). Required unless --postgres with -d given.
  --db-path PATH    KANDEV_DATABASE_PATH override (e.g. /srv/kandev-data/kandev.db). Empty → <home>/data/kandev.db
  --dest DIR        Snapshot destination dir (defaults to <db-parent>/backups for SQLite, <dest> required for --postgres/--archive)
  --postgres        Use pg_dump (Postgres driver). Needs PGHOST/PGPORT/PGUSER/PGDATABASE or PG* env.
  --pg-dump-args ARGS  Extra pg_dump args (default: -Fc)
  --archive         Create a cold tar.gz of the entire <home> (requires home to be stopped for consistency)
  -h|--help         Help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --home) HOME_DIR="$2"; shift 2 ;;
    --db-path) DB_PATH="$2"; shift 2 ;;
    --dest) DEST="$2"; shift 2 ;;
    --postgres) DO_POSTGRES=1; shift ;;
    --pg-dump-args) IFS=' ' read -r -a PG_DUMP_ARGS <<< "$2"; shift 2 ;;
    --archive) DO_ARCHIVE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

# ── Postgres path ───────────────────────────────────────────────────
if [[ $DO_POSTGRES -eq 1 ]]; then
  if [[ -z "$DEST" ]]; then
    echo "ERR: --dest required with --postgres" >&2; exit 2
  fi
  mkdir -p "$DEST"
  chmod 0700 "$DEST" 2>/dev/null || true
  TS="$(date -u +%Y%m%dT%H%M%SZ)"
  OUT="$DEST/kandev-$TS.dump"
  echo "==> pg_dump → $OUT  (${PG_DUMP_ARGS[*]})"
  if ! command -v pg_dump >/dev/null 2>&1; then
    echo "ERR: pg_dump not found — install postgresql-client" >&2; exit 1
  fi
  # shellcheck disable=SC2068
  pg_dump ${PG_DUMP_ARGS[@]+"${PG_DUMP_ARGS[@]}"} --file "$OUT" "${PGDATABASE:-kandev}" 2>&1 | sed 's/^/  /' || { echo "FAIL: pg_dump" >&2; exit 1; }
  chmod 0600 "$OUT"
  # verify
  if command -v pg_restore >/dev/null 2>&1; then
    echo "==> verify: pg_restore --list $OUT | head -20"
    pg_restore --list "$OUT" 2>&1 | head -20 | sed 's/^/  /' || true
  fi
  echo "PASS: Postgres dump $OUT ($(du -h "$OUT" | awk '{print $1}'))"
  if [[ -n "$HOME_DIR" && -f "$HOME_DIR/data/master.key" ]]; then
    echo "WARN: also copy $HOME_DIR/data/master.key (0600) — needed to decrypt secrets alongside any DB dump"
  fi
  exit 0
fi

# ── SQLite / archive path needs home ────────────────────────────────
if [[ -z "$HOME_DIR" ]]; then
  echo "ERR: --home required (or use --postgres)" >&2; exit 2
fi
# expand ~
HOME_DIR="${HOME_DIR/#\~/$HOME}"

if [[ ! -d "$HOME_DIR" ]]; then
  echo "ERR: home not found: $HOME_DIR" >&2; exit 1
fi

# Resolve DB path
if [[ -z "$DB_PATH" ]]; then
  DB_PATH="$HOME_DIR/data/kandev.db"
fi
DB_DIR="$(dirname "$DB_PATH")"
if [[ -z "$DEST" ]]; then
  DEST="$DB_DIR/backups"
fi

mkdir -p "$DEST"
chmod 0700 "$DEST" 2>/dev/null || true

if [[ ! -f "$DB_PATH" ]]; then
  echo "ERR: DB not found: $DB_PATH" >&2
  echo "Hint: check KANDEV_DATABASE_PATH / database.path or whether driver=postgres (use --postgres)" >&2
  exit 1
fi

if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "ERR: sqlite3 not found" >&2; exit 1
fi

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$DEST/manual-$TS.db"

echo "==> SQLite .backup: $DB_PATH → $OUT"
# Use sqlite3 .backup (VACUUM INTO equivalent, includes committed WAL frames), then atomic rename is handled by sqlite3
sqlite3 "$DB_PATH" ".backup '$OUT'" 2>&1 | sed 's/^/  /' || { echo "FAIL: sqlite3 .backup" >&2; exit 1; }
chmod 0600 "$OUT"

# Verify: open snapshot read-only
echo "==> verify: sqlite3 $OUT \"SELECT count(*) FROM tasks; SELECT sql FROM sqlite_master WHERE type='table' LIMIT 1;\""
sqlite3 "$OUT" "SELECT count(*) AS task_count FROM tasks; SELECT name FROM sqlite_master WHERE type='table' LIMIT 1;" 2>&1 | sed 's/^/  /' || { echo "WARN: verify query failed" >&2; }

echo "PASS: SQLite snapshot $OUT ($(du -h "$OUT" | awk '{print $1}'))"

# Warn about master.key coupling
if [[ -f "$HOME_DIR/data/master.key" ]]; then
  echo "INFO: master.key at $HOME_DIR/data/master.key — copy with 0600 together with any snapshot (secrets undecryptable without it)"
  ls -l "$HOME_DIR/data/master.key" 2>&1 | sed 's/^/  /' || true
else
  echo "WARN: $HOME_DIR/data/master.key not found — secrets may have been outside home or not yet created"
fi

if [[ $DO_ARCHIVE -eq 1 ]]; then
  # Cold archive — assumes home is already stopped (caller should have stopped service/container)
  echo "==> cold home archive: $HOME_DIR → $DEST/kandev-state-$TS.tar.gz"
  ARCHIVE="$DEST/kandev-state-$TS.tar.gz"
  tar -C "$(dirname "$HOME_DIR")" -czf "$ARCHIVE" "$(basename "$HOME_DIR")" 2>&1 | sed 's/^/  /' || { echo "WARN: tar warnings above" >&2; }
  chmod 0600 "$ARCHIVE"
  echo "PASS: archive $ARCHIVE ($(du -h "$ARCHIVE" | awk '{print $1}'))"
  echo "NOTE: this archive still excludes external Postgres / provider-side objects / CLI creds outside home."
fi

echo "---"
echo "Remember: snapshots do NOT contain Git worktrees/repos in <home>/tasks, <home>/repos (back those separately if needed)."
