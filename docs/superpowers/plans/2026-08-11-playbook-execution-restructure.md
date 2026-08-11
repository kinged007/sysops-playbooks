# Playbook/Execution Repo Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure this repo from a single-purpose Coder-fleet guide into a general sysops playbook repository: static per-subject `playbooks/`, gitignored self-contained `executions/`, a rewritten general AGENTS.md admin guide, and a strict production-safety doctrine.

**Architecture:** Two-tier model. `playbooks/<name>/` holds committed, static, reusable procedures (README, playbook.md, plan/runbook templates, scripts, templates, notes). `executions/<YYYY-MM-DD>-<client>-<playbook>-<tag>/` holds every per-run artifact (plan, runbook snapshot, inventory, notes, secrets, logs) and is fully gitignored. Existing Coder content migrates into `playbooks/coder-remote-servers/`; existing gitignored fleet data folds into a handover execution; the old dated plan is archived into a historical execution.

**Tech Stack:** Git, Markdown, PowerShell (host OS), bash scripts (migrated as-is). No build system, no tests — verification is `git status`/`git ls-files` checks and secret scans.

**Spec:** `docs/superpowers/specs/2026-08-11-playbook-execution-restructure-design.md` (approved).

**Environment notes:**
- Host OS is Windows; shell is PowerShell 5.1. Use `git mv` for tracked files, `Move-Item` for gitignored files.
- `.gitattributes` enforces LF — `git add` normalizes automatically; never hand-edit line endings.
- The committed AGENTS.md has uncommitted local edits (G2 netdata correction, 2026-08-11). Those edits MUST be preserved — they migrate into `playbooks/coder-remote-servers/notes/gotchas.md` (Task 5). The working-tree AGENTS.md is discarded by Task 7's rewrite, so capture the G2 text before then.
- Do NOT commit anything the user didn't approve. Each task's commit includes ONLY the files listed in that task.

---

### Task 1: Ignore `executions/` in .gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add the executions ignore rule**

Edit `.gitignore`, in the "Private fleet operations" section (line 9-11), add:

```gitignore
# ---- Private fleet operations (real hostnames/IPs) ----
servers/

# ---- Per-run execution folders (self-contained: plans, secrets, logs) ----
executions/
```

- [ ] **Step 2: Verify the ignore works**

