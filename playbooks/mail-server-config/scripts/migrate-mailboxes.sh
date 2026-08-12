#!/usr/bin/env bash
# migrate-mailboxes.sh — imapsync wrapper for the migrate branch.
# Usage:
#   migrate-mailboxes.sh --source <SRC_HOST> --target <TGT_HOST> \
#       --account <USER> [--src-passfile <FILE>] [--tgt-passfile <FILE>] \
#       [--dry-run] [--delta] [--logdir <DIR>]
#   --dry-run  imapsync dry mode (no writes on target)
#   --delta    delta pass (re-run after full pass; imapsync is incremental,
#              so re-runs only copy new messages) — labels the log
# Passwords: files only (--passfile1/--passfile2), NEVER command-line.
# Files come from the run's secrets/ folder (AGENTS.md §1.5).
# Requires imapsync installed locally. See branches/migrate.md §3.

set -euo pipefail

SRC=""; TGT=""; USER=""; PF1=""; PF2=""; DRY=""; DELTA=""; LOGDIR="logs"

while [ $# -gt 0 ]; do
  case "$1" in
    --source) SRC="$2"; shift 2 ;;
    --target) TGT="$2"; shift 2 ;;
    --account) USER="$2"; shift 2 ;;
    --src-passfile) PF1="$2"; shift 2 ;;
    --tgt-passfile) PF2="$2"; shift 2 ;;
    --dry-run) DRY="--dry"; shift ;;
    --delta) DELTA=1; shift ;;
    --logdir) LOGDIR="$2"; shift 2 ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done

[ -n "$SRC" ] && [ -n "$TGT" ] && [ -n "$USER" ] || { echo "usage: see header"; exit 2; }
command -v imapsync >/dev/null || { echo "imapsync not installed (apt: imapsync)"; exit 2; }

[ -n "$PF1" ] && [ -f "$PF1" ] || { echo "source passfile required (run secrets/, no inline passwords)"; exit 2; }
[ -n "$PF2" ] && [ -f "$PF2" ] || { echo "target passfile required"; exit 2; }

mkdir -p "$LOGDIR"
MODE="full"
[ -n "$DELTA" ] && MODE="delta"
LOG="$LOGDIR/migrate-$MODE-$(echo "$USER" | tr '@' '_').log"

echo "== migrate ($MODE) $USER : $SRC -> $TGT  ($( [ -n "$DRY" ] && echo DRY-RUN || echo LIVE )) =="
echo "log: $LOG"

imapsync \
  --host1 "$SRC"  --user1 "$USER"  --passfile1 "$PF1"  --ssl1 \
  --host2 "$TGT"  --user2 "$USER"  --passfile2 "$PF2"  --ssl2 \
  --syncinternaldates --noauthmd5 --addheader \
  $DRY 2>&1 | tee "$LOG"

echo "== done. Report: folders + messages copied per imapsync summary in $LOG =="
echo "== verify counts against source before cutover (migrate.md §3) =="
