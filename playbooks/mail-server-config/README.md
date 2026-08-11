# Playbook: Mail Server Configuration

> **Agent: read `notes/` BEFORE any run.** The notes contain lessons learned
> from previous executions that may change how you plan. Never skip this.

## What it does
Configures or repairs a mail server: baseline inventory, DNS records
(SPF/DKIM/DMARC), MTA configuration, relay/auth, verification with test mail.

## When to use it
New mail server setup, DKIM/SPF/DMARC repairs, relay or auth changes, delivery
troubleshooting. Not for mailbox migration (separate playbook).

## Prerequisites
- SSH (key-based) to the mail server
- DNS control for the domain (records for SPF/DKIM/DMARC)
- Admin panel access if the server uses one (e.g. mailcow, poste.io)

## Risk level
**high** — changes live email delivery; a misconfiguration can cause
rejection by receivers or delivery blacklisting.

## Servers involved
The mail server + DNS provider. Real values live in the execution's
`inventory.md`, never here.

## Files
| Path | Purpose |
|---|---|
| `playbook.md` | Canonical procedure (placeholders only) |
| `plan-template.md` | Copied to `executions/<run>/plan.md` |
| `runbook-template.md` | Copied to `executions/<run>/runbook.md` |
| `templates/` | MTA config templates, DKIM scripts, DNS record examples |
| `scripts/` | Baseline inventory, verification scripts |
| `notes/` | Lessons learned from past configurations |
