# gVisor Docker Workspaces (gvisor-docker)

Coder workspaces as **gVisor-sandboxed containers** (`runsc` runtime) on a
remote Docker daemon, with Docker-outside-of-Docker (DooD) support.

Same remote-connection model as `docker-devcontainer` (TLS to a tailnet-only
daemon endpoint), but the workspace itself runs inside a gVisor sandbox —
a user-space kernel boundary — instead of a privileged container.

## Why this template

| | docker-devcontainer | gvisor-docker |
|---|---|---|
| Workspace isolation | privileged container, host kernel | gVisor sandbox (Sentry intercepts syscalls) |
| Docker in workspace | nested daemon (DinD, privileged) | CLI over TLS (DooD) |
| Docker containers spawned by the dev | inside nested daemon | **host daemon, plain runc containers** |
| `privileged` mode | yes (required for DinD) | **never** |
| Resource overhead | + nested dockerd per workspace (~200–500MB) | + runsc Sentry+Gofer (~60–150MB) |

## runc vs runsc

Both runtimes run the **same container** (image, home volume, mounts,
lifecycle) — the difference is only *how its processes are executed*. runc and
runsc workspaces can coexist on one host, side by side (the runtime is a
per-workspace parameter).

| | runc | runsc (gVisor) |
|---|---|---|
| Isolation | namespaces + cgroups + seccomp — processes run **directly on the host kernel** | user-space kernel (Sentry) — every syscall intercepted/emulated; the workspace never touches the host kernel directly |
| Escape risk | kernel bug or misconfig = host compromise; root in container ≈ root on host | requires a gVisor vulnerability (much smaller, audited attack surface); root in sandbox ≈ root in sandbox |
| RAM per workspace | container only — measured ~2.3GB (incl. a 487MB project + page cache) | container + **60–150MB** (Sentry + Gofer) |
| CPU overhead | ~0% | ~10–30% more on syscall-heavy work (`npm ci`, `composer install`, native compiles); plain compute ≈ parity |
| Compatibility | everything: sudo, TUIs, gdb/strace, FUSE, raw sockets/ICMP | `sudo`/setuid broken, **opencode TUI does not render** (below), no ptrace/FUSE/raw sockets//dev/tun |
| Startup | fastest | +0.5–2s per container start |

**Honest note on isolation:** neither is "total". Both share host CPU/RAM
(cgroups) and — with this template — the docker client certs (root-equivalent
on the host daemon), through which a workspace can spawn **unsandboxed**
containers. runsc protects the workspace *processes*; it does not sandbox the
containers the developer spawns.

**TUI nuance:** the opencode TUI never renders under gVisor (upstream bug
sst/opencode#29802 — the renderer runs but writes no frames to the tty; headless
`opencode run`/`serve` are fine). Other TUIs (vim, nano, htop) DO work. If an
interactive TUI fails silently in a workspace, set `workspace_runtime = runc`
for that workspace — runsc stays the default for everyone else.

## Known gVisor limitations (inside the workspace)

- **The opencode TUI does not render under gVisor** (upstream bug
  sst/opencode#29802: the renderer runs but no frame is ever written to
  the tty; headless `opencode run`/`serve` work fine). Workaround: set
  `workspace_runtime = runc` for that workspace.
- `sudo` / setuid binaries do **not** work in a gVisor sandbox (sudo fails
  with "effective uid is not 0"). Use rootless tooling (nvm, pyenv, mise,
  asdf) or bake packages into the workspace image.
- No nested Docker daemon (dockerd inside the sandbox) — `docker compose up`
  etc. still work over TLS (DooD); containers land on the host daemon.
- No `privileged` containers, kernel modules, `/dev/kvm`, FUSE (`sshfs`),
  `/dev/net/tun` (WireGuard/OpenVPN clients), raw sockets/ICMP (`ping`,
  `tcpdump`), `iptables`, ptrace-based debugging (`gdb`, `strace`).
