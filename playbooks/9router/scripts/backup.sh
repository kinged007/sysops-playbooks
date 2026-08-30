#!/usr/bin/env bash
# backup.sh — 9Router SQLite + config backup
# Produces a timestamped artifact under <BACKUP_DIR> (default: executions/<variant>/backups).
# Supports Docker (named volume or bind), npm, and source modes.
# Never logs secret values.
#
# Usage:
#   ./scripts/backup.sh --alias <ALIAS> --variant 9router              # auto-discovers DATA_DIR
#   ./scripts/backup.sh --alias <ALIAS> --data-dir /var/lib/9router --backup-dir ./backups
#   ./scripts/backup.sh --alias <ALIAS> --compose-dir /opt/9router
#
# The backup contains:
#   data.sqlite            — the 9Router DB (hot backup via sqlite3 .backup when possible)
#   .env.redacted          — env with secrets masked
#   docker-compose.yml     — compose snapshot (if present)
# Requires: ssh access to <ALIAS>. For bind mounts, HOST_DATA_DIR is copied via scp.

set -euo pipefail

ALIAS=""
VARIANT="9router"
DATA_DIR=""
COMPOSE_DIR=""
BACKUP_DIR=""
HOST_DATA_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --alias) ALIAS="$2"; shift 2 ;;
    --variant) VARIANT="$2"; shift 2 ;;
    --data-dir) DATA_DIR="$2"; shift 2 ;;
    --compose-dir) COMPOSE_DIR="$2"; shift 2 ;;
    --backup-dir) BACKUP_DIR="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 --alias ALIAS [--variant 9router[-suffix]] [--data-dir DIR] [--compose-dir DIR] [--backup-dir DIR]"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$ALIAS" ]]; then
  echo "ERR: --alias required" >&2
  exit 2
fi

# Default backup dir: executions/<variant>/backups (persistent per variant)
if [[ -z "$BACKUP_DIR" ]]; then
  BACKUP_DIR="executions/${VARIANT}/backups"
fi

TS="$(date +%Y%m%dT%H%M%S)"
DEST="${BACKUP_DIR}/${TS}"
mkdir -p "$DEST"

say() { printf '%s\n' "$*"; }

# Auto-discover DATA_DIR / COMPOSE_DIR if not given
discover() {
  ssh -o BatchMode=yes "$ALIAS" bash -s <<'EOS'
set -euo pipefail
# Prefer docker inspect, then env, then defaults
if docker inspect 9router --format '{{.Config.Env}}' 2>/dev/null | tr ' ' '\n' | grep -q DATA_DIR; then
  docker inspect 9router --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep DATA_DIR || true
  docker inspect 9router --format '{{json .Mounts}}' 2>/dev/null | head -c 2000; echo
fi
# Check common locations
for p in /var/lib/9router /opt/9router ~/.9router "$HOME/.9router" /app/data; do
  # expand ~ on remote
  rp="$(bash -c "echo $p" 2>/dev/null)"
  if [[ -f "$rp/db/data.sqlite" ]]; then echo "FOUND_DB:$rp/db/data.sqlite"; fi
  if [[ -f "$rp/.env" ]]; then echo "FOUND_ENV:$rp/.env"; fi
  if [[ -f "$rp/docker-compose.yml" ]]; then echo "FOUND_COMPOSE:$rp/docker-compose.yml"; fi
done
# Also check compose default paths
for p in /opt/9router/docker-compose.yml ~/9router/docker-compose.yml ./docker-compose.yml; do
  rp="$(bash -c "echo $p" 2>/dev/null)"
  if [[ -f "$rp" ]]; then echo "FOUND_COMPOSE:$rp"; fi
done
ss -tlnp 2>/dev/null | grep -E ":20128|:20127" | head -n 5 || true
EOS
}

say "==> Discovering on $ALIAS ..."
DISCOVER_OUT="$(discover 2>&1 || true)"
echo "$DISCOVER_OUT" | sed 's/^/  /'

