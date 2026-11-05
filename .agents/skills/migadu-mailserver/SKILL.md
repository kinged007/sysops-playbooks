---
name: migadu-mailserver
description: Manage Migadu-hosted mail (domain DNS setup, mailbox and alias lifecycle) through the Migadu API. Use when onboarding a domain to Migadu, fetching the DNS records a domain needs, or creating, modifying, or deleting mailboxes, aliases, identities, and forwardings. Not for self-hosted stacks (Mailu/postfix) or IMAP mailbox migration sync.
---

# Migadu Mail Server

> Read `references/lessons.md` BEFORE any run. It holds lessons learned from
> earlier runs that can change how you plan. Never edit mid-run.

Risk level: medium — changes live email delivery (DNS records) and live
mailbox state. A wrong DNS record breaks inbound mail; a deleted mailbox is
irreversible. No server root access is involved.

## When to use

- Setup: onboard a domain to Migadu — fetch the required DNS set, publish it
  at the DNS provider, run diagnostics, activate.
- Modify: create, update, disable, or delete a mailbox; manage aliases,
  identities, and forwardings.
- Edit: change domain settings (limits, spam handling, denylists).
- Read: list domains, mailboxes, usage; fetch DNS configs for a domain.

Not for: self-hosted mail (see `mail-server-config`, any branch); moving
message data between providers (IMAP sync is a separate plan); non-Migadu
mail providers.

## Fleet refs needed

Records from `fleet/` this skill reads. Real hosts, IPs, and domains are never
written in this file.

- `fleet/sites.yaml`: the mail domain record (domain name, mailbox list).
- `fleet/providers.yaml`: the DNS provider record (where TXT/MX/CNAME/SRV
  records are published) and the mail provider record (Migadu).

No `fleet/servers.yaml` entry: there is no SSH host in this skill. Everything
runs against `https://api.migadu.com/v1` from the operator machine.

## Vault entries needed

Names follow `<client>-<provider>-<purpose>`. Values are never printed or
written to logs or committed files.

- `<client>-migadu-api-key`: the Migadu API key (Basic-auth password).
  Vault file holds one line: `MIGADU_API_KEY=<key>`. Minimum scope: a key
  from the Migadu account that owns the domain
  (`admin.migadu.com` → My Account → API Keys). Keys are per user, not per
  domain — note whose user owns the key in the run's `inventory.md`.
- The Basic-auth username (the Migadu account email) is not a secret, but
  keep it out of chat transcripts: store it in the run's `secrets/`
  (`migadu_user.txt`, mode 600) and reference it from `inventory.md`.

Never pass the key on a command line (`curl -u user:key` leaks into shell
history and logs). Use `scripts/migadu-api.py`, which reads both files and
redacts the credential from output.

## Procedure

Rules for every step:

- Reads need no flag. Every step that changes a production system is flagged
  **WRITE** and needs approval per the run's permission mode (AGENTS.md §1.3).
- Every destructive **WRITE** (delete mailbox/alias/identity, overwrite a DNS
  record) is preceded by a **Backup** step.
- Every **WRITE** has a **Rollback** line.
- Every fix is followed by a **Verify** step.
- Placeholders only; real domains, users, and keys come from fleet records
  and vault entries, never from this file.
- Planned work is tracked from `templates/plan-template.md` and
  `templates/runbook-template.md` in `runs/migadu-mailserver[-<suffix>]/`;
  logs there are append-only and timestamp-prefixed.

### 0. Pre-flight (reads — no changes)

- [ ] Read `references/lessons.md` — mandatory before any run.
- [ ] Confirm access + permission mode in `plan.md` (AGENTS.md §1.3).
- [ ] `GET /v1/domains/<DOMAIN>` — domain exists, `state` is `active`,
  `can_send`/`can_receive`/`can_access` are true. If `state` is not active,
  stop: the domain needs §1 (setup/activate) first.
- [ ] `GET /v1/domains/<DOMAIN>/usage` — account verified and under storage /
  message limits. A mailbox create on a limited account fails 403 (see
  `references/lessons.md`); check this before promising a new mailbox.
- [ ] `GET /v1/domains/<DOMAIN>/mailboxes` — current mailbox list (shape:
  `{"mailboxes": [...]}`). Record it in `inventory.md`; it is the baseline
  for every lifecycle step below.

### 1. Domain setup — fetch and publish DNS (WRITE at the DNS provider)

- [ ] Read: `GET /v1/domains/<DOMAIN>/records` — the exact set Migadu wants
  (verification TXT, 2× MX, SPF TXT, 3× DKIM CNAMEs, DMARC TXT, autoconfig
  CNAME, 4× SRV). Save the response in the run's `logs/`; it is the source
  of truth, never retype values by hand.
