#!/usr/bin/env bash
# restore.sh — Kandev restore helpers (SQLite file + Postgres pg_restore)
# Destructive — requires STOP of all backends against the target DB before running.
# Never deletes the source snapshot. Uses quarantine for the file being replaced.
#
# Usage:
#   # SQLite (inside home) — stop first, then:
#   kandev service stop --home-dir /srv/kandev   # or: docker compose -f compose.yml stop kandev
#   ./scripts/restore.sh --snapshot /srv/kandev/data/backups/manual-20260501T120000Z.db --home /srv/kandev
#   kandev service start --home-dir /srv/kandev
#
#   # SQLite with custom path outside home:
#   ./scripts/restore.sh --snapshot /srv/kandev-data/backups/manual-20260501T120000Z.db --home /srv/kandev --db-path /srv/kandev-data/kandev.db
#
#   # Postgres (stop ALL backends, then):
#   ./scripts/restore.sh --postgres --snapshot /srv/kandev/backups/kandev-20260501T120000Z.dump
#
# Exit codes: 0 ok, 1 error, 2 usage

set -euo pipefail

SNAPSHOT=""
HOME_DIR=""
DB_PATH=""
DO_POSTGRES=0

usage() {
  cat <<'USAGE'
Usage: restore.sh --snapshot FILE [OPTIONS]
  --snapshot FILE   Snapshot file (SQLite .db or Postgres .dump/.sql). Required.
  --home DIR        KANDEV_HOME_DIR (e.g. /srv/kandev). Needed for SQLite restores.
  --db-path PATH    KANDEV_DATABASE_PATH override (SQLite custom path). Empty → <home>/data/kandev.db
  --postgres        Use pg_restore (Postgres). Needs PGHOST/PGPORT/PGUSER/PGDATABASE or PG* env.
  -h|--help         Help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --snapshot) SNAPSHOT="$2"; shift 2 ;;
    --home) HOME_DIR="$2"; shift 2 ;;
    --db-path) DB_PATH="$2"; shift 2 ;;
    --postgres) DO_POSTGRES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$SNAPSHOT" ]]; then
  echo "ERR: --snapshot required" >&2; exit 2
fi
if [[ ! -f "$SNAPSHOT" ]]; then
  echo "ERR: snapshot not found: $SNAPSHOT" >&2; exit 1
fi
HOME_DIR="${HOME_DIR/#\~/$HOME}"

# ── Postgres ─────────────────────────────────────────────────────────
if [[ $DO_POSTGRES -eq 1 ]]; then
  echo "==> Postgres restore: $SNAPSHOT → \${PGDATABASE:-kandev} @ \${PGHOST:-\${PGHOST}}"
  if ! command -v pg_restore >/dev/null 2>&1; then
    echo "ERR: pg_restore not found — install postgresql-client" >&2; exit 1
  fi
  echo "WARN: ensure ALL Kandev backends using this DB are STOPPED before continuing."
  echo "WARN: this runs: pg_restore --clean --if-exists --no-owner --host ... --dbname ... <snapshot>"
  read -r -p "Type RESTORE to continue: " ans
  if [[ "$ans" != "RESTORE" ]]; then
    echo "Aborted."; exit 1
  fi
  pg_restore --clean --if-exists --no-owner \
    --host "${PGHOST:-localhost}" --port "${PGPORT:-5432}" \
    --username "${PGUSER:-kandev}" --dbname "${PGDATABASE:-kandev}" \
    "$SNAPSHOT" 2>&1 | sed 's/^/  /' || { echo "FAIL: pg_restore" >&2; exit 1; }
  echo "PASS: pg_restore complete. Restart ONE Kandev backend, wait for /ready, verify single-replica first."
  exit 0
fi

# ── SQLite file restore ──────────────────────────────────────────────
if [[ -z "$HOME_DIR" ]]; then
  echo "ERR: --home required for SQLite restores" >&2; exit 2
fi
if [[ ! -d "$HOME_DIR" ]]; then
  echo "ERR: home not found: $HOME_DIR" >&2; exit 1
fi
if [[ -z "$DB_PATH" ]]; then
  DB_PATH="$HOME_DIR/data/kandev.db"
fi
DB_DIR="$(dirname "$DB_PATH")"
mkdir -p "$DB_DIR"
chmod 0700 "$DB_DIR" 2>/dev/null || true

if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "ERR: sqlite3 not found" >&2; exit 1
fi

echo "==> SQLite restore: $SNAPSHOT → $DB_PATH"
echo "WARN: ALL Kandev backends against this file must be STOPPED before continuing."
echo "WARN: this quarantines $DB_PATH (+ -wal/-shm) before installing the staged snapshot."
read -r -p "Type RESTORE to continue: " ans
if [[ "$ans" != "RESTORE" ]]; then
  echo "Aborted."; exit 1
fi

# Validate snapshot can be opened and has expected tables
echo "==> validate snapshot"
if ! sqlite3 "$SNAPSHOT" "SELECT count(*) FROM tasks; SELECT count(*) FROM kandev_meta;" 2>&1 | sed 's/^/  /'; then
  echo "ERR: snapshot validation failed — not installing" >&2
  exit 1
fi

# Quarantine existing DB files
QTS="$(date -u +%Y%m%dT%H%M%SZ)"
QUARANTINE_DIR="$DB_DIR/restore-quarantine-$QTS"
mkdir -p "$QUARANTINE_DIR"
chmod 0700 "$QUARANTINE_DIR" 2>/dev/null || true

for f in "$DB_PATH" "$DB_PATH-wal" "$DB_PATH-shm"; do
  if [[ -f "$f" ]]; then
    echo "  quarantine: $f → $QUARANTINE_DIR/"
    mv -v "$f" "$QUARANTINE_DIR/" 2>&1 | sed 's/^/  /'
  fi
done

# Stage install: copy snapshot → <path>.new, checkpoint, then install
STAGED="$DB_PATH.new"
echo "==> stage: $SNAPSHOT → $STAGED"
cp -a "$SNAPSHOT" "$STAGED"
chmod 0600 "$STAGED"

echo "==> install: $STAGED → $DB_PATH"
if ! mv "$STAGED" "$DB_PATH"; then
  echo "FAIL: install failed — restoring quarantined files" >&2
  for f in "$QUARANTINE_DIR"/*; do
    [[ -f "$f" ]] && mv -v "$f" "$DB_DIR/" 2>&1 | sed 's/^/  /' || true
  done
  exit 1
fi
chmod 0600 "$DB_PATH"

echo "PASS: restore installed. Quarantined previous DB in $QUARANTINE_DIR (keep until verified)."
echo "  snapshot still intact: $SNAPSHOT"
echo "  master.key unchanged: $HOME_DIR/data/master.key (ensure it still matches this snapshot's secrets)"
echo "NEXT: restart Kandev:"
echo "  Service:  kandev service restart --home-dir $HOME_DIR   # then: curl --fail http://127.0.0.1:<PORT>/ready"
echo "  Docker:   docker compose -f <COMPOSE_DIR>/docker-compose.yml restart kandev"
echo "After restart, if quarantine restore is needed: mv $QUARANTINE_DIR/* $DB_DIR/ && restart again."
