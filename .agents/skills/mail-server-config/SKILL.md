---
name: mail-server-config
description: Set up, repair, migrate, and operate mail servers on remote hosts. Covers a fresh Mailu-on-Docker install, diagnosis and repair of an existing server of any stack (postfix, exim, mailcow, Mailu, poste.io), IMAP mailbox migration into a new Mailu, and ongoing ops (backup, restore, update, monitor, accounts, storage), including DNS records (MX/SPF/DKIM/DMARC/PTR), rspamd, ClamAV, and TLS. Not for non-Mailu migration targets, HA/clustered Mailu, or greylisting tuning beyond defaults.
---

# Mail Server Configuration

> Read `references/lessons.md` BEFORE any run. It holds lessons learned from
> earlier runs that can change how you plan. Never skip this.

Risk level: high. Changes live email delivery; a misconfiguration can cause
rejection by receivers or delivery blacklisting. Production servers are
read-only by default (AGENTS.md section 1.1); every write needs plan approval
and the run's permission mode.

One skill for the full mail server lifecycle on remote servers: fresh setup,
diagnosis and repair of existing servers, mailbox migration, and ongoing ops.
The repair branch works on any MTA (postfix, exim, mailcow, Mailu, poste.io,
and others). The setup and migrate branches use Mailu on Docker as the worked
example. It covers DNS records (MX/SPF/DKIM/DMARC/PTR), spam protection
(rspamd), virus scanning (ClamAV), TLS, account and storage provisioning,
hardening, and debugging.

## When to use

- Setup: a brand-new mail server on a fresh VPS.
- Repair: an existing server misbehaves (delivery failures, spam classification, auth failures, blacklisting, slow queues, broken webmail).
- Migrate: moving mailboxes from an old server to a new Mailu deployment (IMAP sync and DNS cutover).
- Ops: backups, restore drills, version updates, monitoring, account lifecycle, storage management, security review.

Not for: migration to non-Mailu targets, HA or clustered Mailu deployments, or greylisting policy tuning beyond defaults.

## Fleet refs needed

The mail server(s) and the DNS provider.

