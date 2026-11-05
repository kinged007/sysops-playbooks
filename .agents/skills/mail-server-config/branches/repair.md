# Branch: Repair — Diagnose & Fix an Existing Mail Server

> **Loaded by the master playbook (D1 = diagnose/repair). Also load
> `branches/common.md` — every audit below lives there.** **Stack-agnostic:**
> works on postfix, exim, mailcow, Mailu, poste.io, or any other MTA. This
> branch is read-only until a fix in §4 is approved — production servers are
> READ-ONLY by default (AGENTS.md §1.1).

**Goal:** find why a mail server misbehaves (delivery failures, spam
classification, auth failures, blacklisting, slow queues, broken UI), fix it
with minimal blast radius, and prove the fix with the common.md battery.

---

## 1. Baseline inventory (reads only)

- [ ] `scripts/mail-diag.sh <MAIL_ALIAS>` — automated inventory (MTA detect,
      version, ports, queue, disk, recent log errors). Manual fallbacks:
      ```bash
      ps -e | grep -Ei 'postfix|exim|dovecot|mailcow'    # what's running
      docker ps                                          # containerized stacks
      postconf -d mail_version; exim --version           # version (per MTA)
      ss -lnt | grep -E ':(25|465|587|143|993)\b'        # listening ports
      postqueue -p | tail -5; exim -bpc                  # queue depth
      df -h /var/mail /var/vmail /var/lib/docker 2>/dev/null   # disk
      ```
- [ ] Record stack (D3), version, queue depth, disk free, and any log errors
      in the runbook before touching anything.

## 2. Audit (common.md — all read-only)

- [ ] **DNS audit** (common.md §1) — MX, SPF, DKIM, DMARC, PTR, DNSBL.
- [ ] **TLS audit** (common.md §2) — ports, STARTTLS, cert expiry, downgrade.
- [ ] Note every FAIL line; these are the candidates for §4.

## 3. Triage

- [ ] Grep the log (common.md §4 log map) for the last day:
      ```bash
      grep -iE 'rejected|deferred|bounce|spam|auth|error' <LOG_PATH> | tail -200
      ```
- [ ] Count failure classes: rejections (`reject:`), tempfails (`deferred`,
      `450`, `451`), auth failures (`SASL authentication failure`), relay
      denials (`relay access denied`).
- [ ] If a specific message misbehaves, extract its **message ID** from the
      complaint/header and trace it: `grep <MESSAGE_ID> <LOG_PATH>`.
- [ ] Order the failures by volume — fix the biggest class first (§5).

## 4. Symptom → cause → fix catalog

> For each row: run the **diagnostic** (read), confirm the **cause**, then
> the **fix** is a **WRITE** needing approval + rollback, then the
> **re-verify** hook. If the symptom matches nothing here → **STOP, record
> the deviation, ask the operator** (AGENTS.md §1.4).

### 4.1 `550 PTR required` / tempfail `450 4.7.1` from major receivers

- **Diagnostic:** `dig +short -x <SERVER_IP>` → NXDOMAIN or wrong name.
- **Cause:** no reverse DNS, or PTR doesn't match the server hostname.
- **Fix (WRITE):** set PTR at the **VPS provider panel** (not the DNS
  registrar) → `mail.<DOMAIN>`. Rollback: remove/change the PTR at the panel.
- **Re-verify:** `dig +short -x <SERVER_IP>` → `mail.<DOMAIN>`;
  resend test mail (common.md §3.1).

### 4.2 SPF `permerror` in Authentication-Results

- **Diagnostic:** `dig +short TXT <DOMAIN> | grep -i spf` → syntax issue.
- **Cause:** malformed record, duplicate `v=spf1` records, or >10 DNS
  lookups (lookup limit).
- **Fix (WRITE):** rewrite to one valid record, e.g.
  `v=spf1 mx ip4:<SERVER_IP> -all`; collapse `include:` chains to stay under
  10 lookups. Rollback: restore the previous TXT.
- **Re-verify:** common.md §1.2 passes; resend test mail, check
  `spf=pass`.

### 4.3 `dkim=fail` (or no DKIM signature at all)

- **Diagnostic:** compare published key vs signing key:
  `dig +short TXT <SELECTOR>._domainkey.<DOMAIN>` vs the key the MTA signs
  with (Mailu: admin UI; opendkim: `/etc/opendkim/keys`; see common.md §1.3).
- **Cause:** selector/key drift — after a migration, compose env change, or
  key regeneration that wasn't republished.
- **Fix (WRITE):** republish the correct key (or re-point the selector in
  the MTA config to the published key). Rollback: republish the old key.
- **Re-verify:** common.md §1.3 + resend test mail, check `dkim=pass`.

### 4.4 `554 ... blocked` / IP listed on a DNSBL

- **Diagnostic:** `dig +short <SERVER_IP_REV>.<ZONE>. A` for the zones in
  common.md §1.6 → `127.0.0.x` answer.
- **Cause:** IP reputation — spam history, open relay, compromised account,
  shared IP with spammers.
- **Fix (WRITE):** (1) fix the root cause first (compromised account →
  §4.7; open relay → close it); (2) request removal via the list's removal
  form (spamhaus.org/removal, spamcop.net, etc. — allow 24–48h); (3) if the
  IP is shared/garbage, request a new IP from the provider and re-run
  setup.md PTR/DNS steps. Rollback: n/a (removal requests are additive).
- **Re-verify:** common.md §1.6 clean; resend test mail.

### 4.5 `452`/`421` — greylisting or rate limiting

- **Diagnostic:** log line shows `452 4.2.2 ... greylist` or `421 ... too
  many connections`; check which side (peer vs local) — grep the peer IP.
