# Playbook: WordPress Migration

> **Agent: read `notes/` BEFORE any run.** The notes contain lessons learned
> from previous executions that may change how you plan. Never skip this.

## What it does
Migrates a WordPress site (files + database) between servers with minimal
downtime: inventory source, backup, transfer, restore + reconfigure, verify,
rollback.

## When to use it
Server-to-server moves, hosting provider changes, VPS upgrades. Not for
same-host restores or theme/plugin work.

## Prerequisites
- SSH (key-based) to source and destination servers
- DB credentials for both sites (read on source, write on destination)
- WP-CLI or `mysqldump`/`mysql` on both ends

## Risk level
**high** — moves live data between servers; a mistake can destroy the
source site or expose credentials in transit.

## Servers involved
Source (production WordPress) + destination (new host). Real values live in
the execution's `inventory.md`, never here.

## Files
| Path | Purpose |
|---|---|
| `playbook.md` | Canonical procedure (placeholders only) |
| `plan-template.md` | Copied to `executions/<run>/plan.md` |
| `runbook-template.md` | Copied to `executions/<run>/runbook.md` |
| `templates/` | Compose files, wp-config scaffolds, nginx/vhost templates |
| `scripts/` | Backup/transfer/restore scripts |
| `notes/` | Lessons learned from past migrations |
