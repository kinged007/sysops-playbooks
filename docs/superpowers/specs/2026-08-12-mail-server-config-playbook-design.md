# Design: Mail Server Config Playbook (branched, multi-stack)

Date: 2026-08-12
Status: approved (operator) — 2026-08-12

## 1. Purpose

A reusable, runnable playbook for mail server work on remote servers, covering
the full lifecycle A–Z:

- **Fresh install** of a new mail server (worked example: Mailu on Docker)
- **Diagnose & repair** of EXISTING mail servers (stack-agnostic: postfix,
  exim, mailcow, Mailu, poste.io, etc.)
- **Migration** of mailboxes from an existing server into a new Mailu
  deployment
- **Ongoing ops**: backup, restore, updates, monitoring, account lifecycle,
  storage management, security review

Decisions agreed with operator:

1. **Multi-stack**: the playbook is stack-agnostic for diagnosis/repair and
   DNS/verification work; Mailu (Docker) is the worked example for setup and
   migration targets.
2. **Modular branches**: `playbook.md` is a small master/routing document.
   Procedures live in `branches/*.md`. The agent loads only the branch(es) a
   run needs.
3. **Shared verification** lives in `branches/common.md`, referenced by
   setup/repair/migrate — one place to maintain DNS/TLS/SMTP checks.
4. **Scale decided per run** via discovery: small (SQLite backend, single
   compose) vs medium/large (PostgreSQL backend, multi-instance capable).
5. **Migration is in scope** (user chose "also migrate mailboxes"): IMAP-sync
   based copy into new Mailu with delta pass + DNS cutover.
6. Branches are mutually exclusive per run; a maintenance/ops run on an
   existing deployed server is its own run of the ops branch.

## 2. Repository layout (committed, placeholders only)

```
playbooks/mail-server-config/
├── README.md              ← overview, when-to-use, risk, files map
├── playbook.md            ← MASTER: discovery questions + branch router (small)
├── plan-template.md       ← + branch/scale/stack fields
├── runbook-template.md    ← + branch file(s) field
├── branches/
│   ├── common.md          ← shared: DNS audit, TLS checks, SMTP tests, log map
│   ├── setup.md           ← fresh install (Mailu worked example)
│   ├── repair.md          ← diagnose & repair existing servers (any stack)
│   ├── migrate.md         ← mailbox migration into new Mailu
│   └── ops.md             ← backup/restore/update/monitor/accounts/storage/security
├── templates/
│   ├── mailu-compose.yml          ← SQLite variant (small)
│   ├── mailu-compose-postgres.yml ← PostgreSQL variant (medium/large)
│   ├── mailu.env                  ← placeholder env for Mailu
│   └── dns-records.md             ← canonical DNS reference table
├── scripts/
│   ├── dns-audit.sh               ← local dig battery: MX/SPF/DKIM/DMARC/PTR/DNSBL
│   ├── mail-diag.sh               ← ssh read-only inventory of any mail server
│   ├── backup-mailu.sh            ← DB + maildir + config, off-box
│   ├── restore-mailu.sh           ← restore from backup
│   └── migrate-mailboxes.sh       ← imapsync wrapper (dry-run/full/delta)
└── notes/
    └── lessons.md                 ← seeded known pitfalls (flagged unverified) + lessons from runs
```

The existing scaffold (`playbooks/mail-server-config/` with stub README,
playbook.md, plan/runbook templates) is rebuilt in place. All other playbooks
(`_playbook-template`, `coder-remote-servers`, `wordpress-migration`) are
untouched.

## 3. Master `playbook.md` — discovery and routing

Phase 0 discovery questions (answer with operator, record in execution
`inventory.md`):

| # | Question | Determines |
|---|----------|------------|
| D1 | Goal: fresh install / diagnose-repair existing / migrate mailboxes / ops run? | Branch selection |
| D2 | Scale: small (<100 mailboxes, SQLite) or medium/large (PostgreSQL)? | Setup branch backend |
| D3 | Existing stack (if any): postfix / exim / mailcow / Mailu / poste.io / other? | Repair branch commands, migrate source |
| D4 | DNS control point (registrar / Cloudflare / other); can PTR be set at VPS provider? | DNS phase feasibility |
| D5 | Access level: SSH alias + root/sudo (access-ladder pattern, see wordpress-migration playbook §1.4); permission mode A/B set at plan approval | All branches |
| D6 | Domains, mailbox count, quotas, disk budget, backup target | Storage provisioning, quota policy |

Routing rule: exactly one branch per run (ops may follow setup as a separate
run). Load `branches/<branch>.md`; setup/repair/migrate additionally load
`branches/common.md`. Never mix branches in one run; deviations require a
stop + operator approval (AGENTS.md §1.4).

