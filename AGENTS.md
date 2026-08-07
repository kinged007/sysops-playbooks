# AGENTS.md — Coder Remote Workspace Fleet: Setup Guide & Operating Memory

This file is the **memory and brain** for this repo. It tells an agent (opencode,
Claude Code, Cursor, etc.) — or a human — how to set up and maintain a fleet of
remote servers that run Docker workspaces for a Coder server, using a Tailscale
tailnet and mutual TLS. It was written **after doing the whole thing once** on a
real fleet, so it contains the actual commands, the gotchas we hit, and the
security rules that keep secrets out of git.

**Read this fully before doing anything.** It replaces guessing. The runbook and
plan docs in `docs/` are task-level checklists; this is the why-and-how.

---

## 1. What this system is

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
   files. See §8.

### Remote topology variants — confirm which one applies FIRST

This guide's canonical setup is a **dedicated `docker:dind` container** per remote
(the `workspace-docker` container). But some users run Coder against a remote's
**host Docker daemon directly** (no container). Before starting, **ask the user
which topology the remote will use** — the difference changes Phase 3 and how
certs are produced:

| | A. dind container (canonical, this guide) | B. Host dockerd (whole server) |
|---|---|---|
| What Coder connects to | inner dockerd inside `workspace-docker` container | the remote host's own dockerd |
| Deploy a container? | Yes — `compose/workspace-docker.yml` via UI | No — configure `/etc/docker/daemon.json` |
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

---

## 2. Roles & division of labor

This matters. An agent should be able to do the work **independently**, **hybrid**,
or just **advise**. State which mode you're operating in up front.

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

---

## 3. Pre-requisites (what the user must provide)

Before any SSH work, the agent needs:

1. **Tailscale account + tailnet.** Personal free plan. Decide auth method:
   - **Reusable pre-auth key** (hands-off): Settings → Keys → Generate key →
     Reusable=on, Ephemeral=off, no tags. Agent uses `sudo tailscale up --auth-key=...`.
     Keys expire (90 days default) — store in gitignored `secrets/`.
   - **Interactive auth URL**: each device prints a URL the user must approve.
2. **SSH access to the Coder host** — user runs `ssh-copy-id`; agent gets
   `<user>@<host>`. The host may be on the public internet or the tailnet.
3. **SSH access to each remote** — same, per remote. See §9 for the exact user
   commands to create/install keys so the agent never sees a password.
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
5. **Decision: networking mode** — this repo standardizes on **Tailscale**.
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

---

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
- On remotes where the agent has **root** SSH (see §9), no sudoers needed.
- On the **Coder host**, the agent does **not** need Docker at all — only
  Tailscale. Template deploys go over Coder's HTTP API, not docker.sock.

### Agent check
`sudo -n -l` must show the scoped entries. Remember: `sudo -n whoami` failing is
**expected** when NOPASSWD only covers tailscale/docker — that's the point.

---

## 5. The process — end to end

Full task-level detail: `docs/plans/2026-08-07-remote-docker-onboarding.md`.
Condensed per-remote checklist: `docs/runbooks/onboarding-a-new-remote.md`.

### Phase 0 — Repo prep
- Real fleet values live in gitignored `secrets/private-fleet-data.md`. Fill it in
  as you discover values (IPs, hostnames, usernames).
- Verify `.gitignore` covers: `secrets/`, `servers/`, `*.pem`, `*.key`, `.tfvars`.

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

Canonical compose: `compose/workspace-docker.yml`. Agent fills in the remote's
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
The unified template lives at `templates/docker-devcontainer/`. It exposes:
`docker_host` (empty = local socket), `docker_ca`, `docker_cert`, `docker_key`
(sensitive).

