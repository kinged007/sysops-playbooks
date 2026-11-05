#!/bin/bash
set -e

# Start Docker daemon if not already running
if ! pgrep -x "dockerd" > /dev/null; then
    echo "Starting Docker daemon..."
    sudo dockerd > /dev/null 2>&1 &
    sleep 2
fi

# Wait for Docker to be ready
echo "Waiting for Docker to be ready..."
TIMEOUT=30
while ! docker info > /dev/null 2>&1; do
    sleep 1
    TIMEOUT=$((TIMEOUT - 1))
    if [ $TIMEOUT -le 0 ]; then
        echo "ERROR: Docker failed to start."
        exit 1
    fi
done

echo "Docker is ready."
