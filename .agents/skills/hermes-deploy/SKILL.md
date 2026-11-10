---
name: hermes-deploy
description: Standard Hermes agent deployment on Dokploy (gateway + dashboard, optional web terminal, shared quota'd volume). Use when asked to deploy Hermes, add/remove its terminal, or wire its domains. Does not cover FileBrowser (use the dashboard instead), mail, or non-Dokploy hosts.
---

# Hermes Deploy

> Read `references/lessons.md` before any run. It holds contract details that
> change how you plan (Dokploy API quirks, ttyd flag changes, s6 env behavior).

Risk level: medium - creates publicly reachable services (terminal, dashboard)
on a shared Dokploy host; every exposed service must carry credentials.

## When to use

- Deploy a Hermes agent (gateway + web dashboard) as a Dokploy Compose app
- Enable/disable the optional web terminal for a deployment
- Add/remove dashboard or terminal domains for a deployment
- Not for: FileBrowser (deleted pattern — the dashboard is the file explorer),
  mail stacks, bare-VPS deploys without Dokploy, Hermes version upgrades

## Inputs needed (collect BEFORE planning — never assume)

| Input | Rule |
|---|---|
| Dokploy target | Management host + the remote server record (serverId), project + environment the app belongs to. Resolve from `fleet/`, never invent. |
| Domains | ONLY on explicit request. One per exposed service (dashboard 9119, terminal 7681 if enabled). Never assume hostnames. |
| DNS | Zone + write access for A records pointing at the remote server. Grey-cloud (DNS-only) TTL 300 for LE http-01. |
| Volume quota | Pick ONE and record the choice: **A.** XFS loop image with hard cap in GB (recommended, works on ext4 hosts); **B.** plain Dokploy named volume (no hard cap, monitoring only); **C.** skip limits (document it). |
| Credentials | Generate fresh per deployment, alphanumeric only, store in the run's `secrets/` (mode 600) + Dokploy app env. Dashboard basic-auth user/pass/secret: MANDATORY whenever the dashboard domain exists (fail-closed without). Terminal user/pass: MANDATORY iff terminal enabled. Never print values, never chat them. |
| Hermes image | Default `nousresearch/hermes-agent:stable`; pin a digest for production. |
| Resource limits | Defaults: hermes 2g/1.5 CPU (upstream minimum 1g/1 CPU); terminal 128m/0.25 CPU. Adjust only with reason recorded. |
| Terminal on/off | Default OFF (commented in template). Enabling needs its local image build + domain + creds (procedure §6). |

## Fleet refs needed

Records from `fleet/` this skill reads. Real hosts, IPs, and domains are never
written in this file.

- `fleet/services.yaml`: service record (compose path, health endpoint)
- `fleet/servers.yaml`: Dokploy management host + remote app host (`ops ssh <server>`)
- `fleet/sites.yaml` / `fleet/providers.yaml`: only for the DNS zone used

## Vault entries needed

Names follow `<client>-<provider>-<purpose>`. Values are never printed.
Use via `ops secret run` / `ops secret insert`, never by reading vault files.

- `<client>-dokploy-api`: Dokploy API key (`x-api-key`, minimum scope)
- `<client>-<dns-provider>-dns`: DNS token scoped to the zone (only if this run manages DNS)

## Secure-by-default rules (non-negotiable)

- No `ports:` published. Ever. Traefik (ports 80/443 owner) reaches services
  via Dokploy domains + `expose:` only.
- Every domain gets TLS (letsencrypt) and every exposed service gets auth:
  dashboard basic-auth gate (mandatory — the dashboard refuses to start gated
  without a provider), terminal `ttyd -c user:pass` (mandatory).
- Official `nousresearch/hermes-agent` image with entrypoint UNMODIFIED
  (s6-overlay needs PID 1; overrides break supervision and volume repair).
- Least privilege elsewhere: `cap_drop: ALL` + minimal adds,
  `no-new-privileges`, `pids_limit`, mem/cpu limits on every service.
- One uid owns the shared volume. The agent entrypoint chowns it to its own
  user at boot; any co-writer (terminal) must run as the SAME uid, or writes
  fail. See lessons.
- Dokploy binds must be relative (`../files/...`). Absolute host paths are
  cleaned on redeploy.
- Secrets travel via env files and TLS sessions, never chat, logs, or shell history.

## Procedure

Rules for every step:

- Reads need no flag. Every step that changes a production system is flagged
  **WRITE** and needs approval per the run's permission mode.
- Every destructive **WRITE** is preceded by a **Backup** step.
- Every **WRITE** has a **Rollback** line.
- Every fix is followed by a **Verify** step.
- `ops log` every action not run through `ops` (repo rule 1.8); session start/end entries.
- Validate compose twice before pushing: `docker compose config` AND strict
  YAML parse — compose tolerates duplicate keys (last-wins), Dokploy fails.

### 0. Pre-flight

- [ ] Read `references/lessons.md`
- [ ] Collect all inputs above; hostnames only as given, never invented
- [ ] Resolve fleet records + vault entries; confirm SSH + Dokploy API read-only

### 1. Create the Dokploy Compose app — **WRITE**

- [ ] **WRITE**: `POST /api/compose.create` {name, environmentId,
  composeType `docker-compose`, serverId, composeFile from
  `templates/docker-compose.yml`}, then `compose.update {sourceType: "raw"}`
  (create defaults to github and the first deploy fails without this).
  - Rollback: `compose.delete`
- [ ] Verify: record composeId/appName; app dir exists on the remote

### 2. Disk quota (only for choice A) — **WRITE**

- [ ] **WRITE** (host, sudo): `truncate` fixed-size image, `mkfs.xfs`, `mkdir`
  the app's `files/<name>` dir, `mount -o loop,pquota`, `chown` to the agent
  uid, persist in `/etc/fstab`. Skip the mount if the dir is non-empty.
  - Rollback: unmount + remove image/fstab line (data lost — back up first)
- [ ] Verify: `df -h` shows the cap; `mount | grep` shows `prjquota`

### 3. Secrets — **WRITE**

- [ ] Generate fresh alphanumeric creds; store in run `secrets/` (600)
- [ ] **WRITE**: push full env via `compose.update {env}` (compose file and env
  are SEPARATE stores — updating one never touches the other).
  - Rollback: restore previous env from run secrets + redeploy
- [ ] Verify: fingerprints only, never values

### 4. Deploy — **WRITE**

- [ ] **WRITE**: `compose.deploy`; expect `up -d --build --remove-orphans`
  - Rollback: `compose.stop` / redeploy previous compose file
- [ ] Verify: all containers up; gateway logs show supervised start; shared
  volume writable from every writer as its runtime uid

### 5. DNS (only if managing DNS) — **WRITE**

- [ ] **WRITE**: A records → remote server IP, DNS-only, TTL 300 (must exist
  before LE http-01 runs)
  - Rollback: delete the records
- [ ] Verify: `dig +short` returns the IP

### 6. Domains — **WRITE**

- [ ] **WRITE**: `domain.create` per exposed service (composeId + serviceName +
  internal port, `domainType: compose`, `certificateType: letsencrypt`)
  - Rollback: `domain.delete` (do this BEFORE removing a service — Dokploy
  refuses deploys while a domain points at a missing service)
- [ ] Verify: `https://<host>/health`-equivalent 200, LE cert dates, auth gate
  enforced (401/302 unauthenticated on protected endpoints)

### 7. Terminal enable/disable — **WRITE**

Default OFF. To enable: build the local terminal image ON the target host
(`FROM tsl0922/ttyd:latest` + `apt-get install nano vim`, tag pinned,
`pull_policy: never`), uncomment the service, set `TTYD_*` creds, create its
domain + DNS, redeploy. To disable: delete its domain FIRST, comment the
service, redeploy (`--remove-orphans` drops the container).

- [ ] Verify after either direction: `docker ps` shows the expected set;
  remaining public endpoints re-checked

### 8. Handover

- [ ] Interactive `hermes setup` (operator, with API keys — never via chat)
- [ ] Colleague write test: file created in terminal visible in dashboard and
  vice versa; `.env` readable/writable by both
- [ ] Schedule host-level backup of the XFS image (Dokploy Volume Backups do
  not cover `../files` binds)

## Rollback

Per-step rollback lines above, in reverse order: domain.delete → DNS delete →
compose.stop/redeploy-previous → compose.delete → unmount XFS image. Stop and
ask if data was written after the backup point.

## Verify

- [ ] `docker ps` shows exactly the intended services, all healthy
- [ ] Each public URL: TLS valid, auth gate enforced (401/302 without creds)
- [ ] Shared write both directions as runtime uids; quota `df` shows the cap
- [ ] No secrets in logs, transcripts, or committed files

## Gotchas

- `compose.update {composeFile}` does not touch `env` and vice versa.
- `docker compose config` passes files Dokploy rejects — strict-parse too.
- ttyd ≥1.7: `-w` = cwd, `-W` = writable (readonly default); old `-W /dir` silently breaks auth.
- Dashboard flag comes from process env, not `/opt/data/.env`.
- Details in `references/lessons.md`.

## Files

| Path | Purpose |
|---|---|
| `scripts/` | (none yet — API calls go through `ops secret run` one-liners) |
| `templates/docker-compose.yml` | Canonical compose; terminal commented out by default |
| `templates/.env.example` | Env template with placeholder values only |
| `templates/plan-template.md`, `runbook-template.md` | Planned-work scaffolding |
| `references/lessons.md` | Upstream contracts + run lessons |
