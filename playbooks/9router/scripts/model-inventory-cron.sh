#!/usr/bin/env bash
# model-inventory-cron.sh — cron wrapper for model-inventory.py (+ optional 9router-sync)
# Runs the multi-provider inventory fetcher from cron / systemd timer.
# Safe for unattended execution: no secrets on CLI, locks to avoid overlap,
# logs to executions/<variant>/logs/ and stdout.
#
# Usage (manual):
#   ./playbooks/9router/scripts/model-inventory-cron.sh [--config PATH] [--output-dir DIR] [--verbose] [--no-sync] [--dry-run]
#   ./playbooks/9router/scripts/model-inventory-cron.sh --help
#
# Cron (every Monday 15:00):
#   0 15 * * 1 /opt/sysops-playbooks/playbooks/9router/scripts/model-inventory-cron.sh >> /var/log/model-inventory-cron.log 2>&1
#   # or user crontab:
#   0 15 * * 1 /home/<user>/sysops-playbooks/playbooks/9router/scripts/model-inventory-cron.sh
#
# Systemd timer alternative: see notes/ below — the script is timer-friendly.
#
# What it does:
#   1. Resolves repo root from its own location (so cron CWD does not matter)
#   2. Picks python: $PYTHON_BIN → .venv/bin/python → .venv/Scripts/python.exe → python3 → python
#   3. Runs model-inventory.py (auto-discovers executions/*9router*/model-inventory.config.yaml)
#   4. If executions/<variant>/9router-sync.config.yaml exists and --no-sync not passed, runs 9router-sync.py
#   5. Writes a timestamped log to executions/<variant>/logs/<ISO>-model-inventory-cron.log
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# playbooks/9router/scripts -> repo root is 3 levels up
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

CONFIG=""
OUTPUT_DIR=""
VERBOSE=""
DRY_RUN=""
NO_SYNC=""
PYTHON_BIN="${PYTHON_BIN:-}"
SYNC_BIN=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    --verbose) VERBOSE="--verbose"; shift ;;
    --dry-run) DRY_RUN="--dry-run"; shift ;;
    --no-sync) NO_SYNC="1"; shift ;;
    --python) PYTHON_BIN="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,120p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# --- resolve python (prefer one that can import yaml/requests) ---
has_yaml() { "$1" -c "import yaml, requests" >/dev/null 2>&1; }
pick_python() {
  if [[ -n "${PYTHON_BIN}" && -x "${PYTHON_BIN}" ]]; then
    echo "${PYTHON_BIN}"; return 0
  fi
  # Candidate order: Windows venv first (Git Bash on Windows), then Unix venv
  # Test each for yaml+requests to avoid picking a bare system python that lacks deps
  for cand in "${REPO_ROOT}/.venv/Scripts/python.exe" "${REPO_ROOT}/.venv/Scripts/python" "./.venv/Scripts/python.exe" "./.venv/Scripts/python" "${REPO_ROOT}/.venv/bin/python" "${REPO_ROOT}/.venv/bin/python3" "./.venv/bin/python" "./.venv/bin/python3"; do
    if [[ -x "${cand}" ]]; then
      if has_yaml "${cand}"; then
        echo "${cand}"; return 0
      fi
    fi
  done
  # fall back to any executable even without yaml (will warn but still try)
  for cand in "${REPO_ROOT}/.venv/Scripts/python.exe" "${REPO_ROOT}/.venv/bin/python" "./.venv/Scripts/python.exe" "./.venv/bin/python"; do
    if [[ -x "${cand}" ]]; then
      echo "${cand}"; return 0
    fi
  done
  # system pythons — prefer one with yaml
  for cand in python3 python py; do
    if command -v "${cand}" >/dev/null 2>&1; then
      if has_yaml "${cand}"; then
        echo "${cand}"; return 0
      fi
    fi
  done
  for cand in python3 python py; do
    if command -v "${cand}" >/dev/null 2>&1; then
      echo "${cand}"; return 0
    fi
  done
  return 1
}

if ! PYTHON="$(pick_python 2>/dev/null)"; then
  echo "ERR: no python found (set PYTHON_BIN or create .venv)" >&2
  exit 1
fi

# If PYTHON is a Windows .exe invoked from MSYS/Git Bash, paths like /d/... need conversion.
# Keep native REPO_ROOT for bash; derive WANT for python args when needed.
to_py_path() {
  local p="$1"
  # If python is Windows native and cygpath exists, convert to Windows style
  if [[ "${PYTHON}" == *".exe" ]] && command -v cygpath >/dev/null 2>&1; then
    cygpath -w "${p}" 2>/dev/null || echo "${p}"
  else
    echo "${p}"
  fi
}
PY_REPO_ROOT="$(to_py_path "${REPO_ROOT}")"
PY_CONFIG=""
if [[ -n "${CONFIG}" ]]; then
  PY_CONFIG="$(to_py_path "${CONFIG}")"
fi

# --- resolve config (for log dir) ---
# Let model-inventory.py do its own discovery if CONFIG empty.
# For logging we need a concrete executions variant dir.
VARIANT_DIR="${REPO_ROOT}/executions/9router"
if [[ -n "${CONFIG}" ]]; then
  # if config is executions/<variant>/*.yaml, variant dir is its parent
  CFG_ABS="$(realpath -m "${CONFIG}" 2>/dev/null || readlink -f "${CONFIG}" 2>/dev/null || echo "${CONFIG}")"
  if [[ "${CFG_ABS}" == *"executions/"* ]]; then
    # executions/9router/model-inventory.config.yaml -> executions/9router
    # executions/9router-foo/... -> executions/9router-foo
    VARIANT_DIR="$(echo "${CFG_ABS}" | sed -E 's#(.*executions/[^/]+)/.*#\1#')"
  fi
