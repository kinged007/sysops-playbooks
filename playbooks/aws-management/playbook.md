# Playbook: AWS Management (General) — Procedure

Canonical steps for a run. **Placeholders only** — never real account IDs,
role ARNs, access keys, SSO URLs, or hostnames. Real values go in the
execution's `plan.md` / `inventory.md` / `secrets/`.
Repo-level rules (folder discipline, secrets, committing): see `AGENTS.md`.

Well-Architected source: [Playbook](https://wa.aws.amazon.com/wellarchitected/2020-07-02T19-33-23/wat.concept.playbook.en.html)
— this playbook implements its "Requirements / Constraints / Process steps +
expected results / Escalation" structure and its "Implement in code + trigger
automatically" guidance.

Conventions: every step that **WRITES** to the live AWS control plane
(`aws ... create/update/delete/put/register`, `cloudformation deploy`,
console writes, etc.) is flagged **WRITE** and needs approval per the run's
permission mode (**A**: per-write confirm / **B**: plan-as-approved). Reads
(`aws ... describe/list/get`, `sts get-caller-identity`, `SELECT`) need no
flag and run freely. Rollback is given for every write.

---

## 0. Pre-flight

- [ ] Read `notes/playbook-concept.md` + `notes/gotchas.md` (mandatory) —
      the Well-Architected playbook concept and prior-run pitfalls may change
      how you plan.
- [ ] Confirm prerequisites (README): AWS identity + permissions, tooling,
      network (egress to `*.amazonaws.com` / proxy if needed).
- [ ] Confirm where the CLI will run: local workstation, bastion/management
      host, or CI runner — record in `inventory.md`.
- [ ] Record the run's permission mode in the runbook (**A** or **B**, per
      `AGENTS.md` §1.3 — ask the operator, never assume).
- [ ] Existing executions: `ls executions/aws-management*` — reuse the matching
      variant or create `executions/aws-management-<SUFFIX>/` with the operator.
      Prior `inventory.md` / `secrets/` is authoritative for that variant.

## 1. Discover current state (reads only)

Run from the management host / workstation where the CLI will live. All steps
in this phase are reads.

- [ ] CLI presence and version:
      `aws --version 2>&1` — expect `aws-cli/2.*`
- [ ] CLI configuration (no secrets printed):
      `aws configure list --profile <PROFILE>` and `cat ~/.aws/config` (redact)
- [ ] Identity and account (read-only, no write):
      `aws sts get-caller-identity --profile <PROFILE> --output table`
      `aws iam get-user --profile <PROFILE> 2>/dev/null || aws sts get-caller-identity --profile <PROFILE>`
- [ ] Region and partition:
      `aws configure get region --profile <PROFILE> 2>/dev/null || echo "<AWS_REGION>"`
      `aws ec2 describe-availability-zones --profile <PROFILE> --region <AWS_REGION> --output table 2>&1 | head -n 30`
- [ ] Network egress (if restricted/VPN/proxy):
      `curl -I https://sts.<AWS_REGION>.amazonaws.com 2>&1 | head -n 5`
      proxy check: `env | grep -i proxy; aws configure get proxy 2>/dev/null || true`
- [ ] Permission surface (read-only policy simulation where available):
      `aws iam simulate-principal-policy --policy-source-arn <PRINCIPAL_ARN> --action-names s3:ListBuckets ec2:DescribeInstances --profile <PROFILE> 2>&1 | head -n 40`
      (skip if no `iam:SimulatePrincipalPolicy` — note as a constraint)
- [ ] Record every finding in the runbook; note: current CLI version, profile
      name(s), account ID, region, identity ARN, MFA status, network path.

### Phase 1 expected results → next step (playbook decision table)

| Observation | Determination | Next step |
|---|---|---|
| `aws --version` missing or `1.x` | CLI not installed / outdated | §2 install/upgrade |
| `sts get-caller-identity` fails (`ExpiredToken`, `InvalidClientTokenId`, `AccessDenied`) | Not authenticated / token expired / wrong profile | §3 configure auth |
| Identity succeeds but `SimulatePrincipalPolicy` shows missing actions needed for the task | Insufficient permissions | §3.5 request/assume scoped permissions |
| Region empty or AZ call fails | Region not configured or network blocked | §3 region + §1 network |
| All reads succeed; task requires no writes | Nothing to install | §4 plan the management task |

## 2. Install and configure the CLI tool (AWS CLI v2)

> This is the playbook's required bootstrap — every management task depends on
> a working CLI with the correct identity and region. Keep it general and
> copy-paste executable with placeholders.

