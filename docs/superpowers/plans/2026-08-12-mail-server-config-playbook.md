# Mail Server Config Playbook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the branched, multi-stack `playbooks/mail-server-config/` playbook per the approved design spec (`docs/superpowers/specs/2026-08-12-mail-server-config-playbook-design.md`), replacing the current stub in place.

**Architecture:** Master `playbook.md` = discovery questions + branch router. Procedures live in `branches/` (common/setup/repair/migrate/ops). Shared verification lives in `branches/common.md` only. Mailu is the worked example (setup/migrate/ops), diagnosis is stack-agnostic. All files committed, placeholders only, every production WRITE flagged with rollback, per AGENTS.md §6/§7.

**Tech Stack:** Markdown playbook + bash scripts (run from operator machine, ssh-alias driven, dig/ssh/rsync/swaks/imapsync/docker compose). Mailu on Docker (SQLite or PostgreSQL backend).

**Spec:** `docs/superpowers/specs/2026-08-12-mail-server-config-playbook-design.md`

**Repo conventions (read before starting):** `AGENTS.md` §6 (authoring rules), §7 (committing rules). Reference style: `playbooks/wordpress-migration/playbook.md` (phases, WRITE flags, rollback, decision tables, `- [ ]` checklists). Placeholder token style: `<UPPER_SNAKE>`. Never real IPs/hostnames/usernames/domains/keys.

---

### Task 1: Master `playbook.md` (discovery + router)

**Files:**
- Overwrite: `playbooks/mail-server-config/playbook.md` (currently a 41-line stub)

- [ ] **Step 1: Replace stub content**

Write `playbooks/mail-server-config/playbook.md` containing:
- Header: "Playbook: Mail Server Configuration — Master" + goal line (one playbook, 4 branches: setup / repair / migrate / ops; multi-stack; Mailu worked example)
- Phase 0 Discovery: the D1–D6 table exactly as in spec §3 (goal → branch; scale → backend; existing stack; DNS control; access level per access-ladder pattern; domains/quotas/backup target)
- "Read `notes/` BEFORE any run" callout (repo convention)
- Branch routing table: D1 answer → `branches/<branch>.md` + note that setup/repair/migrate also load `branches/common.md`
- Explicit rule: exactly one branch per run; ops may follow setup as a separate run; never mix branches; deviations → STOP + operator (AGENTS.md §1.4)
- Link to plan-template.md/runbook-template.md flow (execution lifecycle §3 of AGENTS.md)

- [ ] **Step 2: Verify**

Read back the file. Confirm: D1–D6 all present; routing table covers all 4 branches; no `<PLACEHOLDER>` left unfilled; no real hostnames/IPs; `git status` shows only this file modified.

- [ ] **Step 3: Commit**

```bash
git add playbooks/mail-server-config/playbook.md
git commit -m "docs: add mail-server-config master playbook (discovery + branch router)"
```

### Task 2: README.md rewrite

**Files:**
- Overwrite: `playbooks/mail-server-config/README.md` (currently the scaffold stub)

- [ ] **Step 1: Rewrite README**

Follow `_playbook-template/README.md` structure with mail content:
- Mandatory "Agent: read `notes/` BEFORE any run" line
- What it does: A–Z mail server lifecycle — setup (Mailu), diagnose/repair (any stack), migrate mailboxes, ops (backup/restore/update/security)
- When to use it (per-branch trigger list); what it does NOT cover (mailbox migration TO non-Mailu, HA clustering)
- Prerequisites: SSH key access to mail server(s), DNS control, VPS provider PTR access, Docker (for Mailu branches)
- Risk level: **high** — changes live email delivery; misconfig causes rejection/blacklisting
- Servers involved: mail server + DNS provider; real values only in execution inventory
- Files table: update to list `branches/` (all 5), `templates/` (4), `scripts/` (5), `notes/`

- [ ] **Step 2: Verify + commit**

Read back; confirm no placeholders left unfilled, no real values. Commit: `docs: rewrite mail-server-config README (branched playbook)`

### Task 3: plan-template.md + runbook-template.md updates

**Files:**
- Overwrite: `playbooks/mail-server-config/plan-template.md`
- Overwrite: `playbooks/mail-server-config/runbook-template.md`

