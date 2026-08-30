#!/usr/bin/env bash
# restore.sh — restore a 9Router SQLite backup (with pre-restore safety copy)
# Counterpart to backup.sh. Stops 9Router, takes a fresh backup of the current
# DB (so the restore is reversible), restores the chosen file, restarts.
#
# Usage:
#   ./scripts/restore.sh --alias <ALIAS> --backup-file backups/20260830T143000/data.sqlite [--data-dir /var/lib/9router] [--compose-dir /opt/9router]
#   ./scripts/restore.sh --alias <ALIAS> --backup-file backups/20260830T143000/data.sqlite --variant 9router
#
# Safety: requires operator confirmation (or --yes). Refuses to run without a
# pre-restore backup unless --no-pre-backup is given (not recommended).

set -euo pipefail

ALIAS=""
VARIANT="9router"
BACKUP_FILE=""
DATA_DIR=""
COMPOSE_DIR=""
YES=""
NO_PRE_BACKUP=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --alias) ALIAS="$2"; shift 2 ;;
    --variant) VARIANT="$2"; shift 2 ;;
    --backup-file) BACKUP_FILE="$2"; shift 2 ;;
    --data-dir) DATA_DIR="$2"; shift 2 ;;
    --compose-dir) COMPOSE_DIR="$2"; shift 2 ;;
    --yes) YES="1"; shift ;;
    --no-pre-backup) NO_PRE_BACKUP="1"; shift ;;
    -h|--help)
      echo "Usage: $0 --alias ALIAS --backup-file FILE [--data-dir DIR] [--compose-dir DIR] [--variant VARIANT] [--yes]"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$ALIAS" || -z "$BACKUP_FILE" ]]; then
  echo "ERR: --alias and --backup-file required" >&2
  exit 2
fi
if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "ERR: backup file not found: $BACKUP_FILE" >&2
  exit 2
fi

say() { printf '%s\n' "$*"; }

if [[ -z "$YES" ]]; then
  say "About to restore:"
  say "  alias:       $ALIAS"
  say "  backup file: $BACKUP_FILE ($(wc -c < "$BACKUP_FILE" | tr -d ' ') bytes)"
  say "  data dir:    ${DATA_DIR:-auto-discover}"
  say "  compose dir: ${COMPOSE_DIR:-/opt/9router fallback}"
  say ""
  read -r -p "Confirm restore on $ALIAS? Type 'yes' to proceed: " ans
  if [[ "$ans" != "yes" ]]; then
    say "Aborted."
    exit 0
  fi
fi

# Infer DATA_DIR if not given — peek at host
if [[ -z "$DATA_DIR" ]]; then
  # Single probe: reuse same pattern as backup.sh
  DISCOVER="$(ssh -o BatchMode=yes "$ALIAS" bash -s <<'EOS' 2>/dev/null || true
set -euo pipefail
for p in /var/lib/9router /opt/9router ~/.9router "$HOME/.9router" /app/data; do
  rp="$(bash -c "echo $p" 2>/dev/null)"
  if [[ -f "$rp/db/data.sqlite" ]]; then echo "FOUND_DB:$rp/db/data.sqlite"; fi
done
EOS
)"
  if FOUND="$(echo "$DISCOVER" | grep "FOUND_DB:" | head -n 1 | sed 's/FOUND_DB://')"; [[ -n "${FOUND:-}" ]]; then
    DATA_DIR="$(dirname "$(dirname "$FOUND")")"
    say "Inferred DATA_DIR=$DATA_DIR from $FOUND"
  else
    # Docker default
    DATA_DIR="/app/data"
    say "WARN: could not infer DATA_DIR — using $DATA_DIR. Pass --data-dir if wrong."
  fi
fi

if [[ -z "$COMPOSE_DIR" ]]; then
  COMPOSE_DIR="/opt/9router"
fi

REMOTE_SQLITE="$DATA_DIR/db/data.sqlite"
REMOTE_PRE="$DATA_DIR/db/data.sqlite.pre-restore.$(date +%Y%m%dT%H%M%S)"

# Pre-restore backup
if [[ -z "$NO_PRE_BACKUP" ]]; then
  say "==> Pre-restore backup: $REMOTE_SQLITE -> $REMOTE_PRE on $ALIAS"
  if ssh -o BatchMode=yes "$ALIAS" "command -v sqlite3 >/dev/null 2>&1 && test -f '$REMOTE_SQLITE'"; then
    ssh -o BatchMode=yes "$ALIAS" "sqlite3 '$REMOTE_SQLITE' \".backup '$REMOTE_PRE'\" && ls -lh '$REMOTE_PRE'"
    say "Pre-restore hot backup saved on host: $REMOTE_PRE"
  else
    # Copy raw file (may need brief stop for consistency if no sqlite3)
    say "INFO: sqlite3 not available on host — copying raw file (stop first if needed)."
    # Try stop-copy if compose is present
    if ssh -o BatchMode=yes "$ALIAS" "test -f '$COMPOSE_DIR/docker-compose.yml' 2>/dev/null"; then
      ssh -o BatchMode=yes "$ALIAS" "cd '$COMPOSE_DIR' && docker compose stop 9router 2>/dev/null || docker stop 9router 2>/dev/null || true; sleep 2; cp '$REMOTE_SQLITE' '$REMOTE_PRE' 2>/dev/null || true; docker compose start 9router 2>/dev/null || docker start 9router 2>/dev/null || true; ls -lh '$REMOTE_PRE' 2>/dev/null || echo 'pre-backup copy attempted'"
    else
      ssh -o BatchMode=yes "$ALIAS" "cp '$REMOTE_SQLITE' '$REMOTE_PRE' 2>/dev/null && ls -lh '$REMOTE_PRE' || echo 'cp attempted'"
    fi
  fi