## 4. `branches/common.md` — shared verification (any stack)

Read-only procedures used by setup/repair/migrate:

1. **DNS audit** — `scripts/dns-audit.sh <DOMAIN> [DKIM_SELECTOR]`:
   - MX records present, point at server FQDN/IP
   - SPF: record exists, syntax valid (no permerror), includes server IP/host
   - DKIM: TXT at `<selector>._domainkey.<DOMAIN>` present, matches server key
   - DMARC: policy record present (p=quarantine/reject recommended), rua/rf
   - PTR: reverse DNS for server IP resolves to server hostname
   - DNSBL: server IP not listed on major blocklists
   - Propagation: verify with multiple resolvers, respect TTL
2. **TLS audit** — port reachability 25/465/587/143/993, cert validity/expiry
   (SNI), STARTTLS support on 25/587/143, no weak protocol/cipher downgrade.
3. **SMTP test battery** — send + receive path tests (`swaks` preferred,
   `openssl s_client` fallback): send to external test address, send to own
   domain, receive from external. Header forensics: `Authentication-Results`,
   `DKIM-Signature`, `Received`, `Return-Path`.
4. **Log map** — where each stack logs and how to search by message ID:
   postfix (`/var/log/mail.log`, `postfix -e`), exim (`/var/log/exim4/mainlog`),
   mailcow (docker logs), Mailu (docker logs `mailu-*`), plus journald.

## 5. `branches/setup.md` — fresh install (Mailu worked example)

Phases (each WRITE flagged + rollback):

- **0. Pre-flight (reads):** FQDN hostname, IPv4/IPv6 present, ports
  25/465/587/143/993/80/443 reachable, Docker engine installed, PTR request
  placed with VPS provider BEFORE cutover (PTR propagation lags; missing PTR
  = tempfail from major receivers).
- **1. Deploy (WRITE):** write `mailu-compose.yml` (SQLite) or
  `mailu-compose-postgres.yml` (PostgreSQL) per D2 + `mailu.env` with
  placeholders filled from plan.md; storage provisioning: maildir volume
  sizing (mailboxes × quota × 1.5 headroom), filesystem check; `docker
  compose up -d`; admin account + secrets into run `secrets/`.
- **2. DNS phase (WRITE at provider):** MX → server FQDN; SPF include;
  **DKIM generated via Mailu CLI** and published; DMARC (p=quarantine then
  reject once stable); autodiscover/autoconfig records; optional MTA-STS.
  Verify with common.md DNS audit; wait for propagation before cutover.
- **3. Post-deploy verification:** common.md battery (TLS audit, SMTP tests,
  test mail to external address, header check via mail-tester).
- **4. Account provisioning (WRITE):** domains, users, aliases, quotas,
  catch-all decision, disabled-account policy — via admin UI or Mailu CLI;
  rollback = documented delete path.
- **5. Hardening (WRITE):** firewall rules (only mail/web ports public),
  fail2ban (bundled with Mailu) review, admin 2FA, plaintext-auth over
  non-TLS disabled, rate limits.
- **6. Handover:** credentials only in run `secrets/`, baseline backup taken
  (ops.md), handover notes in `notes.md`.

## 6. `branches/repair.md` — diagnose & repair existing servers (any stack)

1. **Baseline inventory (reads only):** `scripts/mail-diag.sh <MAIL_ALIAS>` —
   MTA + version, service status, listening ports, queue depth, disk usage,
   recent log errors.
2. **Audit:** common.md DNS audit + blacklist scan; TLS audit.
3. **Triage:** queue/deferred counts, rejection codes in logs, auth failures,
   greylisting, relay denials.
4. **Symptom → cause → fix catalog** (the core content; each entry:
   diagnostic command → cause → fix (WRITE, with rollback) → re-verify hook):
   - 550 PTR required → missing/wrong reverse DNS → fix at VPS provider
   - SPF permerror → record syntax/too-many-lookups → rewrite SPF
   - DKIM fail → selector/key mismatch (esp. after migration or env change)
   - 554 blocked → IP on DNSBL → identify list, removal process
   - 452/421 busy → rate limit/greylisting → throttle or remove (carefully)
   - 552 quota → mailbox/domain quota exceeded → increase or clean
   - 535 auth failed → credentials/config mismatch (Dovecot passdb)
   - 451 STARTTLS required → peer requires TLS → enable/cert fix
   - Sending slow / queue buildup → DNS/conn timeout, RDNS, connection reuse
   - Mail landing in spam → SPF/DKIM/DMARC alignment, rDNS, content, list
     hygiene
   - Admin UI / webmail broken → container/service state, proxy config
   - Disk full → log rotation, maildir growth, cleanup