### 2.1 Install AWS CLI v2 (idempotent)

- [ ] Run the installer for the management host's OS:

  **Linux x86_64:**
  ```bash
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
  unzip -qo /tmp/awscliv2.zip -d /tmp
  # fresh install:
  sudo /tmp/aws/install
  # upgrade (if already installed):
  sudo /tmp/aws/install --update
  aws --version   # expect aws-cli/2.*
  ```

  **Linux aarch64 (ARM):**
  ```bash
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o /tmp/awscliv2.zip
  unzip -qo /tmp/awscliv2.zip -d /tmp
  sudo /tmp/aws/install --update
  aws --version
  ```

  **macOS (Homebrew):**
  ```bash
  brew install awscli
  aws --version
  ```

  **Windows / WSL2:** download the MSI from
  <https://awscli.amazonaws.com/AWSCLIV2.msi> (Windows) or follow the Linux
  steps inside WSL2. Verify: `aws --version` / `aws --version` in PowerShell.

  Helper script (Linux/macOS): `scripts/install-aws-cli.sh` — wraps the above
  with arch detection and `--update` handling.
  ```bash
  bash playbooks/aws-management/scripts/install-aws-cli.sh
  aws --version
  ```

- [ ] Verify install (read):
  `aws --version` → `aws-cli/2.*  Python/...`
  `which aws` → `/usr/local/bin/aws` (Linux) or `$(brew --prefix)/bin/aws` (macOS)
- [ ] Optional but recommended:
  `aws --version` notes the bundled Python; `jq --version` for JSON output
  `aws completer` / shell completion: `complete -C aws_completer aws` (bash)

- Rollback: `sudo /usr/local/bin/aws_completer 2>/dev/null; sudo rm -rf /usr/local/aws-cli /usr/local/bin/aws /usr/local/bin/aws_completer` (Linux)
  or `brew uninstall awscli` (macOS). Previous version is not auto-restored —
  record the prior version in the runbook before upgrading.

### 2.2 Configure the CLI — choose ONE credential method

Document the chosen method in `inventory.md`. Never commit real values.

**Option A — IAM Identity Center (SSO) — preferred for humans:**

```bash
aws configure sso --profile <PROFILE>
# prompts: SSO start URL <SSO_START_URL>, SSO region <SSO_REGION>,
#          account <AWS_ACCOUNT_ID>, role <SSO_ROLE_NAME>,
#          region <AWS_REGION>, output json
aws sso login --profile <PROFILE>
aws sts get-caller-identity --profile <PROFILE> --output table
```

- Config lands in `~/.aws/config` as:
  `sso_start_url`, `sso_region`, `sso_account_id`, `sso_role_name`, `region`.
  See `templates/aws-config.example.ini`.
- Token is cached under `~/.aws/sso/cache/`; refresh with `aws sso login`.

**Option B — IAM user access keys (scoped, least privilege):**

```bash
aws configure --profile <PROFILE>
# prompts: Access Key ID <AWS_ACCESS_KEY_ID>, Secret <AWS_SECRET_ACCESS_KEY>,
#          region <AWS_REGION>, output json
# Prefer: paste into ~/.aws/credentials via a secrets file, not inline history
aws sts get-caller-identity --profile <PROFILE> --output table
```

- Keys live in `~/.aws/credentials` (or env `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`).
  See `templates/aws-credentials.example.ini`. Rotate via IAM; never echo keys
  in shell history — use `read -s` or a file from `secrets/`.

**Option C — Assumed role (cross-account / elevated):**

```bash
aws configure set --profile <PROFILE> region <AWS_REGION>
aws configure set --profile <PROFILE> role_arn arn:aws:iam::<AWS_ACCOUNT_ID>:role/<ROLE_NAME>
aws configure set --profile <PROFILE> source_profile <SOURCE_PROFILE>
aws sts get-caller-identity --profile <PROFILE> --output table
# or one-shot:
aws sts assume-role --role-arn arn:aws:iam::<AWS_ACCOUNT_ID>:role/<ROLE_NAME> \
  --role-session-name <SESSION_NAME> --profile <SOURCE_PROFILE>
```

**Option D — EC2/ECS instance profile (management host on AWS):**

No local credentials — the instance/task role is automatic.
```bash
aws sts get-caller-identity --output table   # no --profile needed
curl -s http://169.254.169.254/latest/meta-data/iam/info 2>/dev/null | head -n 20
```

### 2.3 Verify CLI configuration (reads)

