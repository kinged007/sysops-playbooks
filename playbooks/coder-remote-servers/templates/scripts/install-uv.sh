#!/bin/bash
# install-uv.sh — ensure uv (astral.sh/uv) is installed by default, like npm/python/gh/go/rust.
# Used by all Coder workspace templates (docker-devcontainer, gvisor-docker, remote-docker-workspace).
# Handles both privileged (runc) and gVisor (runsc) workspaces: pipx first, then standalone installer to $HOME/.local/bin.
set -e

if command -v uv >/dev/null 2>&1; then
  echo "uv already installed: $(uv --version 2>/dev/null | head -n1)"
  exit 0
fi

echo "Installing uv..."

if command -v pipx >/dev/null 2>&1; then
  echo "Attempting pipx install for uv..."
  pipx install uv 2>/dev/null && echo "uv installed via pipx" || echo "pipx install failed, trying standalone..."
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv via standalone installer..."
  mkdir -p "$HOME/.local/bin" 2>/dev/null || true
  curl -LsSf https://astral.sh/uv/install.sh 2>/dev/null | sh 2>/dev/null && echo "uv installed via astral.sh" || echo "Warning: uv standalone install failed"
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  grep -q 'HOME/.local/bin' "$HOME/.bashrc" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc" 2>/dev/null || true
fi

if command -v uv >/dev/null 2>&1; then
  echo "uv installed: $(uv --version 2>/dev/null | head -n1)"
else
  echo "Warning: uv installation failed - check network or install manually"
fi

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
