#!/usr/bin/env bash
# Install or upgrade AWS CLI v2 — Linux (x86_64/aarch64) and macOS.
# Idempotent: uses --update if already installed.
# Usage: bash playbooks/aws-management/scripts/install-aws-cli.sh
set -euo pipefail

arch="$(uname -m)"
os="$(uname -s)"

if [[ "$os" == "Darwin" ]]; then
  if command -v brew >/dev/null 2>&1; then
    if brew list awscli >/dev/null 2>&1; then
      echo "awscli already via brew — upgrading..."
      brew upgrade awscli || true
    else
      brew install awscli
    fi
  else
    echo "Homebrew not found. Install from https://brew.sh then re-run, or use the macOS PKG from https://awscli.amazonaws.com/AWSCLIV2.pkg" >&2
    exit 1
  fi
  aws --version
  exit 0
fi

# Linux
case "$arch" in
  x86_64|amd64) url="https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" ;;
  aarch64|arm64) url="https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" ;;
  *) echo "Unsupported arch: $arch" >&2; exit 1 ;;
esac

if ! command -v unzip >/dev/null 2>&1; then
  echo "unzip is required (sudo apt-get install -y unzip / sudo dnf install -y unzip)" >&2
  exit 1
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

echo "Downloading AWS CLI v2 ($arch)..."
curl -fsSL "$url" -o "$tmpdir/awscliv2.zip"
unzip -qo "$tmpdir/awscliv2.zip" -d "$tmpdir"

if [[ -x /usr/local/bin/aws ]]; then
  echo "Existing CLI found — upgrading..."
  sudo "$tmpdir/aws/install" --update
else
  sudo "$tmpdir/aws/install"
fi

aws --version
echo "Done. Verify: aws sts get-caller-identity  (after configuring a profile)"