- [ ] Read: list the zone's existing records first. If an SPF `v=spf1`
  record already exists, the Migadu SPF must be **merged** into it — two
  SPF records on one name is a permerror (see `references/lessons.md`).
- [ ] **WRITE** — publish the records at the DNS provider (one WRITE per
  record or one bulk WRITE per provider call; either way list each record
  in `plan.md`). Rollback: delete each added record by id (log the ids).
- [ ] Read: `GET /v1/domains/<DOMAIN>/diagnostics` — all checks pass. If
  not, fix DNS and re-run; do not activate early.
- [ ] **WRITE** — `GET /v1/domains/<DOMAIN>/activate`. (Read-shaped call,
  flagged WRITE because it flips the domain live.) Rollback: none needed —
  activation only succeeds when DNS is correct; deactivation is admin-UI.
- [ ] Verify: `diagnostics` green + inbound test message arrives.

### 2. Mailbox lifecycle (WRITE per action)

- [ ] **Create** — `POST /v1/domains/<DOMAIN>/mailboxes` with
  `{"name": "<DISPLAY>", "local_part": "<LOCAL>", "password": "<GENERATED>"}`
  (or `password_method: invitation` + `password_recovery_email` when the
  owner sets their own password). Generate the password fresh per mailbox
  (≥12 chars, alphanumeric keeps it log-safe), store it in the run's
  `secrets/` (mode 600) **before** the call. Rollback: `DELETE
  /v1/domains/<DOMAIN>/mailboxes/<LOCAL>` (mailbox never lived if create
  failed — verify with SHOW first).
- [ ] **Disable** (departures, holds) — prefer disable over delete; confirm
  the field with `SHOW` before/after. Rollback: re-enable.
- [ ] **Backup before delete** — confirm with the operator what must be kept
  (IMAP export or provider-side retention); record the decision in `plan.md`.
- [ ] **Delete** (operator-approved only) — `DELETE
  /v1/domains/<DOMAIN>/mailboxes/<LOCAL>`. Irreversible. Rollback: restore
  from the §-above backup (re-create + re-import), which is lossy without
  one — hence the backup gate.
- [ ] Verify after each action: `GET
  /v1/domains/<DOMAIN>/mailboxes/<LOCAL>` (SHOW returns 404 when absent)
  shows the expected state; send a test message to a new mailbox.

### 3. Aliases, identities, forwardings (WRITE per action)

- [ ] **Aliases** (same-domain redirects only) — `POST
  /v1/domains/<DOMAIN>/aliases` with `local_part` + `destinations`.
  Rollback: delete the alias.
- [ ] **Identities** (sender personas on a mailbox) — `POST
  /v1/domains/<DOMAIN>/mailboxes/<LOCAL>/identities`. Rollback: delete.
- [ ] **Forwardings** (external destinations) — `POST
  /v1/domains/<DOMAIN>/mailboxes/<LOCAL>/forwardings`. Rollback: delete.
- [ ] Verify: INDEX/SHOW on the parent object lists the new entry.

### 4. Domain settings (WRITE)

- [ ] `PATCH /v1/domains/<DOMAIN>` for spam aggressiveness, limits,
  denylists, catch-all destinations. Record old values in `plan.md` first.
  Rollback: PATCH the old values back.

## Rollback

Each section carries its own **Rollback** line; apply newest first. DNS
rollback is delete-by-id from the logged ids (or re-create the prior value
for merged records like SPF). Mailbox/alias rollback is DELETE, except
mailbox delete itself, whose rollback is re-create + restore from the
pre-delete backup. If a rollback fails, stop and ask the operator.

## Verify

- [ ] `GET /v1/domains/<DOMAIN>` — `active`, can send/receive.
- [ ] `GET /v1/domains/<DOMAIN>/mailboxes` — every intended mailbox present
  with the intended flags; no unintended deletions.
- [ ] `GET /v1/domains/<DOMAIN>/diagnostics` — green after any DNS change.
- [ ] Test message delivered to each created mailbox; webmail login works.

## Gotchas

Details in `references/lessons.md`.

- Unverified/limited accounts get 403 on create — check `usage` first.
- Two SPF records on one name is a permerror, never a merge.
- Mailbox INDEX returns `{"mailboxes": [...]}`, not a bare list.
- Never put the API key on a command line — use the script.

## Files

| Path | Purpose |
|---|---|
| `scripts/migadu-api.py` | Authenticated API helper (reads creds from files, redacts secrets) |
| `templates/plan-template.md`, `templates/runbook-template.md` | Plan and runbook for a run in `runs/migadu-mailserver[-<suffix>]/` |
| `references/lessons.md` | Lessons learned (read before any run) |
