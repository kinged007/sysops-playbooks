# Playbook: <PLAYBOOK NAME>

> **Agent: read `notes/` BEFORE any run.** The notes contain lessons learned
> from previous executions that may change how you plan. Never skip this.

## What it does
<One paragraph. What problem does this playbook solve?>

## When to use it
<What signals trigger this playbook? What does it NOT cover?>

## Prerequisites
<What must exist before a run: access, tools, accounts, credentials>

## Risk level
<low | medium | high> — <one-line justification. Examples: "touches production
Docker daemons", "moves live data between servers", "changes live email delivery">

## Servers involved
<How many servers, what roles each plays (source/dest/app server). Real values
never go here — see plan-template.md>

## Files
| Path | Purpose |
|---|---|
| `playbook.md` | Canonical step-by-step procedure (placeholders only) |
| `plan-template.md` | Copied to `executions/<run>/plan.md` at run start |
| `runbook-template.md` | Copied to `executions/<run>/runbook.md` at run start |
| `templates/` | All templates: compose, scaffolds, configs, code templates |
| `scripts/` | Scripts the playbook uses |
| `notes/` | Lessons learned, gotchas, pitfalls from past runs |