- [ ] `aws configure list --profile <PROFILE>` — shows access key source, region, output
- [ ] `aws sts get-caller-identity --profile <PROFILE> --output json` — record Account, Arn
- [ ] `aws ec2 describe-regions --profile <PROFILE> --output table 2>&1 | head -n 20` — region is valid
- [ ] `aws iam get-account-authorization-details --profile <PROFILE> 2>&1 | head -n 5` — only if needed; can be large
- [ ] Capture `aws --version`, profile name, region, identity ARN, expiry (SSO token `~/.aws/sso/cache/*.json` `expiresAt`) in `inventory.md`.

### 2.4 Expected results → next step

| Observation | Determination | Next step |
|---|---|---|
| `get-caller-identity` returns the expected Account/Arn | Auth OK | §3 (region/defaults) |
| `ExpiredToken` / `TokenRefreshRequired` | SSO token expired | `aws sso login --profile <PROFILE>` |
| `InvalidClientTokenId` | Wrong keys or profile | Re-check `~/.aws/credentials` / env |
| `AccessDenied` on `sts` | Identity lacks `sts:GetCallerIdentity` or SCP denies | Fix IAM/SCP (§3.5) |

## 3. Region, output, and session defaults

- [ ] Set defaults (per profile):
  ```bash
  aws configure set --profile <PROFILE> region <AWS_REGION>
  aws configure set --profile <PROFILE> output json
  # optional: CLI pagination, retries
  aws configure set --profile <PROFILE> cli_pager ""
  ```
- [ ] Verify: `aws configure get region --profile <PROFILE>` → `<AWS_REGION>`
- [ ] For SDK/Lambda parity, also set env when needed:
  `export AWS_PROFILE=<PROFILE> AWS_REGION=<AWS_REGION> AWS_DEFAULT_REGION=<AWS_REGION>`
- [ ] If multiple regions are in scope, record the **default region** and the
      **full region list** in `inventory.md`; every command in §4+ must carry
      explicit `--region <AWS_REGION>` or `--profile <PROFILE>` to avoid
      acting in the wrong region.

## 3.5 Permissions and guardrails (read-first)

Before any write task (§4), confirm the minimum permissions are present.

- [ ] List attached policies for the caller (read):
  `aws iam list-attached-user-policies --user-name <IAM_USER> --profile <PROFILE> 2>&1 | head -n 40`
  `aws iam list-attached-role-policies --role-name <ROLE_NAME> --profile <PROFILE> 2>&1 | head -n 40`
- [ ] Dry-run policy simulation for the exact actions the task needs (read):
  `aws iam simulate-principal-policy --policy-source-arn <PRINCIPAL_ARN> --action-names <ACTION_1> <ACTION_2> --profile <PROFILE>`
- [ ] Check SCPs / Permissions Boundaries if in an Organization (read):
  `aws organizations describe-organization --profile <MGMT_PROFILE> 2>&1 | head -n 20`
  (only with org read access — otherwise note as a constraint).
- [ ] If permissions are insufficient: STOP, record the missing actions in the
      runbook, and ask the operator to grant/assume the scoped policy.
      Never proceed to writes on a best-effort permission set.

## 4. Manage settings and configure things (general task framework)

> The playbook is general — the operator states the task, the agent codifies it
> as gated steps below. Pick the domain that matches the request and follow the
> same read → plan → approved-write → verify → rollback shape. Every
> investigation step's result determines the next step (playbook decision table),
> per Well-Architected.

### 4.0 Task intake (mandatory before any write)

- [ ] Record in `plan.md`: **what** will be configured, **where** (account(s),
      region(s), resource tags/IDs), **why**, **blast radius**, **change window**,
      and **rollback**.
- [ ] Classify each step as **read** or **WRITE**; every WRITE lists the exact
      `aws ...` command (or console path) and its rollback.
- [ ] Operator approves the plan and sets permission mode (**A** or **B**).

### 4.1 IAM

- [ ] Reads: `aws iam list-users --profile <PROFILE>`, `aws iam list-roles --profile <PROFILE>`,
      `aws iam get-policy --policy-arn <POLICY_ARN> --profile <PROFILE>`
- [ ] **WRITE** — example (flagged):
      `aws iam create-user --user-name <NEW_USER> --profile <PROFILE> --region <AWS_REGION>`
      Rollback: `aws iam delete-user --user-name <NEW_USER> --profile <PROFILE>`
- [ ] Verify: `aws iam get-user --user-name <NEW_USER> --profile <PROFILE>`