- `fleet/services.yaml`: service `mail` (Mailu compose path, health endpoint, host), when a Mailu stack already exists.
- `fleet/servers.yaml`: the mail server record (connection via `ops ssh <server>`; `<MAIL_ALIAS>` in the branches is that server's ssh alias), plus the source server record for a migration.
- `fleet/sites.yaml`: the mail domain records (domains, mailbox counts, quotas).
- `fleet/providers.yaml`: DNS provider record (registrar, Cloudflare, or other) and the VPS provider record where PTR is set.

Prerequisites:

- Key-based SSH access to the mail server(s).
- DNS control for the domain(s) at the registrar or provider panel.
- Ability to set PTR/reverse DNS at the VPS provider.
- Docker (the setup, migrate, and ops branches target Mailu on Docker).
- For migration: IMAP credentials per account, or admin access to the source.
- Local tools: `dig`, `ssh`, `scp`, `bash`; `swaks` (recommended); `imapsync` (migration only).

## Vault entries needed

Names follow `<client>-<provider>-<purpose>`. Values are never printed or
logged.

| Vault entry | Used for |
|---|---|
| `<client>-mailu-secret-key` | Mailu `SECRET_KEY`, generated fresh per deployment |
| `<client>-mailu-db-password` | `DB_PASSWORD` (PostgreSQL backend) |
| `<client>-mailu-admin-password` | `ADMIN_PASSWORD` for the Mailu admin account |
| `<client>-mailu-rspamd-password` | `RSPAMD_PASSWORD` |
| `<client>-mail-<domain>-imap-passfile` | Source IMAP credentials for migration (one passfile per source), only for the migrate branch |
| `<client>-<dns-provider>-dns-token` | DNS API token, only if DNS records are written through an API |
| `ssh/<client>-<server>` | ssh key from the server's fleet record |

## Procedure

Rules for every step:

- Reads need no flag. Every step that changes a production system is flagged **WRITE** and needs approval per the run's permission mode (AGENTS.md section 1.3).
- Every destructive **WRITE** (overwrite, delete, restart with data impact, schema change) is preceded by a **Backup** step.
- Every **WRITE** has a **Rollback** line.
- Every fix is followed by a **Verify** step.
- Placeholders only; real values come from fleet records and vault entries, never from this file.
- Planned work is tracked from `templates/plan-template.md` and `templates/runbook-template.md` in `runs/mail-server-config[-<suffix>]/`; logs there are append-only and timestamp-prefixed.

This file runs Discovery and routes to a branch. The procedures live in
`branches/`. Load `branches/<branch>.md`, plus `branches/common.md` for
setup, repair, and migrate, and nothing else.

| Branch | File | Use when |
|---|---|---|
| Setup | `branches/setup.md` | Fresh mail server install (Mailu, Docker) |
| Repair | `branches/repair.md` | Diagnose or fix an existing server (any stack) |
| Migrate | `branches/migrate.md` | Move mailboxes from an existing server into a new Mailu |
| Ops | `branches/ops.md` | Backup, restore, update, monitor, accounts, storage, security review |
| Common | `branches/common.md` | Shared DNS/TLS/SMTP verification; loaded by the branches above, never standalone |

Branch rule (non-negotiable): exactly one branch per run. Never mix branches.
An ops run on a live server is a separate run. Any deviation from the plan:
stop, record it in the runbook, and ask the operator (AGENTS.md section 1.4).

### Phase 0 - Discovery (mandatory, before any branch)

Answer every question with the operator. Record the answers in the run's
`plan.md` with the selected branch. Mark each as answered by the operator or
verified by inspection.

| # | Question | Determines |
|---|----------|------------|
| D1 | Goal of this run: fresh install / diagnose-repair existing / migrate mailboxes / ops run? | Branch selection |
| D2 | Scale: small (<100 mailboxes, SQLite backend) or medium/large (PostgreSQL backend)? | Setup branch DB backend |
| D3 | Existing stack (if any): postfix / exim / mailcow / Mailu / poste.io / other / n/a? | Repair commands, migrate source |
| D4 | Where is DNS hosted (registrar, Cloudflare, other)? Can PTR be set at the VPS provider? | DNS phase feasibility |
| D5 | Access: ssh alias from the server's fleet record, root/sudo level (access-ladder pattern, see `.agents/skills/wordpress-migration` section 1.4). Permission mode A/B set at plan approval (AGENTS.md section 1.3) | All branches |
| D6 | Domains, mailbox count, per-mailbox quota, disk budget, backup target (off-box path) | Storage provisioning, quota policy |

Routing:

- D1 = fresh install: load `branches/setup.md` (+ `common.md`).
- D1 = diagnose/repair: load `branches/repair.md` (+ `common.md`).
- D1 = migrate: load `branches/migrate.md` (+ `common.md`); requires setup branch sections 1-2 completed on the target.
- D1 = ops: load `branches/ops.md`.

### Run lifecycle

0. **Discover**: scan `runs/mail-server-config*` for existing variant folders; present matches and ask the operator to reuse one or create a new `-<suffix>` variant. Never auto-pick.
1. **Bootstrap**: operator confirms reuse of `runs/mail-server-config[-<suffix>]/` or a new `runs/mail-server-config-<suffix>/` folder. If new, create it with a `logs/` subfolder.
2. **Prep**: if new, copy `templates/plan-template.md` to `plan.md` and `templates/runbook-template.md` to `runbook.md`; fill hosts from fleet records and secrets as vault entry names. If reusing, load the existing `plan.md` and `notes.md` as context and propose an updated plan; never overwrite existing logs.
3. **Note-read**: read `references/` (mandatory) and the active branch file (+ `common.md`); propose the step list; flag every production **WRITE**.
4. **Approval**: the operator reviews `plan.md`, sets permission mode (A/B), and approves; the plan is then frozen.
5. **Execute**: tick off `runbook.md` steps; capture output to `logs/` (one timestamp-prefixed file per step, append-only).
6. **Deviation**: anything not in the plan: stop, ask, get approval.
7. **Close**: append findings to `notes.md` (cumulative history); propose lesson promotion to `references/lessons.md` (operator approves).

## Rollback

Each branch gives a **Rollback** line for every **WRITE**, and `branches/ops.md`
holds the restore procedure (`scripts/restore-mailu.sh`). Save a backup
(`scripts/backup-mailu.sh`) before any destructive write. Apply rollback lines
newest first. During a migration, keep the old MX and the source mailboxes
untouched until the target is verified; reverting the MX record and lowering
its TTL is the DNS rollback. If rollback fails, stop and ask the operator.

## Verify

Run the shared checks in `branches/common.md` after every branch:

- [ ] DNS audit passes: `scripts/dns-audit.sh <DOMAIN>` (MX, SPF, DKIM, DMARC, PTR).
- [ ] TLS certificate is valid for `mail.<DOMAIN>` on SMTP, submission, and IMAP.
- [ ] SMTP test with `swaks` delivers to an external mailbox, and an external message is received.
- [ ] `scripts/mail-diag.sh <MAIL_ALIAS>` shows healthy services and an empty or draining queue.
- [ ] Each branch's own verify steps are ticked in `runbook.md`.

## Gotchas

Details in `references/lessons.md`.

- Request PTR at the VPS provider before the first MX query; major receivers tempfail without a matching PTR (24-48h to propagate).
- SPF `permerror` is almost always record syntax or more than 10 lookups, not a blocked IP.
- Re-audit the published DKIM key against the signing key after any compose, env, or migration change.
- DNSBL delisting lags 24-48h; fix the root cause first.
- Back up before any Mailu upgrade; database migrations can be one-way.
- For IMAP migration the target quota must exceed source usage.

## Files

| Path | Purpose |
|---|---|
| `branches/common.md` | Shared DNS/TLS/SMTP verification and log map (any stack) |
| `branches/setup.md` | Fresh install, Mailu worked example |
| `branches/repair.md` | Diagnose and repair existing servers (any stack) |
| `branches/migrate.md` | Mailbox migration into a new Mailu |
| `branches/ops.md` | Backup, restore, update, monitor, accounts, storage |
| `scripts/` | `dns-audit.sh`, `mail-diag.sh`, `backup-mailu.sh`, `restore-mailu.sh`, `migrate-mailboxes.sh` |
| `templates/plan-template.md`, `templates/runbook-template.md` | Plan and runbook for a run in `runs/mail-server-config[-<suffix>]/` |
| `templates/mailu-compose.yml`, `templates/mailu-compose-postgres.yml`, `templates/mailu.env` | Mailu compose (SQLite and PostgreSQL) and env template |
| `templates/dns-records.md` | DNS record reference |
| `references/lessons.md` | Lessons learned (read before any run) |
