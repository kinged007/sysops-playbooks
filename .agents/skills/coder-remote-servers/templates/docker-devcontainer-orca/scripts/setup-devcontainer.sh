#!/bin/bash
set -e

REPO_URL="${repo_url}"
NEW_BRANCH="${new_branch}"
REPO_FOLDER="${repo_folder}"
WORKSPACE_FOLDER="$HOME"

# Ensure gh is available (like npm/python/uv/go/rust) before any git/gh operations
if ! command -v gh >/dev/null 2>&1; then
  if [ -x "$HOME/.local/bin/gh" ]; then
    export PATH="$HOME/.local/bin:$PATH"
  elif [ -f "$(dirname "$0")/install-gh.sh" ]; then
    bash "$(dirname "$0")/install-gh.sh" 2>/dev/null || true
    export PATH="$HOME/.local/bin:$PATH"
  fi
  # Fallback inline if helper not found (handles gVisor/no-sudo) — avoid dollar-brace so Terraform templatefile does not interpolate
  if ! command -v gh >/dev/null 2>&1; then
    mkdir -p "$HOME/.local/bin" 2>/dev/null || true
    GH_VERSION=$(curl -fsSL https://api.github.com/repos/cli/cli/releases/latest 2>/dev/null | grep '"tag_name":' | sed -E 's/.*"v([^"]+)".*/\1/' 2>/dev/null || echo "2.78.0")
    ARCH=$(uname -m); case "$ARCH" in x86_64) ARCH="amd64" ;; aarch64|arm64) ARCH="arm64" ;; *) ARCH="amd64" ;; esac
    curl -fsSL "https://github.com/cli/cli/releases/download/v"$GH_VERSION"/gh_"$GH_VERSION"_linux_"$ARCH".tar.gz" -o /tmp/gh.tar.gz 2>/dev/null && tar -xzf /tmp/gh.tar.gz -C /tmp 2>/dev/null && mv /tmp/gh_"$GH_VERSION"_linux_"$ARCH"/bin/gh "$HOME/.local/bin/gh" 2>/dev/null && chmod +x "$HOME/.local/bin/gh" 2>/dev/null && rm -rf /tmp/gh.tar.gz /tmp/gh_"$GH_VERSION"_linux_"$ARCH" 2>/dev/null || true
    export PATH="$HOME/.local/bin:$PATH"
  fi
fi

# Ensure uv is available (like npm/python/gh/go/rust) before any operations
if ! command -v uv >/dev/null 2>&1; then
  if [ -x "$HOME/.local/bin/uv" ]; then
    export PATH="$HOME/.local/bin:$PATH"
  elif [ -f "$(dirname "$0")/install-uv.sh" ]; then
    bash "$(dirname "$0")/install-uv.sh" 2>/dev/null || true
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  fi
  if ! command -v uv >/dev/null 2>&1; then
    mkdir -p "$HOME/.local/bin" 2>/dev/null || true
    curl -LsSf https://astral.sh/uv/install.sh 2>/dev/null | sh 2>/dev/null || true
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  fi
fi
# Ensure Go is available
if ! command -v go >/dev/null 2>&1; then
  if [ -x "$HOME/.local/go/bin/go" ]; then
    export PATH="$HOME/.local/go/bin:$PATH"
  elif [ -f "$(dirname "$0")/install-go.sh" ]; then
    bash "$(dirname "$0")/install-go.sh" 2>/dev/null || true
    export PATH="$HOME/.local/go/bin:$HOME/go/bin:$PATH"
  fi
  if ! command -v go >/dev/null 2>&1; then
    mkdir -p "$HOME/.local/go" 2>/dev/null || true
    GO_VERSION=$(curl -fsSL https://go.dev/VERSION?m=text 2>/dev/null | head -n1 | sed 's/go//' 2>/dev/null || echo "1.24.3")
    ARCH=$(uname -m); case "$ARCH" in x86_64) ARCH="amd64" ;; aarch64|arm64) ARCH="arm64" ;; *) ARCH="amd64" ;; esac
    curl -fsSL "https://go.dev/dl/go"$GO_VERSION".linux_"$ARCH".tar.gz" -o /tmp/go.tar.gz 2>/dev/null && tar -xzf /tmp/go.tar.gz -C /tmp 2>/dev/null && rm -rf "$HOME/.local/go" 2>/dev/null && mv /tmp/go "$HOME/.local/go" 2>/dev/null && rm -rf /tmp/go.tar.gz 2>/dev/null || true
    export PATH="$HOME/.local/go/bin:$PATH"
  fi
