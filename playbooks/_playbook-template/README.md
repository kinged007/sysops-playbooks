# Playbook: <PLAYBOOK NAME>

> **Agent: read `notes/` BEFORE any run.** The notes contain lessons learned
> from previous executions that may change how you plan. Never skip this.

## What it does
<One paragraph. What problem does this playbook solve?>

## When to use it
<What signals trigger this playbook? What does it NOT cover?>

## Prerequisites
<What must exist before a run: access, tools, accounts, credentials>

> **Template default tooling:** if your template provisions a workspace (e.g. from `codercom/enterprise-node:ubuntu` or `codercom/universal`), ensure **GitHub CLI (`gh`), `uv`, `Go`, and `Rust`** are installed by default like `npm`/`python` — see `playbooks/coder-remote-servers/templates/scripts/install-*.sh` helpers (apt or binary to `~/.local/bin`/`~/.local/go`/`~/.cargo`, handles `runsc` with no sudo).

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
| `plan-template.md` | Copied to `executions/<playbook>/plan.md` on first run (or `executions/<playbook>-<suffix>/plan.md`) |
| `runbook-template.md` | Copied to `executions/<playbook>/runbook.md` on first run |
| `templates/` | All templates: compose, scaffolds, configs, code templates |
| `scripts/` | Scripts the playbook uses |
| `notes/` | Lessons learned, gotchas, pitfalls from past runs |

> Execution folders are **persistent per playbook variant**. The first run creates
> `executions/<playbook>/` (or `executions/<playbook>-<suffix>/` when the operator
> supplies a suffix like `personal`/`company`/`prod`). All subsequent invocations
> for the same variant **reuse and append to the same folder** — `secrets/` and
> `inventory.md` persist, `logs/` is append-only. The agent always scans for an
> existing folder before creating a new one and confirms with the operator.
