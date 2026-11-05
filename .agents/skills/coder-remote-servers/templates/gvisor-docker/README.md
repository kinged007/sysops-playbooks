# gVisor Docker Workspaces (gvisor-docker)

Coder workspaces as **gVisor-sandboxed containers** (`runsc` runtime) or plain
`runc` containers on a **shared, isolated Docker daemon**, with
Docker-outside-of-Docker (DooD) support.

Same remote-connection model as `docker-devcontainer` (TLS to a tailnet-only
daemon endpoint), but workspaces are plain containers that talk to a daemon
over TLS — no per-workspace nested daemon.

> **Standard deployment (recommended): shared isolated daemon**
>
> Each remote runs **one** `workspace-docker` (`docker:dind`) container
> (`templates/workspace-docker.yml`) — the fleet's single nested daemon for
> that host. Workspaces are plain containers **on that daemon** and reach it
> over mTLS at `tcp://<tailscale-ip>:2376` (tailnet IP only). Containers
> spawned by the developer (`docker run`, `docker compose up`) land
> **inside the same shared daemon** — isolated from the host's own dockerd
> (Dokploy/Coolify, Postgres, etc.) and amortizing the ~300–500 MB nested-daemon
> cost across all workspaces on the host. See [Prerequisites](#prerequisites-shared-isolated-daemon) and
> [Docker access](#docker-access-inside-the-workspace-dood-over-tls).

## Why this template

| | docker-devcontainer | gvisor-docker (shared daemon) |
|---|---|---|
| Workspace isolation | privileged container, host kernel | gVisor sandbox (Sentry) **or** plain `runc` — per-workspace choice |
| Docker in workspace | nested daemon (DinD, privileged) **per workspace** | CLI over TLS (DooD) to the **shared isolated daemon** |
| Docker containers spawned by the dev | inside that workspace's own nested daemon | **inside the shared isolated daemon**, plain `runc` containers — never the host daemon |
| `privileged` mode | yes (required for per-workspace DinD) | **never** |
| Resource overhead | + nested dockerd **per workspace** (~200–500 MB) | one shared dockerd per host (~300–500 MB total) + workspace container only; `runsc` adds ~60–150 MB (Sentry+Gofer) |

The gvisor-docker pattern gives you: a docker socket to run containers,
isolation from the host, a sandbox boundary (when you choose `runsc`), and
reduced resource consumption — one daemon for the host, not one per workspace.

Workspaces have the same default tooling as `docker-devcontainer`: **Node.js / npm**, **Python**, **uv**, **GitHub CLI (`gh`)**, **Go**, and **Rust** — `gh`/`uv`/`go`/`rust` are installed on every start if missing (apt or binary to `~/.local/bin`/`~/.local/go`/`~/.cargo`; on `runsc` the binary fallback is the primary path since `sudo` is unsupported under gVisor).

## runc vs runsc

Both runtimes run the **same container** (image, home volume, mounts,
lifecycle) — the difference is only *how its processes are executed*. runc and
runsc workspaces can coexist on one host, side by side (the runtime is a
per-workspace parameter).

| | runc | runsc (gVisor) |
|---|---|---|
| Isolation | namespaces + cgroups + seccomp — processes run **directly on the host kernel** | user-space kernel (Sentry) — every syscall intercepted/emulated; the workspace never touches the host kernel directly |
| Escape risk | kernel bug or misconfig = host compromise; root in container ≈ root on host | requires a gVisor vulnerability (much smaller, audited attack surface); root in sandbox ≈ root in sandbox |
| RAM per workspace | container only | container + **60–150 MB** (Sentry + Gofer) |
| CPU overhead | ~0% | ~10–30% more on syscall-heavy work (`npm ci`, `composer install`, native compiles); plain compute ≈ parity |
| Compatibility | everything: sudo, TUIs, gdb/strace, FUSE, raw sockets/ICMP | `sudo`/setuid broken, **opencode TUI does not render** (below), no ptrace/FUSE/raw sockets//dev/tun |
| Startup | fastest | +0.5–2s per container start |

> **cgroup v2 note (G13):** `runsc` **cannot** run inside a `docker:dind`
> container on a unified cgroup v2 host — the inner dockerd writes cgroup
> v1 paths (`cpu.cfs_quota_us`, `cpuset.cpus`) that don't exist, so container
> create fails. `runc` workspaces on the shared daemon work fine. `runsc` on
> the shared daemon inherits the same limitation; if you need `runsc`, point
> the template at the **host** daemon (TLS on `tcp://<ts-ip>:2378`, `runsc`
> installed on the host) — see [Prerequisites](#prerequisites-shared-isolated-daemon).

**Honest note on isolation:** neither is "total". Both share host CPU/RAM
(cgroups). With the **shared isolated daemon**, the gVisor sandbox protects
the workspace *processes* and spawned containers are isolated from the host's
own dockerd — but workspaces on the same shared daemon can see each other's
spawned containers (`docker ps` on the shared daemon lists siblings). `runsc`
does not sandbox the containers the developer spawns (those are plain runc).
For per-workspace daemon isolation at a higher RAM cost, use
`docker-devcontainer`.

**TUI nuance:** the opencode TUI never renders under gVisor (upstream bug
sst/opencode#29802 — the renderer runs but writes no frames to the tty; headless
`opencode run`/`serve` are fine). Other TUIs (vim, nano, htop) DO work. If an
interactive TUI fails silently in a workspace, set `workspace_runtime = runc`
for that workspace — runsc stays available for everyone else. For `tar`-based
installers (e.g. code-server's `tar -xzf`), plain `tar` extraction can also
hit `Function not implemented` under gVisor — use `npm install -g --prefix`
workarounds or `runc`.

## Known gVisor limitations (inside the workspace)

- **The opencode TUI does not render under gVisor** (upstream bug
  sst/opencode#29802: the renderer runs but no frame is ever written to
  the tty; headless `opencode run`/`serve` work fine). Workaround: set
  `workspace_runtime = runc` for that workspace.
- `sudo` / setuid binaries do **not** work in a gVisor sandbox (sudo fails
  with "effective uid is not 0"). Use rootless tooling (nvm, pyenv, mise,
  asdf) or bake packages into the workspace image. `npm install -g` to the
  system prefix (`/usr/lib`) fails for the same reason — use
  `npm install -g --prefix "$HOME/.local"` and add `~/.local/bin` to `PATH`.
- No nested Docker daemon (dockerd inside the sandbox) — `docker compose up`
  etc. still work over TLS (DooD); containers land in the **shared isolated
  daemon**, not the host daemon.
- No `privileged` containers, kernel modules, `/dev/kvm`, FUSE (`sshfs`),
  `/dev/net/tun` (WireGuard/OpenVPN clients), raw sockets/ICMP (`ping`,
  `tcpdump`), `iptables`, ptrace-based debugging (`gdb`, `strace`).
- Unix-socket bind mounts are unusable (gVisor cannot relay the connect) —
  which is why Docker access uses TLS instead of a socket mount.
- Syscall-heavy builds (`npm ci`, `composer install`, native compiles) run
  slower (~10–30% more CPU time); plain compute is near-parity.
- Socket-based debuggers (xdebug, Node inspector) work fine.

## Security notes

- Docker access in the workspace = **root-equivalent on the target daemon**
  (TLS client certs). With the shared isolated daemon, that's root on the
  **nested daemon**, not the host — still, treat it as privileged. The gVisor
  sandbox protects the workspace *processes*, NOT the containers the developer
  spawns (those are plain runc). Do not use this template for untrusted
  workspaces.
- **To deny Docker entirely, push with `docker_enabled = false`** (see
  above) — no cert mount, no `DOCKER_*` env, nothing to connect with.
- Never add `docker system prune` / daemon-wide cleanup to a shutdown script:
  it would prune the shared daemon. For the shared daemon this wipes the
  *nested* daemon's containers (other workspaces' dev containers); for a
  host-daemon wiring it would prune the host's own apps (Coolify, n8n, Ghost,
  Postgres, Mailu, WordPress). There is deliberately no `shutdown_script`.
- The daemon must be reachable only via tailnet (never bind 2376 publicly).

## Parameters


| Parameter | Type | Default | Description |
|---|---|---|---|
| `docker_host` | `string` | `""` | Docker daemon URI. Empty = local Unix socket; **Standard remote: `tcp://<tailscale-ip>:2376` (shared isolated dind)** — see Prerequisites |
| `docker_ca` / `docker_cert` / `docker_key` | `string` (sensitive) | `""` | Remote only: daemon TLS material (PEM contents) — for the shared dind, the certs from `/certs/client` inside `workspace-docker` |
| `docker_enabled` | `bool` | `true` | **Set per template.** `false` = no cert mount and no `DOCKER_*` env — the docker CLI inside the workspace cannot reach the daemon. Use for templates where the developer should not see (or touch) containers |
| `docker_cert_dir` | `string` | `/certs/client` | Host path of the daemon's client TLS material (`ca.pem`/`cert.pem`/`key.pem`), mounted read-only into the workspace. Ignored when `docker_enabled` is `false` |
| `workspace_runtime` | `string` | `runsc` | **Per-workspace** parameter: `runsc` (gVisor) or `runc` (fallback). For the shared dind on cgroup v2, prefer `runc` — see G13 |
| `workspace_memory_gb` | `number` | `2` | Hard memory limit per workspace in GB (OOM-kill when exceeded; includes Sentry/Gofer overhead) |
| `workspace_cpus` | `number` | `2` | CPU limit per workspace in cores (throttled, not killed) |
| `repo_url` | `string` | `""` | Git repo to clone (empty = blank home) |
| `new_branch` | `string` | `""` | Branch to checkout/create after cloning |
| `setup_command` | `string` | `""` | Shell command run once on first start: install deps, `docker compose up -d`, seed data. Changing it re-runs on next start |
| `startup_command` | `string` | `""` | **Template-level.** Shell command baked into every workspace's agent startup, runs FIRST on every start, before per-workspace setup. Empty = no-op |


## Project setup flow (devcontainer alternative)

1. **Clone** — the git-clone module clones `repo_url` (GitHub auth wired in).
2. **Setup** — the "Project Setup" coder script runs `setup_command` once per
    value (marker file `~/.coder_setup_done`; delete it to force a re-run).
    Typical value: `make dev` or `./scripts/setup.sh` — repos own their
    bootstrap; no devcontainer spec file needed.
3. **Personalize** — Coder's built-in dotfiles feature (set the URL in your
    Coder profile) applies your shell/tooling config automatically; the
    code-server module gives VS Code in the browser.

Seeds/demo data: the project's compose file defines services (`postgres`,
`redis`, ...) — `docker compose up -d` from the workspace runs them **inside
the shared isolated daemon** (DooD); a `make seed` loads fixtures from inside
the sandbox.