- [ ] **Step 1: Update plan-template.md**

Keep the base template (`_playbook-template/plan-template.md` fields) and add:
- `Branch: <setup | repair | migrate | ops>` row
- `Scale: <small | medium-large>` row (setup branch only)
- `Existing stack: <postfix | exim | mailcow | mailu | poste.io | other | n/a>` row (repair/migrate)
- Steps section note: "Steps mirror the ACTIVE branch file (branches/<branch>.md) + referenced common.md sections"
- Keep permission-mode row (A/B per AGENTS.md §1.3) and approval checkboxes

- [ ] **Step 2: Update runbook-template.md**

Keep base template fields + add:
- `Branch file(s): <branches/<branch>.md, branches/common.md>` row
- Note: "This runbook snapshots the active branch with real values filled in; referenced common.md sections are reproduced inline in the step logs"
- Keep status values (`pending`/`in-progress`/`done`/`blocked`), deviations, close-out sections

- [ ] **Step 3: Verify + commit**

Read back both. Commit: `docs: add branch/scale/stack fields to mail-server-config plan & runbook templates`

### Task 4: `branches/common.md` — shared verification

**Files:**
- Create: `playbooks/mail-server-config/branches/common.md`

- [ ] **Step 1: Write common.md**

Sections (per spec §4), all read-only unless marked:
- Header: "Loaded by setup/repair/migrate — never a standalone run"
- §1 DNS audit: `scripts/dns-audit.sh <DOMAIN> [DKIM_SELECTOR]` usage; per-record pass criteria table: MX (present, points at server FQDN), SPF (exists, syntax valid, `-all` or `~all` with server IP included), DKIM (TXT at `<selector>._domainkey.<DOMAIN>`, matches server key — compare via `dig` output vs server-generated key), DMARC (policy `p=quarantine`→`reject`, rua present), PTR (reverse DNS matches hostname), DNSBL (not listed — list the queried zones). Propagation: multi-resolver check, TTL note
- §2 TLS audit: ports 25/465/587/143/993; `openssl s_client -starttls smtp` on 25/587, `-starttls imap` on 143; cert expiry via `openssl x509 -enddate`; reject weak protocols
- §3 SMTP test battery: send-to-external (`swaks --to <TEST_RECIPIENT>`), send-to-self, receive-from-external; header forensics list: `Authentication-Results`, `DKIM-Signature`, `Received` chain, `Return-Path`; mail-tester.com as optional external scoring step
- §4 Log map: per-stack log paths + search-by-message-id commands: postfix (`/var/log/mail.log`, `postfix -e`), exim4 (`/var/log/exim4/mainlog`), mailcow (`docker logs`), Mailu (`docker logs mailu-*`), journald fallback

- [ ] **Step 2: Verify + commit**

Read back; confirm all pass criteria concrete. Commit: `docs: add mail-server-config common branch (DNS/TLS/SMTP audits, log map)`

### Task 5: `branches/setup.md` — fresh install (Mailu)

**Files:**
- Create: `playbooks/mail-server-config/branches/setup.md`

- [ ] **Step 1: Write setup.md**

Phases per spec §5, each step `- [ ]` with **WRITE** flag + rollback where state changes:
- 0. Pre-flight (reads): hostname FQDN check, IPv4/IPv6, port reachability (25/465/587/143/993/80/443), Docker engine check, **PTR request placed with VPS provider BEFORE cutover** (explicit warning: missing PTR = tempfail from major receivers; PTR propagates slowly)
- 1. Deploy (**WRITE**): fill `templates/mailu-compose.yml` (or `-postgres.yml` per scale) + `templates/mailu.env` from plan.md values; storage provisioning rules (mailboxes × quota × 1.5 headroom; `df` check before start); `docker compose up -d`; admin account creation; secrets → run `secrets/`; rollback: `docker compose down` + remove volume if fresh
- 2. DNS phase (**WRITE** at provider, per record): MX → server FQDN, SPF, DKIM (generate via Mailu admin CLI — include exact command form), DMARC, autodiscover/autoconfig, optional MTA-STS; then common.md DNS audit; wait for propagation (TTL note)
- 3. Post-deploy verification: common.md §2 TLS audit + §3 SMTP battery + test mail to external address; header check
- 4. Account provisioning (**WRITE**): domains, users, aliases, quotas, catch-all decision, disabled-account policy; admin UI path + CLI path; rollback = documented delete path per entity
- 5. Hardening (**WRITE**): firewall rules (only mail/web ports public; ssh restricted), fail2ban review (bundled), admin 2FA, plaintext-auth-over-non-TLS disabled, rate limits; rollback each
- 6. Handover: credentials only in `secrets/`; baseline backup via ops.md backup procedure; handover notes to `notes.md`
- Reference common.md for all verification calls; reference `templates/dns-records.md` for exact record forms

