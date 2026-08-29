# Playbook: Mail Server Configuration

> **Agent: read `notes/` BEFORE any run.** The notes contain lessons learned
> from previous executions that may change how you plan. Never skip this.

## What it does
Full mail server lifecycle on remote servers: fresh setup (worked example:
**Mailu on Docker**), diagnosis and repair of **existing** mail servers
(stack-agnostic: postfix, exim, mailcow, Mailu, poste.io, ...), mailbox
migration into a new Mailu, and ongoing ops (backup/restore/update/monitor).
Covers everything from DNS records (MX/SPF/DKIM/DMARC/PTR) through spam
protection (rspamd), virus scanning (ClamAV), TLS, account/storage
provisioning, hardening, and debugging.

## When to use it
- **Setup** — brand-new mail server on a fresh VPS.
- **Repair** — existing server misbehaves: delivery failures, spam
  classification, auth failures, blacklisting, slow queues, broken webmail.
- **Migrate** — moving mailboxes from an old server to a new Mailu deployment
  (IMAP sync + DNS cutover).
- **Ops** — backups, restore drills, version updates, monitoring, account
  lifecycle, storage management, security review.

Does **NOT** cover: migration to non-Mailu targets, HA/clustered Mailu
deployments, or greylisting policy tuning beyond defaults.

## Prerequisites
- SSH (key-based) access to the mail server(s) — user-managed aliases in
  `~/.ssh/config`, never raw hostnames
- DNS control for the domain(s) (registrar or provider panel)
- Ability to set **PTR/reverse DNS** at the VPS provider
- Docker (setup/migrate/ops branches target Mailu on Docker)
- For migration: IMAP credentials per account, or admin access to source
- Local tools: `dig`, `ssh`, `scp`, `bash`; `swaks` (recommended), `imapsync`
  (migration only)

## Risk level
**high** — changes live email delivery; a misconfiguration can cause
rejection by receivers or delivery blacklisting. Production servers are
READ-ONLY by default (AGENTS.md §1.1); every write needs plan approval +
permission mode.

## Servers involved
The mail server(s) + DNS provider. Real values live in the execution's
`inventory.md`, never here.

## Files
| Path | Purpose |
|---|---|
| `playbook.md` | Master: discovery questions + branch router |
| `branches/common.md` | Shared DNS/TLS/SMTP verification + log map (any stack) |
| `branches/setup.md` | Fresh install, Mailu worked example |
| `branches/repair.md` | Diagnose & repair existing servers (any stack) |
| `branches/migrate.md` | Mailbox migration into new Mailu |
| `branches/ops.md` | Backup, restore, update, monitor, accounts, storage |
| `plan-template.md` | Copied to `executions/mail-server-config/plan.md` on first run (or `executions/mail-server-config-<suffix>/plan.md`) |
| `runbook-template.md` | Copied to `executions/mail-server-config/runbook.md` on first run |
| `templates/` | mailu compose (sqlite/postgres), mailu.env, DNS record reference |
| `scripts/` | dns-audit, mail-diag, backup-mailu, restore-mailu, migrate-mailboxes |
| `notes/` | Lessons learned (read before any run) |
