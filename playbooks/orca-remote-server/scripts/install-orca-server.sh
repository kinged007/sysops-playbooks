#!/usr/bin/env bash
# Helper: headless-Linux preflight for an Orca server.
# READ-ONLY by default. Pass --install to perform writes (Tailscale install).
# Usage: bash install-orca-server.sh [--install]
# Never pass secrets on the command line — pre-auth keys come from the
# execution's secrets/ file at join time (see playbook Phase 1).
set -euo pipefail

WRITE=0
if [ "${1:-}" = "--install" ]; then WRITE=1; fi

fail() { echo "FAIL: $*" >&2; exit 1; }
info() { echo "INFO: $*"; }

info "OS: $(uname -a)"
command -v git >/dev/null || fail "git missing — install per OS package manager"

if command -v orca >/dev/null; then
  info "orca CLI: $(command -v orca)"
  orca status --json || info "orca present but no runtime running (expected pre-serve)"
elif command -v orca-ide >/dev/null; then
  info "orca-ide CLI (Linux name): $(command -v orca-ide)"
else
  info "Orca CLI not found — install from https://github.com/stablyai/orca/releases"
fi

if ! command -v tailscale >/dev/null; then
  if [ "$WRITE" -eq 1 ]; then
    curl -fsSL https://tailscale.com/install.sh | sh   # WRITE: installs Tailscale
  else
    info "tailscale missing — re-run with --install to install (WRITE)"
  fi
else
  info "tailscale: $(command -v tailscale)"
  tailscale status || info "tailscale installed but not logged in (expected pre-join)"
fi

# Compiler toolchain for the Orca relay's native modules (else terminals fail, files still work).
if ! command -v make >/dev/null || ! command -v python3 >/dev/null; then
  echo "INFO: build tools missing — Debian/Ubuntu: sudo apt-get install -y build-essential python3"
  echo "INFO: Fedora/RHEL: sudo dnf install -y make gcc gcc-c++ python3"
else
  info "build tools present"
fi

info "done. Next: tailscale up (Phase 1) → orca install verify (Phase 2) → tooling (Phase 3)."