- [ ] **Step 2: Verify + commit**

Read back; confirm every WRITE has rollback; every command uses `<PLACEHOLDER>` tokens. Commit: `docs: add mail-server-config setup branch (fresh Mailu install)`

### Task 6: `branches/repair.md` — diagnose & repair (any stack)

**Files:**
- Create: `playbooks/mail-server-config/branches/repair.md`

- [ ] **Step 1: Write repair.md**

Sections per spec §6:
- Header note: stack-agnostic; works on postfix/exim/mailcow/Mailu/poste.io
- 1. Baseline inventory (reads only): `scripts/mail-diag.sh <MAIL_ALIAS>`; manual fallback commands (MTA detect via `ps`/`ss`/`docker ps`; version; queue depth `postqueue -p`/`exim -bpc`; disk `df -h`; recent log errors)
- 2. Audit: common.md §1 DNS audit + §2 TLS audit
- 3. Triage: how to count deferred/bounced, grep rejection codes, auth failures, greylisting, relay denials (per-stack commands)
- 4. **Symptom → cause → fix catalog** (the heart; one entry per row, each with: symptom text, diagnostic command, cause, fix (**WRITE** + rollback), re-verify hook). Must include at minimum:
  - `550 PTR required` / tempfail → missing/wrong reverse DNS → fix at VPS provider → re-run DNS audit
  - SPF `permerror` → syntax / >10 lookups / too many mechanisms → rewrite SPF record
  - `DKIM fail` → selector/key mismatch (migration or env change) → regenerate + republish, or align selector
  - `554 blocked` → IP on DNSBL → identify list, check why (spam history/open relay), removal process, warm-up
  - `452/421` → greylisting / rate limit → identify which (peer vs local), throttle, whitelist carefully
  - `552` quota → mailbox/domain quota exceeded → increase or clean, distinguish from disk-full
  - `535` auth failed → passdb mismatch (Dovecot), wrong credentials → verify config, test with `doveadm`/`testsaslauthd` equivalent
  - `451 STARTTLS required` → peer requires TLS → enable/repair cert + TLS config
  - Slow delivery / queue buildup → RDNS/DNS timeout, connection reuse → `postconf`/equivalent tuning, resolver check
  - Mail to spam folder → SPF/DKIM/DMARC alignment failures, missing PTR, content/IP reputation → alignment fix, list hygiene, rua/rf monitoring
  - Webmail/admin UI broken → container/service state, proxy config, logs
  - Disk full → log rotation, maildir growth, cleanup; emergency: delete old logs, extend volume
- 5. Repair loop: fix → re-run audit → next; anything outside catalog → STOP + deviation + operator; final full common.md battery + live test mail both directions
- 6. Reference `notes/lessons.md` seeded entries

- [ ] **Step 2: Verify + commit**

Read back; every catalog row has diagnostic command + fix + rollback + re-verify. Commit: `docs: add mail-server-config repair branch (diagnose & fix, any stack)`

### Task 7: `branches/migrate.md` — mailbox migration into Mailu

**Files:**
- Create: `playbooks/mail-server-config/branches/migrate.md`

- [ ] **Step 1: Write migrate.md**

Phases per spec §7:
- 1. Pre-flight: source stack + access (per-user IMAP creds or admin; document in inventory), target Mailu deployed (setup.md §1–2 completed), DNS TTL lowered 24–48h before cutover (exact TTL-lowering step), delta budget agreed with operator
- 2. Provision targets: mirror domains/users/quotas on target (setup.md §4 pattern)
- 3. Copy mailboxes (**WRITE**): `scripts/migrate-mailboxes.sh` usage — dry-run → full → verify folder/message counts vs source → per-account checklist in runbook; include manual `imapsync` fallback command form; quota-on-target warning (target quota must fit source usage)
- 4. DNS cutover (**WRITE**): MX flip + SPF update (source stays live); final delta pass; common.md battery verification; test mail both directions
- 5. Post-cutover: parallel run 48–72h; operator decommissions source + removes old records; rollback = MX flip-back (valid until decommission)

