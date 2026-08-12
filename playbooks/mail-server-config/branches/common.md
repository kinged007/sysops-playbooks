# Branch: Common — Shared Verification Battery

> **Loaded by the setup, repair, and migrate branches. Never a standalone
> run.** These procedures are **read-only** unless a step says otherwise.
> Run them at the checkpoints the calling branch names — never improvise new
> checks mid-run.

Contents: §1 DNS audit · §2 TLS audit · §3 SMTP test battery · §4 Log map.

---

## 1. DNS audit

Automated: `scripts/dns-audit.sh <DOMAIN> [DKIM_SELECTOR]` (run locally).
Manual fallbacks below. Run from **multiple resolvers** (`dig @8.8.8.8`,
`dig @1.1.1.1`) and respect the record's TTL before declaring failure.

### 1.1 MX

```bash
dig +short MX <DOMAIN>
```

**Pass:** one or more MX records, priority 10 (or lower), pointing at
`mail.<DOMAIN>` (or the server FQDN). No MX at all = nobody can send mail to
you.

### 1.2 SPF

```bash
dig +short TXT <DOMAIN> | grep -i spf
```

**Pass:** exactly **one** `v=spf1` record; syntax valid; includes the server's
IP (`ip4:<SERVER_IP>`) or `mx`; ends with `-all` (recommended) or `~all`.
**Fail/`permerror`:** record syntax, >10 DNS lookups, duplicate `v=spf1`
records, or a mechanism that isn't `ip4`/`ip6`/`include`/`mx`/`a`/`exists`.

### 1.3 DKIM

```bash
dig +short TXT <DKIM_SELECTOR>._domainkey.<DOMAIN>
```

**Pass:** TXT starts `v=DKIM1; k=rsa; p=<LONG_BASE64>`. **Verify the key
matches the server's actual key** (Mailu: admin UI → domain → keys, or the
key file in the container; postfix/opendkim: `opendkim.conf` Selector +
`/etc/opendkim/keys/`). A published key that isn't the one the server signs
with = silent DKIM failures on every message.

### 1.4 DMARC

```bash
dig +short TXT _dmarc.<DOMAIN>
```

**Pass:** `v=DMARC1; p=quarantine` (minimum) or `p=reject` (recommended after
stable), `rua=mailto:<POSTMASTER>` present for aggregate reports. Missing
DMARC is not a delivery blocker but leaves you blind to spoofing.

### 1.5 PTR (reverse DNS)

```bash
dig +short -x <SERVER_IP>
```

**Pass:** resolves to the server hostname (e.g. `mail.<DOMAIN>`). **Fail:**
`NXDOMAIN` or resolving to a generic provider hostname. PTR is set at the
**VPS provider's panel** — not at the DNS registrar. Major receivers
(gmail/outlook) tempfail (`450`) mail from IPs without matching PTR.

### 1.6 DNSBL (blacklists)

```bash
# for each zone; an answer of 127.0.0.x = LISTED
dig +short <SERVER_IP_REVERSED>.<ZONE>. A
```

Zones to check (adjust per run): `zen.spamhaus.org`, `bl.spamcop.net`,
`dnsbl.sorbs.net`, `psbl.surriel.com`, `b.barracudacentral.org`.

**Pass:** NXDOMAIN on all. **Listed:** identify the zone, then use that
zone's removal form (see repair.md §4 catalog for the process).

---

## 2. TLS audit

### 2.1 Port reachability (from the operator machine)

```bash
for p in 25 465 587 143 993; do nc -zv <SERVER_IP> $p 2>&1; done   # or: nmap -Pn -p 25,465,587,143,993 <SERVER_IP>
```

**Pass:** 25, 587, 143 open and speaking SMTP/IMAP; 465/993 open (SMTPS/IMAPS).

### 2.2 STARTTLS on submission/IMAP

```bash
openssl s_client -starttls smtp -connect <SERVER_IP>:587 -servername mail.<DOMAIN> 2>/dev/null < /dev/null
openssl s_client -starttls imap -connect <SERVER_IP>:143 -servername mail.<DOMAIN> 2>/dev/null < /dev/null
```

