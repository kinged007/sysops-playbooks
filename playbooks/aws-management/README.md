# Playbook: AWS Management (General)

> **Agent: read `notes/` BEFORE any run.** The notes contain lessons learned
> from previous executions and the Well-Architected playbook concept that may
> change how you plan. Never skip this.

## What it does
General-purpose AWS control-plane playbook for day-to-day management from a
workstation or management host: installs and configures **AWS CLI v2**, validates
identity and permissions, and provides a safe, repeatable framework to **manage
settings and configure things** (IAM, VPC, EC2, S3, RDS, CloudWatch, and similar)
with READ/WRITE segregation, approvals, and rollback. It follows the
[AWS Well-Architected — Playbook](https://wa.aws.amazon.com/wellarchitected/2020-07-02T19-33-23/wat.concept.playbook.en.html)
concept: playbooks are predefined investigation/response steps where each step's
result determines the next step until the issue is identified or escalated.

## When to use it
- First-time AWS setup on a new workstation, bastion, or management host
- Validating or repairing an existing AWS CLI / SSO / IAM configuration
- Any "manage AWS settings" task where the operator wants a gated
  read-first → plan → approved-write workflow instead of ad-hoc CLI calls
- Codifying a frequent or high-impact AWS task into code (SSM Automation,
  Run Command, Lambda) with an event trigger (EventBridge/CloudWatch)

Does **NOT** cover: workload-specific migrations, data-plane restores, or
third-party SaaS configuration outside AWS. For those, create a focused
playbook and reuse this one's CLI bootstrap.

## Prerequisites

Per Well-Architected "What to include in playbooks", a run must document
**requirements to be able to execute** before any write.

### Required permissions
- An AWS **identity** that will run the CLI: IAM user, IAM Identity Center
  (SSO) user, or assumed role. Record the ARN in the execution's
  `inventory.md` — never here.
- The **minimum IAM policy** for the task (least privilege). For a generic
  management run this is typically `ReadOnlyAccess` for discovery plus
  scoped write policies per approved step (e.g. `AmazonS3FullAccess` only if
  S3 writes are planned). MFA present if the account enforces it.
- Ability to create/assume the execution role if cross-account work is needed
  (`sts:AssumeRole`).
- Organization / SCP awareness if the account is in AWS Organizations.

### Required tools and configurations
- **AWS CLI v2** (this playbook installs it if missing) — see `playbook.md` §2
- `unzip` + `curl` (Linux bootstrap) or `brew` (macOS) or PowerShell 5+ (Windows)
- `jq` (recommended for JSON output), `aws-session-manager-plugin` (only if
  using `aws ssm start-session`)
- OS: Linux (x86_64/aarch64), macOS 12+, or Windows 10/11 / WSL2
- Python 3.9+ only if you will author Lambda-based playbooks

### Required network connectivity and access
- HTTPS egress to `*.amazonaws.com` (and `*.awsapps.com` for SSO) — direct,
  via NAT gateway, or via corporate proxy/VPN. Note any proxy URL in
  `inventory.md`.
- DNS resolution for the AWS partition in use (`amazonaws.com`,
  `amazonaws.com.cn`, or `amazonaws.com` GovCloud as applicable).
- If the management host is isolated (no internet), a VPC endpoint strategy
  must be documented as a constraint.

### Constraints on execution
- Change windows, approval gates, and blast radius (account / region / tags).
- Conflicts with other business or operations activities (e.g. concurrent
  deployments, backup windows).
- Billing impact of any resource-creating step.
- Escalation path (see `playbook.md` §7) — who to contact, after how long,
  and with what support information.

## Risk level
**medium** — reads are safe; every `aws ... create/update/delete/put` is a
**WRITE** to the live AWS control plane with direct billing and security
impact. All writes are approval-gated with rollback.

## Servers involved
No fixed servers. The run touches **one AWS account (or Organization) and one
or more Regions**, operated from a **management host / workstation** where the
CLI runs. Real values (account IDs, aliases, Regions, SSO start URL, role
ARNs, profile names) live only in the execution's `inventory.md` and
`secrets/`, never here.

## Files
| Path | Purpose |
|---|---|
| `playbook.md` | Canonical procedure (placeholders only) |
| `plan-template.md` | Copied to `executions/aws-management/plan.md` on first run (or `executions/aws-management-<suffix>/plan.md`) |
| `runbook-template.md` | Copied to `executions/aws-management/runbook.md` on first run |
| `templates/aws-config.example.ini` | Example `~/.aws/config` with SSO and static profiles |
| `templates/aws-credentials.example.ini` | Example `~/.aws/credentials` (placeholder values only) |
| `templates/ssm-automation.example.yaml` | Minimal SSM Automation document skeleton |
| `scripts/install-aws-cli.sh` | Install/upgrade AWS CLI v2 (Linux/macOS) |
| `scripts/aws-doctor.sh` | Read-only diagnostics: CLI, auth, region, permissions |
| `notes/playbook-concept.md` | Summary of the Well-Architected Playbook concept |
| `notes/gotchas.md` | Lessons learned from past runs (read before any run) |

> Execution folders are **persistent per AWS variant**. The first run creates
> `executions/aws-management/` (or `executions/aws-management-<suffix>/` when
> the operator supplies a suffix like `prod`/`staging`/`<client>`). All
> subsequent invocations for the same variant **reuse and append to the same
> folder** — `secrets/` and `inventory.md` persist, `logs/` is append-only.
> The agent always scans for an existing folder before creating a new one and
> confirms with the operator.

## Reference
- AWS Well-Architected Framework — Playbook concept:
  <https://wa.aws.amazon.com/wellarchitected/2020-07-02T19-33-23/wat.concept.playbook.en.html>
  — defines what to document (requirements, constraints, steps + expected
  results, escalation) and where to start (frequent + high-impact issues),
  plus implementation in code (Systems Manager, Lambda) with event triggers
  (CloudWatch Events / EventBridge).