## Template-level startup command (`startup_command`)

An **admin-defined** shell command baked into the template's agent startup —
applies to **every** workspace created from it, with no per-workspace input.
It runs FIRST, before the per-workspace `setup_command` / project setup. Use
it for things every workspace needs regardless of user (e.g. mount common
tools, set env, register a CA cert). It runs on **every** start, not just the
first.

Set it per template at push time:

```sh
coder templates push <name> ./templates/gvisor-docker \
  --var startup_command='echo "bootstrapping..."'
```

Empty (default) = no-op. Different templates pushed from the same source can
bake different startup commands. Note it is a **template variable** (fixed
per template), not a per-workspace parameter — for per-workspace choice, use
the `setup_command` parameter instead.

## Docker access inside the workspace (DooD over TLS)

gVisor **cannot relay connections through bind-mounted unix sockets**, so a
socket mount does NOT work in a runsc sandbox. Instead:

- the daemon's client certs (`ca.pem`/`cert.pem`/`key.pem`) are mounted
  read-only at `/certs/docker` from `docker_cert_dir` (on the shared dind
  this is `/certs/client`, generated by `docker:dind` — the fleet's standard;
  for a host-daemon wiring stage them at e.g. `/home/josh/coder-tls/<remote>/`)
- `coder_agent.env` sets `DOCKER_HOST=tcp://<tailscale-ip>:2376`,
  `DOCKER_TLS_VERIFY=1`, `DOCKER_CERT_PATH=/certs/docker` for every session