5. **Repair loop:** fix → re-run audit → next. Anything outside the catalog →
   STOP, record deviation, ask operator. Re-run full common.md battery after
   all fixes; confirm with live test mail.

## 7. `branches/migrate.md` — mailbox migration into new Mailu

1. **Pre-flight:** source stack + access (per-user IMAP creds or admin),
   target Mailu deployed (setup.md §1–2), DNS TTL lowered 24–48h before
   cutover, delta budget agreed with operator.
2. **Provision targets:** domains/users/quotas on target mirroring source
   (setup.md §4 pattern).
3. **Copy mailboxes (WRITE):** `scripts/migrate-mailboxes.sh` (imapsync
   wrapper) — dry-run per account → full pass → verify folder/message counts
   vs source → record per-account checklist.
4. **DNS cutover (WRITE):** MX flip + SPF update; source stays live; final
   delta pass; verify with common.md battery; test mail both directions.
5. **Post-cutover:** run parallel 48–72h; operator decommissions source and
   removes old records. Rollback: MX flip-back at any point before
   decommission.

## 8. `branches/ops.md` — lifecycle & maintenance

- **Backup:** `scripts/backup-mailu.sh <MAIL_ALIAS> <DEST>` — DB dump +
  maildir + compose/env, off-box, scheduled (cron), verified by test
  extraction; restore drill quarterly (or per policy).
- **Restore:** `scripts/restore-mailu.sh` — step-by-step including maildir
  permissions and DB import; documented in runbook style.
- **Updates:** Mailu release upgrade procedure (compose pull, DB migration
  check, backup before upgrade, rollback = previous compose + restored
  backup).
- **Certificates:** Traefik/LE renewal monitoring, expiry alerts.
- **Monitoring:** health endpoints, container status, queue depth, disk,
  fail2ban ban count, log scan for brute force.
- **Account lifecycle:** create/disable/delete users, aliases, quotas,
  forwarding, catch-all changes.
- **Storage:** disk usage trend, quota reports, maildir growth, archive/
  cleanup policy, log rotation.
- **Security review checklist:** firewall re-audit, open ports, fail2ban
  status, admin access review, credential rotation, patching.

## 9. Templates & scripts inventory

`templates/`:
- `mailu-compose.yml` — SQLite backend, single instance, placeholders
  (domain, volumes, ports, secret key ref)
- `mailu-compose-postgres.yml` — PostgreSQL service, placeholders
- `mailu.env` — full placeholder env matching current Mailu expected vars
- `dns-records.md` — canonical table: MX, SPF, DKIM, DMARC, PTR, autodiscover,
  autoconfig, MTA-STS, with placeholder values and record-type notes

`scripts/` (bash; run from operator machine; ssh-alias driven; placeholders
only; no secrets):
- `dns-audit.sh <DOMAIN> [DKIM_SELECTOR]` — local dig battery incl. DNSBL
  checks; PASS/FAIL table output
- `mail-diag.sh <MAIL_ALIAS>` — ssh read-only inventory (MTA detect, ports,
  queue, disk, log tail)
- `backup-mailu.sh <MAIL_ALIAS> <DEST>` — DB dump + maildir tar + config,
  off-box copy, verify step
- `restore-mailu.sh <MAIL_ALIAS> <BACKUP_PATH>` — restore with pre-flight
  checks
- `migrate-mailboxes.sh` — imapsync wrapper: dry-run / full / delta modes,
  per-account logging

## 10. Plan/runbook template changes (mail-server-config only)

- `plan-template.md`: add Branch (setup/repair/migrate/ops), Scale
  (small/medium-large), Existing stack fields; steps mirror the active
  branch.
- `runbook-template.md`: add "Branch file(s)" field (the runbook snapshots
  the active branch + referenced common.md sections); keep status/label/
  deviation conventions from AGENTS.md.

## 11. Notes seeding

`notes/lessons.md` seeded with well-known pitfalls, each flagged
`(seed — verify on first run)`: PTR before first MX; SPF permerror causes;
DKIM selector drift on env/compose changes; DNSBL removal lag; STARTTLS
peer-required tempfails; quota vs disk-full confusion; backup-before-upgrade.
Real lessons from executions appended per AGENTS.md §1.6/§7.

## 12. Out of scope

- HA/multi-node Mailu clustering beyond compose multi-instance option
- Non-Mailu migration targets (migrate branch targets Mailu only; repair
  branch remains stack-agnostic)
- Greylisting policy tuning beyond defaults
- Full mailbox archival tooling (noted in ops.md storage section)
