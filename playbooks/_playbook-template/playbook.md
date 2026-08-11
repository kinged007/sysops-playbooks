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
