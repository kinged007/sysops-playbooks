#!/bin/bash
set -e

REPO_URL="${repo_url}"
NEW_BRANCH="${new_branch}"
REPO_FOLDER="${repo_folder}"
WORKSPACE_FOLDER="$HOME"

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