else
  # auto-discovery fallback: pick first executions/*9router*/model-inventory.config.yaml
  FOUND_CFG="$(find "${REPO_ROOT}/executions" -maxdepth 4 -path "*9router*model-inventory*.yaml" -print -quit 2>/dev/null || true)"
  if [[ -n "${FOUND_CFG}" ]]; then
    VARIANT_DIR="$(echo "${FOUND_CFG}" | sed -E 's#(.*executions/[^/]+)/.*#\1#')"
    CONFIG="${FOUND_CFG}"
  fi
fi

LOGS_DIR="${VARIANT_DIR}/logs"
mkdir -p "${LOGS_DIR}"

TS="$(date -u +%Y-%m-%dT%H%M%SZ 2>/dev/null || date +%Y%m%dT%H%M%S)"
LOG_FILE="${LOGS_DIR}/${TS%% *}-model-inventory-cron.log"
# For cron, also echo to stdout; tee to log
exec > >(tee -a "${LOG_FILE}") 2>&1 || true

echo "=== model-inventory-cron ${TS} ==="
echo "repo: ${REPO_ROOT}"
echo "python: ${PYTHON} ($(${PYTHON} --version 2>&1 | head -n1))"
echo "variant: ${VARIANT_DIR}"
echo "config: ${CONFIG:-auto-discover}"
echo "logs: ${LOG_FILE}"

# --- lock to avoid overlap (flock if available) ---
LOCK_FILE="/tmp/model-inventory-cron.lock"
if command -v flock >/dev/null 2>&1; then
  exec 9>"${LOCK_FILE}"
  if ! flock -n 9; then
    echo "SKIP: another model-inventory-cron is running (lock ${LOCK_FILE})" >&2
    exit 0
  fi
else
  # fallback: mkdir lock
  if ! mkdir "${LOCK_FILE}.d" 2>/dev/null; then
    echo "SKIP: lock exists ${LOCK_FILE}.d" >&2
    exit 0
  fi
  trap 'rmdir "${LOCK_FILE}.d" 2>/dev/null || true' EXIT
fi

# --- run model-inventory.py ---
INV_ARGS=()
if [[ -n "${CONFIG}" ]]; then
  # use Windows-style path if python is Windows native
  PY_CFG="$(to_py_path "${CONFIG}")"
  INV_ARGS+=(--config "${PY_CFG}")
fi
if [[ -n "${OUTPUT_DIR}" ]]; then
  PY_OUT="$(to_py_path "${OUTPUT_DIR}")"
  INV_ARGS+=(--output-dir "${PY_OUT}")
fi
if [[ -n "${VERBOSE}" ]]; then INV_ARGS+=("${VERBOSE}"); fi
if [[ -n "${DRY_RUN}" ]]; then INV_ARGS+=("${DRY_RUN}"); fi

PY_SCRIPT="$(to_py_path "${REPO_ROOT}/playbooks/9router/scripts/model-inventory.py")"
echo "--- running model-inventory.py ${INV_ARGS[*]:-} ---"
set +e
"${PYTHON}" "${PY_SCRIPT}" "${INV_ARGS[@]}"
INV_RC=$?
set -e
if [[ ${INV_RC} -ne 0 ]]; then
  echo "ERR: model-inventory.py exited ${INV_RC}" >&2
  exit ${INV_RC}
fi
echo "--- model-inventory.py done ---"

# --- optional: 9router-sync.py if config exists and not --no-sync ---
if [[ -z "${NO_SYNC}" ]]; then
  SYNC_CFGS=()
  # discovered via the same glob the sync script uses: executions/*9router*/**/9router-sync*.yaml
  while IFS= read -r -d '' f; do
    SYNC_CFGS+=("$f")
  done < <(find "${REPO_ROOT}/executions" -type f -name "9router-sync*.yaml" -print0 2>/dev/null || true)
  # also check variant dir explicitly
  if [[ -f "${VARIANT_DIR}/9router-sync.config.yaml" ]]; then
    # ensure deduped
    FOUND=0
    for p in "${SYNC_CFGS[@]:-}"; do [[ "$p" == "${VARIANT_DIR}/9router-sync.config.yaml" ]] && FOUND=1; done
    if [[ ${FOUND} -eq 0 ]]; then SYNC_CFGS+=("${VARIANT_DIR}/9router-sync.config.yaml"); fi
  fi
  if [[ ${#SYNC_CFGS[@]} -gt 0 ]]; then
    echo "--- running 9router-sync.py (${#SYNC_CFGS[@]} config(s)) ---"
    for sc in "${SYNC_CFGS[@]}"; do
      echo "  config: ${sc}"
    done
    PY_SYNC="$(to_py_path "${REPO_ROOT}/playbooks/9router/scripts/9router-sync.py")"
    set +e
    "${PYTHON}" "${PY_SYNC}" ${VERBOSE:-} ${DRY_RUN:-}
    SYNC_RC=$?
    set -e
    if [[ ${SYNC_RC} -ne 0 ]]; then
      echo "WARN: 9router-sync.py exited ${SYNC_RC} (inventory updated, sync needs attention)" >&2
      # do not fail the cron — inventory succeeded; surface warning
    else
      echo "--- 9router-sync.py done ---"
    fi
  else
    echo "--- 9router-sync: no executions/*9router*/**/9router-sync*.yaml found (skipping, pass --no-sync to silence) ---"
  fi
else
  echo "--- 9router-sync skipped (--no-sync) ---"
fi

echo "=== done ${TS} log: ${LOG_FILE} ==="
