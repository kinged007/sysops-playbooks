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

### 1.4 Segregation — reuse within a variant, never across variants/playbooks without cause

- Each playbook variant has **one persistent execution folder**:
  `executions/<playbook>/` by default, or `executions/<playbook>-<suffix>/`
  when the operator provides a custom suffix (e.g. `coder-remote-servers-personal`,
  `coder-remote-servers-company`). All invocations of that variant **share and
  append to the same folder** — this is intentional reuse so secrets, inventory,
  and history stay in one place.
- **Never read from a different playbook's execution folder**, and never read
  from a different suffix variant of the same playbook, unless the current task
  explicitly requires it and the operator approves. Different playbooks and
  different suffixes remain fully segregated.
- **Never copy secrets, host aliases, or inventory between execution folders**
  without explicit operator approval. Each variant's `secrets/` and
  `inventory.md` are authoritative for that variant only.
- Real values for the current variant live ONLY in its execution folder.
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
playbooks/<name>/                  ← committed, static, reusable procedures (the only tracked ops content)
executions/<playbook>/             ← gitignored, persistent per-variant state (plans, secrets, logs, inventory)
executions/<playbook>-<suffix>/    ← same, when a custom suffix is used
```

- **Playbook** = one subject (e.g. `coder-remote-servers`, `wordpress-migration`,
  `mail-server-config`): README, canonical `playbook.md` (placeholders only),
  plan/runbook templates, `templates/` (compose/scaffolds/configs), `scripts/`,
  `notes/` (lessons learned — **read before any run**).
- **Execution folder** = one **persistent** folder per playbook variant, not per
  date. Named `executions/<playbook>/` by default; if the operator supplies a
  custom suffix (client, env, purpose), the folder is
  `executions/<playbook>-<suffix>/` (e.g. `coder-remote-servers-personal`,
  `coder-remote-servers-company`). It is gitignored and contains `plan.md`,
  `runbook.md` (playbook snapshot with real values + step statuses),
  `inventory.md`, `notes.md`, `secrets/`, `logs/` (append-only, one file per
  step/session with timestamp prefix). Subsequent requests for the same playbook
  variant **append to the same folder** — updating logs, extending the runbook,
  and reusing existing `secrets/` and `inventory.md` so the agent never re-asks
  for values already known.
- Multiple variants of the same playbook (different suffixes) are fully
  independent; different playbooks are fully independent. The suffix is the
  only disambiguator within a playbook — use it whenever the same playbook
  targets different clients, environments, or purposes.

Legacy note: older runs used dated folders (`executions/<YYYY-MM-DD>-<client>-<playbook>-<tag>/`).
Those folders remain on disk where they exist but are **not created for new
work**. The agent should still surface them during discovery if they match the
requested playbook, and the operator may manually migrate their contents into the
new persistent folder if desired.

## 3. Execution lifecycle — the seven gates (plus discovery)

Every invocation starts with **discovery of existing state**. The agent must
always do this — it is how follow-up questions and repeat runs regain context
without re-asking for secrets.

```
0. DISCOVER    agent scans executions/ for folders matching <playbook> and
               <playbook>-* (including legacy dated folders containing the
               playbook name); reads their inventory/secrets pointers at a
               high level; presents matches to the operator and asks:
               "Found previous execution(s) XYZ — reuse, or create new variant?"
               Never auto-picks; always confirm.
1. BOOTSTRAP   operator confirms: reuse executions/<playbook>[/-<suffix>]/
               or create a new executions/<playbook>-<suffix>/ folder. If new,
               create the folder and its subfolders (secrets/, logs/).
2. PREP        if new folder: copy plan-template.md + runbook-template.md from
               the playbook; fill in real hosts/IPs/credentials in plan.md.
               if reusing: load existing plan.md / inventory.md / secrets/ /
               notes.md as context; propose an updated plan that builds on them
               (new steps appended, WRITE flags still required). Never overwrite
               existing secrets or logs — append/update only.
3. NOTE-READ   read playbook notes/ (mandatory) + playbook.md; propose the
               plan.md content (step list; every production WRITE flagged)
4. APPROVAL    operator reviews plan.md, sets permission mode (A or B, §1.3),
               approves → plan is frozen; changes require re-approval.
               Record permission mode in plan.md.
5. EXECUTE     execute; tick off runbook.md steps; capture outputs to logs/
               (one file per step, timestamp-prefixed so prior sessions are never
               overwritten: e.g. logs/2026-08-29T1430-01-discover.log). Append,
               never delete. Update inventory.md / secrets/ in place if new
               values are discovered.
6. DEVIATION   anything not in the plan → STOP, ask, get approval; never
               improvise on production
