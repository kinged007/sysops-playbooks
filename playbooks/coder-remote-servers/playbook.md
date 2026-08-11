# Playbook: Coder Remote Servers — Procedure

Canonical steps for a run. **Placeholders only** — never real IPs, hostnames,
usernames, or credentials. Real values go in the execution's `plan.md`.
Repo-level rules (folder discipline, secrets, committing): see `AGENTS.md`.

---

## 1. System overview

```
                     Coder Host (Dokploy)
                      ┌──────────────┐
                      │    Coder     │
                      └──────┬───────┘
                             │  Docker API over TLS (2376)
                    ┌────────┴────────┐
                    │   Tailscale    │  (private tailnet)
                    └────────┬────────┘
                             │
             ┌───────────────┼───────────────┐
             ▼               ▼               ▼
        Remote A         Remote B        Remote C
        workspace-       workspace-      workspace-
        docker (dind)    docker (dind)   docker (dind)
```

- The **Coder host** runs Coder (managed by Dokploy) on one server.
- Each **remote** runs a single `docker:dind` container (`workspace-docker`),
  managed by that remote's own deployment UI (Dokploy **or** Coolify).
- Coder reaches each remote daemon over the tailnet at `tcp://<tailscale-ip>:2376`
  with per-remote client certificates.
- The Docker API is bound **only** to the remote's Tailscale IP — never to a
  public interface. See §7 for why that matters and how to verify it.

### Key design decisions (do not "improve" without re-reading these)
1. **One unified Coder template** (`templates/docker-devcontainer/`) serves both
   modes: empty `docker_host` → local Unix socket; `docker_host=tcp://<ts-ip>:2376`
   + TLS material → remote. One template, pushed per-target with different vars.
2. **TLS material is stored as sensitive template variables** (PEM contents),
   NOT mounted files, NOT in this repo.
3. **Per-remote client certs** — each dind daemon generates its own CA + client
   pair. Certs are NOT reusable across remotes.
4. **Tailscale free Personal tier** covers this (≤6 users, unlimited devices,
   non-commercial only). If use becomes commercial → paid Tailscale or self-host
   Headscale.
5. **Repo is publishable.** Real IPs/hostnames/usernames live only in gitignored
   execution folders. See AGENTS.md §7.

### Remote topology variants — confirm which one applies FIRST

This playbook's canonical setup is a **dedicated `docker:dind` container** per
remote (the `workspace-docker` container). But some users run Coder against a
remote's **host Docker daemon directly** (no container). Before starting,
**ask the user which topology the remote will use** — the difference changes
Phase 3 and how certs are produced:

