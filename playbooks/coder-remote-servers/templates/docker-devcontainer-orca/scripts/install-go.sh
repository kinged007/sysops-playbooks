#!/bin/bash
# install-go.sh — ensure Go is installed by default, like npm/python/uv/gh/rust.
# Used by Coder workspace template docker-devcontainer.
# Handles both privileged (runc): tarball to $HOME/.local/go (no sudo), fallback apt.
set -e

if command -v go >/dev/null 2>&1; then
  echo "go already installed: $(go version 2>/dev/null | head -n1)"
  exit 0
fi

echo "Installing Go..."
mkdir -p "$HOME/.local/bin" "$HOME/.local/go" 2>/dev/null || true
GO_VERSION=$(curl -fsSL https://go.dev/VERSION?m=text 2>/dev/null | head -n1 | sed 's/go//' 2>/dev/null || echo "1.24.3")
ARCH=$(uname -m)
case "$ARCH" in
  x86_64) ARCH="amd64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  *) ARCH="amd64" ;;
esac
echo "Downloading Go v${GO_VERSION} for linux_${ARCH}..."
if curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux_${ARCH}.tar.gz" -o /tmp/go.tar.gz 2>/dev/null && tar -xzf /tmp/go.tar.gz -C /tmp 2>/dev/null && rm -rf "$HOME/.local/go" 2>/dev/null && mv /tmp/go "$HOME/.local/go" 2>/dev/null && rm -rf /tmp/go.tar.gz 2>/dev/null; then
  echo "Go installed to $HOME/.local/go"
else
  echo "Go tarball install failed, trying apt..."
fi

if ! command -v go >/dev/null 2>&1 && [ -x "$HOME/.local/go/bin/go" ]; then
  export PATH="$HOME/.local/go/bin:$PATH"
  grep -q 'HOME/.local/go/bin' "$HOME/.bashrc" 2>/dev/null || echo 'export PATH="$HOME/.local/go/bin:$PATH"' >> "$HOME/.bashrc" 2>/dev/null || true
fi

if ! command -v go >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
  echo "Attempting apt install for Go..."
  sudo apt-get update -qq 2>/dev/null && sudo apt-get install -y golang-go -qq 2>/dev/null && echo "Go installed via apt" || echo "apt Go install failed"
fi

export PATH="$HOME/.local/go/bin:$HOME/go/bin:$PATH"

if command -v go >/dev/null 2>&1; then
  echo "Go installed: $(go version 2>/dev/null | head -n1)"
else
  echo "Warning: Go installation failed - check network or install manually"
fi
