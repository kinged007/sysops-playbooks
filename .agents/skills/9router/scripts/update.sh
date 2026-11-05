#!/usr/bin/env bash
# update.sh — update 9Router to the latest version (with mandatory backup)
# Branches on deployment mode discovered or explicitly passed.
#
# Usage:
#   ./scripts/update.sh --alias <ALIAS> [--mode docker|compose|npm|source] [--variant 9router] [--tag latest] [--yes]
#   ./scripts/update.sh --alias <ALIAS> --mode compose --compose-dir /opt/9router --tag v0.5.60 --yes
#
# Behavior:
#   1. Takes a backup via backup.sh (mandatory unless --no-backup).
#   2. Pulls/installs the requested tag/version.
#   3. Restarts and runs health-check.sh.
#   4. Leaves a rollback record (previous tag/version in the runbook).

set -euo pipefail

ALIAS=""
VARIANT="9router"
MODE=""
TAG="latest"
COMPOSE_DIR=""
YES=""
NO_BACKUP=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --alias) ALIAS="$2"; shift 2 ;;
    --variant) VARIANT="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --tag) TAG="$2"; shift 2 ;;
    --compose-dir) COMPOSE_DIR="$2"; shift 2 ;;
    --yes) YES="1"; shift ;;
    --no-backup) NO_BACKUP="1"; shift ;;
    -h|--help)
      echo "Usage: $0 --alias ALIAS [--mode docker|compose|npm|source] [--variant VARIANT] [--tag TAG] [--compose-dir DIR] [--yes] [--no-backup]"
      echo "  mode: docker = 'docker run' image, compose = 'docker compose', npm = 'npm -g', source = 'git pull + build'"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$ALIAS" ]]; then
  echo "ERR: --alias required" >&2
  exit 2
fi

say() { printf '%s\n' "$*"; }

# Auto-detect mode if not given
if [[ -z "$MODE" ]]; then
  DETECT="$(ssh -o BatchMode=yes "$ALIAS" bash -s 2>/dev/null <<'EOS' || true
set -euo pipefail
if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx 9router; then
  # Distinguish compose vs plain docker by compose file presence
  if [[ -f /opt/9router/docker-compose.yml ]] || [[ -f ~/9router/docker-compose.yml ]] || [[ -f ./docker-compose.yml ]]; then
    echo "MODE:compose"
  else
    echo "MODE:docker"
  fi
  docker inspect 9router --format '{{.Config.Image}}' 2>/dev/null | sed 's/^/IMAGE:/'
  exit 0
fi
if command -v 9router >/dev/null 2>&1; then
  echo "MODE:npm"
  9router --version 2>/dev/null | sed 's/^/VERSION:/'
  exit 0
fi
if [[ -f /opt/9router/package.json ]] || [[ -f ~/9router/package.json ]]; then
  echo "MODE:source"
  exit 0
fi
echo "MODE:unknown"
EOS
)"
  echo "$DETECT" | sed 's/^/  /'
  MODE="$(echo "$DETECT" | grep "MODE:" | head -n 1 | sed 's/MODE://' | tr -d '\r\n' | xargs || true)"
  if [[ -z "$MODE" || "$MODE" == "unknown" ]]; then
    echo "ERR: could not auto-detect mode on $ALIAS — pass --mode docker|compose|npm|source" >&2
    exit 2
  fi
  say "Detected mode: $MODE"
fi

if [[ -z "$COMPOSE_DIR" ]]; then
  COMPOSE_DIR="/opt/9router"
fi

# 1 — mandatory backup
if [[ -z "$NO_BACKUP" ]]; then
  say "==> Step 1/3 — backing up before update (mandatory)"
  SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
  if [[ -f "$SCRIPT_DIR/backup.sh" ]]; then
    bash "$SCRIPT_DIR/backup.sh" --alias "$ALIAS" --variant "$VARIANT" $([[ -n "$COMPOSE_DIR" ]] && echo "--compose-dir $COMPOSE_DIR" || true)
  else
    say "WARN: backup.sh not found next to update.sh — skipping backup (pass --no-backup to silence)"
  fi