# Note: do not auto-parse DATA_DIR blindly — operator may have passed it explicitly.
# If DATA_DIR was not given, try to infer a sane default; otherwise require it.
if [[ -z "$DATA_DIR" ]]; then
  # Prefer explicit compose data path if visible; fall back to ~/.9router
  if echo "$DISCOVER_OUT" | grep -q "FOUND_DB:"; then
    FOUND="$(echo "$DISCOVER_OUT" | grep "FOUND_DB:" | head -n 1 | sed 's/FOUND_DB://')"
    DATA_DIR="$(dirname "$(dirname "$FOUND")")"
    say "Inferred DATA_DIR=$DATA_DIR from $FOUND"
  else
    # Ask caller to provide it; keep a placeholder for the artifact
    say "WARN: could not infer DATA_DIR — pass --data-dir explicitly for a guaranteed backup."
    DATA_DIR=""
  fi
fi

# Prefer sqlite3 hot backup when sqlite3 is available on the host
do_backup() {
  local remote_data_dir="$1"
  local remote_sqlite="$remote_data_dir/db/data.sqlite"
  local remote_bak="$remote_data_dir/db/data.sqlite.bak.$TS"

  if [[ -z "$remote_data_dir" ]]; then
    say "SKIP: DATA_DIR unknown — collecting compose/env only."
    return 0
  fi

  say "==> Backing up $remote_sqlite on $ALIAS ..."
  if ssh -o BatchMode=yes "$ALIAS" "test -f '$remote_sqlite'"; then
    # Try sqlite3 .backup (hot, consistent)
    if ssh -o BatchMode=yes "$ALIAS" "command -v sqlite3 >/dev/null 2>&1"; then
      ssh -o BatchMode=yes "$ALIAS" "sqlite3 '$remote_sqlite' \".backup '$remote_bak'\" && ls -lh '$remote_bak'"
      # Pull the hot backup
      scp -q "$ALIAS:$remote_bak" "$DEST/data.sqlite"
      say "Pulled hot backup -> $DEST/data.sqlite ($(wc -c < "$DEST/data.sqlite" | tr -d ' ') bytes)"
      # Keep remote bak for a bit (do not auto-delete; operator decides)
    else
      # Fallback: try to stop, copy, restart — but only if we can detect the supervisor
      say "INFO: sqlite3 not on host — attempting consistent copy (may need a brief stop)."
      # Detect compose vs docker vs systemd vs pm2
      if ssh -o BatchMode=yes "$ALIAS" "test -f '${COMPOSE_DIR:-/opt/9router}/docker-compose.yml' 2>/dev/null || test -f './docker-compose.yml' 2>/dev/null"; then
        local cdir="${COMPOSE_DIR:-/opt/9router}"
        say "  compose detected — stopping 9router for a consistent copy..."
        ssh -o BatchMode=yes "$ALIAS" "cd '$cdir' 2>/dev/null && docker compose stop 9router || docker stop 9router 2>/dev/null || true; sleep 2"
        scp -q "$ALIAS:$remote_sqlite" "$DEST/data.sqlite" || {
          say "WARN: copy failed while stopped — trying without stop"
          ssh -o BatchMode=yes "$ALIAS" "cd '$cdir' 2>/dev/null && docker compose start 9router || docker start 9router 2>/dev/null || true"
          scp -q "$ALIAS:$remote_sqlite" "$DEST/data.sqlite"
        }
        # Restart
        ssh -o BatchMode=yes "$ALIAS" "cd '$cdir' 2>/dev/null && docker compose start 9router || docker start 9router 2>/dev/null || true"
        say "Pulled (stop-copy-start) -> $DEST/data.sqlite"
      else
        # Last resort: direct scp (may be slightly inconsistent on a live DB)
        say "WARN: no supervisor detected — pulling live file (prefer installing sqlite3 on the host for hot backups)."
        scp -q "$ALIAS:$remote_sqlite" "$DEST/data.sqlite" || {
          echo "ERR: could not pull $remote_sqlite" >&2; return 1
        }
        say "Pulled live file -> $DEST/data.sqlite (verify with: sqlite3 $DEST/data.sqlite 'PRAGMA integrity_check;')"
      fi
    fi
  else
    say "WARN: $remote_sqlite not found on $ALIAS — is DATA_DIR correct? ($remote_data_dir)"
    say "  Discover output above may hint at the real path. Re-run with --data-dir <path>."
  fi
}