- [ ] **Step 2: Verify + commit**

Read back; confirm cutover order (delta before flip), rollback defined. Commit: `docs: add mail-server-config migrate branch (mailboxes to Mailu)`

### Task 8: `branches/ops.md` — lifecycle & maintenance

**Files:**
- Create: `playbooks/mail-server-config/branches/ops.md`

- [ ] **Step 1: Write ops.md**

Sections per spec §8:
- Backup: `scripts/backup-mailu.sh <MAIL_ALIAS> <DEST>` (DB dump + maildir + compose/env, off-box, cron schedule suggestion, verify via test extraction); restore drill cadence
- Restore: `scripts/restore-mailu.sh <MAIL_ALIAS> <BACKUP_PATH>` step-by-step incl. maildir permissions + DB import
- Updates: Mailu release upgrade (backup first, compose pull, config diff, DB migration check, rollback = previous compose + restored backup)
- Certificates: LE/Traefik renewal monitoring, expiry alert command
- Monitoring: health checks, container status, queue depth, disk, fail2ban bans, brute-force log scan (exact commands)
- Account lifecycle: create/disable/delete users, aliases, quotas, forwarding, catch-all (exact UI/CLI paths)
- Storage: disk trend, quota reports, maildir growth, archive/cleanup policy, log rotation
- Security review checklist: firewall re-audit, open ports, fail2ban status, admin access review, credential rotation, patching
- Every WRITE flagged with rollback

- [ ] **Step 2: Verify + commit**

Read back. Commit: `docs: add mail-server-config ops branch (backup/restore/update/monitor)`

### Task 9: `templates/` — compose, env, DNS reference

**Files:**
- Create: `playbooks/mail-server-config/templates/mailu-compose.yml`
- Create: `playbooks/mail-server-config/templates/mailu-compose-postgres.yml`
- Create: `playbooks/mail-server-config/templates/mailu.env`
- Create: `playbooks/mail-server-config/templates/dns-records.md`

- [ ] **Step 1: Fetch current Mailu compose/env reference**

Use context7 (`/mailu/mailu` or docs.mailu.io) to confirm current expected `mailu.env` variables (SECRET_KEY, DOMAIN, HOSTNAMES, POSTMASTER, DB_FLAVOR=sqlite|postgresql, DB_USER/DB_PASSWORD/DB_HOST, ANTIVIRUS, WEBMAIL, etc.) and compose service list. Adjust variable names to the fetched current version. Note the version pin in compose image tags (`mailu/...:<VERSION>` placeholder).

- [ ] **Step 2: Write mailu-compose.yml (SQLite variant)**

Single-instance compose: `mailu-front` (nginx, ports 25/465/587/143/993/80/443), `mailu-resolver` (unbound), `mailu-redis`, `mailu-smtp` (postfix), `mailu-imap` (dovecot), `mailu-antispam` (rspamd, enabled if env ANTIVIRUS/WEBMAIL), `mailu-antivirus` (clamav), `mailu-webmail` (roundcube), `mailu-admin` (admin UI), `mailu-webdav` (optional, commented) — match current Mailu compose; volumes: `mailu` data volume (maildir), `overrides`; env_file: `mailu.env`; placeholders for hostname/domain only where needed; version pinned via placeholder `<MAILU_VERSION>`

- [ ] **Step 3: Write mailu-compose-postgres.yml**

Same as SQLite variant + `postgres` service (image `postgres:<VERSION>` placeholder, volume `postgres-data`, healthcheck), env `DB_FLAVOR=postgresql`, `DB_HOST=postgres` references in mailu.env

- [ ] **Step 4: Write mailu.env**