```sh
# local template (empty docker_host → host's unix socket)
coder templates push dev-workspace ./templates/docker-devcontainer

# remote template — variables file is YAML (NOT tfvars), see G6/G7
coder templates push dev-workspace-remote-a ./templates/docker-devcontainer \
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
- Append to **gitignored** `servers/audit-log.md` and update
  `servers/inventory.md` and `secrets/private-fleet-data.md`.
- These files are the fleet's private memory. Never commit them (§8).

---

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

---

## 7. Security invariants (verify every time)

1. **Docker 2376 never on a public interface.** Bind is `"<ts-ip>:2376:2376"`.
   A bare `"2376:2376"` or `0.0.0.0` is a security incident.
2. **Public reachability test fails** on the remote's public IP:2376.
3. **`DOCKER_TLS_SAN` always set** to the tailnet IP.
4. **No secrets in git.** `*.pem`, `*.key`, `.tfvars`, `secrets/`, `servers/`
   are all gitignored. A tracked `*.pem` is an incident → rotate (§8).
5. **`key.pem` staged at `0600`** on the host.
6. **Agent never sees a password.** Keys and pre-auth keys are the only
   credentials; passwords never leave the user.

---

## 8. Secrets & fleet data — the critical rules

### What gets committed (safe for a public repo)
`README.md`, `compose/`, `docs/`, `templates/`,
`.gitignore`, `AGENTS.md`. These contain **zero real IPs, hostnames, usernames,
domains, or keys** — only placeholders (`<TAILSCALE_IP>`, `<user>`, …) and
documented example IPs (RFC 5737 `203.0.113.x` / `198.51.100.x`).

### What must NEVER be committed
- **`servers/`** — the fleet's operational memory: `audit-log.md` (real
  hostnames/IPs), `inventory.md`, `secrets-pointers.md`. Real operational data.
- **`secrets/`** — pre-auth keys, private fleet-data map.
- Any `*.pem`, `*.key`, `.tfvars`, `.env` anywhere.

`.gitignore` enforces this. **Before any commit, always run:**
```powershell
git status                       # confirm servers/ and secrets/ are NOT listed
git ls-files --cached --others --exclude-standard | % { ... scan for real IPs/idents ... }
```
Minimal identifier scan (run in repo root):
```powershell
$files = git ls-files --cached --others --exclude-standard
foreach ($f in $files) { if (Test-Path $f) {
  $c = Get-Content $f -Raw
  if ($c -match '100\.81\.162|207\.180\.216|tskey-|BEGIN (CERTIFICATE|PRIVATE|RSA)') { Write-Output "LEAK: $f" }
}}
```

**How to make a file safe if it must be published:** replace real values with
`<PLACEHOLDER>` tokens, keep the real values in `secrets/private-fleet-data.md`,
and re-run the scan.

### Rotation / incident response
- **Pre-auth key leaked:** revoke in the admin console (Settings → Keys) and
  regenerate; update `secrets/`.
- **Client cert leaked:** delete the dind `workspace-docker-certs-*` volumes and
  restart the container (certs regenerate, CA persists) → re-extract → re-stage →
  update template vars → re-verify TLS.
- **A `*.pem` appears tracked in git:** treat as incident, remove and rotate.

---

## 9. Local SSH setup — user commands (so the agent never needs passwords)

Goal: user creates a dedicated per-server key, installs its public half on the
server, and defines an SSH config alias. The agent then connects using only the
key — no passwords involved.

### A. Generate a dedicated key (one per server)
```bash
# Local machine (Windows PowerShell / macOS / Linux):
ssh-keygen -t ed25519 -f ~/.ssh/coder-workspace-01 -C "coder-workspace-01"
# No passphrase (agent needs non-interactive use). Output: key + key.pub
```

### B. Install the public key on the server
**Option 1 — ssh-copy-id (best when your main SSH key already has access):**
```bash
ssh-copy-id -i ~/.ssh/coder-workspace-01.pub <user>@<public-ip>
```
**Option 2 — paste via the management UI (Coolify/Dokploy terminal), no SSH at all:**
```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo '<contents of coder-workspace-01.pub>' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```
> The UI will not "show" the key you pasted — `authorized_keys` is not managed
> by Coolify. It just works; verify by SSH-ing (below).

### C. Add an SSH config alias (Windows: `C:\Users\<you>\.ssh\config`)
```
Host <alias>                 # e.g. remote-a
  HostName <public-ip>
  User <user>                # e.g. root, or your sudo user
  IdentityFile ~/.ssh/coder-workspace-01
  IdentitiesOnly yes
```

### D. Verify (agent can then use it)
```bash
ssh -i ~/.ssh/coder-workspace-01 -o BatchMode=yes <user>@<public-ip> whoami
```
`BatchMode=yes` guarantees no password prompt — if it asks for a password, the
key isn't installed and the agent should not proceed.

### E. If the server is root-only via key (remotes)
Then no sudoers needed — the agent is already root. Do **not** re-enable root
password login; keep it key-only. Scoped NOPASSWD (§4) is only for non-root
sudo users.

---

## 10. Gotchas & learnings (hit and solved on the real fleet)

**G1 — dind server cert doesn't include the tailnet IP.**
Symptom: `tls: failed to verify certificate: x509: certificate is valid for
10.0.2.2, 127.0.0.1, ::1, not <ts-ip>`. Cause: dind generates its server cert
SAN at startup from container-detected IPs unless told otherwise. **Fix:
`DOCKER_TLS_SAN: "IP:<ts-ip>"` in the compose, then recreate the container.**
Certs regenerate on every start (CA persists in its volume).

**G2 — broken third-party dnf/yum repos break installers.**
On Rocky/CentOS, a stale repo (we hit `netdata`) 404s during metadata refresh and
kills `curl | sh` installers. Fix: disable it first:
```bash
dnf config-manager --set-disabled netdata netdata-repoconfig
dnf install -y --disablerepo='netdata*' tailscale
```
Also: Tailscale's `install.sh` may die before adding the repo on RHEL-family.
Add it manually: `dnf config-manager --add-repo https://pkgs.tailscale.com/stable/rhel/9/tailscale.repo`.

