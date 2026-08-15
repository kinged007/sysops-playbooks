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
                lesson promotion to the playbook's notes/ (IMPORTANT: DO NOT USE CONFIDENTIAL INFORMATION IN NOTES!)
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
| `docs/` | Plans, specs, design docs | ✅ |

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