7. CLOSE       mark runbook steps complete/parked; append findings to notes.md
               (cumulative history, newest at top or bottom with date header);
               propose lesson promotion to the playbook's notes/ (IMPORTANT: DO NOT USE CONFIDENTIAL INFORMATION IN NOTES!)
```

Runbook steps carry status (`pending` / `in-progress` / `done` / `blocked`).
Because the execution folder is persistent, any agent session can resume from it
alone — reading `inventory.md`, `secrets/`, `plan.md`, `runbook.md`, and the tail
of `logs/` is sufficient to reconstruct full context.

## 4. Folder discipline & segregation rules

1. `playbooks/` is the only tracked operational content. Every other
   operational file is gitignored.
2. A variant touches ONLY its own execution folder (`executions/<playbook>/` or
   `executions/<playbook>-<suffix>/`). Do not read from other variants or other
   playbooks without explicit operator approval for that read.
3. Credentials are generated per variant and stored in that variant's `secrets/`.
   They are **persistent and reused** across invocations of the same variant —
   update them in place when rotation is needed; do not duplicate them into
   another variant without explicit approval. There is no shared vault across
   playbooks or variants.
4. `logs/` is **append-only**. Each session writes new timestamped files; never
   delete or overwrite prior session logs. The full history of the variant lives
   there.
5. Before any commit: `git status` must show no `executions/`, no `.pem`/
   `.key`/`.tfvars`, no real IPs/hostnames. See §7.
6. Parked or idle variants keep their credentials until the operator deletes the
   folder. Deletion is always operator-initiated.
7. **Naming:** the folder name is exactly the playbook directory name
   (`playbooks/<name>/`), optionally plus `-<suffix>` where `<suffix>` is a
   short, slugified token supplied by the operator (lowercase, hyphen-separated,
   e.g. `personal`, `company`, `prod`, `staging`). Never include dates, client
   names with spaces, or secrets in the folder name.

## 5. Access & credentials

- **Never handle passwords.** The user installs SSH keys and provides
  per-variant credentials. You connect with keys only.
- **Per-variant secrets** live in that variant's `secrets/` folder and are
  **reused across invocations**. When a run needs a new credential (API token,
  pre-auth key), generate it and store it in that same `secrets/` folder,
  updating the existing file or adding a new timestamped one — do not create a
  second execution folder to hold it.
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
- **Promotion channel:** run findings go to the variant's `notes.md`; after the
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
| `executions/<playbook>/` | Persistent per-variant state: plan, runbook, inventory, notes, secrets, logs (append-only) | ❌ gitignored |
| `executions/<playbook>-<suffix>/` | Same, when a custom suffix is used | ❌ gitignored |
| `docs/` | Plans, specs, design docs | ✅ |

## 9. Common questions

- **What if the plan doesn't match reality?** Stop. Record the deviation in
  the runbook, ask the operator, get approval before continuing.
- **Can I reuse a credential from another run?** Credentials are per-variant and
  intentionally reused *within the same execution folder* (`executions/<playbook>[-<suffix>]/secrets/`).
  Do not copy credentials *between* variants or playbooks without explicit
  operator approval. If the credential is stale, rotate it in place inside the
  same variant's `secrets/`.
- **Can I read another execution to understand the client?** Only the execution
  folder for the *current* playbook variant. If you need context from a different
  playbook or a different suffix variant, ask the operator first. At the start
  of any task, the agent must scan `executions/<playbook>*` and confirm with the
  operator whether to reuse the found folder — this is how follow-up questions
  regain context without re-asking for secrets.
- **How do I pick a suffix?** Use a short slug that disambiguates the target:
  `personal` vs `company`, `prod` vs `staging`, client short name, or env.
  Default is no suffix: `executions/<playbook>/`. Examples:
  `executions/coder-remote-servers/` or `executions/coder-remote-servers-company/`.
- **How do logs work with reuse?** `logs/` is append-only. Each session writes
  new files with an ISO-timestamp prefix (e.g. `2026-08-29T143000-01-discover.log`);
  prior logs are never overwritten. To reconstruct history, read the tail of
  `logs/` plus `notes.md` and `plan.md`.
- **What about my old dated execution folders?** They remain on disk and are
  still gitignored. The agent surfaces them during discovery if their name
  contains the playbook. You may leave them as archive or manually migrate
  `inventory.md` / `secrets/` / `logs/` into the new persistent folder.
- **How do I know a write is allowed?** It must be (a) in the approved plan,
  (b) flagged **WRITE** there, and (c) permitted by the run's permission mode
  (per-write confirm or plan-as-approved). All three, always.
- **What does "explicit permission" look like?** A direct operator statement
  approving the specific write, in this session. Silence is not permission.
- **Who deletes executions?** The operator. Never delete execution folders
  yourself.
