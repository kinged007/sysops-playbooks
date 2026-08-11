# Remote Docker Workspace Onboarding — Implementation Plan

> **For agentic workers:** this plan is executed step-by-step, task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking. Each task ends by writing
> an audit-log entry in `servers/audit-log.md`.

**Goal:** Connect a live Coder host (on Dokploy) to remote `docker:dind`
daemons over a Tailscale tailnet, using per-remote Coder templates with
mutual-TLS material stored as sensitive template variables. Repeatable for 3–4
remote servers.

**Architecture:** Every remote runs a `docker:dind` container (managed by that
remote's Dokploy) that exposes the Docker API on `2376`, bound ONLY to the
remote's Tailscale IP. The Coder host joins the same tailnet and talks to each
remote over `tcp://<tailscale-ip>:2376` with client certs. One Coder template
per remote holds `docker_host` + cert material as sensitive variables. No Docker
port is exposed on any public interface.

**Tech Stack:** Tailscale (free personal tier), Docker Engine (`docker:dind`),
Dokploy (on each server), Coder (on the host), Terraform (Coder template).

**Roles:**
- **User (by hand):** creates the Tailscale tailnet, approves auth, runs
  `ssh-copy-id`, deploys the compose app via the Dokploy UI, pastes certs into
  Coder template variables.
- **Agent (opencode):** generates all files, installs/configures Tailscale and
  certs over SSH, verifies TLS from the host, builds the Coder template.

---

## Phase 0 — Pre-requisites & what I need from you

Before any SSH work starts, I need:

- [ ] **Tailscale account + tailnet** (https://login.tailscale.com/start).
      Free Personal plan is fine for this (non-commercial, ≤6 users, unlimited
      devices). Tell me whether you'll approve each device with an auth URL
      (interactive) or give me a pre-auth key.
- [ ] **SSH access to the Coder host.** Run on YOUR machine:
      `ssh-copy-id <user>@<host-public-ip>` — then give me `<user>@<host-public-ip>`.
      (You hold the keys; I use your already-authorized key. No passwords to me.)
- [ ] **SSH access to Remote A.** Same as above for the remote's public IP.
- [ ] **Existing local Coder template** (the one that's live today) — paste the
      HCL into this chat, or let me pull it from the host via
      `coder templates list` / `coder templates pull`. I clone its workspace
      resource block so the remote template matches exactly.

Once provided, log them in `servers/inventory.md` and continue.

---

## Phase 1 — Tailscale on the Coder host

**Hostname:** coder-host

- [ ] **Task 1.1: Install Tailscale on the host**

  Over SSH to the host:
  ```bash
  curl -fsSL https://tailscale.com/install.sh | sh
  ```

- [ ] **Task 1.2: Join the tailnet**

  ```bash
  sudo tailscale up
  ```
  Expected: device prints an auth URL → **you** approve it in the browser.
  If you provided a pre-auth key:
  ```bash
  sudo tailscale up --auth-key=<KEY>
  ```

- [ ] **Task 1.3: Record host's Tailscale IP**

  ```bash
  tailscale ip
  ```
  Expected: `100.x.y.z` → record as `Tailscale IP` for coder-host in
  `servers/inventory.md`. Also record the node name with `tailscale status`.

- [ ] **Task 1.4: Audit log**

  `2026-08-07 -- coder-host — Tailscale installed, joined tailnet, IP <ip> — by agent (auth by user)`

---

## Phase 2 — Tailscale on Remote A

**Hostname:** remote-a

- [ ] **Task 2.1: Install Tailscale on the remote**

  Over SSH to remote-a:
  ```bash
  curl -fsSL https://tailscale.com/install.sh | sh
  ```

- [ ] **Task 2.2: Join the tailnet**

  Nodes are NAMED at auth time: the host is `coder-host`; each remote is
  `coder-workspace-01`, `-02`, … (sequential, never reused).

  ```bash
  sudo tailscale up --auth-key=<KEY> --hostname=coder-workspace-01
  ```
  (Using the reusable pre-auth key — no manual approval needed.)

- [ ] **Task 2.3: Record remote's Tailscale IP**

  ```bash
  tailscale ip
  ```
  → record as `Tailscale IP` for remote-a in inventory.

- [ ] **Task 2.4: Verify tailnet connectivity (host → remote)**

  From the host:
  ```bash
  tailscale ping remote-a    # expect: pong from <ip>
  ```

- [ ] **Task 2.5: Audit log**

  `2026-08-07 -- remote-a — Tailscale installed, joined tailnet, IP <ip> — by agent (auth by user)`

---

## Phase 3 — Deploy workspace-docker on Remote A

- [ ] **Task 3.1: Fill in the Tailscale IP in the compose file**

  I edit `compose/workspace-docker.yml` replacing the `100.100.10.20` bind with
  remote-a's actual Tailscale IP. The result is given to you to paste into
  Dokploy.

- [ ] **Task 3.2: You deploy it via Dokploy UI**

  In Dokploy on remote-a: **New service → Compose**, paste the compose, deploy.
  Verify container state:
  ```bash
  docker ps --filter name=workspace-docker
  ```
  Expected: `workspace-docker` Up, port `2376` published on `<ts-ip>:2376`.

  > Troubleshooting: if `docker ps` shows an error like `iptables` / `socket`,
  > the `privileged: true` flag isn't taking effect — check Dokploy's
  > advanced/privileged toggle is on.

- [ ] **Task 3.3: Confirm TLS certs were generated**

  ```bash
  docker exec workspace-docker ls -la /certs/client
  ```
  Expected: `ca.pem cert.pem key.pem`

- [ ] **Task 3.4: Audit log**

  `2026-08-07 -- remote-a — workspace-docker deployed via Dokploy (IP <ts-ip>), TLS certs generated — by user (deploy) / agent (verify)`

---

## Phase 4 — Pull + stage certs on the host

- [ ] **Task 4.1: Create staging dir on the host**

  ```bash
  sudo mkdir -p /root/coder-tls/remote-a && cd /root/coder-tls/remote-a
  ```

- [ ] **Task 4.2: Copy certs from the remote**

  From the host, over SSH to remote-a:
  ```bash
  ssh <user>@remote-a "docker cp workspace-docker:/certs/client/ca.pem -" | sudo tee /root/coder-tls/remote-a/ca.pem > /dev/null
  ssh <user>@remote-a "docker cp workspace-docker:/certs/client/cert.pem -" | sudo tee /root/coder-tls/remote-a/cert.pem > /dev/null
  ssh <user>@remote-a "docker cp workspace-docker:/certs/client/key.pem -" | sudo tee /root/coder-tls/remote-a/key.pem > /dev/null
  sudo chmod 0600 /root/coder-tls/remote-a/key.pem
  ```
  (Alternative if `ssh <user>@remote-a` isn't configured: do the `docker cp` on
  the remote, then `scp` the files to the host.)

- [ ] **Task 4.3: Verify the certs**

  ```bash
  openssl x509 -in /root/coder-tls/remote-a/ca.pem -noout -subject -dates
  ```

- [ ] **Task 4.4: Audit log**

  `2026-08-07 -- remote-a — client certs staged at /root/coder-tls/remote-a/ on host — by agent`

---

## Phase 5 — Test Docker TLS from the host

- [ ] **Task 5.1: Direct TLS test**

  From the host (needs the `docker` CLI installed there, or run via the Coder
  container):
  ```bash
  docker \
    --tlsverify \
    --tlscacert=/root/coder-tls/remote-a/ca.pem \
    --tlscert=/root/coder-tls/remote-a/cert.pem \
    --tlskey=/root/coder-tls/remote-a/key.pem \
    -H=tcp://<remote-a-tailscale-ip>:2376 \
    info
  ```
  Expected: prints server version, storage driver, etc. — no TLS error.

- [ ] **Task 5.2: Audit log**

  `2026-08-07 -- remote-a — TLS connection verified from host (docker info OK) — by agent`

---

## Phase 6 — Create the Coder template for Remote A

**UPDATED approach (2026-08-07):** instead of a bespoke per-remote template, we
adopt the **unified template** from `github.com/<user>/coder-templates`
(docker-devcontainer) as the single source for BOTH local and remote
workspaces. It lives in this repo at `templates/docker-devcontainer/`.

It exposes `docker_host` + sensitive `docker_ca`/`docker_cert`/`docker_key`:
- empty `docker_host` → local Unix socket (workspaces on the Coder host)
- `docker_host=tcp://<ts-ip>:2376` + cert material → remote workspaces

- [ ] **Task 6.1: Get user authenticated** — `coder login` (browser, interactive).
- [ ] **Task 6.2: Push LOCAL template** — same code, empty docker_host.
- [ ] **Task 6.3: Push REMOTE A template** — `coder templates push "docker-devcontainer-remote-a"` with the four variables from `/home/<user>/coder-tls/remote-a/` (see template README for exact command).
- [ ] **Task 6.4: Audit log**

  `2026-08-07 -- coder-host — template "Developer Workspace — Remote A" created, sensitive vars set — by agent`

---

## Phase 7 — Verify a workspace on Remote A

- [ ] **Task 7.1: Create a test workspace**

  In Coder UI, new workspace with the Remote A template. Watch the build logs
  from the host:
  ```bash
  coder logs --follow <workspace>
  ```
  Expected: agent connects, container appears on remote-a:
  ```bash
  docker exec workspace-docker docker ps
  ```

- [ ] **Task 7.2: Destroy the test workspace**

  ```bash
  coder delete <workspace> -y
  ```

- [ ] **Task 7.3: Audit log**

  `2026-08-07 -- remote-a — test workspace built + destroyed successfully — by agent`

---

## Phase 8 — Record & hand off

- [ ] **Task 8.1: Update `servers/inventory.md`** — full per-server records for
      coder-host and remote-a (from Phase 0 input + phases above).
- [ ] **Task 8.2: Update `servers/secrets-pointers.md`** with any deviations.
- [ ] **Task 8.3: Final audit entries** — close out the "Next steps" checklist.

---

## Repeat for Remote B, C, D

Same flow, starting at Phase 2. Only these values change:
- the remote's hostname/Tailscale IP (inventory, compose bind, `docker_host`)
- its own cert set (they are per-daemon and NOT reusable)
- its own template name (`Developer Workspace — Remote B`, …)

The runbook for a single new remote is captured in `docs/runbooks/onboarding-a-new-remote.md`.

---

## Rollback / incident notes

- **Host Tailscale removal:** `sudo tailscale down && sudo tailscale logout`.
- **Remote removal:** `sudo tailscale logout` on the remote, delete the Dokploy
  compose app (this removes the dind container; volumes remain by default).
- **Cert rotation:** delete the `workspace-docker-certs-*` volumes and restart
  the container, OR clear `/root/coder-tls/<remote>/` and re-run Phase 4–6.
- **Free-tier limit watch:** Personal plan = 6 users / unlimited devices / 50
  tagged resources. Fleet of 5 devices fits; do not exceed without checking
  [pricing](https://tailscale.com/pricing).
