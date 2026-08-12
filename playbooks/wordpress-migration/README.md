# Playbook: WordPress Migration

> **Agent: read `notes/` BEFORE any run.** The notes contain lessons learned
> from previous executions that may change how you plan. Never skip this.

## What it does
Migrates a WordPress site (files + database) between servers with minimal
risk and clear verification at every stage: discovery, backup, transfer
while the source stays live, staging + testing on the destination, then a
cutover via either a maintenance window (Branch A) or a DNS cutover with
final delta sync (Branch B), with a defined rollback path throughout.

## When to use it
Server-to-server moves, hosting provider changes, VPS upgrades, container
re-platforming (bare metal → Docker/Dokploy). Not for same-host restores,
theme/plugin work, or in-place upgrades (the playbook deliberately migrates
like-for-like — PHP/DB versions are pinned, never upgraded during a
migration).

## Prerequisites
- SSH (key-based) to source and destination servers (L3+; L2/L1 fallback via
  panels/plugins exists but is weaker)
- DB credentials for both sites (read on source, write on destination)
- WP-CLI or `mysqldump`/`mysql` on both ends
- DNS control (for cutover) — at minimum a documented rollback path
- Site owner/operator as go-no-go approver

## Risk level
**high** — moves live data between servers; a mistake can destroy the
source site, corrupt serialized data, or serve stale/corrupt content after
cutover. Rollback plan is mandatory and must be signed off before work.

## Servers involved
Source (production WordPress) + destination (new host). Real values live in
the execution's `inventory.md`, never here.

## Branching model
The playbook has **two mutually exclusive branches** chosen at Phase 1 —
**Branch A** (single maintenance window; simplest, safest) and **Branch B**
(zero/near-zero downtime via DNS cutover; complex). Never mix them.

## Files
| Path | Purpose |
|---|---|
| `playbook.md` | Canonical procedure (placeholders only; WRITE flags on every production write) |
| `plan-template.md` | Copied to `executions/<run>/plan.md` |
| `runbook-template.md` | Copied to `executions/<run>/runbook.md` |
| `templates/` | Compose files, wp-config scaffolds, nginx/vhost templates |
| `scripts/` | Backup/transfer/restore scripts |
| `notes/` | Lessons learned from past migrations (verified incidents, gotchas) |