**G3 — Coolify renames the container.**
Coolify deploys the compose with a suffixed container name
(`workspace-docker-dgkmftx...`). Any `docker exec workspace-docker` fails with
"no such container". Use `name=$(docker ps -aq --filter name=workspace-docker | head -1)`.

**G4 — port conflict on redeploy.**
If the agent creates/validates the container via SSH and the user then redeploys
via Coolify, the port `ts-ip:2376` is still held → "port is already allocated".
**Always remove the agent-created container before a Coolify redeploy**
(`docker rm -f <name>`), then have the user redeploy so Coolify owns it.

**G5 — `/root` is often unreadable for the sudo user.**
Staging certs under `/root/coder-tls/` fails with "Permission denied" for user. Use a user-writable path: `/home/<user>/coder-tls/<remote>/`.

**G6 — `coder templates push --var` breaks with multiline PEM.**
`--var docker_ca="$(cat ca.pem)"` mangles multi-line content through the shell.
Use `--variables-file <file>`. **Coder's variables file is YAML, not tfvars:**
```yaml
docker_host: tcp://<ts-ip>:2376
docker_ca: |
  -----BEGIN CERTIFICATE-----
  ...
  -----END CERTIFICATE-----
```

**G7 — Windows PowerShell array interpolation joins with SPACES.**
Building the YAML in PowerShell via `"$(...)"` collapsed PEM lines into one
space-separated line → "tls: failed to find any PEM data". Fix: build a
`List[string]` and `-join "`n"` (real newlines), then write the file.

**G8 — Tailscale policy: grants syntax ≠ legacy ACL syntax.**
`autogroup:member:41641` fails with "host name must not contain colon". In
`grants`, ports live in the `ip` field (`tcp:22`, `icmp:*`), never appended to
`dst`. 41641 is auto-allowed. Replacing the policy drops default SSH — re-add if needed.

**G12 — Tailscale API ACL updates: use POST, never an empty body.**
Updating the policy file via the API is `POST /api/v2/tailnet/<tailnet>/acl`
(`PUT` returns 405). **A POST with an empty/malformed body can reset the policy
to the default allow-all** — we hit this live and had to restore immediately.
Always: GET the current policy, edit it, and POST the full content back with
`Content-Type: application/hujson`; verify with a follow-up GET. Scope required
is `policy_file`. Fetch the tailnet name from the host's
`tailscale status --json` (`MagicDNSSuffix`, e.g. `tailcXXXX.ts.net`).
The key can be stored in gitignored `secrets/tailscale-api-key.txt`.

**G9 — Coder CLI session expires.** `coder whoami` → "signed out". User runs
`coder login <url>` (browser). The CLI URL is stored in the coderv2 config; check
it before blaming a wrong URL.

**G10 — dind image tag.** Use a **current** `docker:dind` tag (e.g. `29.7.1-dind`).
Older pins in docs (e.g. `29.6.2-dind`) may not exist — verify against Docker Hub
before deploying.

**G11 — Windows → remote script execution.**
Piping a script into `ssh ... bash -s` from PowerShell re-encodes newlines to
CRLF and breaks bash. Write the script with LF endings and `scp` it, then run
`bash /tmp/script.sh`. Also: PowerShell interpolates `$()` in double-quoted ssh
commands **locally** — use single quotes or script files for anything with
`$(...)`.

---

## 11. File map

| Path | Purpose | Committed? |
|---|---|---|
| `AGENTS.md` | This guide | ✅ |
| `README.md` | Public overview, security rules, ACL example | ✅ |
| `compose/workspace-docker.yml` | Canonical dind compose (placeholders) | ✅ |
| `templates/docker-devcontainer/` | Unified Coder template (local + remote) | ✅ |
| `docs/plans/2026-08-07-remote-docker-onboarding.md` | Full implementation plan | ✅ |
| `docs/runbooks/onboarding-a-new-remote.md` | Per-remote checklist | ✅ |
| `servers/audit-log.md` | Private chronological log | ❌ gitignored |
| `servers/inventory.md` | Private fleet records | ❌ gitignored |
| `servers/secrets-pointers.md` | Where certs live (pointers only) | ❌ gitignored |
| `secrets/` | Pre-auth keys + private fleet-data map | ❌ gitignored |
| `.gitignore` | Enforces the above | ✅ |

---

## 12. Common questions

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
