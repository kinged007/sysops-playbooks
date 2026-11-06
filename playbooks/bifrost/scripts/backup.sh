#!/usr/bin/env bash
# Back up Bifrost SQLite state. Prefers online .backup, falls back to file copy.
# Usage: backup.sh <ALIAS> <APP_DIR> [<BACKUP_DIR>]
# Prints the backup path. Live DB is never modified.
set -euo pipefail
ALIAS="${1:?usage: backup.sh ALIAS APP_DIR [BACKUP_DIR]}"
APP_DIR="$2"
BACKUP_DIR="${3:-$APP_DIR/backups}"
STAMP="$(date +%F-%H%M%S)"
ssh "$ALIAS" "mkdir -p '$BACKUP_DIR' && \
  (sqlite3 '$APP_DIR/config.db' '.backup $BACKUP_DIR/config.db.bak-$STAMP' 2>/dev/null && \
   sqlite3 '$APP_DIR/logs.db' '.backup $BACKUP_DIR/logs.db.bak-$STAMP' 2>/dev/null && \
   cp '$APP_DIR/config.json' '$BACKUP_DIR/config.json.bak-$STAMP' 2>/dev/null || \
   cp -a '$APP_DIR/config.db' '$BACKUP_DIR/config.db.bak-$STAMP') && \
  ls -lh '$BACKUP_DIR/'*"-$STAMP"*"