**Pass:** handshake completes, certificate chain valid (`verify return code:
0`), cert CN/SAN matches `mail.<DOMAIN>`.

### 2.3 Certificate expiry

```bash
echo | openssl s_client -connect <SERVER_IP>:465 -servername mail.<DOMAIN> 2>/dev/null | openssl x509 -noout -enddate
```

**Pass:** expiry > 14 days ahead. Record the date in the runbook — renewal
monitoring is an ops.md step.

### 2.4 No weak protocol downgrade

```bash
openssl s_client -connect <SERVER_IP>:465 -tls1 2>&1 < /dev/null | grep -E 'alert|error'
```

**Pass:** TLSv1.0 handshake fails (alerts) — old protocols disabled.

---

## 3. SMTP test battery

Send AND receive must both pass. Use `swaks` if installed
(apt/brew: `swaks`); fall back to `openssl s_client` manual SMTP dialogue.

### 3.1 Send to external test address

```bash
swaks --to <TEST_RECIPIENT> --server mail.<DOMAIN> --from <TEST_SENDER> --header "Subject: test" --body "test from <DATE>"
```

**Pass:** `250 2.0.0 Ok: queued` (or similar) from the server, and the test
recipient actually receives it. **Fail:** 550/554 = rejection; 450/451 =
tempfail (see repair.md catalog).

### 3.2 Send to self (loop-back within the domain)

```bash
swaks --to <LOCAL_USER>@<DOMAIN> --server mail.<DOMAIN> --from <TEST_SENDER> --body "loop test"
```

**Pass:** message lands in the local mailbox (verify via webmail or
`docker exec` maildir listing).

### 3.3 Receive from external

Send a mail from an external account (gmail/outlook/proton) to
`<LOCAL_USER>@<DOMAIN>`.

**Pass:** arrives within minutes. Check spam folder too — landing in spam =
authentication/alignment issue (see §3.4).

### 3.4 Header forensics (when a mail passes but misbehaves)

Grab the raw headers of a test message and check:

- `Authentication-Results` → `spf=pass`, `dkim=pass`, `dmarc=pass`
- `DKIM-Signature` → `d=<DOMAIN>` and `s=<SELECTOR>` match what DNS publishes
- `Return-Path` and `From` → same domain (alignment)
- `Received` chain → each hop adds a Received line; first external hop sees
  the server's IP with correct rDNS

**Any `fail`/`permerror` in Authentication-Results → the DNS audit (§1) is
the next step; the publish-vs-sign mismatch is the usual root cause.**

Optional external scoring: send a test mail to `check-auth@verifier.port25.com`
or use mail-tester.com (browser step, operator machine) for a full report.

---

## 4. Log map (per stack)

Where the server logs, and how to search by message ID. Read-only.

| Stack | Log location | Search by message ID |
|---|---|---|
| postfix (Debian/Ubuntu) | `/var/log/mail.log`, `/var/log/mail.err` | `grep <MESSAGE_ID> /var/log/mail.log` |
| postfix (RHEL/CentOS) | `/var/log/maillog` | `grep <MESSAGE_ID> /var/log/maillog` |
| exim4 | `/var/log/exim4/mainlog`, `rejectlog` | `grep <MESSAGE_ID> /var/log/exim4/mainlog` |
| mailcow (docker) | `docker logs <container>` (postfix-mailcow, dovecot-mailcow) | `docker logs postfix-mailcow 2>&1 \| grep <MESSAGE_ID>` |
| Mailu (docker) | `docker logs mailu-smtp`, `mailu-imap`, `mailu-admin`, `mailu-antispam` | `docker logs mailu-smtp 2>&1 \| grep <MESSAGE_ID>` |
| systemd journald | `journalctl -u postfix -u dovecot --since "<TIME>"` | `journalctl --grep=<MESSAGE_ID>` |

**Quick triage pattern (any stack):**

```bash
# last 200 log lines with levels of interest, newest first
grep -iE 'error|rejected|deferred|bounce|warning' <LOG_PATH> | tail -200
# queue depth
postqueue -p | tail -3        # postfix
exim -bpc                     # exim
```
