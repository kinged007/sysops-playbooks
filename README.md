# Coder Remote Workspace Fleet

Provision Coder development workspaces across **multiple remote servers** from a
single Coder host — secured by a private Tailscale tailnet and mutual TLS on
every Docker API connection.

```
                     Coder Host
                      ┌──────────────┐
                      │    Coder     │   ← one server, hosts the control plane
                      └──────┬───────┘
                             │  Docker API over TLS (tcp://…:2376)
                    ┌────────┴────────┐
                    │   Tailscale    │   ← private tailnet (free Personal tier)
                    └────────┬────────┘
                             │
             ┌───────────────┼───────────────┐
             ▼               ▼               ▼
        Remote A         Remote B        Remote C      ← each runs docker:dind
        workspace-       workspace-      workspace-
        docker (dind)    docker (dind)   docker (dind)
```

## What this is for

Coder normally provisions workspaces on the machine that runs it. This repo
lets you spread that workload across any number of remote VPS/servers, each
contributing compute and isolation, without ever exposing the Docker API to the
public internet.

Use it when you want:

- **More capacity** — add VPSes as your developer count grows; the Coder host
  stays small.
- **Separation** — developer workspaces run on dedicated remote servers, not on
  the box that runs Coder/Dokploy/your other apps.
- **A consistent workspace** — every developer gets the same Docker-in-Docker
  devcontainer experience regardless of which server it lands on.
- **Security by default** — no public ports, no shared daemons, per-remote
  client certificates.

## Problems it solves

| Problem | How this repo solves it |
|---|---|
| Coder needs Docker on the same box | Workspaces are provisioned on remote daemons over the tailnet |
| Exposing Docker on `tcp://0.0.0.0` is a root-level risk | `2376` binds **only** to each remote's Tailscale IP; public port is verified unreachable |
| Docker API without TLS is plaintext root | Mutual TLS everywhere; dind auto-generates a per-remote CA + client certs |
| Reusing certs across servers | Each remote's daemon generates its own CA/client pair; not reusable |
| One-off template per server | A **single unified template** serves both local and remote mode via template variables |
| Manually keeping secrets in the repo | Cert/key material lives only in Coder's encrypted template variable store; repo stores placeholders |
| Repeating the same setup per server | A condensed onboarding runbook (`docs/runbooks/`) makes each new remote a checklist |

## How it works

- Each **remote** runs one `docker:dind` container (deployed via its own Dokploy
  or Coolify UI), which exposes the Docker API on `2376` bound to that remote's
  Tailscale IP.
- The **Coder host** joins the same tailnet and connects to each remote with
  `tcp://<tailscale-ip>:2376`, using per-remote client certificates.
- One **Coder template** (`templates/docker-devcontainer/`) is pushed once per
  target: empty `docker_host` → local Unix socket; `docker_host` + TLS material
  → remote. The cert PEMs are passed as **sensitive template variables** — never
  as files, never in the repo.
- A **Tailscale ACL** restricts the tailnet so only the Coder host can reach
  each remote's `2376`.

## Repository layout