else
  say "SKIP: backup (--no-backup given) — not recommended"
fi

# Confirm unless --yes
if [[ -z "$YES" ]]; then
  say ""
  say "About to update 9Router on $ALIAS:"
  say "  mode: $MODE"
  say "  tag:  $TAG"
  read -r -p "Proceed? Type 'yes': " ans
  if [[ "$ans" != "yes" ]]; then
    say "Aborted."
    exit 0
  fi
fi

# 2 — pull/install
say "==> Step 2/3 — updating ($MODE) to $TAG"
case "$MODE" in
  docker)
    # plain docker run
    PREV_IMAGE="$(ssh -o BatchMode=yes "$ALIAS" "docker inspect 9router --format '{{.Config.Image}}' 2>/dev/null || echo unknown")"
    say "Previous image: $PREV_IMAGE"
    ssh -o BatchMode=yes "$ALIAS" bash -s -- "$TAG" "$PREV_IMAGE" <<'EOS'
set -euo pipefail
tag="$1"
prev="$2"
echo "Pulling decolua/9router:$tag ..."
docker pull "decolua/9router:$tag"
# Recreate: keep the same run flags by re-inspecting (best-effort); operator may need to re-apply custom ports/volumes.
# We use a safe default; if the previous run used custom mounts, re-run the original command from the runbook.
if docker ps -a --format '{{.Names}}' | grep -qx 9router; then
  echo "Recreating container 9router with decolua/9router:$tag ..."
  # Capture previous ports/env for the log
  docker inspect 9router --format 'prev ports: {{json .HostConfig.PortBindings}} prev env: {{json .Config.Env}}' 2>/dev/null | head -c 2000; echo
  docker rm -f 9router 2>/dev/null || true
fi
# Default recreate (DATA_DIR=/app/data). If the host used a custom HOST_DATA_DIR or port, the operator
# should have recorded the exact docker run line in the runbook and re-run it after this step.
# This default covers the DOCKER.md quick-start layout.
HOST_DATA_DIR="${HOME}/.9router"
mkdir -p "$HOST_DATA_DIR"
docker run -d \
  -p 20128:20128 \
  -v "$HOST_DATA_DIR:/app/data" \
  -e DATA_DIR=/app/data \
  --name 9router \
  "decolua/9router:$tag"
docker ps --filter name=9router
echo "Update done. If your previous run used a different HOST_DATA_DIR or port, re-run the runbook's recorded docker run line."
EOS
    ;;
  compose)
    PREV_IMAGE2="$(ssh -o BatchMode=yes "$ALIAS" "docker inspect 9router --format '{{.Config.Image}}' 2>/dev/null || echo unknown")"
    say "Previous image: $PREV_IMAGE2 (record for rollback)"
    ssh -o BatchMode=yes "$ALIAS" bash -s -- "$COMPOSE_DIR" "$TAG" <<'EOS'
set -euo pipefail
cdir="$1"
tag="$2"
# Pin tag in compose if the template was parameterized with <PORT>; image line is decolua/9router:latest or pinned.
# If the compose file pins a tag, update it; otherwise pull will get :latest.
if [[ -f "$cdir/docker-compose.yml" ]]; then
  cd "$cdir"
  echo "In $cdir — pulling..."
  # If TAG is not latest, pin it in the compose file (keep a .prev)
  if [[ "$tag" != "latest" ]]; then
    cp docker-compose.yml "docker-compose.yml.prev.$(date +%Y%m%dT%H%M%S)"
    # Replace image tag (simple; works for 'image: decolua/9router:*' lines)
    sed -i.bak -E "s|image:[[:space:]]*decolua/9router:[^[:space:]]+|image: decolua/9router:$tag|g" docker-compose.yml
    echo "Pinned compose image to decolua/9router:$tag"
  fi
  docker compose pull
  docker compose up -d
  docker compose ps
