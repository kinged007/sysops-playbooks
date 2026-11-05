#!/usr/bin/env bash
# restore-mailu.sh — restore a Mailu server from a backup-mailu.sh archive.
# Usage: restore-mailu.sh <MAIL_ALIAS> <BACKUP_PATH>
#   <BACKUP_PATH> = local .tar.gz produced by backup-mailu.sh
# WARNING: OVERWRITES live mail data. Requires explicit operator approval
# (branches/ops.md §2). Assumes the stack is DOWN (docker compose down)
# before restoring; refuses to run if mail containers are still up.

set -euo pipefail

ALIAS="${1:?usage: restore-mailu.sh <MAIL_ALIAS> <BACKUP_PATH>}"
BACKUP="${2:?usage: restore-mailu.sh <MAIL_ALIAS> <BACKUP_PATH>}"
[ -f "$BACKUP" ] || { echo "BACKUP file not found: $BACKUP"; exit 2; }

echo "!! This OVERWRITES live mail data on $ALIAS !!"
echo "!! Operator approval required (branches/ops.md §2)         !!"
read -r -p "Type YES to continue: " CONFIRM
[ "$CONFIRM" = "YES" ] || { echo "Aborted."; exit 1; }

echo "[1/5] Pre-flight: stack must be DOWN"
ssh "$ALIAS" 'docker ps --format "{{.Names}}" | grep -E "mailu-" && { echo "ERROR: mailu containers still running — run docker compose down first"; exit 1; } || echo "OK: stack is down"'

echo "[2/5] Uploading archive"
REMOTE_TMP="/tmp/mailu-restore"
ssh "$ALIAS" "mkdir -p $REMOTE_TMP"
scp "$BACKUP" "$ALIAS:$REMOTE_TMP/restore.tar.gz"

echo "[3/5] Restoring volume + DB + configs"
# maildir volume (contents of /mailu incl. main.db for sqlite)
ssh "$ALIAS" "docker run --rm -v mailu-data:/mailu -v $REMOTE_TMP:/restore alpine sh -c 'tar xzf /restore/restore.tar.gz -C /tmp 2>/dev/null; tar xzf /tmp/volumes.tar.gz -C /mailu; chown -R 5000:5000 /mailu'"
# postgres variant: load dump (if present)
ssh "$ALIAS" 'if [ -f '"$REMOTE_TMP"'/main.sql ] || tar tzf '"$REMOTE_TMP"'/restore.tar.gz 2>/dev/null | grep -q main.sql; then
  PG="$(docker ps --format "{{.Names}}" --all | grep postgres | head -1)"
  [ -n "$PG" ] && { docker start "$PG" >/dev/null; sleep 5; docker exec -i "$PG" psql -U "$(docker exec "$PG" printenv POSTGRES_USER)" "$(docker exec "$PG" printenv POSTGRES_DB)" < '"$REMOTE_TMP"'/main.sql || echo "WARN: pg restore failed — check dump format"; }
fi'
# configs (compose + env) — assumes mailu.env ROOT or /opt/mailu
ssh "$ALIAS" "cd /opt/mailu 2>/dev/null && tar xzf $REMOTE_TMP/configs.tar.gz && echo configs restored" || echo "WARN: configs not restored — place compose/env manually"

echo "[4/5] Starting stack"
ssh "$ALIAS" 'cd /opt/mailu && docker compose -p mailu up -d'

echo "[5/5] Verifying — run branches/common.md §2 (TLS) + §3 (SMTP) battery now."
ssh "$ALIAS" 'docker compose -p mailu ps 2>/dev/null || cd /opt/mailu && docker compose ps'
echo "Cleanup note: remove $REMOTE_TMP on the server after verification."
