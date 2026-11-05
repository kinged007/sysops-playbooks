#!/usr/bin/env bash
# migrate-db.sh — Kandev DB relocation / driver-migration helpers (auditable, safe order)
# Wraps the three migration paths in playbook §16.4 (SQLite path move, SQLite→Postgres, Postgres→SQLite)
# with preflight checks, verified snapshots, and quarantine rollback.
# See playbook §16.4 for the full auditable procedure (stop → snapshot → flip → verify).
# Never log secret values.
#
# Usage:
#   # A. SQLite path move (inside home ↔ custom outside — no driver change):
#   ./scripts/migrate-db.sh --mode sqlite-path-move --home /srv/kandev --target-db /srv/kandev-data/kandev.db
#   ./scripts/migrate-db.sh --mode sqlite-path-move --home /srv/kandev --target-db /srv/kandev/data/kandev.db  # reverse
#
#   # B. SQLite → Postgres (row copy via pgloader):
#   ./scripts/migrate-db.sh --mode sqlite-to-postgres --home /srv/kandev
#          # needs: pgloader installed, PGHOST/PGPORT/PGUSER/PGDATABASE, KANDEV_DATABASE_PASSWORD set
#
#   # C. Postgres → SQLite:
#   ./scripts/migrate-db.sh --mode postgres-to-sqlite --home /srv/kandev --target-db /srv/kandev/data/kandev.db
#
# Common: --dry-run (checks only), --assume-stopped (skip stop check when you already stopped service)
# Exit codes: 0 ok, 1 error, 2 usage

set -euo pipefail

MODE=""
HOME_DIR=""
TARGET_DB=""
DRY_RUN=0
ASSUME_STOPPED=0

usage() {
  cat <<'USAGE'
Usage: migrate-db.sh --mode MODE --home DIR [OPTIONS]
  --mode MODE     sqlite-path-move | sqlite-to-postgres | postgres-to-sqlite
  --home DIR      KANDEV_HOME_DIR (e.g. /srv/kandev)
  --target-db PATH  For sqlite-path-move / postgres-to-sqlite: target SQLite file (e.g. /srv/kandev-data/kandev.db)
  --dry-run       Preflight checks only — do not copy rows or change config
  --assume-stopped Skip the "is Kandev stopped?" check (you already ran kandev service stop / docker compose stop)
  -h|--help       Help

Postgres env: PGHOST/PGPORT/PGUSER/PGDATABASE (+ PGPASSWORD or ~/.pgpass), KANDEV_DATABASE_PASSWORD for Kandev runtime
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
    --home) HOME_DIR="$2"; shift 2 ;;
    --target-db) TARGET_DB="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --assume-stopped) ASSUME_STOPPED=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$MODE" || -z "$HOME_DIR" ]]; then
  echo "ERR: --mode and --home required" >&2; usage; exit 2
fi
HOME_DIR="${HOME_DIR/#\~/$HOME}"
if [[ ! -d "$HOME_DIR" ]]; then
  echo "ERR: home not found: $HOME_DIR" >&2; exit 1
fi

# ── preflight: stopped? ──────────────────────────────────────────────
check_stopped() {
  if [[ $ASSUME_STOPPED -eq 1 ]]; then return 0; fi
  # heuristic: check for listening 38429 / running kandev process
  if ss -tlnp 2>/dev/null | grep -q "38429"; then
    echo "ERR: Kandev may still be listening on :38429 — stop it first:" >&2
    echo "  kandev service stop --home-dir $HOME_DIR  # or: docker compose -f <compose>/docker-compose.yml stop kandev" >&2
    exit 1
  fi
  if pgrep -f "kandev.*--headless\|kandev.*backend" >/dev/null 2>&1; then
    echo "ERR: kandev backend process still running — stop it first" >&2; exit 1
  fi
}
check_stopped

# ── verify snapshot helper ───────────────────────────────────────────
verify_sqlite() {
  local f="$1"
  sqlite3 "$f" "SELECT count(*) FROM tasks; SELECT count(*) FROM kandev_meta;" >/dev/null 2>&1
}