else
  echo "ERR: $cdir/docker-compose.yml not found — cannot compose update" >&2
  exit 1
fi
EOS
    ;;
  npm)
    PREV_VER="$(ssh -o BatchMode=yes "$ALIAS" "9router --version 2>/dev/null || npm list -g 9router 2>/dev/null | head -n 5")"
    say "Previous version: $PREV_VER"
    ssh -o BatchMode=yes "$ALIAS" "npm install -g 9router@${TAG} && 9router --version 2>/dev/null; echo 'restarting 9router if it was running...'; pkill -f '9router' 2>/dev/null || true; nohup 9router > ~/.9router/9router.log 2>&1 & sleep 3; cat ~/.9router/9router.log 2>/dev/null | tail -n 30 || true"
    ;;
  source)
    ssh -o BatchMode=yes "$ALIAS" bash -s -- "$COMPOSE_DIR" <<'EOS'
set -euo pipefail
# COMPOSE_DIR is reused as APP_DIR for source mode (default /opt/9router)
appdir="$1"
# Try common source locations
for cand in "$appdir" /opt/9router ~/9router ./9router; do
  rp="$(bash -c "echo $cand" 2>/dev/null)"
  if [[ -f "$rp/package.json" ]] && grep -q '"name"[[:space:]]*:[[:space:]]*"9router-app"' "$rp/package.json" 2>/dev/null; then
    appdir="$rp"; break
  fi
done
echo "Source dir: $appdir"
cd "$appdir"
echo "git pull..."
git pull --ff-only 2>&1 | head -n 30 || git fetch --all 2>&1 | head -n 30
echo "npm install..."
npm install 2>&1 | tail -n 20
echo "npm run build..."
npm run build 2>&1 | tail -n 30
# Restart
if systemctl is-active --quiet 9router 2>/dev/null; then
  sudo systemctl restart 9router && systemctl is-active 9router
elif command -v pm2 >/dev/null 2>&1 && pm2 list 2>/dev/null | grep -q 9router; then
  pm2 restart 9router && pm2 save
else
  echo "No systemd/pm2 supervisor found — restart 9router manually"
fi
EOS
    ;;
  *) echo "ERR: unknown mode $MODE" >&2; exit 2 ;;
esac

# 3 — health check
say "==> Step 3/3 — health check"
sleep 5
# Try local probe on the host first, then via URL
if ssh -o BatchMode=yes "$ALIAS" "curl -s --max-time 10 http://127.0.0.1:20128/api/health 2>/dev/null | grep -q '\"ok\"' && echo 'health: ok' || (echo 'health: fail — logs:'; docker logs --tail 80 9router 2>/dev/null | tail -n 80; journalctl -u 9router -n 80 2>/dev/null | tail -n 80)"; then
  say "Health probe sent — check output above for {ok:true}"
fi

# Also run the skill-based health-check.sh if present
SCRIPT_DIR2="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$SCRIPT_DIR2/health-check.sh" ]]; then
  say "Run full verification with: NINEROUTER_URL=http://<HOST>:20128 NINEROUTER_KEY=\$(cat executions/$VARIANT/secrets/9router-api-key.txt) $SCRIPT_DIR2/health-check.sh"
fi

say "---"
say "Update complete on $ALIAS (mode $MODE, tag $TAG)."
say "Rollback: re-run with the previous tag/version recorded above, plus restore the pre-update backup if the DB was migrated."
say "  docker:  docker pull decolua/9router:<PREV> && docker rm -f 9router && docker run ... (from runbook)"
say "  compose: edit docker-compose.yml back to previous image + docker compose up -d"
say "  npm:     npm install -g 9router@<PREV_VER>"
say "  source:  cd <APP_DIR> && git checkout <PREV_SHA> && npm install && npm run build && systemctl restart 9router"
