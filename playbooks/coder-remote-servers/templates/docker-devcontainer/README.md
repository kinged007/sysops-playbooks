# Docker-in-Docker Dev Containers

Provision Docker containers as Coder workspaces with Docker-in-Docker support and optional Dev Containers. This template lets each developer get an isolated, full-featured development environment that can run VS Code, SSH, or any web-based IDE — with or without a Git repository and devcontainer configuration.

## Features

- **Docker-in-Docker** — each workspace runs its own Docker daemon inside a privileged container, so developers can build images, run containers, and use `docker compose` without affecting each other.
- **Optional Git clone + Dev Container** — provide a repository URL during workspace creation and the template will clone it and automatically run `devcontainer up` if a `devcontainer.json` is found. Leave the URL blank to get a plain home directory.
- **Code Server (VS Code in the browser)** — the [code-server](https://registry.coder.com/modules/coder/code-server) module is pre-configured with the Dracula theme. Available immediately in the workspace dashboard.
- **Persistent home volume** — `/home/coder` is backed by a Docker volume that survives workspace restarts.
- **Persistent Docker volume** — `/var/lib/docker` is persisted so devcontainer caches and pulled images are reused across restarts.
- **Startup & shutdown scripts** — Docker is cleaned up on stop (`docker system prune -a -f`) and the environment is initialised on start.
- **Git ready** — `GIT_AUTHOR_NAME` and `GIT_AUTHOR_EMAIL` are set automatically from the Coder user profile.
- **Resource monitoring** — CPU, RAM, disk, and host-level metrics are displayed in the workspace dashboard.

## Configuration Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `docker_host` | `string` | `""` | Docker daemon URI. **Empty = local Unix socket** (workspaces run on the Coder server's Docker). **Remote** = `tcp://<tailscale-ip>:2376` (workspaces run on a remote server over the tailnet with mutual TLS). |
| `docker_ca` | `string` (sensitive) | `""` | Remote only: contents of the remote daemon's `ca.pem`. |
| `docker_cert` | `string` (sensitive) | `""` | Remote only: contents of the remote daemon's `cert.pem`. |
| `docker_key` | `string` (sensitive) | `""` | Remote only: contents of the remote daemon's `key.pem`. |
| `repo_url` | `string` | `""` | URL of a Git repository to clone. If it contains a `devcontainer.json` (at the root or under `.devcontainer/`), the devcontainer CLI will start it automatically. Leave empty to skip cloning. |
| `new_branch` | `string` | `""` | Optional: after cloning, checkout or create this branch. |

## Local vs Remote workspaces

This template serves both deployment modes from the same code. The only
difference is the template-level variable values.

**Local** (workspaces on the Coder server's own Docker daemon):
```sh
coder templates push docker-devcontainer ./templates/docker-devcontainer
```
Leave `docker_host` empty. Builds use `/var/run/docker.sock`.

**Remote** (workspaces on a remote server, e.g. remote-a):
```sh
coder templates push "docker-devcontainer-remote-a" ./templates/docker-devcontainer \
  --var docker_host=tcp://<TAILSCALE_IP_REMOTE>:2376 \
  --var docker_ca="$(cat /home/<user>/coder-tls/remote-a/ca.pem)" \
  --var docker_cert="$(cat /home/<user>/coder-tls/remote-a/cert.pem)" \
  --var docker_key="$(cat /home/<user>/coder-tls/remote-a/key.pem)"
```
The three cert variables are marked **sensitive** — Coder stores them encrypted
and never displays them. No files are mounted into the Coder container.

See the playbook (`playbooks/coder-remote-servers/playbook.md`) and the
execution's `inventory.md` for each remote's endpoint + cert staging path.

## Modules Included

| Module | Version | Source |
|---|---|---|
| [devcontainers-cli](https://registry.coder.com/modules/coder/devcontainers-cli) | `~> 1.0` | `registry.coder.com/coder/devcontainers-cli/coder` |
| [code-server](https://registry.coder.com/modules/coder/code-server) | `1.5.0` | `registry.coder.com/coder/code-server/coder` |
| [git-clone](https://registry.coder.com/modules/coder/git-clone) | `~> 2.0` | `registry.coder.com/coder/git-clone/coder` |

### code-server

The [code-server module](https://registry.coder.com/modules/coder/code-server) provides VS Code in the browser via the workspace dashboard. It is pinned to version `1.5.0` and pre-configured with the Dracula theme (`dracula-theme.theme-dracula`).

To customise — add more extensions, change the theme, or pin a different version — edit the `module "code-server"` block in `main.tf`. Full configuration options are available at:

- **Registry reference:** https://registry.coder.com/modules/coder/code-server
- **Source:** https://github.com/coder/registry/tree/main/registry/coder/modules/code-server

## How to Use

### 1. Deploy the template

```sh
# From your Coder admin machine
coder templates push docker-devcontainer ./templates/docker-devcontainer
```

### 2. Create a workspace

In the Coder UI, click **Create Workspace**, select the **Docker-in-Docker Dev Containers** template, and optionally provide:

- **Git Repository** — the URL of a repo you want to clone (leave blank for a blank workspace)

Once the workspace is running, you'll see code-server available in the dashboard and can open a terminal or SSH in.

### 3. Bring your own devcontainer

If you provided a repository URL and that repo contains a `.devcontainer/devcontainer.json` or `.devcontainer.json`, the template will automatically run `devcontainer up` inside it. All standard devcontainer features (Docker-in-Docker, language runtimes, extensions, etc.) will be available. If the repo has **no** devcontainer config, it is skipped and you just get a terminal in the cloned repo.

### 3b. Cloning PRIVATE repositories

The template includes `data "coder_external_auth" "github"` so Coder can clone
repos you can access on GitHub. Two things must be true:

1. **A Git provider is configured in Coder:** Admin → External Auth → Git
   Providers → add/enable **GitHub**, and allow this template to use it.
2. **You connect GitHub once** — on first workspace start Coder shows a
   "Connect GitHub" prompt in the workspace build. Approve it; the clone then
   uses your token.

Without this you'll see:
```
fatal: unable to access 'https://github.com/<owner>/<repo>.git/': The requested URL returned error: 403
```
(That error is GitHub refusing an unauthenticated request to a private repo.)

If `repo_url` is left empty, no auth prompt and no clone — just a blank home.

### 4. Workspace lifecycle

- **Start** — Docker daemon is started, any repo is cloned, and the devcontainer is launched.
- **Stop** — unused Docker resources are pruned and the Docker service is stopped.
- **Delete** — the workspace container and both volumes (home + Docker) are destroyed.

## Prerequisites

The VM running Coder must have a running Docker socket and the `coder` user must be in the Docker group:

```sh
sudo adduser coder docker
sudo systemctl restart coder
sudo -u coder docker ps
```

> **Note** — This template is a starting point. Edit `main.tf` to add or remove modules, change the base image, adjust resource limits, or modify startup behaviour.