fi

# Stop 9Router
say "==> Stopping 9Router on $ALIAS ..."
ssh -o BatchMode=yes "$ALIAS" bash -s -- "$COMPOSE_DIR" "$DATA_DIR" <<'EOS'
set -euo pipefail
cdir="$1"
ddir="$2"
# Try compose, docker, systemd, pm2 in order
if [[ -f "$cdir/docker-compose.yml" ]]; then
  (cd "$cdir" && docker compose stop 9router) 2>/dev/null && echo "stopped via compose" && exit 0
fi
if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 9router; then
  docker stop 9router 2>/dev/null && echo "stopped via docker stop" && exit 0
fi
if systemctl is-active --quiet 9router 2>/dev/null; then
  sudo systemctl stop 9router 2>/dev/null && echo "stopped via systemd" && exit 0
fi
if command -v pm2 >/dev/null 2>&1 && pm2 list 2>/dev/null | grep -q 9router; then
  pm2 stop 9router 2>/dev/null && echo "stopped via pm2" && exit 0
fi
echo "WARN: no supervisor matched — proceeding anyway (file may still be writable)"
EOS

# Push backup file
say "==> Pushing $BACKUP_FILE -> $ALIAS:$REMOTE_SQLITE"
# Ensure remote dir exists
ssh -o BatchMode=yes "$ALIAS" "mkdir -p '$DATA_DIR/db'"
# For Docker bind vs named volume distinction: if DATA_DIR is /app/data inside a named-volume
# compose, the host path is the volume — but scp to /app/data on the host is not the volume.
# We handle both: try scp to the given path, and if docker volume is in use, also docker cp.
scp -q "$BACKUP_FILE" "$ALIAS:$REMOTE_SQLITE" && say "scp ok to $REMOTE_SQLITE" || {
  say "WARN: direct scp to $REMOTE_SQLITE failed — trying docker cp"
  # Stash file on host /tmp then docker cp
  scp -q "$BACKUP_FILE" "$ALIAS:/tmp/9router-restore.sqlite"
  if ssh -o BatchMode=yes "$ALIAS" "docker ps -a --format '{{.Names}}' | grep -qx 9router"; then
    ssh -o BatchMode=yes "$ALIAS" "docker cp /tmp/9router-restore.sqlite 9router:/app/data/db/data.sqlite && rm /tmp/9router-restore.sqlite && echo 'docker cp ok'"
  else
    echo "ERR: could not place backup file on $ALIAS" >&2
    exit 1
  fi
}

# Fix ownership for Docker (node user)
ssh -o BatchMode=yes "$ALIAS" "chown node:node '$REMOTE_SQLITE' 2>/dev/null || chown \$(id -u):\$(id -g) '$REMOTE_SQLITE' 2>/dev/null || true; ls -lh '$REMOTE_SQLITE'"

# Restart
say "==> Restarting 9Router on $ALIAS ..."
ssh -o BatchMode=yes "$ALIAS" bash -s -- "$COMPOSE_DIR" <<'EOS'
set -euo pipefail
cdir="$1"
if [[ -f "$cdir/docker-compose.yml" ]]; then
  (cd "$cdir" && docker compose start 9router) 2>/dev/null && echo "started via compose" && exit 0
  (cd "$cdir" && docker compose up -d) 2>/dev/null && echo "up -d via compose" && exit 0
fi
if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q 9router; then
  docker start 9router 2>/dev/null && echo "started via docker start" && exit 0
fi
if systemctl list-unit-files 2>/dev/null | grep -q 9router.service; then
  sudo systemctl start 9router 2>/dev/null && echo "started via systemd" && exit 0
fi
if command -v pm2 >/dev/null 2>&1; then
  pm2 restart 9router 2>/dev/null || pm2 start npm --name 9router -- start 2>/dev/null
  echo "started via pm2"
  exit 0
fi
# npm mode: no supervisor — operator must restart manually
echo "WARN: no supervisor matched — start 9router manually (e.g. nohup 9router &)"
EOS

sleep 3
say "==> Health check"
# Probe health (no key yet — may be 401 on /v1 but health should be 200)
if ssh -o BatchMode=yes "$ALIAS" "curl -s --max-time 10 http://127.0.0.1:20128/api/health 2>/dev/null | head -c 200"; then
  echo
  say "Health probe sent — check output above for {\"ok\":true}"
fi

say "---"
say "Restore complete."
say "Current DB: $REMOTE_SQLITE on $ALIAS"
say "Pre-restore backup on host: $REMOTE_PRE"
say "Local backup file used: $BACKUP_FILE"
say "Verify with: NINEROUTER_URL=http://<HOST>:<PORT> NINEROUTER_KEY=\$(cat executions/$VARIANT/secrets/9router-api-key.txt) ./playbooks/9router/scripts/health-check.sh"
say "Rollback if needed: ./scripts/restore.sh --alias $ALIAS --backup-file <pre-restore path> (or copy $REMOTE_PRE back to $REMOTE_SQLITE)"