- Unix-socket bind mounts are unusable (gVisor cannot relay the connect) —
  which is why Docker access uses TLS instead of a socket mount.
- Syscall-heavy builds (`npm ci`, `composer install`, native compiles) run
  slower (~10–30% more CPU time); plain compute is near-parity.
- Socket-based debuggers (xdebug, Node inspector) work fine.

## Security notes

- Docker access in the workspace = **root-equivalent on that daemon** (TLS
  client certs). The gVisor sandbox protects the workspace *processes*, NOT
  the containers the developer spawns (those are plain runc). Do not use
  this template for untrusted workspaces.
- Never add `docker system prune` / daemon-wide cleanup to a shutdown script:
  it would prune the shared daemon (Coolify apps, n8n, Ghost, Postgres,
  Mailu, WordPress). There is deliberately no `shutdown_script`.
- The daemon must be reachable only via tailnet (never bind 2376 publicly).

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `docker_host` | `string` | `""` | Docker daemon URI. Empty = local Unix socket; Remote = `tcp://<tailscale-ip>:2376` |
| `docker_ca` / `docker_cert` / `docker_key` | `string` (sensitive) | `""` | Remote only: daemon TLS material (PEM contents) |
| `workspace_runtime` | `string` | `runsc` | **Per-workspace** parameter: `runsc` (gVisor) or `runc` (fallback). Daemon must have the runtime registered |
| `docker_cert_dir` | `string` | `/certs/client` | Host path of the daemon's client TLS material (`ca.pem`/`cert.pem`/`key.pem`), mounted read-only into the workspace |
| `repo_url` | `string` | `""` | Git repo to clone (empty = blank home) |
| `new_branch` | `string` | `""` | Branch to checkout/create after cloning |
| `setup_command` | `string` | `""` | Shell command run once on first start: install deps, `docker compose up -d`, seed data. Changing it re-runs on next start |

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
`redis`, ...) — `docker compose up -d` from the workspace runs them on the
host daemon (DooD); a `make seed` loads fixtures from inside the sandbox.

## Docker access inside the workspace (DooD over TLS)

gVisor **cannot relay connections through bind-mounted unix sockets**, so a
socket mount does NOT work in a runsc sandbox. Instead:

- the daemon's client certs (`ca.pem`/`cert.pem`/`key.pem`) are mounted
  read-only at `/certs/docker` from `docker_cert_dir` (on the daemon host —
  for the dind test layout this is `/certs/client`, generated by docker:dind)
- `coder_agent.env` sets `DOCKER_HOST=tcp://<tailscale-ip>:2376`,
  `DOCKER_TLS_VERIFY=1`, `DOCKER_CERT_PATH=/certs/docker` for every session

No secrets appear in scripts or logs — only paths and the endpoint.

## Prerequisites (remote daemon host)

1. `runsc` installed and registered in the daemon's `/etc/docker/daemon.json`
   (the daemon that creates workspace containers must know the runtime):
   ```json
   {
     "runtimes": {
       "runsc": { "path": "/usr/local/bin/runsc" }
     }
   }
   ```
2. TLS listener on the tailnet IP only (`tcp://<ts-ip>:2376`), mTLS client
   certs staged at `docker_cert_dir`; template variables set from the client
   certs.

## Devcontainer note

The devcontainers-cli module is intentionally NOT included: devcontainers
spawned through a shared daemon socket compete for control of the daemon
(Coder recommends against this). Use plain shells / code-server, or run
containers manually with `docker compose`.

## Verify a workspace

```sh
coder ping <workspace>            # agent connectivity
coder ssh <workspace>             # shell into the sandbox
# inside the workspace:
docker ps                        # talks to the daemon over TLS (DooD)
docker run --rm hello-world      # spawns a runc container on the host
uname -r                         # shows 4.19.0-gvisor inside the sandbox
```