Full placeholder env: SECRET_KEY (ref to run secrets/), DOMAIN, HOSTNAMES, POSTMASTER, DB_FLAVOR, DB_* (postgres variant), ANTIVIRUS=true, WEBMAIL=roundcube, WEBDAV, ADMIN (admin user placeholder), TLS settings (LETSENCRYPT=true, TLS_FLAVOR=letsencrypt), SITENAME, WILDCARD (false), RELAYHOST (empty), RSPAMD_PASSWORD ref, etc. — every secret as `<SECRET_REF>` token, never a real value. Comments explain each var (no secrets).

- [ ] **Step 5: Write dns-records.md**

Canonical table (per spec §9): MX (`10 mail.<DOMAIN>.`), SPF (`v=spf1 mx a:<SERVER_IP> -all`), DKIM (`<selector>._domainkey.<DOMAIN>` TXT `v=DKIM1; k=rsa; p=<KEY>`), DMARC (`_dmarc.<DOMAIN>` `v=DMARC1; p=quarantine; rua=mailto:<POSTMASTER>`), PTR (`<IP>` → `mail.<DOMAIN>`), autodiscover/autoconfig (SRV/CNAME), MTA-STS (`_mta-sts.<DOMAIN>` TXT + `mta-sts.<DOMAIN>` policy file note). One row per record: type, name, value placeholder, TTL suggestion, propagation check

- [ ] **Step 6: Verify + commit**

Read back each; confirm env vars match fetched Mailu docs; no real values. Commit: `docs: add mail-server-config templates (mailu compose x2, env, dns records)`

### Task 10: `scripts/` part 1 — dns-audit.sh, mail-diag.sh

**Files:**
- Create: `playbooks/mail-server-config/scripts/dns-audit.sh`
- Create: `playbooks/mail-server-config/scripts/mail-diag.sh`

- [ ] **Step 1: Write dns-audit.sh**

Bash, run locally, args `dns-audit.sh <DOMAIN> [DKIM_SELECTOR]`:
- Uses `dig` (+short). Checks: MX exists; SPF TXT exists + `v=spf1` present + includes `-all`/`~all`; DKIM TXT at `${selector}._domainkey.${domain}` exists; DMARC at `_dmarc.${domain}` with `p=` policy; PTR: reverse lookup of the MX-resolved IP must match (print both); DNSBL: query server IP against a fixed list of zones (`zen.spamhaus.org`, `bl.spamcop.net`, `dnsbl.sorbs.net`, `psbl.surriel.com`, `b.barracudacentral.org`) via dig `A`; output per-check PASS/FAIL/WARN lines + summary. Exit 0 if all pass, 1 otherwise
- No secrets, no ssh (pure local dig). Shebang `#!/usr/bin/env bash`, `set -uo pipefail`

- [ ] **Step 2: Write mail-diag.sh**

Bash, run locally, arg `mail-diag.sh <MAIL_ALIAS>` (ssh config alias):
- `ssh <MAIL_ALIAS>` read-only commands: MTA detect (`ps -e | grep -Ei 'postfix|exim|dovecot'`, `docker ps` if docker present), listening mail ports (`ss -lnt` grep 25/465/587/143/993), queue (`postqueue -p | tail` if postfix, `exim -bpc` if exim), disk (`df -h /var/mail /var/vmail /var/lib/docker` if exist), last errors (tail mail log per detected MTA, grep -i 'error|deferred|rejected|bounce' last 50 lines)
- Read-only only — no state change; print labeled sections. Exit 0

- [ ] **Step 3: Verify + commit**

If bash available: `bash -n` both files. Read back. Commit: `feat: add mail-server-config diagnostic scripts (dns-audit, mail-diag)`

### Task 11: `scripts/` part 2 — backup, restore, migrate

**Files:**
- Create: `playbooks/mail-server-config/scripts/backup-mailu.sh`
- Create: `playbooks/mail-server-config/scripts/restore-mailu.sh`
- Create: `playbooks/mail-server-config/scripts/migrate-mailboxes.sh`

- [ ] **Step 1: Write backup-mailu.sh**

Bash, `backup-mailu.sh <MAIL_ALIAS> <DEST>`:
- On server (**WRITE**, additive only): `docker compose` dir discovery, stop-safe DB dump (sqlite: `sqlite3` copy via `docker exec`; postgres: `pg_dump` via `docker exec`), tar maildir volume + compose files + mailu.env into a timestamped archive under a server temp dir; pull via `scp` to `<DEST>` (off-box); verify: `tar tzf` count + `gzip -t`; cleanup server temp file after successful pull
- Print archive path + size + verify result. Helpers: `set -euo pipefail`, echo step markers