| | A. dind container (canonical, this guide) | B. Host dockerd (whole server) |
|---|---|---|
| What Coder connects to | inner dockerd inside `workspace-docker` container | the remote host's own dockerd |
| Deploy a container? | Yes — `templates/workspace-docker.yml` via UI | No — configure `/etc/docker/daemon.json` |
| Certs | dind auto-generates CA + client/server at startup | **generated manually** (openssl), server cert must include the TS IP in its SAN |
| Isolation | workspaces isolated from the host's other apps | **not isolated** — workspaces share the host daemon with any other apps (Coolify/Dokploy services, etc.) |
| Recommended when | remote also runs other services (like remote-a's Ghost/n8n/Postgres) | remote is **dedicated** to workspaces only |
| Risk | lower | network access to dockerd ≈ root on that host — tailnet-only bind + TLS + ACL are even more critical |
| `DOCKER_TLS_SAN` env | required in compose (see G1) | N/A — SAN set at cert generation time |

Everything else — Tailscale join/naming, tailnet ACL, cert staging on the host,
TLS verification, template push, end-to-end test, secrets handling — is identical.

**Question to ask up front (adapt to the user's situation):**
> "On this remote, will Coder's workspaces run inside a dedicated
> `docker:dind` container, or will Coder talk directly to the server's own
> Docker daemon (whole-server)? If the server also hosts other applications,
> the dind container is the safer choice."

## 2. Roles

Division of labor. An agent can work **independently**, **hybrid**, or just
**advise** — state which mode you're operating in up front.

| Task | Who does it | Why |
|---|---|---|
| Create Tailscale account/tailnet, approve devices | **User** | Owns the identity |
| Provide SSH access (`ssh-copy-id` + key) | **User** | Agent must never handle passwords |
| Deploy the `workspace-docker` compose via Dokploy/Coolify UI | **User** | Agent may not have UI access |
| Paste cert values into Coder template vars (or approve CLI push) | **User** | Coder auth |
| Everything else (Tailscale install/join, cert extraction/staging, TLS test, template push, verification) | **Agent** | Technical work |

**The agent's golden rule: never ask for (or accept) a password.** If a step
needs privilege the agent doesn't have, solve it with scoped NOPASSWD sudoers
(§4) or hand the user the exact command to run.

## 3. Prerequisites

Before any SSH work, the agent needs:

1. **Tailscale account + tailnet.** Personal free plan. Decide auth method:
   - **Reusable pre-auth key** (hands-off): Settings → Keys → Generate key →
     Reusable=on, Ephemeral=off, no tags. Agent uses `sudo tailscale up --auth-key=...`.
     Keys expire (90 days default) — store in the execution's `secrets/`.
   - **Interactive auth URL**: each device prints a URL the user must approve.
2. **SSH access to the Coder host** — user runs `ssh-copy-id`; agent gets
   `<user>@<host>`. The host may be on the public internet or the tailnet.
3. **SSH access to each remote** — same, per remote. See AGENTS.md §5 for the
   exact user commands to create/install keys so the agent never sees a password.
4. **Coder CLI, installed AND authenticated (agent side).** The orchestrating
   agent needs the `coder` CLI on the machine it works from (e.g. the user's
   workstation or the host) to push templates (Phase 6) and create/test
   workspaces (Phase 7):
   - **Install:** Windows → `C:\Program Files\Coder\bin\coder.exe` (or install
     from coder.com/download); Linux → install script, binary on PATH.
   - **Authenticate:** the CLI holds a session that **expires** (G9). The user
     must run `coder login <url>` (opens browser, saves session locally) — the
     agent must NOT handle the user's session token or password. Verify with
     `coder whoami` → shows the logged-in user + URL.
   - **Check the URL first:** `coder whoami` tells you which server the CLI is
     pointed at (stored in the coderv2 config). It can be "signed out" while the
     URL is correct, or pointed at a stale URL — both look similar, so verify
     before blaming the config. Confirm the target URL (e.g. `coder.example.com`)
     before running any `coder` command.
   - The CLI talks to Coder over its **HTTP API** — the agent does NOT need
     Docker access on the Coder host for template work.
5. **Decision: networking mode** — this playbook standardizes on **Tailscale**.
   Alternative: no VPN (public IP + UFW + TLS) — see "No-VPN alternative" below.

### No-VPN alternative (if you don't want a tailnet)
- Bind 2376 to the remote's **public IP**: `ports: ["<PUBLIC_IP>:2376:2376"]`.
- Firewall so **only the Coder host's public IP** can reach it (never allow
  `2376/tcp` to the world):
  ```bash
  sudo ufw allow from <CODER_HOST_PUBLIC_IP> to any port 2376 proto tcp
  ```
  Also configure the VPS provider's firewall/security group as a second layer.
- TLS is still **mandatory** — `tcp://<PUBLIC_IP>:2376` with the same client
  certs, never plain `2375`.
- `DOCKER_TLS_SAN` must then use the **public IP** (not a Tailscale IP).
- Everything downstream (cert extraction, template, verification) is identical —
  only `docker_host` and the cert SAN change.

## 4. Access & privilege model (the sudo problem)

### Symptom
Production hosts often have **root SSH disabled** and a user whose `sudo`
requires a password every time. An agent SSH-ing as that user cannot run any
privileged command non-interactively.

### Solution: scoped NOPASSWD sudoers (NOT blanket NOPASSWD)
Allow exactly the binaries the setup needs, nothing else. User runs these once:

```bash
# EVERY server (tailscale needed everywhere):
echo '<user> ALL=(root) NOPASSWD: /usr/bin/tailscale' | sudo tee /etc/sudoers.d/coder-setup
sudo chmod 0440 /etc/sudoers.d/coder-setup
sudo visudo -c        # must print "parsed OK"

# REMOTE servers ONLY (docker needed to extract dind client certs):
echo '<user> ALL=(root) NOPASSWD: /usr/bin/docker' | sudo tee /etc/sudoers.d/coder-setup-docker
sudo chmod 0440 /etc/sudoers.d/coder-setup-docker
```

- **Removable after onboarding** (re-locks everything).
- On remotes where the agent has **root** SSH, no sudoers needed.
- On the **Coder host**, the agent does **not** need Docker at all — only
  Tailscale. Template deploys go over Coder's HTTP API, not docker.sock.

### Agent check
`sudo -n -l` must show the scoped entries. Remember: `sudo -n whoami` failing is
**expected** when NOPASSWD only covers tailscale/docker — that's the point.

## 5. Procedure — Phases 0–8

### Phase 0 — Repo prep
- Real fleet values live in the execution folder's `inventory.md` + `secrets/`.
  Fill them in as you discover values (IPs, hostnames, usernames).
- Verify `.gitignore` covers: `executions/`, `secrets/`, `servers/`, `*.pem`,
  `*.key`, `.tfvars` — see AGENTS.md §7.

### Phase 1 — Coder host
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --auth-key=<KEY> --hostname=coder-host   # or interactive
tailscale ip                                               # record host TS IP
```
- Coder host TS IP becomes the ACL source (see §6).

### Phase 2 — Each remote (repeat for B, C, D)
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --auth-key=<KEY> --hostname=coder-workspace-NN   # NN sequential, never reused
tailscale ip
```
- Name nodes AT AUTH TIME: host = `coder-host`, remotes = `coder-workspace-01`,
  `-02`, … (never reuse a number).
- Verify host↔remote: `tailscale ping coder-workspace-NN` from the host.

### Phase 3 — Deploy the dind container (USER does the UI part)
> **Branch on topology (§1):** the canonical path below deploys a
> `workspace-docker` dind container. If the remote uses topology **B (host
> dockerd)**, SKIP the container — instead enable TLS on the host daemon:
> `/etc/docker/daemon.json` with `hosts: ["tcp://<ts-ip>:2376",
> "unix:///var/run/docker.sock"]` + `tlsverify` + cert paths, restart dockerd,
> and generate the CA/server/client certs manually with the TS IP in the server
> cert's SAN. Verification (Phase 5) and everything after is identical.

Canonical compose: `templates/workspace-docker.yml`. Agent fills in the remote's
Tailscale IP, user pastes into Dokploy **or** Coolify and deploys.

```yaml
services:
  workspace-docker:
    image: docker:29.7.1-dind
    container_name: workspace-docker
    restart: unless-stopped
    privileged: true
    environment:
      DOCKER_TLS_CERTDIR: /certs
      DOCKER_TLS_SAN: "IP:<TAILSCALE_IP>"        # MANDATORY — see gotcha G1
    volumes:
      - workspace-docker-data:/var/lib/docker
      - workspace-docker-certs-ca:/certs/ca
      - workspace-docker-certs-client:/certs/client
    ports:
      - "<TAILSCALE_IP>:2376:2376"               # bind to tailnet IP ONLY
volumes:
  workspace-docker-data:
  workspace-docker-certs-ca:
  workspace-docker-certs-client:
```

Verify (agent, over SSH):
```bash
docker ps --filter name=workspace-docker          # Up; note Coolify renames (G3)
ss -tlnp | grep 2376                              # must show <ts-ip>:2376, NOT 0.0.0.0
docker exec <container> ls /certs/client          # ca.pem cert.pem key.pem
```

**Verify public inaccessibility** (critical): from outside, TCP connect to the
remote's PUBLIC IP on 2376 must fail/timeout. Example (PowerShell):
```powershell
(Test-NetConnection <public-ip> -Port 2376 -WarningAction SilentlyContinue).TcpTestSucceeded  # False
```

### Phase 4 — Stage certs on the host
- Extract from the dind container (they are per-daemon, regenerated on restart):
  ```bash
  docker exec <container> cat /certs/client/ca.pem > ca.pem   # + cert.pem + key.pem
  ```
- Stage on the **host** in a user-writable dir (NOT `/root` — see G5):
  `/home/<user>/coder-tls/<remote>/`. Permissions: `key.pem` = `0600`, others `0644`.
- The cert values will be pasted into Coder template vars; the staged copy is the
  convenient source.

### Phase 5 — Verify TLS from the host
```bash
docker --tlsverify \
  --tlscacert=/home/<user>/coder-tls/<remote>/ca.pem \
  --tlscert=/home/<user>/coder-tls/<remote>/cert.pem \
  --tlskey=/home/<user>/coder-tls/<remote>/key.pem \
  -H=tcp://<ts-ip>:2376 info
```
Must print server info. **If it fails with "certificate is valid for … not
<ts-ip>" → the container was started without `DOCKER_TLS_SAN` (G1).**

### Phase 6 — Coder templates
The unified template lives at `templates/docker-devcontainer/` (this playbook's
`templates/` folder — full path: `playbooks/coder-remote-servers/templates/docker-devcontainer`).
It exposes: `docker_host` (empty = local socket), `docker_ca`, `docker_cert`,
`docker_key` (sensitive).

```sh
# local template (empty docker_host → host's unix socket)
coder templates push dev-workspace ./playbooks/coder-remote-servers/templates/docker-devcontainer

# remote template — variables file is YAML (NOT tfvars), see G6/G7
coder templates push dev-workspace-remote-a ./playbooks/coder-remote-servers/templates/docker-devcontainer \
  --variables-file /path/to/remote-a-vars.yaml
```

**Before Phase 6, confirm the Coder CLI is installed AND authenticated** (see
§3 prerequisite #4). Sessions expire — if `coder whoami` says "signed out", the
user runs `coder login <url>` (browser). Do NOT handle their token.

### Phase 7 — Verify end-to-end
```sh
coder create test-remote-a --template dev-workspace-remote-a --yes \
  --parameter repo_url= --parameter new_branch=
coder logs test-remote-a --follow
coder ping test-remote-a          # agent should respond
```
- On the remote, confirm the workspace container is inside the dind daemon
  (NOT the host daemon): `docker exec <workspace-docker> docker ps`.
- Test the **local** template the same way (`dev-workspace`, no params).
- Delete test workspaces when done.

### Phase 8 — Record
- Append to the execution's `notes.md` and update the execution's
  `inventory.md` and `secrets-pointers.md`. These files are the run's private
  memory — never commit them (AGENTS.md §7).

## 6. Tailscale ACL / grants (tailnet hardening)

Apply in the admin console (Access Controls). **Grants syntax**, not legacy ACL
syntax. `src`/`dst` are device selectors; **ports go in the `ip` field** (G8).

```json
{
  "hosts": {
    "coder-host": "<TS_IP_CODER_HOST>",
    "coder-workspace-01": "<TS_IP_WS_01>"
  },
  "grants": [
    { "src": ["autogroup:member"], "dst": ["*"], "ip": ["tcp:22", "icmp:*"] },
    { "src": ["coder-host"], "dst": ["coder-workspace-01"], "ip": ["tcp:2376"] }
  ]
}
```

- WireGuard handshake (41641) + control-plane traffic are **auto-allowed** — no rule.
- Replacing the policy **removes Tailscale's default SSH-to-own-devices**; add an
  `ssh` block if you rely on `tailscale ssh` (see README §3).
- Add each new remote: alias+IP in `hosts`, plus a `coder-host → <remote>`
  grant for `tcp:2376`. No hostname wildcards in selectors — list explicitly.

## 7. Security invariants (verify every time)

1. **Docker 2376 never on a public interface.** Bind is `"<ts-ip>:2376:2376"`.
   A bare `"2376:2376"` or `0.0.0.0` is a security incident.
2. **Public reachability test fails** on the remote's public IP:2376.
3. **`DOCKER_TLS_SAN` always set** to the tailnet IP.
4. **No secrets in git.** `*.pem`, `*.key`, `.tfvars`, `executions/` are all
   gitignored. A tracked `*.pem` is an incident → rotate (AGENTS.md §7).
5. **`key.pem` staged at `0600`** on the host.
6. **Agent never sees a password.** Keys and pre-auth keys are the only
   credentials; passwords never leave the user.

## 8. Common questions

- **Why Tailscale vs Headscale?** Tailscale free Personal covers ≤6 users /
  unlimited devices, non-commercial. Headscale = self-hosted control plane
  (free to run, one more service). Public-IP + UFW + TLS = no VPN at all
  (see §3 "No-VPN alternative").
- **Can I reuse certs across remotes?** No. Each dind generates its own CA/client
  pair; they're only valid for that daemon.
- **Do I need Docker API access on the Coder host?** No. Coder templates go over
  Coder's HTTP API. Only the `docker` CLI (no daemon) is needed for remote TLS tests.
- **Why is the health flag false on a fresh workspace?** Startup scripts
  (code-server install) are still running; check `coder logs <ws>` before
  worrying.

> **Gotchas:** read `notes/gotchas.md` (G1–G12) before any run — real pitfalls
> hit on the fleet, each with its fix.

---

## 9. Quick run: onboarding a new remote

Condensed checklist for adding another remote. Fill in `<REMOTE>` (alias),
`<user>`, and IPs as you go. Log each step in the execution's `notes.md`.

### 0. Pre-flight
- [ ] Tailscale free tier headroom? (unlimited devices, 6 users — fine unless
      fleet grows)
- [ ] `ssh-copy-id <user>@<public-ip>` done; note alias `<REMOTE>` in the
      execution's `inventory.md`.
- [ ] Tailscale tailnet exists (host already joined from first onboarding).
- [ ] **Scoped NOPASSWD sudo for the agent** (root SSH often disabled; agent
      needs passwordless `tailscale` + `docker` — see §4):
      ```bash
      echo '<user> ALL=(root) NOPASSWD: /usr/bin/tailscale' | sudo tee /etc/sudoers.d/coder-setup
      echo '<user> ALL=(root) NOPASSWD: /usr/bin/docker'    | sudo tee /etc/sudoers.d/coder-setup-docker
      sudo chmod 0440 /etc/sudoers.d/coder-setup /etc/sudoers.d/coder-setup-docker
      sudo visudo -c
      ```

### 1. Tailscale on the remote
- [ ] `curl -fsSL https://tailscale.com/install.sh | sh`
- [ ] `sudo tailscale up --auth-key=<KEY> --hostname=coder-workspace-NN`
      (name the node at auth time — the host is `coder-host`, remotes are
      `coder-workspace-01`, `-02`, `-03`, …; sequential, never reused)
- [ ] `tailscale ip` → record IP; `tailscale status` → confirm name.
- [ ] From host: `tailscale ping coder-workspace-NN` → expect pong.
- [ ] Add the node to the tailnet ACL (SSH 22 + Docker 2376) — see §6. Do this
      **before** testing TLS from the host, or the 2376 TCP check will time out.
      Apply via the admin console **or** the API (POST the full policy with
      `Content-Type: application/hujson`; an empty body resets the policy to
      allow-all — see notes/gotchas.md G12).

### 2. Compose + deploy
- [ ] Copy `templates/workspace-docker.yml`, replace the `2376` bind IP with
      this remote's Tailscale IP.
- [ ] **Also update `DOCKER_TLS_SAN` to `IP:<tailscale-ip>`** — without it the
      dind server cert won't cover the tailnet IP and TLS will fail with
      "certificate is valid for ..., not <ip>". (Gotcha found on remote-a.)
- [ ] Deploy via the remote's UI (Coolify or Dokploy). Verify:
      `docker ps --filter name=workspace-docker`.
- [ ] `docker exec workspace-docker ls /certs/client` → `ca.pem cert.pem key.pem`

### 3. Stage certs on the Coder host
- [ ] `mkdir -p /home/<user>/coder-tls/<REMOTE>` (user-writable — see G5)
- [ ] Copy the three files from the remote (docker cp / scp) into that dir.
- [ ] `chmod 0600 /home/<user>/coder-tls/<REMOTE>/key.pem`

### 4. Verify TLS from host
- [ ] `docker --tlsverify --tlscacert=/home/<user>/coder-tls/<REMOTE>/ca.pem
      --tlscert=.../cert.pem --tlskey=.../key.pem -H=tcp://<ts-ip>:2376 info`

### 5. Coder template
- [ ] Push the unified template for this remote (Phase 6 above)
- [ ] In Coder UI set template vars: `docker_host=tcp://<ts-ip>:2376` +
      `docker_ca`/`docker_cert`/`docker_key` = file contents (sensitive).

### 6. Verify
- [ ] Create + destroy a test workspace (watch `coder logs --follow`).
- [ ] Update the execution's `inventory.md` + `notes.md`.

---

## 10. Wildcard app subdomains

How Coder's **workspace app previews**
(`https://3000--main--<workspace>--<user>.coder.<domain>`) are exposed through
Dokploy + Traefik, and how to make them actually work (routing **and** TLS).
This is the knowledge gained when the preview URLs returned Traefik's
`404 page not found` and an invalid certificate.

> Replace `<domain>` (e.g. `example.com`), `<user>`, `<ORIGIN_PUBLIC_IP>`, and
> the Coder app name with your real values. Real fleet values stay in the
> execution folder.

**TL;DR — the two things that must both be right:**
1. **Routing** — Traefik must match `*.coder.<domain>` with a `HostRegexp`
   rule (Dokploy's domain UI can't do this).
2. **TLS** — Traefik must serve a **wildcard** cert for `*.coder.<domain>`,
   issued via **DNS-01** (HTTP-01 cannot issue wildcards).

### 10.1 How the pieces fit together

```
 browser
   │  https://3000--main--<workspace>--<user>.coder.<domain>
   ▼
 coder.<domain>  ──► Cloudflare proxy (orange cloud)
   │                 TLS terminated by Cloudflare edge
   ▼
 *.coder.<domain> ──► <ORIGIN_PUBLIC_IP> (origin, DNS-only / grey cloud)
                       TLS terminated by Dokploy's Traefik
                       ▼
                       Traefik ─► Coder (internal port 7080)
                                     ▼
                                     workspace app on port 3000
```

#### DNS split — intentional, do not "fix" it
- `coder.<domain>` → **Cloudflare** (proxied). Cloudflare terminates TLS with
  its own edge cert, so the dashboard works even though the origin serves
  Traefik's default cert.
- `*.coder.<domain>` → **origin IP directly** (DNS-only). This is the *only*
  option because:
  - Cloudflare will not proxy wildcard (`*`) DNS records — wildcards must be
    grey-cloud.
  - Cloudflare Universal SSL covers `*.<domain>` (one level) but **not**
    `*.coder.<domain>` (two levels), so Cloudflare can't hand you a valid cert
    for it anyway.

The two hostnames resolving to different targets is correct and required.

### 10.2 Coder side (server config)

Set in the Coder deployment env (Dokploy compose for the Coder app):

```dotenv
CODER_ACCESS_URL=https://coder.<domain>
CODER_WILDCARD_ACCESS_URL=*.coder.<domain>
CODER_HTTP_ADDRESS=0.0.0.0:7080
```

Coder only *generates* app URLs of the form
`<port>--<agent>--<workspace>--<user>.coder.<domain>` when the wildcard access
URL is set. If you can see such a URL in the Coder UI, this side is correct.
Nothing else to do here.

### 10.3 Reverse proxy (Dokploy/Traefik) — routing

#### The trap
Dokploy wraps every domain you enter as `Host(\`<host>\`)`
(`packages/server/src/utils/docker/domain.ts`). Traefik's `Host()` matcher does
**exact** hostname comparison only (`pkg/muxer/http/matcher.go`:
`reqHost == host`). So `Host(\`*.coder.<domain>\`)` never matches real
subdomains — the request falls through to Traefik's default cert + `404 page
not found`. **There is no way to express a working wildcard rule through
Dokploy's Domains UI.**

#### The fix — a HostRegexp router via compose labels
1. In the Coder app → **Domains**, delete the `*.coder.<domain>` entry
   (keep `coder.<domain>`).
2. In the Coder app → **compose editor**, add these labels to the `coder`
   service (user-authored labels survive Dokploy redeploys):
   ```yaml
   labels:
     - traefik.http.routers.coder-wildcard-web.rule=HostRegexp(`^[a-z0-9-]+\.coder\.<domain>$`)
     - traefik.http.routers.coder-wildcard-web.entrypoints=web
     - traefik.http.routers.coder-wildcard-web.service=coder-wildcard-web
     - traefik.http.routers.coder-wildcard-web.middlewares=redirect-to-https@file
     - traefik.http.services.coder-wildcard-web.loadbalancer.server.port=7080
     - traefik.http.routers.coder-wildcard-websecure.rule=HostRegexp(`^[a-z0-9-]+\.coder\.<domain>$`)
     - traefik.http.routers.coder-wildcard-websecure.entrypoints=websecure
     - traefik.http.routers.coder-wildcard-websecure.service=coder-wildcard-websecure
     - traefik.http.services.coder-wildcard-websecure.loadbalancer.server.port=7080
     - traefik.http.routers.coder-wildcard-websecure.tls=true
   ```
3. **Deploy.**

Notes:
- `port=7080` is Coder's internal HTTP port (`CODER_HTTP_ADDRESS`).
- `tls=true` (not `certresolver`) so Traefik serves the wildcard cert from its
  store instead of trying to ACME-issue per hostname (it can't — the rule is a
  regex, Traefik can't extract a domain from it).
- Keep the router/service names unique and unrelated to Dokploy's generated
  names (e.g. `coder-wildcard-*`) so Dokploy never collides with them.

### 10.4 TLS — the wildcard certificate

#### The trap
Dokploy's Traefik `letsencrypt` resolver only has an `httpChallenge`
(`/etc/dokploy/traefik/traefik.yml`). Let's Encrypt **cannot issue wildcard
certs over HTTP-01** — wildcards require **DNS-01**. So no wildcard cert ever
lands in the ACME store, and Dokploy's custom-cert dir
(`/etc/dokploy/traefik/dynamic/certificates/`) is empty → Traefik serves its
self-signed `TRAEFIK DEFAULT CERT`. A "Let's Encrypt" setting in the Dokploy
domain UI validates DNS, it does **not** produce a wildcard cert.

#### The fix — acme.sh + Cloudflare DNS-01 into Dokploy's cert dir
Script: `scripts/setup-wildcard-cert.sh` (run as root on the Coder host):

```bash
ssh <alias>
sudo bash /tmp/setup-wildcard-cert.sh     # token file: /home/<user>/.cf-token
```

Prereqs:
- Cloudflare **API token** with `Zone → DNS → Edit` for `<domain>`, saved to
  `/home/<user>/.cf-token` (or `$CF_Token` env).
- The token must **not** be IP-restricted (acme.sh runs from the host, not your
  workstation).
- Tokens expire (max TTL typically 1 year) — use the longest TTL and plan to
  rotate before expiry, or the first auto-renewal breaks.

What it does:
1. Installs acme.sh as root (so the renewal cron runs as root).
2. Issues `*.coder.<domain>` via the `dns_cf` plugin (creates/removes the
   `_acme-challenge` TXT record automatically).
3. Writes `chain.crt`, `privkey.key`, and `certificate.yml` into
   `/etc/dokploy/traefik/dynamic/certificates/wildcard-coder/`.
4. Traefik's file provider (watch: true) picks them up automatically — no reload
   needed.

`certificate.yml` (Dokploy's file-provider layout; Traefik mounts the dynamic
dir at the same path):
```yaml
tls:
  certificates:
    - certFile: /etc/dokploy/traefik/dynamic/certificates/wildcard-coder/chain.crt
      keyFile: /etc/dokploy/traefik/dynamic/certificates/wildcard-coder/privkey.key
```

#### Token lifecycle / renewal
- LE certs last 90 days; acme.sh's cron re-issues at ~60 days and re-applies the
  install, so renewal is automatic **as long as the Cloudflare token is still
  valid at renewal time**.
- When you rotate the token, update **two** places on the host:
  `/home/<user>/.cf-token` **and** acme.sh's cached copy in
  `/root/.acme.sh/*.coder.<domain>/*.coder.<domain>.conf`
  (acme.sh uses its cached `CF_Token` for renewals, not the file).

### 10.5 Verification

From any machine:

```bash
# 1. TLS — cert served must be the wildcard (subjectAltName DNS:*.coder.<domain>)
echo | openssl s_client -connect <ORIGIN_PUBLIC_IP>:443 \
  -servername anything.coder.<domain> 2>/dev/null \
  | openssl x509 -noout -subject -ext subjectAltName

# 2. Routing — must return Coder's response, NOT Traefik's "404 page not found"
curl -sk https://3000--main--<workspace>--<user>.coder.<domain>/

# 3. Traefik actually forwarded it (origin status != 0)
ssh <alias> "grep 3000--main--<workspace>--<user> \
  /etc/dokploy/traefik/dynamic/access.log | tail -1"
```

#### Troubleshooting table

| Symptom | Cause | Fix |
|---|---|---|
| `404 page not found`, self-signed cert | No router matches the app hostname | `HostRegexp` rule (§10.3); confirm `OriginStatus != 0` in access log |
| Valid cert in Dokploy UI but browser says invalid | Cert was never served (empty cert dir, HTTP-01-only resolver) | Issue via DNS-01 (§10.4) |
| `Host(\`*\`)` router present but never matches | Traefik `Host()` is exact-match only | Use `HostRegexp` (§10.3) |
| acme.sh: token rejected | Token IP-restricted, or zone lacks `DNS:Edit` | Recreate token, no IP restriction, scope `<domain>` |
| Renewal fails silently | Token expired between renewals | Long-TTL token; update `/home/<user>/.cf-token` + acme.sh cache (§10.4) |

---

## Authoring rules
- Steps must be copy-paste executable with placeholders filled.
- Flag every step that WRITES to a production system with **WRITE** in bold
  (e.g. `- [ ] **WRITE** install package X on <host>`). Reads need no flag.
- Add rollback instructions for every write step.
- After each run, promote lessons into `notes/` (via the operator, never
  mid-run).
