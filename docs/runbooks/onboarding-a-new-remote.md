# Runbook: Onboarding a New Remote Server

Checklist for adding another remote to the Coder fleet. This is the condensed
repeatable version of the full plan (`docs/plans/2026-08-07-remote-docker-onboarding.md`).
Fill in `<REMOTE>` (alias), `<user>`, and IPs as you go. Log each step in
`servers/audit-log.md`.

## 0. Pre-flight
- [ ] Tailscale free tier headroom? (unlimited devices, 6 users — fine unless
      fleet grows)
- [ ] `ssh-copy-id <user>@<public-ip>` done; note alias `<REMOTE>` in
      `servers/inventory.md`.
- [ ] Tailscale tailnet exists (host already joined from first onboarding).
- [ ] **Scoped NOPASSWD sudo for the agent** (root SSH often disabled; agent
      needs passwordless `tailscale` + `docker` — see README "Known issues"):
      ```bash
      echo '<user> ALL=(root) NOPASSWD: /usr/bin/tailscale' | sudo tee /etc/sudoers.d/coder-setup
      echo '<user> ALL=(root) NOPASSWD: /usr/bin/docker'    | sudo tee /etc/sudoers.d/coder-setup-docker
      sudo chmod 0440 /etc/sudoers.d/coder-setup /etc/sudoers.d/coder-setup-docker
      sudo visudo -c
      ```

## 1. Tailscale on the remote
- [ ] `curl -fsSL https://tailscale.com/install.sh | sh`
- [ ] `sudo tailscale up --auth-key=<KEY> --hostname=coder-workspace-NN`
      (name the node at auth time — the host is `coder-host`, remotes are
      `coder-workspace-01`, `-02`, `-03`, …; sequential, never reused)
- [ ] `tailscale ip` → record IP; `tailscale status` → confirm name.
- [ ] From host: `tailscale ping coder-workspace-NN` → expect pong.
- [ ] Add the node to the tailnet ACL (SSH 22 + Docker 2376) — see README
      "Security rules" §3. Do this **before** testing TLS from the host, or the
      2376 TCP check will time out. Apply via the admin console **or** the API
      (POST the full policy with `Content-Type: application/hujson`; an empty
      body resets the policy to allow-all — see AGENTS.md G12).

## 2. Compose + deploy
- [ ] Copy `compose/workspace-docker.yml`, replace the `2376` bind IP with this
      remote's Tailscale IP.
- [ ] **Also update `DOCKER_TLS_SAN` to `IP:<tailscale-ip>`** — without it the
      dind server cert won't cover the tailnet IP and TLS will fail with
      "certificate is valid for ..., not <ip>". (Gotcha found on remote-a.)
- [ ] Deploy via the remote's UI (Coolify or Dokploy). Verify:
      `docker ps --filter name=workspace-docker`.
- [ ] `docker exec workspace-docker ls /certs/client` → `ca.pem cert.pem key.pem`

## 3. Stage certs on the Coder host
- [ ] `sudo mkdir -p /root/coder-tls/<REMOTE>`
- [ ] Copy the three files from the remote (docker cp / scp) into that dir.
- [ ] `sudo chmod 0600 /root/coder-tls/<REMOTE>/key.pem`

## 4. Verify TLS from host
- [ ] `docker --tlsverify --tlscacert=/root/coder-tls/<REMOTE>/ca.pem
      --tlscert=.../cert.pem --tlskey=.../key.pem -H=tcp://<ts-ip>:2376 info`

## 5. Coder template
- [ ] Clone `templates/remote-docker-workspace.hcl` → `templates/<REMOTE>/main.tf`
- [ ] `coder templates push "Developer Workspace — <REMOTE>" --directory templates/<REMOTE>/`
- [ ] In Coder UI set template vars: `docker_host=tcp://<ts-ip>:2376` +
      `docker_ca`/`docker_cert`/`docker_key` = file contents (sensitive).

## 6. Verify
- [ ] Create + destroy a test workspace (watch `coder logs --follow`).
- [ ] Update `servers/inventory.md` + `servers/audit-log.md`.
