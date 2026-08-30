# Runbook: <RUN NAME>

Snapshot of `playbooks/9router/playbook.md` being executed, with real values
filled in. State lives here and in `logs/` — any agent session can resume from
these files alone. This folder is persistent per playbook variant
(`executions/9router[/-<suffix>]/`); subsequent invocations append to it,
never replace it. `logs/` is append-only — each session adds timestamp-prefixed
files (e.g. `logs/2026-08-29T143000-01-discover.log`).

| Field | Value |
|---|---|
| Run | <run name> |
| Playbook | `9router` |
| Execution folder | `executions/9router/` or `executions/9router-<suffix>/` |
| Client | <client> |
| Started | <date> |
| Permission mode | <A / B> (set at plan approval) |
| Mode | <A / B / C / C+Headroom / D> |
| Target | <alias> → <HOST>:<PORT> (and https://<DOMAIN> if exposed) |

## Steps

Status values: `pending` / `in-progress` / `done` / `blocked`.

- [ ] **0. Pre-flight** (read) — status: pending
  - Log: `logs/<timestamp>-00-preflight.log` (skill fetch + notes read + access check)
  - Skill: `logs/<timestamp>-00-skill.md` (fetched live)

- [ ] **1. Discover current state** (read) — status: pending
  - Log: `logs/<timestamp>-01-discover.log`

- [ ] **2. Deployment-mode decision** (ask operator) — status: pending
  - Log: `logs/<timestamp>-02-decision.log`

- [ ] **3. Prepare host** (read) — status: pending
  - Log: `logs/<timestamp>-03-prepare-host.log`

- [ ] **4. Prepare DATA_DIR + secrets** (**WRITE**) — status: pending
  - Log: `logs/<timestamp>-04-secrets.log` (redact SECRET/PASSWORD/KEY/TOKEN)
  - Mode A note: operator confirmation required before writing secrets/env.

- [ ] **5. Install 9Router (mode branch)** (**WRITE**) — status: pending
  - Log: `logs/<timestamp>-05-install.log`
  - Sub-branch: <A npm / B docker run / C compose / C+Headroom / D source>
  - Prev version/tag: <PREV> (for rollback)

- [ ] **6. Dashboard first-login + password rotation** (read + **WRITE**) — status: pending
  - Log: `logs/<timestamp>-06-dashboard.log` (redact password)

- [ ] **7. Harden API key & auth** (**WRITE**) — status: pending
  - Log: `logs/<timestamp>-07-auth.log` (redact keys)
  - `REQUIRE_API_KEY=<true|false>`, `AUTH_COOKIE_SECURE=<true|false>`

- [ ] **8. Token-saver tuning** (read + **WRITE**) — status: pending
  - Log: `logs/<timestamp>-08-tokensaver.log`
  - RTK / Headroom / Ponytail / Caveman settings

- [ ] **9. Reverse proxy + firewall (if exposed)** (**WRITE**) — status: pending
  - Log: `logs/<timestamp>-09-proxy.log`
  - Proxy: <none / Nginx / Traefik / Caddy / Tunnel>

- [ ] **10. Providers & combos** (**WRITE**) — status: pending
  - Log: `logs/<timestamp>-10-providers.log` (redact keys)

- [ ] **11. Verification (skill-based probes)** (read) — status: pending
  - Log: `logs/<timestamp>-11-verify.log`
  - Health + `/v1/models/*` + `chat/completions` (or capability-specific)

- [ ] **12. Operational lifecycle (backup + docs)** (**WRITE** for artifact) — status: pending
  - Log: `logs/<timestamp>-12-ops.log`
  - Backup path: <PATH>

## Deviations

Anything not in the plan → STOP, record here, ask operator. Never improvise.

| Time | Planned step | What happened | Operator decision |
|---|---|---|---|
| | | | |

## Close-out

- [ ] Runbook complete (all steps done or blocked+explained)
- [ ] `scripts/health-check.sh` (or manual §8 probes) passes — health OK, at least one model answers
- [ ] Every **WRITE** has a rollback recorded (secrets `*.prev-*`, `.env.prev-*`, compose prev, image prev tag, DB backup path, proxy/firewall revert)
- [ ] `git status` clean of `executions/` / `*.pem` / `*.key` / `*.crt` / `.tfvars` leaks (AGENTS.md §7)
- [ ] Findings appended to `executions/9router[-<suffix>]/notes.md` (cumulative history — do not overwrite)
- [ ] Promotion candidates proposed to operator (→ playbook `notes/gotchas.md`)
