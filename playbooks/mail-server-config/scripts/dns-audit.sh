#!/usr/bin/env bash
# dns-audit.sh — mail DNS verification battery (read-only, runs locally).
# Usage: dns-audit.sh <DOMAIN> [DKIM_SELECTOR]
# Checks MX, SPF, DKIM, DMARC, PTR (of the MX-resolved IP) and DNSBLs.
# Prints PASS/FAIL/WARN lines; exit 0 = all pass, 1 = any fail.
# See branches/common.md §1 for interpretation.

set -uo pipefail

DOMAIN="${1:?usage: dns-audit.sh <DOMAIN> [DKIM_SELECTOR]}"
SELECTOR="${2:-dkim}"
PASS=0; FAIL=0; WARN=0

ok()   { echo "PASS  $1"; PASS=$((PASS+1)); }
bad()  { echo "FAIL  $1"; FAIL=$((FAIL+1)); }
warn() { echo "WARN  $1"; WARN=$((WARN+1)); }

q() { dig +short "$1" "$2" 2>/dev/null; }

echo "== DNS audit for $DOMAIN (selector $SELECTOR) =="

# --- MX ---
MX="$(q MX "$DOMAIN")"
if [ -z "$MX" ]; then
  bad "MX: no MX record for $DOMAIN"
else
  ok "MX: $(echo "$MX" | tr '\n' ' ')"
fi

# --- SPF ---
SPF="$(q TXT "$DOMAIN" | grep -i 'v=spf1' || true)"
SPF_COUNT="$(echo "$SPF" | grep -c 'v=spf1' || true)"
if [ "$SPF_COUNT" -eq 0 ]; then
  bad "SPF: no v=spf1 record found"
elif [ "$SPF_COUNT" -gt 1 ]; then
  bad "SPF: multiple v=spf1 records ($SPF_COUNT) -> permerror"
else
  if echo "$SPF" | grep -qiE '\-all|~all'; then
    ok "SPF: $(echo "$SPF" | cut -c1-90)"
  else
    warn "SPF: record exists but no -all/~all: $(echo "$SPF" | cut -c1-90)"
  fi
fi

# --- DKIM ---
DKIM="$(q TXT "$SELECTOR._domainkey.$DOMAIN")"
if [ -z "$DKIM" ]; then
  bad "DKIM: no TXT at $SELECTOR._domainkey.$DOMAIN"
elif echo "$DKIM" | grep -qi 'v=DKIM1'; then
  ok "DKIM: key published at $SELECTOR._domainkey.$DOMAIN"
  echo "      (match against the server's signing key — common.md §1.3)"
else
  warn "DKIM: TXT present but not v=DKIM1: $(echo "$DKIM" | cut -c1-60)"
fi

# --- DMARC ---
DMARC="$(q TXT "_dmarc.$DOMAIN")"
if [ -z "$DMARC" ]; then
  warn "DMARC: no record (not a delivery blocker, but spoofing goes unseen)"
elif echo "$DMARC" | grep -qiE 'p=(reject|quarantine|none)'; then
  ok "DMARC: $(echo "$DMARC" | cut -c1-90)"
else
  warn "DMARC: record without p= policy: $(echo "$DMARC" | cut -c1-60)"
fi

# --- PTR of the first MX-resolved IP ---
MX_IP="$(q A "$(q MX "$DOMAIN" | awk '{print $2}' | head -1)")"
if [ -n "$MX_IP" ]; then
  PTR="$(q PTR "$MX_IP")"
  if [ -n "$PTR" ]; then
    ok "PTR: $MX_IP -> $PTR"
    echo "      (should match the server hostname — common.md §1.5)"
  else
    bad "PTR: no reverse DNS for $MX_IP (major receivers tempfail 450)"
  fi
else
  warn "PTR: could not resolve MX host to an IP — skipped"
fi

# --- DNSBL ---
BL_ZONES="zen.spamhaus.org bl.spamcop.net dnsbl.sorbs.net psbl.surriel.com b.barracudacentral.org"
LISTED=0
for IP in $MX_IP; do
  REV="$(echo "$IP" | awk -F. '{print $4"."$3"."$2"."$1}')"
  for ZONE in $BL_ZONES; do
    HIT="$(q A "$REV.$ZONE" | grep -E '^127\.' || true)"
    if [ -n "$HIT" ]; then
      bad "DNSBL: $IP listed on $ZONE ($HIT) -> repair.md §4.4"
      LISTED=1
    else
      ok "DNSBL: $IP clean on $ZONE"
    fi
  done
done

echo "== Summary: $PASS pass, $FAIL fail, $WARN warn =="
[ "$FAIL" -eq 0 ] || exit 1
exit 0
