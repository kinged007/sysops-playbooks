# Coder Workspaces — Fleet Management

Runbook, audit log, and config for the Coder workspace fleet: one Coder host
(on Dokploy) orchestrating Docker workspaces on multiple remote servers, each
reached over Tailscale with mutual TLS.

```
                     Coder Host (Dokploy)
                      ┌──────────────┐
                      │    Coder     │
                      └──────┬───────┘
                             │  Docker API over TLS (2376)
                    ┌────────┴────────┐
                    │   Tailscale    │  (free personal tailnet)
                    └────────┬────────┘
                             │
             ┌───────────────┼───────────────┐
             ▼               ▼               ▼
        Remote A         Remote B        Remote C
        workspace-       workspace-      workspace-
        docker (dind)    docker (dind)   docker (dind)
```

- Every remote runs one `docker:dind` container managed by its own Dokploy.
- The Docker API (`2376`) is bound **only** to each remote's Tailscale IP —
  never exposed on a public interface.
- The Coder host connects with per-remote **client certificates**, stored as
  sensitive template variables — one Coder template per remote.

## Status: ⏳ Phase 0 — awaiting pre-requisites from user

See `docs/plans/2026-08-07-remote-docker-onboarding.md`. Current fleet:

| Hostname | Role | Status |
|----------|------|--------|
| (Coder host) | coder-host | LIVE (existing, local Docker) |
| (Remote A) | remote-a | PENDING — needs Tailscale + compose |

## Repo layout

| Path | What it is |
|------|------------|
| `docs/plans/2026-08-07-remote-docker-onboarding.md` | Full onboarding implementation plan |
| `docs/runbooks/onboarding-a-new-remote.md` | Condensed checklist for adding any future remote |
| `compose/workspace-docker.yml` | Canonical dind compose for a remote (bind IP must be set per-remote) |
| `templates/remote-docker-workspace.hcl` | Canonical Coder template (remote host + sensitive TLS vars) |
| `servers/inventory.md` | Fleet records: IPs, endpoints, templates, status |
| `servers/audit-log.md` | Append-only log of everything done to every server |
| `servers/secrets-pointers.md` | Where certs/keys live — pointers only, never the material |

## Security rules

1. **No secrets in git.** `*.pem`, `*.key`, `.tfvars` are gitignored. A tracked
   cert is an incident — rotate it.
2. **Docker API never on the public internet.** `2376` binds to a Tailscale IP.
   Never change the bind to `0.0.0.0` / all interfaces.
3. **Tailscale ACLs.** Restrict tailnet traffic so only the Coder host can reach
   each remote's `2376` (see AGENTS.md §6). Once you add a custom policy
   in the admin console (**Access Controls**), it **replaces** the default
   allow-all. Grants syntax: `src`/`dst` are device selectors, ports go in the
   `ip` capability field (NOT appended to `dst`). WireGuard handshake (41641)
   and control-plane traffic are auto-allowed — no rule needed.

   ```json
   {
     "hosts": {
       "coder-host": "<TAILSCALE_IP_CODER_HOST>",
       "coder-workspace-01": "<TAILSCALE_IP_WORKSPACE_01>"
     },
     "grants": [
       {
         "src": ["autogroup:member"],
         "dst": ["*"],
         "ip": ["tcp:22", "icmp:*"]
       },
       {
         "src": ["coder-host"],
         "dst": ["coder-workspace-01"],
         "ip": ["tcp:2376"]
       }
     ]
   }
   ```

   As each remote joins: add its alias+IP to `hosts`, and add a grant block
   `"src": ["coder-host"] → "dst": ["coder-workspace-NN"]` with `"ip":
   ["tcp:2376"]`. (No wildcard exists for hostnames in selectors — list them
   explicitly.)

   > Replacing the policy also removes Tailscale's default Tailscale-SSH rules
   > (SSH to your own devices). Add an `ssh` block if you rely on Tailscale SSH:
   > ```json
   > "ssh": [
   >   { "action": "accept", "src": ["autogroup:member"], "dst": ["autogroup:self"], "users": ["autogroup:nonroot"] }
   > ]
   > ```
4. Tailscale Personal plan is **non-commercial only**. If use becomes commercial,
   move to paid Tailscale or self-host Headscale.

## Known issues & lessons learned

### Root SSH disabled + password-gated sudo (host server, 2026-08-07)
- **Symptom:** SSH root login is disabled; the sudo user needs a password for
  every privileged command. An agent SSH-ing as that user can't run `sudo`
  non-interactively without the password.
- **Why it matters:** an operator (or agent) needs passwordless access to a
  *small, specific* set of commands — not all of root.
- **Fix used:** scoped `NOPASSWD` sudoers entries for exactly the binaries
  required (`/usr/bin/tailscale` everywhere; `/usr/bin/docker` on remotes for
  cert extraction). Blanket `ALL=(ALL) NOPASSWD` was NOT used.
- **Commands (one-time, run by the user):**
  ```bash
  # on EVERY server:
  echo '<user> ALL=(root) NOPASSWD: /usr/bin/tailscale' | sudo tee /etc/sudoers.d/coder-setup
  sudo chmod 0440 /etc/sudoers.d/coder-setup
  sudo visudo -c          # must print "parsed OK"

  # on REMOTE servers only (docker needed to extract dind client certs):
  echo '<user> ALL=(root) NOPASSWD: /usr/bin/docker' | sudo tee /etc/sudoers.d/coder-setup-docker
  sudo chmod 0440 /etc/sudoers.d/coder-setup-docker
  ```
- **Cleanup:** after onboarding, delete `/etc/sudoers.d/coder-setup*` to
  re-lock. (This is a homelab setup; per-command NOPASSWD is an acceptable
  trade-off. For higher-security environments, prefer a service account with
  per-command sudo or a full configuration-management approach.)
- **Key design note:** the Coder container is managed by Dokploy — an agent
  never needs Docker API access on the Coder host. Template deploys go over
  Coder's HTTP API, and remote TLS checks use only the `docker` CLI (no local
  daemon socket). So only Tailscale sudo is required on the host.

### Never expose the Docker daemon on TCP
- Exposing `2376` (or `2375`) on all interfaces = root-equivalent remote
  access. Always bind to the Tailscale IP and keep TLS mandatory. See
  `AGENTS.md` §7.

### Remote management UIs differ (Dokploy vs Coolify)
- The Coder host runs Dokploy. Remote A runs **Coolify**. Both deploy
  docker-compose apps, so the workflow is identical from our side — just the
  UI changes. Check `servers/inventory.md` for which UI each server uses.

## Quick reference

- Install Tailscale: `curl -fsSL https://tailscale.com/install.sh | sh`
- Host-side TLS test to a remote:
  ```
  docker --tlsverify --tlscacert=/root/coder-tls/<remote>/ca.pem \
    --tlscert=/root/coder-tls/<remote>/cert.pem \
    --tlskey=/root/coder-tls/<remote>/key.pem \
    -H=tcp://<tailscale-ip>:2376 info
  ```
- Push a Coder template: `coder templates push "<name>" --directory <dir>`