| Path | What it is |
|------|------------|
| `compose/workspace-docker.yml` | Canonical `docker:dind` compose for a remote (set the bind IP + `DOCKER_TLS_SAN` to the remote's Tailscale IP) |
| `templates/docker-devcontainer/` | Unified Coder template: local *and* remote mode via variables (`main.tf`, scripts, README) |
| `templates/remote-docker-workspace.hcl` | Simpler standalone remote template (code-server only) |
| `docs/plans/2026-08-07-remote-docker-onboarding.md` | Full end-to-end implementation plan |
| `docs/runbooks/onboarding-a-new-remote.md` | Condensed checklist for adding a remote |
| `docs/runbooks/wildcard-app-subdomains.md` | Exposing Coder app previews via Dokploy/Traefik wildcard subdomains |
| `servers/` | **Private** fleet records (inventory, audit log, secrets pointers) — gitignored |
| `secrets/` | **Private** pre-auth keys / API keys — gitignored |

## Prerequisites

1. **A Coder host** (any deployment, e.g. Dokploy-managed) with the `coder` CLI
   installed and authenticated on your admin machine.
2. **A Tailscale account + tailnet** (free Personal tier covers ≤6 users,
   unlimited devices, non-commercial only).
3. **SSH access** (key-based) to the Coder host and to each remote you want to
   add.
4. **A management UI on each remote** (Dokploy or Coolify) to deploy the dind
   compose — or run it directly with `docker compose up -d`.

## Quick start

### 1. Join the tailnet

```bash
# On the Coder host and on every remote:
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --auth-key=<KEY> --hostname=<node-name>   # or interactive auth URL
```

Name nodes consistently: `coder-host`, `coder-workspace-01`, `coder-workspace-02`, …

### 2. Deploy a dind daemon on a remote

Copy `compose/workspace-docker.yml`, replace the placeholder Tailscale IP in
both the port bind **and** `DOCKER_TLS_SAN`, then deploy via the remote's UI:

```yaml
environment:
  DOCKER_TLS_SAN: "IP:100.100.10.20"      # ← remote's Tailscale IP
ports:
  - "100.100.10.20:2376:2376"             # ← binds to tailnet IP ONLY
```

> `DOCKER_TLS_SAN` is mandatory. Without it, dind's server cert won't cover the
> tailnet IP and the Coder host will reject the TLS connection.

### 3. Verify TLS from the Coder host

Extract the daemon's client certs and test:

```bash
docker exec workspace-docker cat /certs/client/ca.pem
docker exec workspace-docker cat /certs/client/cert.pem
docker exec workspace-docker cat /certs/client/key.pem

docker --tlsverify \
  --tlscacert=ca.pem --tlscert=cert.pem --tlskey=key.pem \
  -H=tcp://<tailscale-ip>:2376 info
```

### 4. Push the template for this remote

```sh
# LOCAL workspaces (Coder host's own daemon) — leave docker_host empty:
coder templates push dev-workspace ./templates/docker-devcontainer

# REMOTE workspaces — variables file is YAML (PEM contents, block scalars):
coder templates push dev-workspace-remote-a ./templates/docker-devcontainer \
  --variables-file remote-a-vars.yaml
```

```yaml
# remote-a-vars.yaml
docker_host: tcp://<tailscale-ip>:2376
docker_ca: |
  -----BEGIN CERTIFICATE-----
  ...
docker_cert: |
  -----BEGIN CERTIFICATE-----
  ...
docker_key: |
  -----BEGIN PRIVATE KEY-----
  ...
```

### 5. Create a workspace

```sh
coder create my-workspace --template dev-workspace-remote-a --yes \
  --parameter repo_url= --parameter new_branch=
```

Workspace containers land inside the remote's dind daemon — verify with
`docker exec <workspace-docker> docker ps` on the remote.

## Security model

1. **Docker API never on a public interface.** `2376` binds to the Tailscale IP
   only. A bare `:2376` or `0.0.0.0` is a security incident.
2. **Mutual TLS is mandatory.** dind auto-generates a per-remote CA + client
   cert; Coder connects with `--tlsverify`.
3. **No secrets in git.** `*.pem`, `*.key`, `.tfvars`, `secrets/`, and `servers/`
   are all gitignored. A tracked cert is an incident — rotate it.
4. **Tailscale ACL restricts traffic.** Only the Coder host may reach each
   remote's `2376`. See `AGENTS.md` §6 for the exact grants syntax.
5. **Agent/operator never handles passwords.** Only keys and pre-auth tokens.

## Common gotchas

| Symptom | Cause | Fix |
|---|---|---|
| `certificate is valid for … not <ip>` | `DOCKER_TLS_SAN` missing | Set `DOCKER_TLS_SAN: "IP:<ts-ip>"`, recreate container |
| `tls: failed to find any PEM data` | PEM newlines collapsed when passing via shell/PowerShell | Use a `--variables-file` (YAML), not `--var`; keep real newlines |
| `port is already allocated` on redeploy | manual container still holds the port | `docker rm -f` the manual one, then redeploy from the UI |
| 2376 reachable from public internet | bind widened to all interfaces | Rebind to `<ts-ip>:2376`; check with `Test-NetConnection <public-ip> -Port 2376` |
| Tailscale policy rejected / 405 | old `ACL` syntax or wrong method | Use `grants` syntax; API is `POST` with the full policy body |

## Fleet records

Real IPs, hostnames, and pointers to where certs live are kept in gitignored
files (`servers/inventory.md`, `servers/audit-log.md`, `servers/secrets-pointers.md`)
so this repo stays publishable. Create equivalents in your own deployment and
never commit them.

---

See `AGENTS.md` for the full operating guide, and
`docs/runbooks/onboarding-a-new-remote.md` for the per-remote checklist.