### 4.2 Networking (VPC, subnets, security groups, NACLs)

- [ ] Reads: `aws ec2 describe-vpcs --profile <PROFILE> --region <AWS_REGION>`,
      `aws ec2 describe-security-groups --profile <PROFILE> --region <AWS_REGION>`
- [ ] **WRITE** — example:
      `aws ec2 create-security-group --group-name <SG_NAME> --description "<DESC>" --vpc-id <VPC_ID> --profile <PROFILE> --region <AWS_REGION>`
      Rollback: `aws ec2 delete-security-group --group-id <SG_ID> --profile <PROFILE> --region <AWS_REGION>`
- [ ] Verify: `aws ec2 describe-security-groups --group-ids <SG_ID> --profile <PROFILE> --region <AWS_REGION>`

### 4.3 Compute / storage / database (EC2, S3, RDS)

- [ ] Reads: `aws ec2 describe-instances --profile <PROFILE> --region <AWS_REGION>`,
      `aws s3 ls --profile <PROFILE>`, `aws s3api get-bucket-policy --bucket <BUCKET> --profile <PROFILE>`,
      `aws rds describe-db-instances --profile <PROFILE> --region <AWS_REGION>`
- [ ] **WRITE** — example:
      `aws s3api put-bucket-versioning --bucket <BUCKET> --versioning-configuration Status=Enabled --profile <PROFILE>`
      Rollback: `aws s3api put-bucket-versioning --bucket <BUCKET> --versioning-configuration Status=Suspended --profile <PROFILE>`
- [ ] Verify: `aws s3api get-bucket-versioning --bucket <BUCKET> --profile <PROFILE>`

### 4.4 Observability and config

- [ ] Reads: `aws cloudwatch describe-alarms --profile <PROFILE> --region <AWS_REGION>`,
      `aws logs describe-log-groups --profile <PROFILE> --region <AWS_REGION>`
- [ ] **WRITE** — example:
      `aws cloudwatch put-metric-alarm --alarm-name <ALARM> ... --profile <PROFILE> --region <AWS_REGION>`
      Rollback: `aws cloudwatch delete-alarms --alarm-names <ALARM> --profile <PROFILE> --region <AWS_REGION>`

### 4.5 Execution logging (append-only)

Every step — read or write — appends a timestamped log file under
`executions/aws-management[-<suffix>]/logs/<ISO8601>-<NN>-<slug>.log` with the
exact command, output (redacted), and result. Never overwrite prior logs.

## 5. Implement playbooks in code and trigger automatically

Per Well-Architected "Implement your playbooks in code and trigger their
execution" — when a management task is **frequent or high-impact**, codify it
and hook it to an event rather than running the CLI by hand.

### 5.1 Codify with AWS-native tooling

| Tool | Use for | Template |
|---|---|---|
| **SSM Automation** | Cross-resource remediation, patching, runbook steps | `templates/ssm-automation.example.yaml` |
| **SSM Run Command** | Ad-hoc or scheduled shell on managed instances | `aws ssm send-command --document-name AWS-RunShellScript ...` |
| **Lambda** | Event-driven logic, API-backed checks | Python/Node handler + EventBridge rule |
| **CloudFormation / CDK / Terraform** | Declarative infrastructure as the playbook artifact | Stack per task |

- [ ] Store the codified playbook (Automation document, Lambda code, stack
      template) in the execution's `logs/` or the playbook's `templates/` if
      it is reusable. Never commit secrets into the document.

### 5.2 Trigger automatically

- [ ] Identify the **monitoring test / event** that fires the playbook
      (e.g. CloudWatch alarm → `ALARM` state, EventBridge rule matching
      `CloudTrail` API call `CreateSecurityGroup`).
- [ ] Implement the trigger:

  **EventBridge → SSM Automation:**
  ```bash
  aws events put-rule --name <RULE_NAME> --event-pattern '{"source":["aws.cloudtrail"],"detail-type":["AWS API Call via CloudTrail"],"detail":{"eventName":["CreateSecurityGroup"]}}' --profile <PROFILE> --region <AWS_REGION>
  aws events put-targets --rule <RULE_NAME> --targets Id=1,Arn=arn:aws:ssm:<AWS_REGION>:<AWS_ACCOUNT_ID>:automation-definition/<DOC_NAME> --profile <PROFILE> --region <AWS_REGION>
  ```

  **CloudWatch alarm → Lambda / SNS:**
  ```bash
  aws cloudwatch put-metric-alarm --alarm-name <ALARM> --metric-name <METRIC> ... --alarm-actions arn:aws:sns:<AWS_REGION>:<AWS_ACCOUNT_ID>:<TOPIC> --profile <PROFILE> --region <AWS_REGION>
  ```

  **EventBridge Scheduler / cron for periodic runs:**
  ```bash
  aws scheduler create-schedule --name <SCHED> --schedule-expression "rate(1 hour)" --target Arn=arn:aws:ssm:... --profile <PROFILE> --region <AWS_REGION>
  ```

