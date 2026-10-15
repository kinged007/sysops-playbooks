# Runbook: <RUN NAME>

Snapshot of `playbooks/aws-management/playbook.md` being executed, with
real values filled in. State lives here and in `logs/` — any agent session can
resume from these files alone. This folder is persistent per playbook variant
(`executions/aws-management[/-<suffix>]/`); subsequent invocations append to it,
never replace it. `logs/` is append-only — each session adds
timestamp-prefixed files (e.g. `logs/2026-08-29T143000-01-discover.log`).

| Field | Value |
|---|---|
| Run | <run name> |
| Playbook | `aws-management` |
| Execution folder | `executions/aws-management/` or `executions/aws-management-<suffix>/` |
| Client | <client> |
| AWS account | `<AWS_ACCOUNT_ID>` / `<ACCOUNT_ALIAS>` |
| Region | `<AWS_REGION>` |
| Profile | `<PROFILE>` |
| Started | <date> |
| Permission mode | <A / B> (set at plan approval) |

## Steps

Status values: `pending` / `in-progress` / `done` / `blocked`.

- [ ] **0. Pre-flight** (read) — status: pending
  - Log: `logs/<timestamp>-00-preflight.log` (append-only; prior logs never overwritten)
- [ ] **1. Discover current state** (read) — status: pending
  - Log: `logs/<timestamp>-01-discover.log`
  - Reads: `aws --version`, `aws sts get-caller-identity --profile <PROFILE>`, `aws configure list`, region/AZ check
- [ ] **2. Install / upgrade AWS CLI v2** (conditional **WRITE**) — status: pending
  - Log: `logs/<timestamp>-02-install-cli.log`
  - Mode A note: operator confirmation required before install/upgrade.
  - Rollback: remove `/usr/local/aws-cli` + `/usr/local/bin/aws` (Linux) or `brew uninstall awscli` (macOS)
- [ ] **3. Configure CLI profile `<PROFILE>`** (conditional **WRITE**) — status: pending
  - Log: `logs/<timestamp>-03-configure.log`
  - Writes `~/.aws/config` / `~/.aws/credentials` or runs `aws sso login`. Rollback: restore `.bak` copy.
- [ ] **4. Region / output defaults** (**WRITE** if changed) — status: pending
  - Log: `logs/<timestamp>-04-region.log`
- [ ] **5. Verify identity + region** (read) — status: pending
  - Log: `logs/<timestamp>-05-verify-identity.log`
- [ ] **6. Task step — <domain> read** (read) — status: pending
  - Log: `logs/<timestamp>-06-task-read.log`
- [ ] **7. Task step — <describe the WRITE>** (**WRITE**) — status: pending
  - Log: `logs/<timestamp>-07-task-write.log`
  - Mode A note: operator confirmation required before running.
  - Rollback: <exact rollback command>
- [ ] **8. Verification** (read) — status: pending
  - Log: `logs/<timestamp>-08-verify.log`
  - Re-read changed resource + `aws cloudtrail lookup-events` if applicable
- [ ] **9. Codify / trigger (if in scope)** (conditional **WRITE**) — status: pending
  - Log: `logs/<timestamp>-09-codify.log`
  - Rollback: `aws events remove-targets` / `delete-rule` / `aws ssm delete-document`

Duplicate steps 6–7 per additional task. Every WRITE carries its rollback inline.

## Deviations

Anything not in the plan → STOP, record here, ask operator. Never improvise on
the live AWS account.

## Escalation log

Time-stamped escalation attempts (who, when, how, outcome). Not a WRITE to AWS.

## Close-out

- [ ] Runbook complete (all steps done or blocked+explained)
- [ ] Findings appended to `notes.md` (cumulative history — do not overwrite; date header per session)
- [ ] Promotion candidates proposed to operator (→ playbook `notes/gotchas.md` or `templates/`)