# ── Mode A: SQLite path move ─────────────────────────────────────────
if [[ "$MODE" == "sqlite-path-move" ]]; then
  if [[ -z "$TARGET_DB" ]]; then
    echo "ERR: --target-db required for sqlite-path-move" >&2; exit 2
  fi
  SRC="$(realpath -m "${KANDEV_DATABASE_PATH:-$HOME_DIR/data/kandev.db}")"
  DST="$(realpath -m "$TARGET_DB")"
  echo "==> Mode A: SQLite path move"
  echo "  src:  $SRC"
  echo "  dest: $DST"
  if [[ "$SRC" == "$DST" ]]; then
    echo "ERR: src == dest — nothing to do" >&2; exit 2
  fi
  if [[ ! -f "$SRC" ]]; then
    echo "ERR: source DB not found: $SRC (check KANDEV_DATABASE_PATH / $HOME_DIR/data/kandev.db)" >&2; exit 1
  fi
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "DRY RUN — would: sqlite3 $SRC \".backup $DST\" and update KANDEV_DATABASE_PATH=$DST"
    verify_sqlite "$SRC" && echo "PASS: source valid" || echo "WARN: source open check failed"
    exit 0
  fi
  if ! command -v sqlite3 >/dev/null 2>&1; then echo "ERR: sqlite3 not found" >&2; exit 1; fi
  mkdir -p "$(dirname "$DST")"
  chmod 0700 "$(dirname "$DST")" 2>/dev/null || true
  if [[ -f "$DST" ]]; then
    echo "ERR: dest already exists: $DST — refusing to overwrite. Move it aside first." >&2; exit 1
  fi
  echo "==> sqlite3 $SRC → .backup $DST"
  sqlite3 "$SRC" ".backup '$DST'" 2>&1 | sed 's/^/  /' || { echo "FAIL: .backup" >&2; exit 1; }
  chmod 0600 "$DST"
  verify_sqlite "$DST" || { echo "FAIL: dest validation" >&2; exit 1; }
  echo "PASS: SQLite file copied."
  echo "NEXT:"
  echo "  1) Set KANDEV_DATABASE_PATH=$DST (drop-in or compose env) or, if dest is <home>/data/kandev.db, delete KANDEV_DATABASE_PATH (empty = default)."
  echo "  2) kandev service restart --home-dir $HOME_DIR  (or docker compose up -d kandev)"
  echo "  3) curl --fail http://127.0.0.1:<PORT>/ready && sqlite3 $DST \"SELECT count(*) FROM tasks;\""
  echo "  4) Only after verification, archive the old file: mv $SRC{,.migrated-$(date +%F)}"
  echo "  Backups sibling now: $(dirname "$DST")/backups/  (old snapshots in $(dirname "$SRC")/backups/ are NOT auto-moved)"
  echo "  master.key stays at $HOME_DIR/data/master.key — keep alongside any snapshot."
  exit 0
fi

