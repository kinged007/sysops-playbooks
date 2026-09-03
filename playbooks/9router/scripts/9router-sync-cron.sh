#!/usr/bin/env bash
# 9router-sync-cron.sh — cron wrapper for 9router-sync.py
# Syncs model-inventory -> 9Router providers/combos + regenerates CLI configs.
# Safe for unattended execution: no secrets on CLI, flock lock, timestamped logs.
#
# What it does (every Monday 16:00):
#   1. Resolves repo root from its own location (so cron CWD does not matter)
#   2. Picks python: $PYTHON_BIN → .venv/bin/python → .venv/Scripts/python.exe → python3 → python
#   3. Runs 9router-sync.py (auto-discovers executions/*9router*/**/9router-sync*.yaml)
#   4. Logs to executions/<variant>/logs/<ISO>-9router-sync-cron.log (+ stdout for cron mail)
#
# Usage (manual):
#   ./playbooks/9router/scripts/9router-sync-cron.sh [--config PATH] [--verbose] [--dry-run]
#   ./playbooks/9router/scripts/9router-sync-cron.sh --help
#
# Cron (every Monday 16:00):
#   0 16 * * 1 /opt/sysops-playbooks/playbooks/9router/scripts/9router-sync-cron.sh >> /var/log/9router-sync-cron.log 2>&1
#   # or user crontab:
#   0 16 * * 1 /home/<user>/sysops-playbooks/playbooks/9router/scripts/9router-sync-cron.sh
#
# Systemd timer alternative:
#   See templates/systemd-9router-sync.{service,timer}
#   systemctl enable --now 9router-sync.timer
#
# Note: model-inventory-cron.sh at 15:00 fetches the inventory first; this 16:00 job
# syncs it to 9Router. You can run either independently — this script also works if
# inventory is already fresh.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# playbooks/9router/scripts -> repo root is 3 levels up
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

CONFIG=""
VERBOSE=""
DRY_RUN=""
PYTHON_BIN="${PYTHON_BIN:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2 ;;
    --verbose) VERBOSE="--verbose"; shift ;;
    --dry-run) DRY_RUN="--dry-run"; shift ;;
    --python) PYTHON_BIN="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,80p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# --- resolve python ---
pick_python() {
  if [[ -n "${PYTHON_BIN}" && -x "${PYTHON_BIN}" ]]; then
    echo "${PYTHON_BIN}"; return 0
  fi
  for cand in "${REPO_ROOT}/.venv/bin/python" "${REPO_ROOT}/.venv/Scripts/python.exe" "${REPO_ROOT}/.venv/bin/python3" "./.venv/bin/python" "./.venv/Scripts/python.exe"; do
    if [[ -x "${cand}" ]]; then
      echo "${cand}"; return 0
    fi
  done
  if command -v python3 >/dev/null 2>&1; then echo "python3"; return 0; fi
  if command -v python >/dev/null 2>&1; then echo "python"; return 0; fi
  return 1
}

if ! PYTHON="$(pick_python 2>/dev/null)"; then
  echo "ERR: no python found (set PYTHON_BIN or create .venv)" >&2
  exit 1
fi

# --- resolve variant dir for logging ---
VARIANT_DIR="${REPO_ROOT}/executions/9router"
if [[ -n "${CONFIG}" ]]; then
  CFG_ABS="$(realpath -m "${CONFIG}" 2>/dev/null || readlink -f "${CONFIG}" 2>/dev/null || echo "${CONFIG}")"
  if [[ "${CFG_ABS}" == *"executions/"* ]]; then
    VARIANT_DIR="$(echo "${CFG_ABS}" | sed -E 's#(.*executions/[^/]+)/.*#\1#')"
  fi
else
  FOUND_CFG="$(find "${REPO_ROOT}/executions" -maxdepth 4 -path "*9router*9router-sync*.yaml" -print -quit 2>/dev/null || true)"
  if [[ -n "${FOUND_CFG}" ]]; then
    VARIANT_DIR="$(echo "${FOUND_CFG}" | sed -E 's#(.*executions/[^/]+)/.*#\1#')"
    CONFIG="${FOUND_CFG}"
  fi
fi

LOGS_DIR="${VARIANT_DIR}/logs"
mkdir -p "${LOGS_DIR}"

TS="$(date -u +%Y-%m-%dT%H%M%SZ 2>/dev/null || date +%Y%m%dT%H%M%S)"
LOG_FILE="${LOGS_DIR}/${TS%% *}-9router-sync-cron.log"
# tee to log + stdout (cron mail)
exec > >(tee -a "${LOG_FILE}") 2>&1 || true

echo "=== 9router-sync-cron ${TS} ==="
echo "repo: ${REPO_ROOT}"
echo "python: ${PYTHON} ($(${PYTHON} --version 2>&1 | head -n1))"
echo "variant: ${VARIANT_DIR}"
echo "config: ${CONFIG:-auto-discover (executions/*9router*/**/9router-sync*.yaml)}"
echo "logs: ${LOG_FILE}"

# --- lock to avoid overlap with model-inventory-cron (also touches 9Router) ---
LOCK_FILE="/tmp/9router-sync-cron.lock"
if command -v flock >/dev/null 2>&1; then
  exec 9>"${LOCK_FILE}"
  if ! flock -n 9; then
    echo "SKIP: another 9router-sync-cron is running (lock ${LOCK_FILE})" >&2
    exit 0
  fi
else
  if ! mkdir "${LOCK_FILE}.d" 2>/dev/null; then
    echo "SKIP: lock exists ${LOCK_FILE}.d" >&2
    exit 0
  fi
  trap 'rmdir "${LOCK_FILE}.d" 2>/dev/null || true' EXIT
fi

# --- run 9router-sync.py ---
SYNC_ARGS=()
if [[ -n "${CONFIG}" ]]; then SYNC_ARGS+=(--config "${CONFIG}"); fi
if [[ -n "${VERBOSE}" ]]; then SYNC_ARGS+=("${VERBOSE}"); fi
if [[ -n "${DRY_RUN}" ]]; then SYNC_ARGS+=("${DRY_RUN}"); fi

echo "--- running 9router-sync.py ${SYNC_ARGS[*]:-} ---"
set +e
"${PYTHON}" "${REPO_ROOT}/playbooks/9router/scripts/9router-sync.py" "${SYNC_ARGS[@]}"
SYNC_RC=$?
set -e
if [[ ${SYNC_RC} -ne 0 ]]; then
  echo "ERR: 9router-sync.py exited ${SYNC_RC}" >&2
  exit ${SYNC_RC}
fi

echo "--- 9router-sync.py done ---"
echo "=== done ${TS} log: ${LOG_FILE} ==="
echo "combos: ${VARIANT_DIR}/combos/*.json + *.csv"
echo "generated: ${VARIANT_DIR}/generated/"

