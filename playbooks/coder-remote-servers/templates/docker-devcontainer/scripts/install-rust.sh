#!/bin/bash
# install-rust.sh — ensure Rust (rustup/cargo/rustc) is installed by default, like npm/python/uv/gh/go.
# Used by Coder workspace template docker-devcontainer.
# Works on both privileged (runc): installs to $HOME/.cargo without sudo.
set -e

if command -v rustc >/dev/null 2>&1 && command -v cargo >/dev/null 2>&1; then
  echo "Rust already installed: $(rustc --version 2>/dev/null | head -n1) $(cargo --version 2>/dev/null | head -n1)"
  exit 0
fi

echo "Installing Rust (rustup)..."
mkdir -p "$HOME/.cargo/bin" 2>/dev/null || true
if curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs 2>/dev/null | sh -s -- -y --no-modify-path --default-toolchain stable --profile minimal 2>/dev/null; then
  echo "Rust installed via rustup"
else
  echo "Warning: rustup install failed"
fi

export PATH="$HOME/.cargo/bin:$PATH"
grep -q 'HOME/.cargo/bin' "$HOME/.bashrc" 2>/dev/null || echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> "$HOME/.bashrc" 2>/dev/null || true

if command -v rustc >/dev/null 2>&1; then
  echo "Rust installed: $(rustc --version 2>/dev/null | head -n1) $(cargo --version 2>/dev/null | head -n1)"
else
  echo "Warning: Rust installation failed - check network or install manually"
fi