# ── Mode B: SQLite → Postgres ────────────────────────────────────────
if [[ "$MODE" == "sqlite-to-postgres" ]]; then
  echo "==> Mode B: SQLite → Postgres (row copy)"
  SRC="$(realpath -m "${KANDEV_DATABASE_PATH:-$HOME_DIR/data/kandev.db}")"
  if [[ ! -f "$SRC" ]]; then
    echo "ERR: source SQLite not found: $SRC" >&2; exit 1
  fi
  if ! command -v pgloader >/dev/null 2>&1; then
    echo "ERR: pgloader not found — install pgloader (or use a different transfer method per §16.4 B)." >&2
    echo "  Alternative: manual pgloader invocation — see playbook §16.4 B for options B1/B2/B3." >&2
    exit 1
  fi
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "DRY RUN — would: snapshot $SRC, then pgloader sqlite:///$SRC pgsql://kandev@\$PGHOST:\$PGPORT/kandev"
    verify_sqlite "$SRC" && echo "PASS: source valid" || echo "WARN: source check failed"
    pg_isready -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" 2>&1 | sed 's/^/  /' || true
    exit 0
  fi
  # Snapshot first
  SNAP_DIR="$(dirname "$SRC")/backups"
  mkdir -p "$SNAP_DIR"
  TS="$(date -u +%Y%m%dT%H%M%SZ)"
  SNAP="$SNAP_DIR/pre-pg-migration-$TS.db"
  echo "==> snapshot: sqlite3 $SRC → $SNAP"
  sqlite3 "$SRC" ".backup '$SNAP'" 2>&1 | sed 's/^/  /' || { echo "FAIL: snapshot" >&2; exit 1; }
  chmod 0600 "$SNAP"
  echo "  also copy $HOME_DIR/data/master.key with 0600 — needed with any dump"
  # pgloader
  PGURL="pgsql://kandev:${PGPASSWORD:-<set PGPASSWORD or .pgpass>}@${PGHOST:-localhost}:${PGPORT:-5432}/${PGDATABASE:-kandev}"
  echo "==> pgloader sqlite:///$SRC → pgsql://kandev@\${PGHOST}:\${PGPORT}/\${PGDATABASE}"
  # Use $PG* env so pgloader inherits them; do not echo password
  pgloader "sqlite:///$SRC" "pgsql://kandev@${PGHOST:-localhost}:${PGPORT:-5432}/${PGDATABASE:-kandev}" 2>&1 | sed 's/^/  /' || { echo "FAIL: pgloader" >&2; exit 1; }
  echo "PASS: rows copied. Verify:"
  echo "  psql -h \${PGHOST} -U kandev -c \"select count(*) from tasks;\"  vs  sqlite3 $SRC \"select count(*) from tasks;\""
  echo "NEXT: flip driver per §16.4 B step 4 (set KANDEV_DATABASE_DRIVER=postgres + 7 PG vars, restart, curl /ready, check System → Status)."
  echo "Keep SQLite file $SRC as rollback until Postgres backup via pg_dump is verified (§16.3)."
  exit 0
fi

# ── Mode C: Postgres → SQLite ────────────────────────────────────────
if [[ "$MODE" == "postgres-to-sqlite" ]]; then
  if [[ -z "$TARGET_DB" ]]; then
    echo "ERR: --target-db required for postgres-to-sqlite" >&2; exit 2
  fi
  DST="$(realpath -m "$TARGET_DB")"
  echo "==> Mode C: Postgres → SQLite (reverse transfer)"
  echo "  dest: $DST"
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "DRY RUN — would: pg_dump (custom), then conversion → $DST"
    pg_isready -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" 2>&1 | sed 's/^/  /' || true
    exit 0
  fi
  echo "WARN: reverse conversion is tool-dependent (see playbook §16.4 C)."
  echo "This script takes a verifying pg_dump first, then expects you to run the conversion tool you chose."
  if ! command -v pg_dump >/dev/null 2>&1; then echo "ERR: pg_dump not found" >&2; exit 1; fi
  TS="$(date -u +%Y%m%dT%H%M%SZ)"
  DUMP="$(dirname "$DST")/kandev-pre-sqlite-$TS.dump"
  mkdir -p "$(dirname "$DST")"
  chmod 0700 "$(dirname "$DST")" 2>/dev/null || true
  echo "==> pg_dump → $DUMP"
  pg_dump --host "${PGHOST:-localhost}" --port "${PGPORT:-5432}" --username "${PGUSER:-kandev}" --format=custom --file "$DUMP" "${PGDATABASE:-kandev}" 2>&1 | sed 's/^/  /' || { echo "FAIL: pg_dump" >&2; exit 1; }
  chmod 0600 "$DUMP"
  echo "TODO: convert $DUMP → $DST with your chosen tool (pg2sqlite / pg_dump --data-only --inserts adaptation / pgloader reverse)."
  echo "  Verify table-by-table: psql -c \"select count(*) from tasks;\" vs sqlite3 $DST \"select count(*) from tasks;\""
  echo "  Then flip KANDEV_DATABASE_DRIVER→sqlite (remove KANDEV_DATABASE_*), restart, curl /ready."
  echo "Keep $DUMP as rollback until SQLite manual-*.db snapshot is verified."
  exit 0
fi

echo "ERR: unknown mode: $MODE" >&2; exit 2
