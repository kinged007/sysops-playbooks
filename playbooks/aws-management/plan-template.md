# Plan: <RUN NAME>

| Field | Value |
|---|---|
| Client | <client> |
| Playbook | `aws-management` |
| Execution folder | `executions/aws-management/` or `executions/aws-management-<suffix>/` |
| Permission mode | **UNSET — set by operator at approval** (A: per-write confirm / B: plan-as-approved) |
| Status | draft → approved → executing → closed |

## AWS target (THIS variant only)

| Field | Value |
|---|---|
| AWS account ID / alias | `<AWS_ACCOUNT_ID>` / `<ACCOUNT_ALIAS>` |
| Partition | `aws` / `aws-cn` / `aws-us-gov` |
| Default region | `<AWS_REGION>` (e.g. `eu-central-1`) |
| Additional regions in scope | `<REGION_2>, <REGION_3>` or `—` |
| CLI profile name | `<PROFILE>` |
| Credential method | SSO (Identity Center) / IAM user keys / assumed role / instance profile |
| SSO start URL (if SSO) | `<SSO_START_URL>` |
| SSO region (if SSO) | `<SSO_REGION>` |
| Principal ARN | `arn:aws:iam::<AWS_ACCOUNT_ID>:user/<USER>` or `arn:aws:iam::<AWS_ACCOUNT_ID>:role/<ROLE>` |
| Management host | `<workstation / bastion alias or "local">` |
| Network path | direct egress / NAT / proxy `<PROXY_URL>` / isolated VPC endpoints |

Real values never go in the playbook — only here and in `inventory.md` / `secrets/`.
Record SSO URLs, ARNs, and proxy URLs in `inventory.md`; keys and tokens only in `secrets/`.

## Credentials / secrets (THIS variant only)

Files in `secrets/` of this execution folder; never inline values here.
Secrets persist in this folder across invocations — update in place when rotating.

- `secrets/aws-credentials.<PROFILE>.env` — `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` if using keys (0600)
- `~/.aws/sso/cache/` — SSO token cache (outside executions; note expiry in inventory)
- `secrets/assume-role.<ROLE>.json` — `sts assume-role` output if using cross-account

## Task definition

> Well-Architected "What to include": document requirements, constraints, and
> expected results before any write.

- **Goal of this run:** <one sentence — e.g. "Install CLI and enable S3 versioning on <BUCKET> in <AWS_REGION>">
- **Why:** <reason / ticket ref>
- **Scope:** account(s) `<AWS_ACCOUNT_ID>`, region(s) `<AWS_REGION>`, resources `<ARN / tag filter>`
- **Change window:** <date/time or "no window — reads only">
- **Blast radius:** <what could be affected if a step is wrong>
- **Billing impact:** <none / estimate>

## Steps

Numbered steps mirroring `runbook.md`, with **WRITE** flags. Every WRITE lists
the exact command and its rollback.

1. Discover current state — reads (`aws --version`, `sts get-caller-identity`) (read)
2. Install/upgrade AWS CLI v2 if needed (read; WRITE only if install runs)
3. Configure CLI profile `<PROFILE>` — SSO / keys / assume-role (WRITE — writes `~/.aws/config` / `~/.aws/credentials`)
4. Set region/output defaults for `<PROFILE>` (WRITE — writes `~/.aws/config`)
5. Verify identity + region (read)
6. <Task step — e.g. S3 / IAM / VPC read> (read)
7. <Task step — e.g. `aws s3api put-bucket-versioning ...`> (**WRITE** — rollback: `aws s3api put-bucket-versioning --versioning-configuration Status=Suspended ...`)
8. Verify resource state + CloudTrail (read)
9. (If codified) Create SSM Automation document / EventBridge rule (**WRITE** — rollback: `delete-document` / `remove-targets` + `delete-rule`)

Flag every production WRITE in bold. Reads need no flag.

## Constraints on execution

- Conflicts with other business/operations activities: <none / list>
- Required approvals beyond this plan: <none / e.g. "network team for VPC change">
- Network constraints: <egress / proxy / isolated — note here>

## Escalation (Well-Architected §Escalation)

- Primary on-call: <name / contact> — escalate if not identified within <N> min
- AWS Support plan / case routing: <plan level, account>
- Decision maker to notify before production writes: <name>

## Risk assessment

What could go wrong; blast radius; rollback plan. Every WRITE above already
lists its rollback — summarize here.

## Approval

- [ ] Operator reviewed plan and set permission mode: <A or B>
- [ ] Operator approved execution on <date>
