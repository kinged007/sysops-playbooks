#!/usr/bin/env bash
# mail-diag.sh — read-only baseline inventory of any mail server (remote).
# Usage: mail-diag.sh <MAIL_ALIAS>   (ssh config alias, key-based access)
# Detects the MTA, checks services/ports/queue/disk and tails recent log
# errors. NEVER modifies state — this is the repair branch's §1 entry point.

set -uo pipefail

ALIAS="${1:?usage: mail-diag.sh <MAIL_ALIAS>}"

section() { echo; echo "== $1 =="; }

section "Host"
ssh "$ALIAS" 'hostname -f; echo; uname -a'

section "Mail processes / containers"
ssh "$ALIAS" 'ps -e -o comm= | grep -Ei "postfix|exim|dovecot|master" | sort -u; echo ---; docker ps --format "{{.Names}}\t{{.Status}}" 2>/dev/null | grep -Ei "mail|postfix|dovecot|rspamd|clam" || echo "(no docker or no mail containers)"'

section "MTA version"
ssh "$ALIAS" 'postconf -d mail_version 2>/dev/null; exim --version 2>/dev/null | head -1; docker ps --format "{{.Image}}" 2>/dev/null | grep -Ei "mailu|mailcow" | sort -u'

section "Listening mail ports"
ssh "$ALIAS" 'ss -lnt 2>/dev/null | grep -E ":(25|465|587|143|993|110|995|4190)\b" || netstat -lnt 2>/dev/null | grep -E ":(25|465|587|143|993|110|995|4190)\b"'

section "Queue depth"
ssh "$ALIAS" 'echo -n "postfix: "; postqueue -p 2>/dev/null | tail -1 || echo "n/a"; echo -n "exim: "; exim -bpc 2>/dev/null || echo "n/a"; echo -n "mailu smtp: "; docker exec mailu-smtp postqueue -p 2>/dev/null | tail -1 || echo "n/a"'

section "Disk"
ssh "$ALIAS" 'df -h / /var/mail /var/vmail /var/lib/docker 2>/dev/null | sort -u'

section "Recent log errors (last 50 lines of interest)"
ssh "$ALIAS" 'LOG=""; for c in /var/log/mail.log /var/log/maillog /var/log/exim4/mainlog; do [ -f "$c" ] && LOG="$LOG $c"; done; if [ -n "$LOG" ]; then grep -hiE "error|rejected|deferred|bounce|warning" $LOG | tail -50; else echo "(no classic mail logs found — check docker logs via branches/common.md §4)"; fi; docker ps --format "{{.Names}}" 2>/dev/null | grep -Ei "mailu|mailcow" | while read -r n; do echo "--- $n ---"; docker logs "$n" --tail 20 2>&1 | grep -iE "error|rejected|deferred|warning" | tail -10; done'

echo
echo "== done (read-only). Full interpretation: branches/repair.md §1-3 =="
exit 0