Run: `git check-ignore -v executions/2026-08-11-test-run/plan.md`
Expected: output matching `.gitignore` with the `executions/` rule. (File need not exist — `check-ignore` works on paths.)

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore executions/ per-run folders"
```

---

### Task 2: Fold existing fleet data into a handover execution

**Files:**
- Create: `executions/2026-08-11-coder-fleet-current-state/README.md`
- Move: `secrets/*` → `executions/2026-08-11-coder-fleet-current-state/secrets/`
- Move: `servers/*` → `executions/2026-08-11-coder-fleet-current-state/` (as `inventory.md`, `audit-log.md`, `secrets-pointers.md`)
- Create: `executions/2026-08-11-coder-fleet-current-state/logs/.gitkeep`
- Delete: `secrets/`, `servers/` (top-level folders)

This preserves the fleet's operational memory under the new per-run-secrets rule. Real values stay in this folder; nothing here can ever be committed.

- [ ] **Step 1: Confirm nothing sensitive is tracked**

Run:
```bash
git ls-files | Select-String -Pattern 'secrets|servers'
```
Expected: NO output. (If output appears, stop — something sensitive is tracked and must be handled before moving on.)

- [ ] **Step 2: Create the execution folder structure**

Run:
```powershell
New-Item -ItemType Directory -Path "executions\2026-08-11-coder-fleet-current-state\secrets", "executions\2026-08-11-coder-fleet-current-state\logs" -Force | Out-Null
New-Item -ItemType File -Path "executions\2026-08-11-coder-fleet-current-state\logs\.gitkeep" -Force | Out-Null
```

- [ ] **Step 3: Move the fleet data**

Run:
```powershell
Move-Item -Path secrets\* -Destination executions\2026-08-11-coder-fleet-current-state\secrets\
Move-Item -Path servers\audit-log.md -Destination executions\2026-08-11-coder-fleet-current-state\audit-log.md
Move-Item -Path servers\inventory.md -Destination executions\2026-08-11-coder-fleet-current-state\inventory.md
Move-Item -Path servers\secrets-pointers.md -Destination executions\2026-08-11-coder-fleet-current-state\secrets-pointers.md
```

- [ ] **Step 4: Write the handover README**

Create `executions/2026-08-11-coder-fleet-current-state/README.md`:

```markdown
# Handover: Coder Fleet Current State (2026-08-11)

Historical snapshot folded in during the playbook/execution repo restructure.

- `inventory.md` — fleet servers (real hostnames/IPs) as of restructure date
- `audit-log.md` — chronological ops log prior to restructure
- `secrets-pointers.md` — where certs/keys lived prior to restructure
- `secrets/` — pre-auth keys, API keys, private fleet-data map
- `logs/` — reserved for future transcripts

Under the new model every future run gets its own execution folder; this one
exists only to preserve pre-restructure state. Delete it once the content has
been carried into newer runs or is deemed obsolete.
```

- [ ] **Step 5: Remove empty top-level folders**

Run:
```powershell
Remove-Item -Path servers, secrets -Recurse -Force
```
Verify: `Test-Path servers`, `Test-Path secrets` → both False.

- [ ] **Step 6: Verify nothing sensitive is left tracked and nothing untracked leaked**

Run:
```bash
git status --short
git ls-files | Select-String -Pattern 'secrets|servers'
```
Expected: git status shows only the previous task's commit (clean working tree); `git ls-files` output is empty. All moved files are under `executions/` which is ignored.

- [ ] **Step 7: Commit (nothing staged — this task only moves gitignored files; commit is empty-record)**

```bash
git commit --allow-empty -m "chore: fold pre-restructure fleet data into handover execution"
```

---

### Task 3: Archive the historical onboarding plan

**Files:**
- Create: `executions/2026-08-07-coder-fleet-initial-setup/README.md`
- Move: `docs/plans/2026-08-07-remote-docker-onboarding.md` → `executions/2026-08-07-coder-fleet-initial-setup/plan.md`

- [ ] **Step 1: Create the execution folder**

Run: `New-Item -ItemType Directory -Path "executions\2026-08-07-coder-fleet-initial-setup" -Force | Out-Null`

- [ ] **Step 2: Move the plan (tracked file — use git mv so history is preserved)**

Run: `git mv docs/plans/2026-08-07-remote-docker-onboarding.md executions/2026-08-07-coder-fleet-initial-setup/plan.md`

- [ ] **Step 3: Write the archive README**

Create `executions/2026-08-07-coder-fleet-initial-setup/README.md`:

```markdown
# Execution: Coder Fleet Initial Setup (2026-08-07)

Historical run — the original end-to-end onboarding plan for the Coder
remote-workspace fleet. Archived here during the playbook/execution repo
restructure (2026-08-11). Superseded by `playbooks/coder-remote-servers/`.

- `plan.md` — the original dated implementation plan (placeholder-safe)
```

- [ ] **Step 4: Remove the now-empty docs/plans tree**

Run:
```powershell
Remove-Item -Path docs\plans -Recurse -Force
```
(If `docs/plans` contains other files, move them first per the design; at restructure time only the one plan exists.)

- [ ] **Step 5: Verify + commit**

Run: `git status --short`
Expected: `D  docs/plans/2026-08-07-remote-docker-onboarding.md` (renamed to ignored `executions/...`). The move must NOT leave a tracked copy behind: `git ls-files | Select-String 'remote-docker-onboarding'` → empty.

Note: `git mv` has already staged the rename. Do NOT use `git add -A` here — the working tree contains an unrelated uncommitted `AGENTS.md` edit (pre-existing G2 netdata note) that must NOT enter this commit.

```bash
git commit -m "chore: archive historical onboarding plan into gitignored execution"
```

---

### Task 4: Create the `_playbook-template` skeleton

**Files:**
- Create: `playbooks/_playbook-template/README.md`
- Create: `playbooks/_playbook-template/playbook.md`
- Create: `playbooks/_playbook-template/plan-template.md`
- Create: `playbooks/_playbook-template/runbook-template.md`
- Create: `playbooks/_playbook-template/templates/.gitkeep`
- Create: `playbooks/_playbook-template/scripts/.gitkeep`
- Create: `playbooks/_playbook-template/notes/.gitkeep`

- [ ] **Step 1: Create folders**

Run:
```powershell
New-Item -ItemType Directory -Path "playbooks\_playbook-template\templates", "playbooks\_playbook-template\scripts", "playbooks\_playbook-template\notes" -Force | Out-Null
New-Item -ItemType File -Path "playbooks\_playbook-template\templates\.gitkeep", "playbooks\_playbook-template\scripts\.gitkeep", "playbooks\_playbook-template\notes\.gitkeep" -Force | Out-Null
```

- [ ] **Step 2: Write `README.md`**

```markdown
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
```

- [ ] **Step 3: Write `playbook.md`**

```markdown
# Playbook: <PLAYBOOK NAME> — Procedure

Canonical steps for a run. **Placeholders only** — never real IPs, hostnames,
usernames, or credentials. Real values go in the execution's `plan.md`.

## 0. Pre-flight
- [ ] Confirm prerequisites (see README)
- [ ] Read `notes/` for lessons that affect this run

## 1. <Step group>
- [ ] <Step description> — `command with <PLACEHOLDER>`

## 2. <Step group>
- [ ] <Step description>

## N. Verification
- [ ] <How to confirm the run succeeded>
- [ ] <How to roll back>

---

## Authoring rules
- Steps must be copy-paste executable with placeholders filled.
- Flag every step that WRITES to a production system with **WRITE** in bold
  (e.g. `- [ ] **WRITE** install package X on <host>`). Reads need no flag.
- Add rollback instructions for every write step.
- After each run, promote lessons into `notes/` (via the operator, never
  mid-run).
```

- [ ] **Step 4: Write `plan-template.md`**

```markdown
# Plan: <RUN NAME>

| Field | Value |
|---|---|
| Client | <client> |
| Playbook | `<playbook-name>` |
| Date | <YYYY-MM-DD> |
| Execution folder | `executions/<YYYY-MM-DD>-<client>-<playbook>-<tag>/` |
| Permission mode | **UNSET — set by operator at approval** (A: per-write confirm / B: plan-as-approved) |
| Status | draft → approved → executing → closed |

## Servers involved (THIS run only)
| Alias (ssh config) | Role | Purpose | Access key |
|---|---|---|---|
| <alias> | <source/prod/dest> | <what it does in this run> | `~/.ssh/<key>` |

## Credentials / secrets (THIS run only)
<Files in `secrets/` of this execution folder; never inline values here>

## Steps
Numbered steps mirroring `runbook.md`, with **WRITE** flags:

1. <step> (read)
2. <step> (**WRITE** — describe exactly what changes on which host)
3. ...

## Risk assessment
<What could go wrong; what is the blast radius; rollback plan>

## Approval
- [ ] Operator reviewed plan and set permission mode: <A or B>
- [ ] Operator approved execution on <date>
```

- [ ] **Step 5: Write `runbook-template.md`**

```markdown
# Runbook: <RUN NAME>

Snapshot of `playbooks/<name>/playbook.md` being executed, with real values
filled in. State lives here and in `logs/` — a run can be resumed by any agent
session from these files alone.

| Field | Value |
|---|---|
| Run | <run name> |
| Playbook | <playbook-name> |
| Client | <client> |
| Started | <date> |
| Permission mode | <A / B> (set at plan approval) |

## Steps
Status values: `pending` / `in-progress` / `done` / `blocked`.

- [ ] **1. <step>** (read) — status: pending
  - Log: `logs/01-<short-name>.log`
- [ ] **2. <step>** (**WRITE**) — status: pending
  - Log: `logs/02-<short-name>.log`
  - Mode A note: operator confirmation required before running.

## Deviations
<Anything not in the plan → STOP, record here, ask operator. Never improvise.>

## Close-out
- [ ] Runbook complete (all steps done or blocked+explained)
- [ ] Findings recorded in `notes.md`
- [ ] Promotion candidates proposed to operator (→ playbook `notes/`)
```

- [ ] **Step 6: Verify + commit**

Run: `git status --short` — only the new template files untracked.

```bash
git add playbooks/_playbook-template
git commit -m "feat: add playbook authoring template skeleton"
```

---

### Task 5: Create `playbooks/coder-remote-servers/` (migrate + write)

**Files:**
- Create: `playbooks/coder-remote-servers/README.md`
- Create: `playbooks/coder-remote-servers/playbook.md`
- Create: `playbooks/coder-remote-servers/plan-template.md`
- Create: `playbooks/coder-remote-servers/runbook-template.md`
- Create: `playbooks/coder-remote-servers/notes/gotchas.md`
- Create: `playbooks/coder-remote-servers/notes/wildcard-subdomains.md`
- Move: `compose/workspace-docker.yml` → `playbooks/coder-remote-servers/templates/workspace-docker.yml`
- Move: `templates/docker-devcontainer/` → `playbooks/coder-remote-servers/templates/docker-devcontainer/`
- Move: `templates/remote-docker-workspace.hcl` → `playbooks/coder-remote-servers/templates/remote-docker-workspace.hcl`
- Move: `scripts/setup-wildcard-cert.sh` → `playbooks/coder-remote-servers/scripts/setup-wildcard-cert.sh`
- Delete: `docs/runbooks/` (content absorbed into playbook.md + notes)
- Delete: top-level `compose/`, `scripts/` (after moves)

- [ ] **Step 1: Create the playbook folder structure**

Run:
```powershell
New-Item -ItemType Directory -Path "playbooks\coder-remote-servers\templates", "playbooks\coder-remote-servers\scripts", "playbooks\coder-remote-servers\notes" -Force | Out-Null
```

- [ ] **Step 2: Migrate tracked files with git mv**

Run:
```bash
git mv compose/workspace-docker.yml playbooks/coder-remote-servers/templates/workspace-docker.yml
git mv templates/docker-devcontainer playbooks/coder-remote-servers/templates/docker-devcontainer
git mv templates/remote-docker-workspace.hcl playbooks/coder-remote-servers/templates/remote-docker-workspace.hcl
git mv scripts/setup-wildcard-cert.sh playbooks/coder-remote-servers/scripts/setup-wildcard-cert.sh
```

- [ ] **Step 3: Update the moved `workspace-docker.yml` comment to reference its new path**

Edit `playbooks/coder-remote-servers/templates/workspace-docker.yml`: any comment that references `compose/` or `AGENTS.md` sections should reference the playbook path instead (`playbooks/coder-remote-servers/...`). Read the file first; update only references, keep the compose content identical.

- [ ] **Step 4: Write `README.md`**

```markdown
# Playbook: Coder Remote Servers

> **Agent: read `notes/` BEFORE any run.** The notes contain lessons learned
> from previous executions (G1–G12 + wildcard subdomain traps) that may change
> how you plan. Never skip this.

## What it does
Provisions Coder development workspaces across multiple remote servers from a
single Coder host — private Tailscale tailnet, mutual TLS on every Docker API
connection (2376 bound to tailnet IPs only). Includes onboarding new remotes,
Coder template pushes, and exposing workspace app previews via wildcard
subdomains.

## When to use it
- Onboarding a new remote workspace server into the fleet
- Pushing/updating the unified Coder template for a target (local or remote)
- Setting up or repairing wildcard app subdomains (`.coder.<domain>` previews)
- TLS/ACL troubleshooting for remote daemons

## Prerequisites
- Coder host (Dokploy-managed) with `coder` CLI installed and authenticated
- Tailscale account + tailnet (free Personal: ≤6 users, unlimited devices)
- Key-based SSH access to the Coder host and each remote
- Management UI (Dokploy or Coolify) on each remote, or direct compose access

## Risk level
**medium** — touches production Docker daemons (via TLS) and live Coder
configuration. Never binds 2376 to a public interface; that is an incident.

## Servers involved
One Coder host + one or more remotes (each running a `docker:dind` container).
Real values live in the execution's `inventory.md`, never here.

## Files
| Path | Purpose |
|---|---|
| `playbook.md` | Canonical procedure (placeholders only) |
| `plan-template.md` | Copied to `executions/<run>/plan.md` |
| `runbook-template.md` | Copied to `executions/<run>/runbook.md` |
| `templates/workspace-docker.yml` | Canonical dind compose (bind IP + `DOCKER_TLS_SAN` = placeholders) |
| `templates/docker-devcontainer/` | Unified Coder template (local + remote via vars) |
| `templates/remote-docker-workspace.hcl` | Simpler standalone remote template (code-server only) |
| `scripts/setup-wildcard-cert.sh` | acme.sh + Cloudflare DNS-01 wildcard cert installer |
| `notes/gotchas.md` | G1–G12: real pitfalls hit on the fleet, with fixes |
| `notes/wildcard-subdomains.md` | Wildcard preview routing/TLS traps and fixes |
```

- [ ] **Step 5: Write `playbook.md` — composed from committed AGENTS.md + old runbooks**

The canonical procedure is composed from the COMMITTED version of the old
AGENTS.md (git show HEAD:AGENTS.md — NOT the working tree, which has the
G2 netdata edit; that edit goes to notes in Step 7). Copy the following
sections verbatim (they are already placeholder-safe), renaming headings:

| Old location (committed AGENTS.md) | New home in `playbook.md` |
|---|---|
| §1 "What this system is" (incl. diagram, design decisions, topology table) | "## 1. System overview" |
| §2 "Roles & division of labor" (roles table) | "## 2. Roles" |
| §3 "Pre-requisites" (items 1–5, incl. No-VPN alternative) | "## 3. Prerequisites" |
| §4 "Access & privilege model" (scoped NOPASSWD sudoers) | "## 4. Access & privilege" |
| §5 "The process — end to end" (Phases 0–8) | "## 5. Procedure — Phases 0–8" (checkboxes) |
| §6 "Tailscale ACL / grants" | "## 6. Tailscale ACL / grants" |
| §7 "Security invariants" | "## 7. Security invariants" |
| §10 "Gotchas & learnings" | REMOVED from playbook.md — lives in `notes/gotchas.md` (Step 7). Insert a pointer: "See `notes/gotchas.md` for G1–G12." |
| §12 "Common questions" | "## 8. Common questions" |
| `docs/runbooks/onboarding-a-new-remote.md` (full text) | "## 9. Quick run: onboarding a new remote" (condensed checklist, updated: `compose/workspace-docker.yml` → `templates/workspace-docker.yml`; `servers/inventory.md` → the execution's `inventory.md`) |
| `docs/runbooks/wildcard-app-subdomains.md` (full text) | "## 10. Wildcard app subdomains" (verbatim, plus pointer to `notes/wildcard-subdomains.md`) |

Also update §5 Phase 6 to reference the playbook's template path
(`playbooks/coder-remote-servers/templates/docker-devcontainer`) and Phase 8 to
record into the execution folder instead of `servers/` + `secrets/`.
Old §8 "Secrets & fleet data" and §9 "Local SSH setup" and §11 "File map" are
NOT copied — they are generalized into the new AGENTS.md (Task 7); add a line
in §5 Phase 0: "Repo-level rules: see AGENTS.md".

- [ ] **Step 6: Write `plan-template.md` and `runbook-template.md`**

Copy `playbooks/_playbook-template/plan-template.md` and
`playbooks/_playbook-template/runbook-template.md` verbatim to
`playbooks/coder-remote-servers/` (same filenames). No changes needed —
they are playbook-agnostic.

- [ ] **Step 7: Write `notes/gotchas.md`**

```markdown
# Gotchas (G1–G12) — Coder Remote Servers

Real pitfalls hit on the fleet, with fixes. Read BEFORE any run (mandated by
README).

**G1 — dind server cert doesn't include the tailnet IP.**
Symptom: `tls: failed to verify certificate: x509: certificate is valid for
10.0.2.2, 127.0.0.1, ::1, not <ts-ip>`. Cause: dind generates its server cert
SAN at startup from container-detected IPs unless told otherwise. **Fix:
`DOCKER_TLS_SAN: "IP:<ts-ip>"` in the compose, then recreate the container.**
Certs regenerate on every start (CA persists in its volume).

**G2 — broken third-party dnf/yum repos break installers.**
On Rocky/CentOS, a stale repo (we hit netdata) 404s during metadata refresh and
kills `curl | sh` installers. Fix: disable it first:
```bash
dnf config-manager --set-disabled netdata netdata-repoconfig
dnf install -y --disablerepo='netdata*' tailscale
```
**Netdata root cause (corrected 2026-08-11):** the 404 was NOT a dead repo —
netdata's `.repo` file uses `$releasever_major` in `baseurl`, which dnf 4.14 on
Rocky 9 does not substitute (built-in only since dnf 4.21), so the literal
`$releasever_major` went to the server. Fix that survives repo-file updates:
```bash
echo 9 > /etc/dnf/vars/releasever_major   # generic dnf var substitution, works in 4.14
dnf config-manager --set-enabled netdata netdata-repoconfig
```
(`--setopt=releasever_major=9` does NOT work — only the vars file does.)
Also: Tailscale's `install.sh` may die before adding the repo on RHEL-family.
Add it manually: `dnf config-manager --add-repo https://pkgs.tailscale.com/stable/rhel/9/tailscale.repo`.

**G3 — Coolify renames the container.**
Coolify deploys the compose with a suffixed container name
(`workspace-docker-dgkmftx...`). Any `docker exec workspace-docker` fails with
"no such container". Use `name=$(docker ps -aq --filter name=workspace-docker | head -1)`.

**G4 — port conflict on redeploy.**
If the agent creates/validates the container via SSH and the user then redeploys
via Coolify, the port `ts-ip:2376` is still held → "port is already allocated".
**Always remove the agent-created container before a Coolify redeploy**
(`docker rm -f <name>`), then have the user redeploy so Coolify owns it.

**G5 — `/root` is often unreadable for the sudo user.**
Staging certs under `/root/coder-tls/` fails with "Permission denied" for user.
Use a user-writable path: `/home/<user>/coder-tls/<remote>/`.

**G6 — `coder templates push --var` breaks with multiline PEM.**
`--var docker_ca="$(cat ca.pem)"` mangles multi-line content through the shell.
Use `--variables-file <file>`. **Coder's variables file is YAML, not tfvars:**
```yaml
docker_host: tcp://<ts-ip>:2376
docker_ca: |
  -----BEGIN CERTIFICATE-----
  ...
  -----END CERTIFICATE-----
```

**G7 — Windows PowerShell array interpolation joins with SPACES.**
Building the YAML in PowerShell via `"$(...)"` collapsed PEM lines into one
space-separated line → "tls: failed to find any PEM data". Fix: build a
`List[string]` and `-join "`n"` (real newlines), then write the file.

**G8 — Tailscale policy: grants syntax ≠ legacy ACL syntax.**
`autogroup:member:41641` fails with "host name must not contain colon". In
`grants`, ports live in the `ip` field (`tcp:22`, `icmp:*`), never appended to
`dst`. 41641 is auto-allowed. Replacing the policy drops default SSH — re-add if needed.

**G12 — Tailscale API ACL updates: use POST, never an empty body.**
Updating the policy file via the API is `POST /api/v2/tailnet/<tailnet>/acl`
(`PUT` returns 405). **A POST with an empty/malformed body can reset the policy
to the default allow-all** — we hit this live and had to restore immediately.
Always: GET the current policy, edit it, and POST the full content back with
`Content-Type: application/hujson`; verify with a follow-up GET. Scope required
is `policy_file`. Fetch the tailnet name from the host's
`tailscale status --json` (`MagicDNSSuffix`, e.g. `tailcXXXX.ts.net`).
The key can be stored in gitignored `executions/<run>/secrets/`.

**G9 — Coder CLI session expires.** `coder whoami` → "signed out". User runs
`coder login <url>` (browser). The CLI URL is stored in the coderv2 config; check
it before blaming a wrong URL.

**G10 — dind image tag.** Use a **current** `docker:dind` tag (e.g. `29.7.1-dind`).
Older pins in docs (e.g. `29.6.2-dind`) may not exist — verify against Docker Hub
before deploying.

**G11 — Windows → remote script execution.**
Piping a script into `ssh ... bash -s` from PowerShell re-encodes newlines to
CRLF and breaks bash. Write the script with LF endings and `scp` it, then run
`bash /tmp/script.sh`. Also: PowerShell interpolates `$()` in double-quoted ssh
commands **locally** — use single quotes or script files for anything with
`$(...)`.
```

- [ ] **Step 8: Write `notes/wildcard-subdomains.md`**

```markdown
# Wildcard App Subdomains — Traps and Fixes

Lessons from `docs/runbooks/wildcard-app-subdomains.md` (now §10 of
playbook.md). Read BEFORE any run that touches Coder app previews.

- **Trap 1 — Dokploy UI cannot express wildcard rules.** Dokploy wraps domains
  as `Host(\`...\`)`, and Traefik's `Host()` is exact-match. `Host(\`*.coder.<domain>\`)`
  never matches. Fix: `HostRegexp` router via compose labels
  (`traefik.http.routers.coder-wildcard-websecure.rule=HostRegexp(\`^[a-z0-9-]+\.coder\.<domain>$\`)`,
  entrypoint websecure, `tls=true` not a certresolver, service port 7080).
- **Trap 2 — no wildcard cert possible via Dokploy's ACME.** Dokploy's
  letsencrypt resolver is HTTP-01 only; wildcards require DNS-01. Fix:
  `scripts/setup-wildcard-cert.sh` (acme.sh + Cloudflare DNS-01) installing
  into `/etc/dokploy/traefik/dynamic/certificates/` — Traefik's file provider
  picks it up, no reload.
- **Trap 3 — DNS split is intentional.** `coder.<domain>` → Cloudflare proxied;
  `*.coder.<domain>` → origin IP DNS-only (Cloudflare can't proxy wildcards and
  can't issue certs for two-level wildcards). Do not "fix" this.
- **Trap 4 — token renewal.** LE certs renew at ~60 days; acme.sh uses its
  cached `CF_Token`. Rotating the token means updating BOTH
  `/home/<user>/.cf-token` and `/root/.acme.sh/...conf`. Use non-IP-restricted
  tokens with longest TTL.
- **Verification:** `openssl s_client -connect <ip>:443 -servername anything.coder.<domain>`
  must show the wildcard SAN; `curl -sk` the preview URL must NOT return
  Traefik's "404 page not found".
```

- [ ] **Step 9: Remove old top-level locations**

Run:
```powershell
Remove-Item -Path docs\runbooks, compose, scripts -Recurse -Force
```
Verify: `Test-Path docs\runbooks`, `Test-Path compose`, `Test-Path scripts` → all False.
Confirm no tracked file is lost: `git status --short` must show only renames
(deletions with corresponding additions), no plain `D` entries.

- [ ] **Step 10: Verify + commit**

Run: `git status --short`
Expected: renames of the 5 migrated paths + `docs/runbooks/` deletions + new
playbook files untracked. `git ls-files | Select-String 'compose/|scripts/|docs/runbooks|templates/'`
must show only the NEW paths.

Note: do NOT use `git add -A` — the unrelated uncommitted `AGENTS.md` edit must
not enter this commit. The `git mv` renames are already staged; stage the new
playbook files and the `docs/runbooks/` deletions explicitly:

```bash
git add playbooks/coder-remote-servers docs/runbooks
git commit -m "feat: migrate Coder content into playbooks/coder-remote-servers"
```

---

### Task 6: Scaffold `wordpress-migration` and `mail-server-config` playbooks

**Files:**
- Create: `playbooks/wordpress-migration/README.md`, `playbook.md`, `plan-template.md`, `runbook-template.md`, `templates/.gitkeep`, `scripts/.gitkeep`, `notes/.gitkeep`
- Create: `playbooks/mail-server-config/README.md`, `playbook.md`, `plan-template.md`, `runbook-template.md`, `templates/.gitkeep`, `scripts/.gitkeep`, `notes/.gitkeep`

- [ ] **Step 1: Scaffold `wordpress-migration`**

Copy the `_playbook-template` files into the new playbook folder, then write
the playbook-specific `README.md` and `playbook.md` (full content below).
`plan-template.md` and `runbook-template.md` copy verbatim from
`_playbook-template` (they are playbook-agnostic).

Run:
```powershell
$tpl = "playbooks\_playbook-template"
$dst = "playbooks\wordpress-migration"
New-Item -ItemType Directory -Path "$dst\templates", "$dst\scripts", "$dst\notes" -Force | Out-Null
Copy-Item "$tpl\plan-template.md", "$tpl\runbook-template.md" -Destination $dst
New-Item -ItemType File -Path "$dst\templates\.gitkeep", "$dst\scripts\.gitkeep", "$dst\notes\.gitkeep" -Force | Out-Null
```

Then write `README.md` (full content):

```markdown
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
```

And `playbook.md` (full content):

```markdown
# Playbook: WordPress Migration — Procedure

Canonical steps for a run. **Placeholders only** — never real IPs, hostnames,
usernames, or credentials. Real values go in the execution's `plan.md`.

## 0. Pre-flight
- [ ] Confirm prerequisites (see README)
- [ ] Read `notes/` for lessons that affect this run
- [ ] Confirm with operator: source is read-only for this run

## 1. Inventory source
- [ ] Record WP version, PHP version, plugins/themes list — `wp core version` on <SOURCE_ALIAS>

## 2. Backup (files + DB)
- [ ] **WRITE** — take full file backup on <SOURCE_ALIAS> (tar to <BACKUP_PATH>)
- [ ] **WRITE** — dump database on <SOURCE_ALIAS> (read-only mysqldump; SELECT only)
- [ ] Verify backup integrity (sizes, checksums) before proceeding

## 3. Transfer
- [ ] **WRITE** — copy backup from <SOURCE_ALIAS> to <DEST_ALIAS> (scp/rsync over SSH keys)
- [ ] Verify transfer (checksums match)

## 4. Restore + reconfigure
- [ ] **WRITE** — extract files on <DEST_ALIAS>
- [ ] **WRITE** — import database on <DEST_ALIAS>
- [ ] **WRITE** — update `wp-config.php` (DB creds, URLs) on <DEST_ALIAS>
- [ ] **WRITE** — apply per-server config (php-fpm, nginx/vhost) on <DEST_ALIAS>

## 5. Verification
- [ ] Site loads on <DEST_ALIAS> (curl homepage, wp-admin login)
- [ ] Check DB consistency (wp core verify-checksums / db check)
- [ ] Confirm with operator before any further production writes

## 6. Rollback
- [ ] If verification fails: point DNS back to <SOURCE_ALIAS>, no changes there were made
- [ ] Document what remains to be cleaned up (backup files) in `notes.md`

---

## Authoring rules
- Steps must be copy-paste executable with placeholders filled.
- Flag every step that WRITES to a production system with **WRITE** in bold.
- Add rollback instructions for every write step.
- After each run, promote lessons into `notes/` (via the operator, never mid-run).
```

- [ ] **Step 2: Scaffold `mail-server-config`**

Run:
```powershell
$tpl = "playbooks\_playbook-template"
$dst = "playbooks\mail-server-config"
New-Item -ItemType Directory -Path "$dst\templates", "$dst\scripts", "$dst\notes" -Force | Out-Null
Copy-Item "$tpl\plan-template.md", "$tpl\runbook-template.md" -Destination $dst
New-Item -ItemType File -Path "$dst\templates\.gitkeep", "$dst\scripts\.gitkeep", "$dst\notes\.gitkeep" -Force | Out-Null
```

Then write `README.md` (full content):

```markdown
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
```

And `playbook.md` (full content):

```markdown
# Playbook: Mail Server Configuration — Procedure

Canonical steps for a run. **Placeholders only** — never real IPs, hostnames,
usernames, or credentials. Real values go in the execution's `plan.md`.

## 0. Pre-flight
- [ ] Confirm prerequisites (see README)
- [ ] Read `notes/` for lessons that affect this run

## 1. Baseline inventory
- [ ] Record MTA, version, current config state on <MAIL_ALIAS> (reads only)

## 2. DNS records (SPF/DKIM/DMARC)
- [ ] **WRITE** — add/update SPF record (TXT at <DOMAIN>) — via DNS provider
- [ ] **WRITE** — add/update DKIM record (TXT at <DKIM_SELECTOR>._domainkey.<DOMAIN>) — via DNS provider
- [ ] **WRITE** — add/update DMARC record (TXT at _dmarc.<DOMAIN>) — via DNS provider
- [ ] Verify DNS propagation (dig / nslookup) before MTA changes

## 3. MTA configuration
- [ ] **WRITE** — apply MTA config changes on <MAIL_ALIAS> (main.cf / postfix, exim conf, etc.)
- [ ] **WRITE** — restart mail service on <MAIL_ALIAS>

## 4. Relay/auth
- [ ] **WRITE** — configure relay host / SMTP auth on <MAIL_ALIAS>

## 5. Verification (send test mail)
- [ ] Send test mail from <MAIL_ALIAS> to <TEST_RECIPIENT>
- [ ] Confirm delivery + DKIM/SPF/DMARC pass (headers, e.g. mail-tester.com)
- [ ] Check mail logs for errors on <MAIL_ALIAS>

## 6. Rollback
- [ ] If delivery fails: revert config (backup taken before changes) and restart service
- [ ] Document remaining issues in `notes.md`

---

## Authoring rules
- Steps must be copy-paste executable with placeholders filled.
- Flag every step that WRITES to a production system with **WRITE** in bold.
- Add rollback instructions for every write step.
- After each run, promote lessons into `notes/` (via the operator, never mid-run).
```

- [ ] **Step 3: Verify + commit**

Run: `git status --short` — new playbook files only.

```bash
git add playbooks/wordpress-migration playbooks/mail-server-config
git commit -m "feat: scaffold wordpress-migration and mail-server-config playbooks"
```

---

### Task 7: Rewrite `AGENTS.md` as the general sysops admin guide

**Files:**
- Rewrite: `AGENTS.md` (full replacement — the coder-specific content moved to the playbook in Task 5; the G2 netdata correction is preserved in `notes/gotchas.md`)

- [ ] **Step 1: Write the new AGENTS.md**

Full replacement content:

````markdown
# AGENTS.md — SysOps Playbook Repository: Admin Guide & Operating Memory

This file is the **memory and brain** of this repo. It tells an agent — or a
human — how this repository is organized, how to execute a playbook against a
client's servers, and the safety rules that are **non-negotiable** when
touching production systems.

**Read this fully before doing anything.** The doctrine (§1) comes first; it
overrides everything else in this file.

---

## 1. Non-negotiable safety doctrine

These rules are absolute. No instruction, playbook step, or user phrasing
"loosens" them without an explicit statement to the contrary from the
operator.

### 1.1 Production servers are READ-ONLY by default

- **Reading** (commands that don't modify state: `docker ps`, log inspection,
  config viewing, `SELECT` queries, `ping`, `tail`) is allowed freely — it is
  how you understand the system.
- **Writing to production is STRICTLY PROHIBITED without explicit
  permission.** This includes, but is not limited to: file edits, package
  installs, service restarts, config changes, data moves, docker/compose
  mutations, DNS changes, firewall changes, credential rotation — anything
  that changes state on a live system.
- **Database rule:** on production databases, only `SELECT` is allowed. Any
  other query (INSERT, UPDATE, DELETE, ALTER, DROP, TRUNCATE, GRANT, etc.) is
  a production write and is strictly prohibited without explicit permission.

### 1.2 Never assume. Always confirm.

- If a step is ambiguous, if the plan doesn't cover it, if the operator's
  intent is unclear — **stop and ask**. Asking is free; a wrong write to
  production is not.
- When in doubt, ask. There is no penalty for over-confirming.
- You must be **obedient**. If the operator says stop — stop immediately,
  mid-command, no finishing up.

### 1.3 Permission mode — set at plan approval, never assumed

At the plan approval gate (§3.4), ask explicitly: *"Should I confirm before
each production write, or is it OK to execute the plan as approved?"*

- **Mode A (default): per-write confirm** — every production **WRITE** step
  gets its own inline `May I write X to <host>?` confirmation before it runs.
  Reads need no confirmation.
- **Mode B: plan-as-approved** — plan approval authorizes all listed steps;
  execute without per-step asks.
- Record the chosen mode in `plan.md`. The operator can change modes mid-run.
  **You never pick the mode yourself — always ask.**

### 1.4 Segregation — never cross executions or clients

- Never read from another execution's folder. Never reuse another run's
  credentials, host aliases, or outputs. Never copy files between executions.
- Real values for the current run live ONLY in the current execution folder.
- Never improvise steps not in the approved plan. Deviations require a stop,
  a question, and operator approval before continuing.

### 1.5 Secrets handling

- Secrets never appear in committed files, shell history, or logs. No
  passwords in SSH command lines — keys and scoped tokens only.
- Sensitive data transfers between servers use scoped methods (SCP/rsync over
  SSH keys, encrypted archives). Never pipe credentials through shell.
- Playbooks contain placeholders only. Real values belong in `executions/`.

### 1.6 Playbooks are read-only during a run

Corrections go to the run's `notes.md`. Promotion into the playbook happens
after the run, with operator approval. Never edit `playbooks/` mid-run.

---

## 2. What this repo is

```
playbooks/<name>/   ← committed, static, reusable procedures (the only tracked ops content)
executions/<run>/   ← gitignored, self-contained per-run state (plans, secrets, logs, inventory)
```

- **Playbook** = one subject (e.g. `coder-remote-servers`, `wordpress-migration`,
  `mail-server-config`): README, canonical `playbook.md` (placeholders only),
  plan/runbook templates, `templates/` (compose/scaffolds/configs), `scripts/`,
  `notes/` (lessons learned — **read before any run**).
- **Execution** = one run of a playbook against one client's servers. Named
  `executions/<YYYY-MM-DD>-<client>-<playbook>-<short-tag>/`, fully
  gitignored, containing `plan.md`, `runbook.md` (playbook snapshot with real
  values + step statuses), `inventory.md`, `notes.md`, `secrets/`, `logs/`.
- Executions of different playbooks (or clients) are fully independent; a
  playbook may be executed any number of times, each with its own folder.

## 3. Execution lifecycle — the seven gates

```
1. BOOTSTRAP    operator creates executions/<run>/ folder
2. PREP         copy plan-template.md + runbook-template.md from the playbook;
                fill in real hosts/IPs/credentials in plan.md
3. NOTE-READ    read playbook notes/ (mandatory) + playbook.md; propose the
                plan.md content (step list; every production WRITE flagged)
4. APPROVAL     operator reviews plan.md, sets permission mode (A or B, §1.3),
                approves → plan is frozen; changes require re-approval
5. EXECUTE      execute; tick off runbook.md steps; capture outputs to logs/
                (one file per step)
6. DEVIATION    anything not in the plan → STOP, ask, get approval; never
                improvise on production
7. CLOSE        mark runbook complete/parked; findings → notes.md; propose
                lesson promotion to the playbook's notes/
```

Runbook steps carry status (`pending` / `in-progress` / `done` / `blocked`).
Any agent session can resume a run from the execution folder alone.

## 4. Folder discipline & segregation rules

1. `playbooks/` is the only tracked operational content. Every other
   operational file is gitignored.
2. A run touches ONLY its own execution folder. No reads from other runs.
3. Credentials are generated per run and stored in that run's `secrets/`.
   There is no shared vault.
4. Before any commit: `git status` must show no `executions/`, no `.pem`/
   `.key`/`.tfvars`, no real IPs/hostnames. See §7.
5. Parked runs keep their credentials until the operator deletes the folder.

## 5. Access & credentials

- **Never handle passwords.** The user installs SSH keys and provides
  per-run credentials. You connect with keys only.
- **Per-run secrets** live in the run's `secrets/` folder. When a run needs a
  credential (API token, pre-auth key), generate it fresh for that run.
- **SSH config aliases** (user-managed, `~/.ssh/config`) are the interface:
  the plan references `<alias>`, never raw hostnames.
- Scoped NOPASSWD sudoers (exactly the binaries a playbook needs, nothing
  more) are the privilege model where root SSH is unavailable:
  ```bash
  echo '<user> ALL=(root) NOPASSWD: /usr/bin/tailscale' | sudo tee /etc/sudoers.d/playbook-setup
  sudo chmod 0440 /etc/sudoers.d/playbook-setup
  sudo visudo -c        # must print "parsed OK"
  ```
  Removable after the run.

## 6. Authoring & maintaining playbooks

- To create a playbook, copy `playbooks/_playbook-template/` (it documents
  the required files and rules).
- Every playbook README must state: what it does, when to use it,
  prerequisites, **risk level**, servers involved, and the mandatory line
  "Agent: read `notes/` BEFORE any run."
- `playbook.md` steps: copy-paste executable with `<PLACEHOLDER>` tokens;
  every step that writes to production flagged **WRITE**; rollback steps for
  every write.
- **Promotion channel:** run findings go to the run's `notes.md`; after the
  run, propose promotion into the playbook's `notes/` (and rarely its
  `playbook.md`). The operator approves promotions.

## 7. Committing rules (repo is publishable)

**Committed** (safe for a public repo): `README.md`, `AGENTS.md`,
`playbooks/`, `docs/`, `.gitignore`, `.gitattributes` — placeholders only,
zero real IPs/hostnames/usernames/domains/keys.

**NEVER committed:** anything under `executions/`, `secrets/`, `servers/`
(if they exist), any `*.pem`, `*.key`, `*.tfvars`, `.env` anywhere.

Before every commit, run:
```powershell
git status                       # executions/ and secrets must NOT appear
git ls-files --cached --others --exclude-standard | ForEach-Object { if (Test-Path $_) {
  $c = Get-Content $_ -Raw
  if ($c -match 'tskey-|BEGIN (CERTIFICATE|PRIVATE|RSA)') { Write-Output "LEAK: $_" }
}}
```
Any hit is an incident: unstage, move the file into an execution folder,
rotate the credential if it was ever committed.

## 8. File map

| Path | Purpose | Committed? |
|---|---|---|
| `AGENTS.md` | This guide | ✅ |
| `README.md` | Public overview | ✅ |
| `playbooks/_playbook-template/` | Skeleton for new playbooks | ✅ |
| `playbooks/<name>/` | One folder per subject: README, playbook.md, plan/runbook templates, templates/, scripts/, notes/ | ✅ |
| `executions/<run>/` | Per-run state: plan, runbook, inventory, notes, secrets, logs | ❌ gitignored |
| `docs/` | Plans, specs, runbook archives | ✅ |

## 9. Common questions

- **What if the plan doesn't match reality?** Stop. Record the deviation in
  the runbook, ask the operator, get approval before continuing.
- **Can I reuse a credential from another run?** No. Generate fresh, store in
  this run's `secrets/`.
- **Can I read another execution to understand the client?** No. If context
  is missing, ask the operator.
- **How do I know a write is allowed?** It must be (a) in the approved plan,
  (b) flagged **WRITE** there, and (c) permitted by the run's permission mode
  (per-write confirm or plan-as-approved). All three, always.
- **What does "explicit permission" look like?** A direct operator statement
  approving the specific write, in this session. Silence is not permission.
- **Who deletes executions?** The operator. Never delete execution folders
  yourself.
````

- [ ] **Step 2: Verify the doctrine is intact**

Run:
```powershell
$c = Get-Content AGENTS.md -Raw
$checks = @('READ-ONLY','SELECT','permission mode','Never assume','segregation','promotion')
foreach ($ch in $checks) { if ($c -notmatch $ch) { Write-Output "MISSING: $ch" } }
```
Expected: no "MISSING" output. (Some checks are case-insensitive substring
matches — the doc contains all of them.)

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs: rewrite AGENTS.md as general sysops admin guide"
```

---

### Task 8: Rewrite `README.md` as the general ops-repo overview

**Files:**
- Rewrite: `README.md` (full replacement)

- [ ] **Step 1: Write the new README.md**

```markdown
# SysOps Playbook Repository

A publishable repository of **reusable server procedures** ("playbooks") —
Coder remote workspace fleets, WordPress migrations, mail server
configuration, and more — each executed against real servers with strictly
segregated, per-run state.

```
playbooks/              ← static, reusable procedures (committed)
  _playbook-template/      skeleton for new playbooks
  coder-remote-servers/    Coder workspaces across remote servers (Tailscale + mTLS)
  wordpress-migration/     scaffolded
  mail-server-config/      scaffolded
executions/             ← per-run state (GITIGNORED)
  <date>-<client>-<playbook>-<tag>/
    plan.md  runbook.md  inventory.md  notes.md  secrets/  logs/
```

## How it works

- **Playbooks are static.** Each playbook is one subject: a canonical
  procedure (`playbook.md`, placeholders only), templates, scripts, and a
  `notes/` folder of lessons learned. Playbooks are never edited during a run.
- **Executions are self-contained.** Every run gets one gitignored folder
  holding its plan, runbook (the playbook being executed, with real values and
  step statuses), inventory of the servers it touches, credentials, and logs.
  Runs for different clients never mix.
- **Safety doctrine.** Production servers are read-only by default; every
  write — including any non-`SELECT` database query — requires explicit
  permission; permission mode (per-write confirm or plan-as-approved) is set
  at plan approval; agents never assume, always confirm, and are strictly
  obedient. See `AGENTS.md` §1.

## Starting a run

1. Create `executions/<YYYY-MM-DD>-<client>-<playbook>-<tag>/`
2. Copy the playbook's `plan-template.md` + `runbook-template.md` into it;
   fill in real hosts and credentials
3. Read the playbook's `notes/` (mandatory)
4. Present the plan for approval; the operator sets the permission mode
5. Execute against the runbook, capture logs, record findings
6. Close out: mark steps done, write `notes.md`, propose lesson promotion

## Repository layout

| Path | What it is |
|------|------------|
| `playbooks/_playbook-template/` | Skeleton for authoring new playbooks |
| `playbooks/coder-remote-servers/` | Coder workspace fleet: remote dind daemons, Tailscale, mTLS, wildcard app subdomains |
| `playbooks/wordpress-migration/` | (scaffolded) WordPress site migration between servers |
| `playbooks/mail-server-config/` | (scaffolded) mail server configuration |
| `executions/` | **Private** per-run state — gitignored, never committed |
| `AGENTS.md` | Full admin guide: doctrine, lifecycle, folder discipline |
| `docs/` | Plans, specs, design docs |

## Security rules

1. **Never commit execution state.** `executions/` is gitignored; real IPs,
   hostnames, and credentials live only there.
2. **Placeholders only in committed files.** Real values use
   `<PLACEHOLDER>` tokens.
3. **Production is read-only by default.** Writes require explicit permission
   (see `AGENTS.md` §1).
4. **Per-run secrets.** Credentials are generated per run, never shared
   across runs.

## Contributing a playbook

Copy `playbooks/_playbook-template/`, fill in README (what/why/risk level),
`playbook.md` (procedure with `WRITE` flags), templates, scripts. Promote
lessons from past runs into `notes/`. See `AGENTS.md` §6.
```

- [ ] **Step 2: Verify no stale Coder-fleet-only claims remain**

Run:
```powershell
$c = Get-Content README.md -Raw
$checks = @('docker:dind','Tailscale','executions','playbook','GITIGNORED')
foreach ($ch in $checks) { if ($c -notmatch $ch) { Write-Output "MISSING: $ch" } }
```
Expected: no "MISSING" output.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README as general ops-playbook overview"
```

---

### Task 9: Final verification

**Files:** none modified

- [ ] **Step 1: Full secret + tracking audit**

Run:
```bash
git status
git ls-files
```
Expected: working tree clean; tracked files = `.gitattributes`, `.gitignore`,
`AGENTS.md`, `README.md`, `playbooks/**`, `docs/**` only. NO `executions/`,
`secrets/`, `servers/`, no `.pem`/`.key`/`.tfvars`.

- [ ] **Step 2: Identifier scan over all tracked files**

Run:
```powershell
$files = git ls-files
foreach ($f in $files) { if (Test-Path $f) {
  $c = Get-Content $f -Raw
  if ($c -match '100\.81\.162|207\.180\.216|tskey-|BEGIN (CERTIFICATE|PRIVATE|RSA)') { Write-Output "LEAK: $f" }
}}
```
Expected: no output.

- [ ] **Step 3: Structure check**

Run:
```powershell
$expected = @(
  'playbooks\_playbook-template\README.md',
  'playbooks\coder-remote-servers\README.md',
  'playbooks\coder-remote-servers\playbook.md',
  'playbooks\coder-remote-servers\plan-template.md',
  'playbooks\coder-remote-servers\runbook-template.md',
  'playbooks\coder-remote-servers\notes\gotchas.md',
  'playbooks\coder-remote-servers\notes\wildcard-subdomains.md',
  'playbooks\coder-remote-servers\templates\workspace-docker.yml',
  'playbooks\coder-remote-servers\scripts\setup-wildcard-cert.sh',
  'playbooks\wordpress-migration\README.md',
  'playbooks\mail-server-config\README.md'
)
foreach ($e in $expected) { if (-not (Test-Path $e)) { Write-Output "MISSING: $e" } }
```
Expected: no output.

- [ ] **Step 4: Verify gitignored folders hold the moved data**

Run:
```powershell
Get-ChildItem executions\2026-08-11-coder-fleet-current-state -Recurse -File | Select-Object -ExpandProperty FullName
Get-ChildItem executions\2026-08-07-coder-fleet-initial-setup -File | Select-Object -ExpandProperty Name
```
Expected: handover contains README.md, audit-log.md, inventory.md,
secrets-pointers.md, secrets/*.txt + private-fleet-data.md, logs/.gitkeep;
archive contains README.md + plan.md.

- [ ] **Step 5: Final commit (if anything uncommitted remains)**

Run: `git status --short` — if any untracked/modified files remain, commit them
with an appropriate message. Expected final state: clean working tree.
````