- **Cause:** local greylist (rspamd) on a bursty sender; or local rate limit
  hit; or the PEER greylisting/limiting YOU (reputation).
- **Fix (WRITE):** if local: tune greylist/rate limits (admin UI; rspamd
  settings) — whitelist trusted peers only, never broad-disable spam
  protection. If peer-side: treat as reputation (§4.4) and slow your send
  rate. Rollback: restore prior rspamd settings.
- **Re-verify:** resend after the hold window; watch the log for the same
  code.

### 4.6 `552` quota exceeded (distinct from disk-full!)

- **Diagnostic:** log `552 ... mailbox full` or `quota exceeded`; then
  check actual quota: `doveadm quota get -A` (dovecot) / admin UI / maildir
  size `du -sh <MAILBOX_DIR>`.
- **Cause:** per-user or per-domain quota reached.
- **Fix (WRITE):** raise the quota (admin UI / `doveadm quota set`) or have
  the user clean mail. **Never** confuse with §4.12 (disk full) — different
  fix. Rollback: lower the quota back.
- **Re-verify:** `doveadm quota get <USER>` shows headroom; resend.

### 4.7 `535 authentication failed`

- **Diagnostic:** log `SASL authentication failure` + client IP; test the
  account with `swaks --auth` (common.md §3.1) and check the user actually
  exists (dovecot: `doveadm user <USER>`).
- **Cause:** wrong password (brute force in progress — check ban status),
  or passdb misconfig (Dovecot/Postfix auth mismatch), or account disabled.
- **Fix (WRITE):** if brute force: reset the account password (run
  `secrets/`), enable/confirm fail2ban jail (`postfix-sasl`). If passdb
  misconfig: align Dovecot/Postfix auth settings per distro docs. Rollback:
  restore previous auth config / re-enable account.
- **Re-verify:** successful authenticated send via swaks; ban list reviewed.

### 4.8 `451 STARTTLS required` tempfails from peers enforcing TLS

- **Diagnostic:** log shows peer name with `STARTTLS required`; check local
  TLS: common.md §2.2 handshake.
- **Cause:** server cert expired/mismatched or STARTTLS disabled — peers
  that enforce TLS refuse plaintext delivery.
- **Fix (WRITE):** fix the cert (renew via provider/Mailu Traefik; common.md
  §2.3 expiry check first) and/or re-enable STARTTLS on 25 in the MTA
  config. Rollback: revert config change (old cert restored).
- **Re-verify:** common.md §2.2 handshake OK + resend test mail.

### 4.9 Slow delivery / queue buildup

- **Diagnostic:** `postqueue -p` shows many `deferred`; log shows
  `connect to ...: Connection timed out`.
- **Cause:** outbound DNS failures (resolver down / /etc/resolv.conf),
  provider outbound filtering (port 25 blocked — test:
  `nc -zv <PEER> 25`), or high load.
- **Fix (WRITE):** fix resolver (`systemd-resolved`/`/etc/resolv.conf`),
  raise postfix connection limits
  (`postconf -e smtp_connection_reuse_time_limit=300s` style tuning per
  distro docs), or contact provider about port 25. Rollback: revert
  postconf values. 
- **Re-verify:** queue drains (`postqueue -p` → empty); logs show delivery.

### 4.10 Mail delivered but lands in the spam folder

- **Diagnostic:** header forensics (common.md §3.4) — read
  `Authentication-Results` on a message the user fished out of spam.
- **Cause:** one or more of: SPF/DKIM/DMARC fail or misaligned (§4.2/§4.3),
  missing PTR (§4.1), sender reputation (§4.4), or content signals (user's
  own list hygiene).
- **Fix (WRITE):** fix whichever authentication check fails; monitor DMARC
  aggregate reports (`rua` mailbox) for a week. Rollback: n/a.
- **Re-verify:** new test mail to the same recipient lands in inbox with
  all three checks `pass`.

### 4.11 Webmail / admin UI broken

- **Diagnostic:** `docker compose ps` (Mailu) / service status; container
  logs; `curl -sI https://mail.<DOMAIN>` status code.
- **Cause:** container down/restart-loop (disk full §4.12, OOM), proxy/TLS
  config broken (§4.8), DB backend issue (Mailu: sqlite/postgres).
- **Fix (WRITE):** restart the failing service
  (`docker compose restart <svc>`), check DB container health, free disk
  (§4.12). Rollback: n/a for restarts (no config change).
- **Re-verify:** UI loads, login works, logs clean.

### 4.12 Disk full

- **Diagnostic:** `df -h` → 100%; `du -sh` top offenders: maildirs, docker
  overlay, logs.
- **Cause:** maildir growth past provisioned size, unbounded logs, orphaned
  backups/containers.
- **Fix (WRITE):** emergency: rotate/truncate logs, remove orphaned
  containers/old backups; permanent: extend the volume, tighten log rotation
  (ops.md storage section), enforce quotas (§4.6). **Never delete
  maildirs.** Rollback: n/a (frees space only).
- **Re-verify:** `df -h` headroom; mail flows again; set a disk alert
  (ops.md monitoring).

## 5. Repair loop

- [ ] Fix the highest-volume failure class first → re-run the affected
      common.md audit → confirm PASS → next class.
- [ ] After all fixes: full **common.md battery** (DNS + TLS + SMTP both
      directions, §3.4 header check) — the run is only closed when every
      check passes.
- [ ] Anything matching no catalog row → STOP, record deviation in
      runbook.md, ask the operator. Never improvise on production.
- [ ] Record findings in `notes.md`; propose lesson promotion to
      `notes/lessons.md` (operator approves, per AGENTS.md §1.6).