No secrets appear in scripts or logs — only paths and the endpoint.

Standard push (shared isolated dind on remote `100.107.165.73`):

```sh
coder templates push 24gb-169-58-gvisor-shared-docker \
  ./playbooks/coder-remote-servers/templates/gvisor-docker \
  --variables-file ./secrets/24gb-169-58/gvisor-shared-vars.yaml
# gvisor-shared-vars.yaml:
# docker_host: tcp://100.107.165.73:2376
# docker_ca: |
#   -----BEGIN CERTIFICATE----- ...
# docker_cert: |
#   -----BEGIN CERTIFICATE----- ...
# docker_key: |
#   -----BEGIN PRIVATE KEY----- ...
# docker_enabled: true
```

### Locking Docker off (`docker_enabled = false`)

Docker access in the workspace is **root-equivalent on the target daemon**
(`docker ps` shows every container on that daemon — with the shared dind,
that's other workspaces' dev containers). If a template's users must not see
or touch that, push the template with `docker_enabled = false`:

```sh
coder templates push gvisor-docker-locked ./templates/gvisor-docker \
  --var docker_enabled=false
```

That removes the cert mount **and** the `DOCKER_*` env vars: the docker CLI
inside the workspace cannot connect to anything. The sandbox still runs
normally (shell, code-server, git, project setup). Same template, different
config — enable Docker on trusted dev templates, disable it on locked-down
ones.

