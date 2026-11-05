#!/usr/bin/env bash
# ------------------------------------------------------------------
# setup-wildcard-cert.sh — issue a Let's Encrypt WILDCARD cert for
# *.coder.<domain> via DNS-01 (Cloudflare) and install it into
# Dokploy's Traefik file-provider cert dir, with auto-renewal.
#
# WHY DNS-01: Let's Encrypt cannot issue wildcard certs over HTTP-01
# (Dokploy's default resolver). DNS-01 proves ownership by creating a
# TXT record, which requires a Cloudflare API token with DNS edit.
#
# USAGE (run as root on the Coder/Dokploy host):
#   sudo WILDCARD_DOMAIN='*.coder.example.com' bash /tmp/setup-wildcard-cert.sh
#
# Required env:
#   WILDCARD_DOMAIN   e.g. *.coder.example.com
# Before running: place the Cloudflare API token in one of:
#   - /home/<user>/.cf-token          (default; the sudo user's home)
#   - $CF_TOKEN_FILE                  (override path)
#   - $CF_Token env var               (override both)
#
# The token must have "Zone > DNS > Edit" permission for the zone.
# ------------------------------------------------------------------
set -euo pipefail

DOMAIN="${WILDCARD_DOMAIN:?set WILDCARD_DOMAIN e.g. '*.coder.example.com'}"
CERT_NAME="${CERT_NAME:-wildcard-coder}"
CERT_DIR="/etc/dokploy/traefik/dynamic/certificates/${CERT_NAME}"
ACME_EMAIL="${ACME_EMAIL:-admin@${DOMAIN#\*.}}"
ACME_HOME="${ACME_HOME:-$HOME/.acme.sh}"
CF_TOKEN_FILE="${CF_TOKEN_FILE:-/home/${SUDO_USER:-root}/.cf-token}"

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: run as root (sudo bash $0)" >&2
  exit 1
fi

# --- Resolve the Cloudflare token ------------------------------------
if [ -n "${CF_Token:-}" ]; then
  CF_TOKEN="$CF_Token"
elif [ -f "$CF_TOKEN_FILE" ]; then
  CF_TOKEN="$(tr -d '[:space:]' < "$CF_TOKEN_FILE")"
else
  echo "ERROR: no Cloudflare token found (set CF_Token, or write it to $CF_TOKEN_FILE)" >&2
  exit 1
fi
if [ -z "$CF_TOKEN" ]; then
  echo "ERROR: Cloudflare token is empty" >&2
  exit 1
fi

# --- Install acme.sh (as root so the renewal cron runs as root) -------
if [ ! -x "$ACME_HOME/acme.sh" ]; then
  echo ">>> Installing acme.sh ..."
  curl -fsSL https://get.acme.sh | sh -s email="$ACME_EMAIL"
fi
ACME="$ACME_HOME/acme.sh"

# --- Issue the wildcard cert via Cloudflare DNS-01 --------------------
echo ">>> Issuing ${DOMAIN} via Cloudflare DNS-01 ..."
export CF_Token="$CF_TOKEN"
if ! "$ACME" --issue --dns dns_cf --server letsencrypt -d "$DOMAIN" \
  --keylength ec-256 --force; then
  echo "ERROR: issuance failed. Check the token has DNS:Edit for the zone." >&2
  exit 1
fi

# --- Install into Dokploy's Traefik cert dir --------------------------
mkdir -p "$CERT_DIR"

# certificate.yml is Dokploy's file-provider config. Traefik mounts the
# dynamic dir at the SAME path, so the file paths below are correct.
cat > "$CERT_DIR/certificate.yml" <<EOF
tls:
  certificates:
    - certFile: $CERT_DIR/chain.crt
      keyFile: $CERT_DIR/privkey.key
EOF

echo ">>> Installing cert files to $CERT_DIR ..."
"$ACME" --install-cert -d "$DOMAIN" \
  --fullchain-file "$CERT_DIR/chain.crt" \
  --key-file "$CERT_DIR/privkey.key" \
  --reloadcmd "chmod 644 '$CERT_DIR/chain.crt' && chmod 600 '$CERT_DIR/privkey.key' && echo wildcard-cert-reloaded"

chmod 644 "$CERT_DIR/certificate.yml" "$CERT_DIR/chain.crt" 2>/dev/null || true
chmod 600 "$CERT_DIR/privkey.key" 2>/dev/null || true

SAMPLE_HOST="test.${DOMAIN#\*.}"
echo
echo "======================================================================"
echo "DONE. Wildcard cert installed + auto-renewal cron configured."
echo "Verify TLS (run from any machine):"
echo "  echo | openssl s_client -connect ${SAMPLE_HOST}:443 -servername ${SAMPLE_HOST} 2>/dev/null | openssl x509 -noout -subject -ext subjectAltName"
echo "You should see subjectAltName containing DNS:${DOMAIN}"
echo "======================================================================"