do_backup "$DATA_DIR"

# Collect env (redacted) + compose
collect_aux() {
  local cdir="${COMPOSE_DIR:-}"
  # Try to locate env
  for cand in "$DATA_DIR/.env" "${cdir:-/opt/9router}/.env" "./.env" "$HOME/.9router/.env"; do
    # expand ~ on remote for the test, but do it via bash -c
    if ssh -o BatchMode=yes "$ALIAS" "test -f '$cand' 2>/dev/null || test -f \"\$(bash -c 'echo $cand')\" 2>/dev/null"; then
      # Pull and redact
      local tmp
      tmp="$(mktemp)"
      if scp -q "$ALIAS:$cand" "$tmp" 2>/dev/null; then
        sed -E 's/(SECRET|PASSWORD|KEY|TOKEN)([^=]*)=.*/\1\2=***redacted***/I' "$tmp" > "$DEST/.env.redacted"
        rm -f "$tmp"
        say "Collected env (redacted) from $cand -> $DEST/.env.redacted"
      elif rpcand="$(ssh -o BatchMode=yes "$ALIAS" "bash -c 'echo $cand'" 2>/dev/null)"; scp -q "$ALIAS:$rpcand" "$tmp" 2>/dev/null; then
        sed -E 's/(SECRET|PASSWORD|KEY|TOKEN)([^=]*)=.*/\1\2=***redacted***/I' "$tmp" > "$DEST/.env.redacted"
        rm -f "$tmp"
        say "Collected env (redacted) from $rpcand -> $DEST/.env.redacted"
      fi
      break
    fi
  done

  # Compose file
  for cand in "${cdir:-/opt/9router}/docker-compose.yml" "./docker-compose.yml" "$HOME/9router/docker-compose.yml"; do
    if ssh -o BatchMode=yes "$ALIAS" "test -f '$cand' 2>/dev/null || test -f \"\$(bash -c 'echo $cand')\" 2>/dev/null"; then
      local tmp2
      tmp2="$(mktemp)"
      if scp -q "$ALIAS:$cand" "$tmp2" 2>/dev/null; then
        cp "$tmp2" "$DEST/docker-compose.yml"
        rm -f "$tmp2"
        say "Collected $cand -> $DEST/docker-compose.yml"
      elif rpcand2="$(ssh -o BatchMode=yes "$ALIAS" "bash -c 'echo $cand'" 2>/dev/null)"; scp -q "$ALIAS:$rpcand2" "$tmp2" 2>/dev/null; then
        cp "$tmp2" "$DEST/docker-compose.yml"
        rm -f "$tmp2"
        say "Collected $rpcand2 -> $DEST/docker-compose.yml"
      fi
      break
    fi
  done
}

collect_aux || true

# Manifest
{
  echo "variant: $VARIANT"
  echo "alias: $ALIAS"
  echo "timestamp: $TS"
  echo "data_dir: ${DATA_DIR:-unknown}"
  echo "compose_dir: ${COMPOSE_DIR:-unknown}"
  echo "artifact: $DEST"
  echo "files:"
  ls -lh "$DEST" 2>/dev/null | sed 's/^/  /'
} > "$DEST/MANIFEST.txt"

say "---"
say "Backup artifact: $DEST"
ls -lh "$DEST" | sed 's/^/  /'
if [[ -f "$DEST/data.sqlite" ]]; then
  say "DB bytes: $(wc -c < "$DEST/data.sqlite" | tr -d ' ')"
  # Quick integrity hint (local)
  if command -v sqlite3 >/dev/null 2>&1; then
    say "Integrity: $(sqlite3 "$DEST/data.sqlite" 'PRAGMA integrity_check;' 2>&1 | head -n 5)"
  fi
fi
say "Next: record $DEST in the runbook; keep it alongside executions/$VARIANT/secrets/ (both gitignored)."