Note: `docker_enabled` is a **template variable**, so it is fixed per
template push, not per workspace. If you need per-workspace choice, make it a
`coder_parameter` like `workspace_runtime`.

### Ports — shared daemon vs Coder proxy (`host.docker.internal` vs `localhost`)

`gvisor-docker` is **DooD** (Docker outside of Docker): `docker run -p 3000:3000` creates a **sibling container on the shared isolated daemon** (`playbooks/coder-remote-servers/templates/workspace-docker.yml:15`), not a child inside the workspace netns. The port is published on the **dind host**, not on workspace `localhost`.

The Coder agent proxies `localhost:PORT` inside the **workspace** (`main.tf:496` `host.docker.internal=host-gateway`, `main.tf:308` `DOCKER_HOST` over TLS). So `curl localhost:3000` inside the workspace fails → Coder auto port-detect (which watches workspace `localhost`) sees nothing, and a `coder_app` with `url = "http://localhost:3000"` will 502 — this is **expected for DooD**, not a gVisor/`runc` limitation.

**Fix — make the daemon port visible on workspace `localhost`:**

```sh
# inside the workspace (runc or runsc, both use same DooD)
docker run -d --name myapp -p 3000:3000 myapp:latest
# publish on dind host; now expose it on workspace localhost via:
socat TCP-LISTEN:3000,reuseaddr,fork TCP:host.docker.internal:3000 &
# Coder now detects localhost:3000 and coder_app with localhost:3000 works
curl localhost:3000  # via socat
# or point a coder_app directly at the dind host:
# url = "http://host.docker.internal:3000" (no socat needed)
```

To verify: `docker ps` (on shared daemon) shows `0.0.0.0:3000->3000/tcp`, `ss -tlnp | grep 3000` inside workspace is empty, `docker exec workspace-docker ss -tlnp | grep 3000` shows the listener, `curl host.docker.internal:3000` works from workspace.

