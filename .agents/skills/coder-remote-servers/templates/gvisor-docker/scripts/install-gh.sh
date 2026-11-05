#!/bin/bash
# install-gh.sh — ensure GitHub CLI (gh) is installed by default, like npm/python/uv/go/rust.
# Used by all Coder workspace templates (docker-devcontainer, gvisor-docker, remote-docker-workspace).
# Handles both privileged (runc) and gVisor (runsc) workspaces: tries apt with sudo first,
# falls back to binary download to $HOME/.local/bin which works without sudo.
set -e

if command -v gh >/dev/null 2>&1; then
  echo "gh already installed: $(gh --version 2>/dev/null | head -n1)"
  exit 0
fi

echo "Installing GitHub CLI (gh)..."

# Try apt if sudo is available (privileged/runc workspaces).
if command -v apt-get >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
  echo "Attempting apt install for gh..."
  sudo mkdir -p /usr/share/keyrings 2>/dev/null || true
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg 2>/dev/null && sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg 2>/dev/null || true
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null 2>/dev/null || true
  sudo apt-get update -qq 2>/dev/null && sudo apt-get install -y gh -qq 2>/dev/null && echo "gh installed via apt" || echo "apt install failed, trying binary..."
fi

# Fallback: binary download to $HOME/.local/bin (works without sudo, primary for runsc/gVisor).
if ! command -v gh >/dev/null 2>&1; then
  echo "Installing gh via binary download..."
  mkdir -p "$HOME/.local/bin"
  GH_VERSION=$(curl -fsSL https://api.github.com/repos/cli/cli/releases/latest 2>/dev/null | grep '"tag_name":' | sed -E 's/.*"v([^"]+)".*/\1/' 2>/dev/null || echo "2.78.0")
  ARCH=$(uname -m)
  case "$ARCH" in
    x86_64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) ARCH="amd64" ;;
  esac
  curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${ARCH}.tar.gz" -o /tmp/gh.tar.gz 2>/dev/null && \
    tar -xzf /tmp/gh.tar.gz -C /tmp 2>/dev/null && \
    mv "/tmp/gh_${GH_VERSION}_linux_${ARCH}/bin/gh" "$HOME/.local/bin/gh" 2>/dev/null && \
    chmod +x "$HOME/.local/bin/gh" 2>/dev/null && \
    rm -rf "/tmp/gh.tar.gz" "/tmp/gh_${GH_VERSION}_linux_${ARCH}" 2>/dev/null && \
    echo "gh installed to $HOME/.local/bin/gh" || echo "Warning: gh binary install failed"
  export PATH="$HOME/.local/bin:$PATH"
  grep -q 'HOME/.local/bin' "$HOME/.bashrc" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc" 2>/dev/null || true
fi

if command -v gh >/dev/null 2>&1; then
  echo "gh installed: $(gh --version 2>/dev/null | head -n1)"
else
  echo "Warning: gh installation failed - check network or install manually"
fi

# Ensure $HOME/.local/bin is on PATH for this session
export PATH="$HOME/.local/bin:$PATH"