- [ ] **Step 2: Write restore-mailu.sh**

Bash, `restore-mailu.sh <MAIL_ALIAS> <BACKUP_PATH>`:
- Pre-flight: confirm server is down (`docker compose down`) or restore-in-place mode flag; restore DB from dump, extract maildir into volume, restore compose/env; fix ownership (`chown -R 5000:5000` Mailu default or documented); `docker compose up -d`; post-restore verification hooks (containers healthy, test mail via common.md SMTP battery reference)
- WARN loudly before starting: this OVERWRITES live mail data (WRITE). Placeholder-driven, no secrets

- [ ] **Step 3: Write migrate-mailboxes.sh**

Bash, `migrate-mailboxes.sh --source <SRC_IMAP_HOST> --target <TGT_IMAP_HOST> --account <USER> [--dry-run] [--delta]`:
- Wraps `imapsync` (verify installed; error if missing): dry-run adds `--dry`; delta adds `--syncinternaldates` + excludes nothing (document); per-account log file to `logs/` of execution folder; after run, print counts (source/target) via imapsync report summary
- Password handling: `--password` via env var read from execution `secrets/` file (never on command line — use `imapsync --passwordfile` if available, else `--passfile`); document secret sourcing

- [ ] **Step 4: Verify + commit**

If bash available: `bash -n` all three. Read back. Commit: `feat: add mail-server-config ops scripts (backup, restore, migrate)`

### Task 12: `notes/lessons.md`

**Files:**
- Create: `playbooks/mail-server-config/notes/lessons.md`

- [ ] **Step 1: Write lessons.md**

Per spec §11: header explaining the notes convention (read before any run; append after runs with date+run tag; promotion channel per AGENTS.md §1.6). Seed entries (each flagged `(seed — verify on first run)`):
1. PTR must exist before first MX query — major receivers tempfail otherwise
2. SPF `permerror` is usually record syntax or >10 DNS lookups
3. DKIM selector/key drift after compose env changes or migration — always re-audit
4. DNSBL removal lags; use the list's own removal form, expect 24–48h
5. `451 STARTTLS required` tempfails when peer enforces TLS and server cert is broken/absent
6. Quota exceeded (552) vs disk-full are different failure modes with different fixes
7. Always back up before a Mailu version upgrade — DB migration can be one-way
8. IMAP migration: quota on target must exceed source usage or sync fails mid-pass

- [ ] **Step 2: Verify + commit**

Read back. Commit: `docs: seed mail-server-config notes with field pitfalls (unverified)`

### Task 13: Final repo-wide verification

- [ ] **Step 1: Leak/consistency scan (AGENTS.md §7)**

```powershell
git status
git ls-files --cached --others --exclude-standard | ForEach-Object { if (Test-Path $_) {
  $c = Get-Content $_ -Raw
  if ($c -match 'tskey-|BEGIN (CERTIFICATE|PRIVATE|RSA)') { Write-Output "LEAK: $_" }
}}
```
Expected: no `executions/` in status; zero LEAK lines; only playbook files modified/added.

- [ ] **Step 2: Placeholder scan**

Grep all new playbook files for leftover TODO/TBD; confirm no real IPs (regex `\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b` outside placeholder docs — dns-records.md may contain none), no `tskey-`, no `.pem`/`.key` refs outside placeholders.

- [ ] **Step 3: Structure check**

`ls` confirms: README.md, playbook.md, plan-template.md, runbook-template.md, branches/ (5 files), templates/ (4 files), scripts/ (5 files), notes/ (1 file). Scripts executable bit not required (Windows repo) but shebangs present.

- [ ] **Step 4: Final commit if anything staged**

```bash
git status
# if clean → done. Otherwise commit remaining intended files only.
```

**Self-review notes:** Tasks map 1:1 to spec §2 (layout), §4–§8 (branches), §9 (templates/scripts), §10 (template changes), §11 (notes). No TDD applicable — verification is read-back + syntax check + leak scan (doc repo). All command forms use `<PLACEHOLDER>` tokens per AGENTS.md §6.
