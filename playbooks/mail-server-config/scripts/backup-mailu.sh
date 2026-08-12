#!/usr/bin/env bash
# backup-mailu.sh — off-box backup of a Mailu server (WRITE on the server,
# additive only). Usage: backup-mailu.sh <MAIL_ALIAS> <DEST>
#   <DEST> = local directory that receives the archive (off-box, required)
# Backs up: DB (sqlite consistent snapshot / postgres pg_dump), maildir
# volume, certs, overrides, compose + env. Verifies the archive, then
# deletes the server-side temp copy. See branches/ops.md §1.
# Requires ssh key access and docker on the server.

set -euo pipefail

ALIAS="${1:?usage: backup-mailu.sh <MAIL_ALIAS> <DEST>}"
DEST="${2:?usage: backup-mailu.sh <MAIL_ALIAS> <DEST>}"
[ -d "$DEST" ] || { echo "DEST must be an existing local directory"; exit 2; }

TS="$(date +%Y%m%d-%H%M%S)"
STAMP="mailu-backup-$TS"
REMOTE_TMP="/tmp/$STAMP"
ARCHIVE="$STAMP.tar.gz"

echo "[1/6] Taking DB snapshot on $ALIAS"
ssh "$ALIAS" "mkdir -p $REMOTE_TMP"
ssh "$ALIAS" 'if docker exec mailu-admin test -f /mailu/main.db 2>/dev/null; then
  docker exec mailu-admin python3 -c "import sqlite3; s=sqlite3.connect(\"/mailu/main.db\"); d=sqlite3.connect(\"/tmp/main.db\"); s.backup(d); d.close(); s.close()"
  docker cp mailu-admin:/tmp/main.db '"$REMOTE_TMP"'/main.db
else
  PG="$(docker ps --format "{{.Names}}" | grep postgres | head -1)"
  docker exec "$PG" pg_dump -U "$(docker exec "$PG" printenv POSTGRES_USER)" "$(docker exec "$PG" printenv POSTGRES_DB)" > '"$REMOTE_TMP"'/main.sql
fi'

echo "[2/6] Archiving maildir volume + configs"
ssh "$ALIAS" "docker run --rm -v mailu-data:/mailu:ro -v $REMOTE_TMP:/backup alpine tar czf /backup/volumes.tar.gz -C /mailu . 2>/dev/null"
ssh "$ALIAS" "cd $(ssh "$ALIAS" 'printenv ROOT 2>/dev/null || echo /opt/mailu') 2>/dev/null; tar czf $REMOTE_TMP/configs.tar.gz docker-compose.yml mailu.env 2>/dev/null || echo WARN: config files not found at assumed root"

echo "[3/6] Pulling archive off-box to $DEST"
ssh "$ALIAS" "tar czf $REMOTE_TMP/$ARCHIVE -C $REMOTE_TMP main.db main.sql volumes.tar.gz configs.tar.gz 2>/dev/null || tar czf $REMOTE_TMP/$ARCHIVE -C $REMOTE_TMP main.db volumes.tar.gz configs.tar.gz"
scp "$ALIAS:$REMOTE_TMP/$ARCHIVE" "$DEST/$ARCHIVE"

echo "[4/6] Verifying archive"
gzip -t "$DEST/$ARCHIVE"
echo "  files in archive: $(tar tzf "$DEST/$ARCHIVE" | wc -l)"
ls -lh "$DEST/$ARCHIVE"

echo "[5/6] Cleaning up server-side temp"
ssh "$ALIAS" "rm -rf $REMOTE_TMP"

echo "[6/6] DONE. Next: ops.md §1 verify step (spot-extract + open the dump)."