`docker-devcontainer` (`playbooks/coder-remote-servers/templates/docker-devcontainer/main.tf:17`) is **DiD** (per-workspace nested `dockerd`, `privileged=true`): `docker run -p 3000:3000` publishes directly on **workspace `localhost`** → Coder `localhost:3000` proxy works without `socat` or `host.docker.internal`. Use `docker-devcontainer` if you need transparent `localhost:PORT` for many services.

## Prerequisites (shared isolated daemon — standard)

1. **Deploy the shared isolated daemon** on the remote — one
   `workspace-docker` (`docker:dind`) container per remote, tailnet-only:
   ```yaml
   # templates/workspace-docker.yml — fill in the remote's Tailscale IP
   services:
     workspace-docker:
       image: docker:29.7.1-dind
       environment:
         DOCKER_TLS_CERTDIR: /certs
         DOCKER_TLS_SAN: "IP:<TAILSCALE_IP>"
       ports: ["<TAILSCALE_IP>:2376:2376"]
       privileged: true
       volumes:
         - workspace-docker-data:/var/lib/docker
         - workspace-docker-certs-ca:/certs/ca
         - workspace-docker-certs-client:/certs/client
   ```
   Deploy via the remote's Dokploy/Coolify UI. The inner daemon's certs are
   generated automatically; extract the client certs from
   `/certs/client` inside the container (see playbook Phase 4). No `runsc`
   needed in the dind for the standard `runc` workspaces — bake it only if you
   intend to offer `runsc` on the shared daemon (and see G13 for the cgroup
   v2 limitation).

2. **Push the template** with the TLS material as sensitive template
   variables (`docker_host`, `docker_ca`, `docker_cert`, `docker_key`) from
   the extracted certs. The three cert variables are marked `sensitive` —
   Coder stores them encrypted.

### Alternative: host daemon (only if you need `runsc` on cgroup v2)

On unified cgroup v2 hosts, `runsc` **cannot** run inside the shared dind
(G13). If you need `runsc` workspaces, point the template at the **host**
daemon instead: TLS listener on the tailnet IP at a **different port** (e.g.
`tcp://<ts-ip>:2378` — 2377 is Docker Swarm's manager port, G14), `runsc`
installed and registered in the host's `/etc/docker/daemon.json`:
```json
{
  "runtimes": {
    "runsc": { "path": "/usr/local/bin/runsc" }
  }
}
```
Install a current `runsc` from the GitHub release tarball
(`gvisor-x86_64.tar.bz2`, needs `bzip2` — the `.../release/latest/runsc`
URLs are stale, G15).

## Devcontainer note

The devcontainers-cli module is intentionally NOT included: devcontainers
spawned through a shared daemon socket compete for control of the daemon
(Coder recommends against this). Use plain shells / code-server, or run
containers manually with `docker compose`.

## Resource limits

`workspace_memory_gb` (default `2`) and `workspace_cpus` (default `2`) are
**template variables** — set once per template, applied to every workspace
it creates. Limits are kernel-enforced via cgroups and work identically for
runc and runsc:

- **Memory**: hard limit in GB. A workspace that exceeds it is OOM-killed
  (the runsc Sentry + Gofer count toward it, as they share the cgroup). No
  swap.
- **CPU**: cgroup quota (cores, e.g. `"1.5"`) — throttled, never killed.

Set higher defaults (e.g. `4`) when provisioning on hosts with spare RAM, or
keep them modest to fit more concurrent workspaces. (If per-workspace sizing
is ever needed, these can become `coder_parameter`s like `workspace_runtime`.)

## Verify a workspace

```sh
coder ping <workspace>            # agent connectivity
coder ssh <workspace>             # shell into the sandbox
# inside the workspace:
docker ps                        # talks to the shared isolated daemon over TLS (DooD)
docker run --rm hello-world      # spawns a runc container inside the shared daemon
uname -r                         # 4.19.0-gvisor inside the sandbox, generic kernel on runc
```