- [ ] Verify the trigger: emit a test event or force the alarm to `ALARM`
      (`aws cloudwatch set-alarm-state ...`) and confirm the automation
      execution appears: `aws ssm describe-automation-executions --profile <PROFILE> --region <AWS_REGION>`

- [ ] **WRITE** steps in this section (put-rule, put-targets, create-schedule,
      create-document) are all approval-gated with rollback:
      `aws events remove-targets --rule <RULE_NAME> --ids 1` /
      `aws events delete-rule --name <RULE_NAME>` /
      `aws ssm delete-document --name <DOC_NAME>`.

## 6. Verification

- [ ] CLI: `aws --version` + `aws sts get-caller-identity --profile <PROFILE>` → expected identity
- [ ] Config: `aws configure list --profile <PROFILE>` → expected region/output
- [ ] Resource state: re-run the §4 read for the resource that was changed and
      compare to the expected state recorded in `plan.md`
- [ ] If codified (§5): trigger a dry run and confirm the automation execution
      succeeds; check CloudTrail `LookupEvents` for the expected API calls:
      `aws cloudtrail lookup-events --lookup-attributes AttributeKey=EventName,AttributeValue=<EVENT> --profile <PROFILE> --region <AWS_REGION> 2>&1 | head -n 30`
- [ ] Record the verification output in `logs/` and mark runbook steps `done`.

## 7. Escalation

Per Well-Architected "Document escalation processes". Record the run's
escalation matrix in `plan.md` before any write.

- [ ] **Whom to escalate to** if the active operator cannot identify the source
      of the issue: primary on-call, account owner, network/security team —
      names and contact methods in `inventory.md` (never here).
- [ ] **After what period** to escalate if not yet identified: e.g. 30 min for
      sev-2, 15 min for sev-1 — record the threshold in `plan.md`.
- [ ] **Third parties** and when to involve them: AWS Support (plan level,
      case severity), vendor support — include support contract/case routing
      info if applicable.
- [ ] **Support information required** for third-party escalation: account ID,
      affected resource ARNs, region(s), CloudTrail event IDs, support case
      template — stage in `inventory.md`.
- [ ] **Decision makers** and when to notify: e.g. changes to production VPC,
      IAM, or billing-impacting resources notify `<DECISION_MAKER>` before
      execution — list in `plan.md`.

Escalation itself is not a WRITE to AWS, but the runbook must show
time-stamped escalation attempts in `logs/`.

## 8. Rollback

Every **WRITE** in §2–§5 lists its rollback inline. General rollback order:

1. Remove event triggers created in §5.2 (`remove-targets` → `delete-rule` → `delete-document`)
2. Revert resource configuration to the prior state captured in the pre-write read (§4)
3. For CLI bootstrap: remove the profile or restore the prior `~/.aws/config` backup (the installer backs up to `~/.aws/config.bak` if you copy it first)
4. Verify rollback with the same reads used in verification (§6)

If rollback itself fails: escalate per §7 and record the deviation in
`runbook.md` — never improvise on the live account.

## 9. Close-out

- [ ] Runbook complete (all steps `done` or `blocked` with reason)
- [ ] Findings appended to the execution's `notes.md` (cumulative history —
      do not overwrite; date-header per session)
- [ ] Promotion candidates proposed to the operator → `notes/gotchas.md` or
      `templates/` (operator approves promotion, never mid-run)
- [ ] Secrets: confirm `secrets/` holds only the current variant's material
      (SSO cache pointers, assumed-role session files, key references) and that
      no real credential appears in `plan.md`/`runbook.md`/`logs/` (redact).

---

## Authoring rules

- Steps are copy-paste executable with `<PLACEHOLDER>` tokens; real values
  only in the execution folder.
- Every step that WRITES to the live AWS control plane is flagged **WRITE**
  in bold, with rollback instructions.
- After each run, promote lessons into `notes/` (via the operator, never
  mid-run).
- Keep the playbook general — domain-specific deep dives belong in a new
  playbook that reuses this one's §2 CLI bootstrap.