fi
# Ensure Rust is available
if ! command -v rustc >/dev/null 2>&1 && ! command -v cargo >/dev/null 2>&1; then
  if [ -x "$HOME/.cargo/bin/rustc" ]; then
    export PATH="$HOME/.cargo/bin:$PATH"
  elif [ -f "$(dirname "$0")/install-rust.sh" ]; then
    bash "$(dirname "$0")/install-rust.sh" 2>/dev/null || true
    export PATH="$HOME/.cargo/bin:$PATH"
  fi
  if ! command -v rustc >/dev/null 2>&1; then
    mkdir -p "$HOME/.cargo/bin" 2>/dev/null || true
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs 2>/dev/null | sh -s -- -y --no-modify-path --default-toolchain stable --profile minimal 2>/dev/null || true
    export PATH="$HOME/.cargo/bin:$PATH"
  fi
fi
export PATH="$HOME/.local/bin:$HOME/.local/go/bin:$HOME/go/bin:$HOME/.cargo/bin:$PATH"

if [ -n "$REPO_URL" ]; then
    if [ -n "$REPO_FOLDER" ]; then
        WORKSPACE_FOLDER="$HOME/$REPO_FOLDER"
    else
        WORKSPACE_FOLDER="$HOME"
    fi
    echo "Waiting for repository to be cloned into '$REPO_FOLDER'..."
    TIMEOUT=60
    while [ ! -d "$WORKSPACE_FOLDER" ] && [ $TIMEOUT -gt 0 ]; do
        sleep 2
        TIMEOUT=$((TIMEOUT - 2))
    done
    if [ -d "$WORKSPACE_FOLDER" ]; then
        # If a new branch name was provided, checkout or create it
        if [ -n "$NEW_BRANCH" ]; then
            cd "$WORKSPACE_FOLDER"
            echo "Setting up branch '$NEW_BRANCH'..."
            git checkout "$NEW_BRANCH" 2>/dev/null || git checkout -b "$NEW_BRANCH"
            echo "Switched to branch '$NEW_BRANCH'."
        fi

        # Authenticate with ghcr.io using Coder's existing GitHub token (if available)
        if command -v coder > /dev/null 2>&1; then
            GH_TOKEN=$(coder external-auth access-token github 2>/dev/null || echo "")
            if [ -n "$GH_TOKEN" ]; then
                echo "$GH_TOKEN" | docker login ghcr.io -u coder --password-stdin 2>/dev/null || echo "Warning: ghcr.io login failed (non-critical)"
            fi
        fi

        # Wait for the devcontainer CLI to be installed (installed in parallel)
        if [ -f "$WORKSPACE_FOLDER/.devcontainer/devcontainer.json" ] || [ -f "$WORKSPACE_FOLDER/.devcontainer.json" ]; then
            echo "Waiting for devcontainer CLI to be installed..."
            TIMEOUT=120
            while ! command -v devcontainer > /dev/null 2>&1 && [ $TIMEOUT -gt 0 ]; do
                sleep 2
                TIMEOUT=$((TIMEOUT - 2))
            done

            if ! command -v devcontainer > /dev/null 2>&1; then
                echo "ERROR: devcontainer CLI not found after waiting. Check the devcontainers-cli module install."
                exit 1
            fi
        fi

        if [ -f "$WORKSPACE_FOLDER/.devcontainer/devcontainer.json" ]; then
            echo "Devcontainer configuration found at .devcontainer/devcontainer.json. Starting devcontainer..."
            devcontainer up --workspace-folder "$WORKSPACE_FOLDER"
            echo "Devcontainer started successfully."
        elif [ -f "$WORKSPACE_FOLDER/.devcontainer.json" ]; then
            echo "Devcontainer configuration found at .devcontainer.json. Starting devcontainer..."
            devcontainer up --workspace-folder "$WORKSPACE_FOLDER"
            echo "Devcontainer started successfully."
        else
            echo "No devcontainer configuration found in '$REPO_FOLDER'."
        fi
    else
        echo "Repository folder '$REPO_FOLDER' not found after waiting."
    fi
else
    echo "No repository URL provided. Working directory: $HOME"
fi
