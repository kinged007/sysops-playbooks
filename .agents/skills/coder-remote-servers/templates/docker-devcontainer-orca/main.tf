terraform {
  required_providers {
    coder = {
      source = "coder/coder"
    }
    docker = {
      source = "kreuzwerker/docker"
    }
  }
}

locals {
  username = data.coder_workspace_owner.me.name

  # Use a workspace image that supports rootless Docker
  # (Docker-in-Docker) and Node.js. Default tooling like npm, python,
  # uv, gh (GitHub CLI), go, and rust is ensured at workspace start via
  # startup_script (installed if missing).
  workspace_image = "codercom/enterprise-node:ubuntu"

  has_repo           = data.coder_parameter.repo_url.value != ""
  repo_folder        = try(module.git-clone[0].folder_name, "")
  code_server_folder = local.has_repo ? "/home/coder/${local.repo_folder}" : "/home/coder"
}

# ------------------------------------------------------------------
# Docker daemon endpoint selection.
#
# LOCAL workspaces: leave docker_host empty (""). The provider falls
# back to the local Unix socket (/var/run/docker.sock) on the machine
# running the build — i.e. the Coder server's Docker daemon.
#
# REMOTE workspaces (this repo's remote-a/b/c): set
#   docker_host     = "tcp://<tailscale-ip>:2376"
#   docker_ca       = contents of the remote's ca.pem
#   docker_cert     = contents of the remote's cert.pem
#   docker_key      = contents of the remote's key.pem
#
# The cert material is passed as PEM CONTENTS via these variables — no
# files need to be mounted into the Coder container. Marked sensitive so
# they're encrypted at rest and never shown in the UI.
# ------------------------------------------------------------------

variable "docker_host" {
  default     = ""
  description = "(Optional) Docker daemon URI. Empty = local Unix socket. Remote: tcp://<tailscale-ip>:2376"
  type        = string
}

variable "docker_ca" {
  default     = ""
  description = "(Remote only) Docker CA certificate PEM contents"
  type        = string
  sensitive   = true
}

variable "docker_cert" {
  default     = ""
  description = "(Remote only) Docker client certificate PEM contents"
  type        = string
  sensitive   = true
}

variable "docker_key" {
  default     = ""
  description = "(Remote only) Docker client private key PEM contents"
  type        = string
  sensitive   = true
}

# ------------------------------------------------------------------
# Template-level startup command.
#
# Baked into the agent startup script (applies to ALL workspaces from
# this template). Runs FIRST, before any per-workspace setup (the
# repo clone / devcontainer startup / setup-devcontainer script).
# Set per template at push time. Empty = no-op.
# ------------------------------------------------------------------

variable "startup_command" {
  default     = ""
  description = "(Template-level) Shell command baked into every workspace's agent startup. Runs first, before per-workspace setup. Empty = no-op."
  type        = string
}

# ------------------------------------------------------------------
# ORCA experiment: publish the in-workspace Orca server port on the
# Docker host. Set to the host's Tailscale IP at push time so the port
# is reachable ONLY from the tailnet — never the public internet.
# (Same constrained-bind pattern as workspace-docker.yml.)
# Empty = no published port (pure base-template behaviour).
# ------------------------------------------------------------------

variable "orca_publish_ip" {
  default     = ""
  description = "(Orca experiment) Docker-host IP to publish the workspace Orca server on, e.g. the host's Tailscale IP. Empty = no published port."
  type        = string
}

data "coder_parameter" "orca_port" {
  type         = "number"
  name         = "orca_port"
  display_name = "Orca server host port"
  description  = "Host port publishing this workspace's Orca server (container 6768). Must be free on the Docker host — one Orca workspace per port."
  default      = 6769
  mutable      = true
}

data "coder_parameter" "repo_url" {
  type         = "string"
  name         = "repo_url"
  display_name = "Git Repository"
  description  = "Enter the URL of a Git repository to clone. If provided, the workspace will clone it and attempt to start a devcontainer. Leave empty to skip cloning and work in the home directory."
  default      = ""
  mutable      = true
}

data "coder_parameter" "new_branch" {
  type         = "string"
  name         = "new_branch"
  display_name = "New Branch Name"
  description  = "Optional: after cloning, checkout or create this branch. If the branch does not exist, it will be created from HEAD. Useful for starting work on a new feature branch."
  default      = ""
  mutable      = true
}

provider "docker" {
  # Local: empty docker_host -> use the default Unix socket.
  # Remote: docker_host set -> use TLS with the provided material.
  host = var.docker_host != "" ? var.docker_host : null

  ca_material   = var.docker_ca != "" ? var.docker_ca : null
  cert_material = var.docker_cert != "" ? var.docker_cert : null
  key_material  = var.docker_key != "" ? var.docker_key : null
}

data "coder_provisioner" "me" {}
data "coder_workspace" "me" {}
data "coder_workspace_owner" "me" {}

resource "coder_agent" "main" {
  arch           = data.coder_provisioner.me.arch
  os             = "linux"
  startup_script = <<-EOT
    set -e

    # Template-level startup command (applies to ALL workspaces from this
    # template). Runs first, before per-workspace setup. Set via the
    # template variable startup_command; empty = no-op.
    %{ if var.startup_command != "" }
    echo "Running template startup command..."
    ${var.startup_command}
    %{ endif }

    # Prepare user home with default files on first start.
    if [ ! -f ~/.init_done ]; then
      cp -rT /etc/skel ~
      touch ~/.init_done
    fi

    # Ensure GitHub CLI (gh) is installed — required by default like npm, python, uv, go, rust.
    # Tries apt (privileged container with sudo) first, falls back to binary download
    # to $HOME/.local/bin so it also works without sudo.
    if ! command -v gh >/dev/null 2>&1; then
      echo "Installing GitHub CLI (gh)..."
      if command -v apt-get >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
        echo "Attempting apt install for gh..."
        sudo mkdir -p /usr/share/keyrings 2>/dev/null || true
        curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg 2>/dev/null && sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg 2>/dev/null || true
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null 2>/dev/null || true
        sudo apt-get update -qq 2>/dev/null && sudo apt-get install -y gh -qq 2>/dev/null && echo "gh installed via apt" || echo "apt install failed, trying binary..."
      fi
      if ! command -v gh >/dev/null 2>&1; then
        echo "Installing gh via binary download..."
        mkdir -p $HOME/.local/bin
        GH_VERSION=$(curl -fsSL https://api.github.com/repos/cli/cli/releases/latest 2>/dev/null | grep '"tag_name":' | sed -E 's/.*"v([^"]+)".*/\1/' 2>/dev/null || echo "2.78.0")
        ARCH=$(uname -m); case $ARCH in x86_64) ARCH="amd64" ;; aarch64|arm64) ARCH="arm64" ;; *) ARCH="amd64" ;; esac
        curl -fsSL "https://github.com/cli/cli/releases/download/v"$GH_VERSION"/gh_"$GH_VERSION"_linux_"$ARCH".tar.gz" -o /tmp/gh.tar.gz 2>/dev/null && tar -xzf /tmp/gh.tar.gz -C /tmp 2>/dev/null && mv /tmp/gh_"$GH_VERSION"_linux_"$ARCH"/bin/gh $HOME/.local/bin/gh 2>/dev/null && chmod +x $HOME/.local/bin/gh 2>/dev/null && rm -rf /tmp/gh.tar.gz /tmp/gh_"$GH_VERSION"_linux_"$ARCH" 2>/dev/null && echo "gh installed to $HOME/.local/bin/gh" || echo "Warning: gh binary install failed"
        export PATH="$HOME/.local/bin:$PATH"
        # Ensure future shells have gh on PATH
        grep -q 'HOME/.local/bin' $HOME/.bashrc 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> $HOME/.bashrc 2>/dev/null || true
      fi
      if command -v gh >/dev/null 2>&1; then
        echo "gh installed: $(gh --version 2>/dev/null | head -n1)"
      else
        echo "Warning: gh installation failed - check network or install manually"
      fi
    else
      echo "gh already installed: $(gh --version 2>/dev/null | head -n1)"
    fi
    # Ensure $HOME/.local/bin is on PATH for this session if gh was installed there
    export PATH="$HOME/.local/bin:$PATH"

    # Ensure uv is installed — Python package manager (astral.sh/uv)
    if ! command -v uv >/dev/null 2>&1; then
      echo "Installing uv..."
      if command -v pipx >/dev/null 2>&1; then
        pipx install uv 2>/dev/null && echo "uv installed via pipx" || echo "pipx install failed, trying standalone..."
      fi
      if ! command -v uv >/dev/null 2>&1; then
        echo "Installing uv via standalone installer..."
        mkdir -p $HOME/.local/bin 2>/dev/null || true
        curl -LsSf https://astral.sh/uv/install.sh 2>/dev/null | sh 2>/dev/null && echo "uv installed via astral.sh" || echo "Warning: uv standalone install failed"
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
        grep -q 'HOME/.local/bin' $HOME/.bashrc 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$PATH"' >> $HOME/.bashrc 2>/dev/null || true
      fi
      if command -v uv >/dev/null 2>&1; then
        echo "uv installed: $(uv --version 2>/dev/null | head -n1)"
      else
        echo "Warning: uv installation failed - check network or install manually"
      fi
    else
      echo "uv already installed: $(uv --version 2>/dev/null | head -n1)"
    fi
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

    # Ensure Go is installed — https://go.dev
    if ! command -v go >/dev/null 2>&1; then
      echo "Installing Go..."
      mkdir -p $HOME/.local/bin $HOME/.local/go 2>/dev/null || true
      GO_VERSION=$(curl -fsSL https://go.dev/VERSION?m=text 2>/dev/null | head -n1 | sed 's/go//' 2>/dev/null || echo "1.24.3")
      ARCH=$(uname -m); case $ARCH in x86_64) ARCH="amd64" ;; aarch64|arm64) ARCH="arm64" ;; *) ARCH="amd64" ;; esac
      echo "Downloading Go v"$GO_VERSION" for linux_"$ARCH"..."
      curl -fsSL "https://go.dev/dl/go"$GO_VERSION".linux_"$ARCH".tar.gz" -o /tmp/go.tar.gz 2>/dev/null && tar -xzf /tmp/go.tar.gz -C /tmp 2>/dev/null && rm -rf $HOME/.local/go 2>/dev/null && mv /tmp/go $HOME/.local/go 2>/dev/null && rm -rf /tmp/go.tar.gz 2>/dev/null && echo "Go installed to $HOME/.local/go" || echo "Go tarball install failed, trying apt..."
      if ! command -v go >/dev/null 2>&1 && [ -x "$HOME/.local/go/bin/go" ]; then
        export PATH="$HOME/.local/go/bin:$PATH"
        grep -q 'HOME/.local/go/bin' $HOME/.bashrc 2>/dev/null || echo 'export PATH="$HOME/.local/go/bin:$PATH"' >> $HOME/.bashrc 2>/dev/null || true
      fi
      if ! command -v go >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
        echo "Attempting apt install for Go..."
        sudo apt-get update -qq 2>/dev/null && sudo apt-get install -y golang-go -qq 2>/dev/null && echo "Go installed via apt" || echo "apt Go install failed"
      fi
      export PATH="$HOME/.local/go/bin:$HOME/go/bin:$PATH"
      if command -v go >/dev/null 2>&1; then
        echo "Go installed: $(go version 2>/dev/null | head -n1)"
      else
        echo "Warning: Go installation failed - check network or install manually"
      fi
    else
      echo "Go already installed: $(go version 2>/dev/null | head -n1)"
    fi
    export PATH="$HOME/.local/go/bin:$HOME/go/bin:$PATH"

    # Ensure Rust is installed — https://rustup.rs
    if ! command -v rustc >/dev/null 2>&1 && ! command -v cargo >/dev/null 2>&1; then
      echo "Installing Rust (rustup)..."
      mkdir -p $HOME/.cargo/bin 2>/dev/null || true
      curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs 2>/dev/null | sh -s -- -y --no-modify-path --default-toolchain stable --profile minimal 2>/dev/null && echo "Rust installed via rustup" || echo "Warning: rustup install failed"
      export PATH="$HOME/.cargo/bin:$PATH"
      grep -q 'HOME/.cargo/bin' $HOME/.bashrc 2>/dev/null || echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> $HOME/.bashrc 2>/dev/null || true
      if command -v rustc >/dev/null 2>&1; then
        echo "Rust installed: $(rustc --version 2>/dev/null | head -n1) $(cargo --version 2>/dev/null | head -n1)"
      else
        echo "Warning: Rust installation failed - check network or install manually"
      fi
    else
      echo "Rust already installed: $(rustc --version 2>/dev/null | head -n1) $(cargo --version 2>/dev/null | head -n1)"
    fi
    export PATH="$HOME/.cargo/bin:$PATH"
    # Ensure all toolchain bins are on PATH for this session
    export PATH="$HOME/.local/bin:$HOME/.local/go/bin:$HOME/go/bin:$HOME/.cargo/bin:$PATH"

    # Add any commands that should be executed at workspace startup
    # (e.g. install requirements, start a program, etc) here.

    # ORCA experiment: self-heal the Orca server after rebuild/reboot.
    # Rebuild wipes /opt (system layer); $HOME persists. Reinstall the .deb
    # when orca-ide is missing, then (re)start serve via nohup (no systemd
    # in containers). Pairing address = host tailnet IP + published ext
    # port; internal bind stays 6768. Idempotent: skips a live listener.
    # NOTE: the advertised host IP is baked at template push time via
    # var.orca_publish_ip (same var as the docker publish). If the host
    # tailnet IP changes, push the template with the new IP and restart.
    %{ if var.orca_publish_ip != "" }
    (
      export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
      if ! command -v orca-ide >/dev/null 2>&1; then
        echo "Orca missing after rebuild — reinstalling..."
        ORCA_VER=$(curl -fsSL https://api.github.com/repos/stablyai/orca/releases/latest | grep -m1 '"tag_name"' | cut -d'"' -f4 | tr -d v) || ORCA_VER="1.4.200"
        cd /tmp && curl -fsSLO "https://github.com/stablyai/orca/releases/download/v$${ORCA_VER}/orca-ide_$${ORCA_VER}_amd64.deb" \
          && sudo dpkg -i "orca-ide_$${ORCA_VER}_amd64.deb" \
          && sudo apt-get install -f -y \
          && sudo apt-get install -y libasound2t64 libnss3 libnspr4 libatk1.0-0t64 libatk-bridge2.0-0t64 libcups2t64 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libgtk-3-0 libnotify4 libxss1 libxtst6 xdg-utils libatspi2.0-0 libsecret-1-0 \
          && echo "Orca reinstalled: $(orca-ide --version 2>/dev/null)" \
          || echo "WARNING: Orca reinstall failed — start orca-ide serve manually"
      fi
      if command -v orca-ide >/dev/null 2>&1; then
        if (ss -tln 2>/dev/null || netstat -tln 2>/dev/null) | grep -q ':6768 '; then
          echo "Orca serve already listening on 6768 — leaving it alone"
        else
          echo "Starting orca-ide serve (advertise ${var.orca_publish_ip}:${data.coder_parameter.orca_port.value})..."
          setsid nohup orca-ide serve --port 6768 --pairing-address ${var.orca_publish_ip}:${data.coder_parameter.orca_port.value} > "$HOME/.orca-serve.out" 2>&1 < /dev/null &
          sleep 12
          grep -a -E "Bound endpoint|Advertised endpoint" "$HOME/.orca-serve.out" | head -4 || echo "WARNING: serve log has no endpoints yet — check ~/.orca-serve.out"
        fi
      fi
    )
    %{ endif }

    # ORCA experiment: `preview` shell helper — print this workspace's Coder
    # preview URL for a local port (usage: preview 5173). Compensates for
    # Orca terminal links opening client-localhost: Orca does not honour
    # VSCODE_PROXY_URI (verified: absent from the Orca binary), while Coder's
    # code-server module always sets that var. Idempotent ~/.bashrc install.
    if ! grep -q 'preview() {' $HOME/.bashrc 2>/dev/null; then
      cat >> $HOME/.bashrc << 'PREVIEW_EOF' 2>/dev/null || true
# preview <port> — print this workspace's Coder preview URL for a local port.
preview() { echo "$${VSCODE_PROXY_URI//'{{port}}'/$1}"; }
PREVIEW_EOF
      echo "preview helper installed in ~/.bashrc"
    fi
  EOT
  # NOTE: no shutdown_script by design. A previous version ran
  # `docker system prune -a -f` + `sudo service docker stop` at shutdown.
  # That is only safe while the workspace's docker CLI talks to its OWN
  # nested daemon. Once a host docker socket is mounted into workspaces
  # (DooD), a shutdown prune would wipe HOST containers/images
  # (Coolify, n8n, Ghost, Postgres, ...). Never run daemon-wide docker
  # cleanup from a workspace.

  # These environment variables allow you to make Git commits right away after creating a
  # workspace. Note that they take precedence over configuration defined in ~/.gitconfig!
  # You can remove this block if you'd prefer to configure Git manually or using
  # dotfiles. (see docs/dotfiles.md)
  env = {
    GIT_AUTHOR_NAME     = coalesce(data.coder_workspace_owner.me.full_name, data.coder_workspace_owner.me.name)
    GIT_AUTHOR_EMAIL    = "${data.coder_workspace_owner.me.email}"
    GIT_COMMITTER_NAME  = coalesce(data.coder_workspace_owner.me.full_name, data.coder_workspace_owner.me.name)
    GIT_COMMITTER_EMAIL = "${data.coder_workspace_owner.me.email}"
  }

  # The following metadata blocks are optional. They are used to display
  # information about your workspace in the dashboard. You can remove them
  # if you don't want to display any information.
  # For basic resources, you can use the `coder stat` command.
  # If you need more control, you can write your own script.
  metadata {
    display_name = "CPU Usage"
    key          = "0_cpu_usage"
    script       = "coder stat cpu"
    interval     = 10
    timeout      = 1
  }

  metadata {
    display_name = "RAM Usage"
    key          = "1_ram_usage"
    script       = "coder stat mem"
    interval     = 10
    timeout      = 1
  }

  metadata {
    display_name = "Home Disk"
    key          = "3_home_disk"
    script       = "coder stat disk --path $${HOME}"
    interval     = 60
    timeout      = 1
  }

  metadata {
    display_name = "CPU Usage (Host)"
    key          = "4_cpu_usage_host"
    script       = "coder stat cpu --host"
    interval     = 10
    timeout      = 1
  }

  metadata {
    display_name = "Memory Usage (Host)"
    key          = "5_mem_usage_host"
    script       = "coder stat mem --host"
    interval     = 10
    timeout      = 1
  }

  metadata {
    display_name = "Load Average (Host)"
    key          = "6_load_host"
    # get load avg scaled by number of cores
    script   = <<EOT
      echo "`cat /proc/loadavg | awk '{ print $1 }'` `nproc`" | awk '{ printf "%0.2f", $1/$2 }'
    EOT
    interval = 60
    timeout  = 1
  }

  metadata {
    display_name = "Swap Usage (Host)"
    key          = "7_swap_host"
    script       = <<EOT
      free -b | awk '/^Swap/ { printf("%.1f/%.1f", $3/1024.0/1024.0/1024.0, $2/1024.0/1024.0/1024.0) }'
    EOT
    interval     = 10
    timeout      = 1
  }
}

resource "coder_script" "init_docker_in_docker" {
  count        = data.coder_workspace.me.start_count
  agent_id     = coder_agent.main.id
  display_name = "Initialize Docker-in-Docker"
  run_on_start = true
  icon         = "/icon/docker.svg"
  script       = file("${path.module}/scripts/init-docker-in-docker.sh")
}

# See https://registry.coder.com/modules/coder/devcontainers-cli
module "devcontainers-cli" {
  count    = data.coder_workspace.me.start_count
  source   = "registry.coder.com/coder/devcontainers-cli/coder"
  agent_id = coder_agent.main.id

  # This ensures that the latest non-breaking version of the module gets
  # downloaded, you can also pin the module version to prevent breaking
  # changes in production.
  version = "~> 1.0"
}

# See https://registry.coder.com/modules/coder/code-server
module "code-server" {
  count    = data.coder_workspace.me.start_count
  source   = "registry.coder.com/coder/code-server/coder"
  version  = "1.5.0"
  agent_id = coder_agent.main.id
  folder     = local.code_server_folder
  extensions = [
    "dracula-theme.theme-dracula",
    "cweijan.vscode-database-client2",
    "ms-vscode.live-server",
    "mathematic.vscode-pdf"
  ]
}

# See https://registry.coder.com/modules/coder/git-clone
module "git-clone" {
  count    = data.coder_workspace.me.start_count * (local.has_repo ? 1 : 0)
  source   = "registry.coder.com/coder/git-clone/coder"
  agent_id = coder_agent.main.id
  url      = data.coder_parameter.repo_url.value
  base_dir = "~"
  # This ensures that the latest non-breaking version of the module gets
  # downloaded, you can also pin the module version to prevent breaking
  # changes in production.
  version = "~> 2.0"
}

# Enables git authentication for cloning PRIVATE repositories.
#
# Without this, cloning a private repo fails with:
#   fatal: unable to access 'https://github.com/<owner>/<repo>.git/':
#   The requested URL returned error: 403
# ("Write access to repository not granted").
#
# This requires a Git provider configured in Coder:
#   Admin -> External Auth -> "GitHub" -> enabled for this template.
# On first workspace start Coder then prompts the user to connect GitHub,
# and the git-clone module uses that token to clone.
#
# Leave the repo_url parameter EMPTY to skip cloning entirely (no prompt).
data "coder_external_auth" "github" {
  id = "github"
}

# Automatically set up the devcontainer for the workspace.
resource "coder_script" "setup_devcontainer" {
  count        = data.coder_workspace.me.start_count
  agent_id     = coder_agent.main.id
  display_name = "Setup Devcontainer"
  run_on_start = true
  icon         = "/icon/docker.svg"
  script       = templatefile("${path.module}/scripts/setup-devcontainer.sh", {
    repo_url    = data.coder_parameter.repo_url.value
    new_branch  = data.coder_parameter.new_branch.value
    repo_folder = local.repo_folder
  })
}

resource "docker_volume" "home_volume" {
  name = "coder-${data.coder_workspace.me.id}-home"
  # Protect the volume from being deleted due to changes in attributes.
  lifecycle {
    ignore_changes = all
  }
  # Add labels in Docker to keep track of orphan resources.
  labels {
    label = "coder.owner"
    value = data.coder_workspace_owner.me.name
  }
  labels {
    label = "coder.owner_id"
    value = data.coder_workspace_owner.me.id
  }
  labels {
    label = "coder.workspace_id"
    value = data.coder_workspace.me.id
  }
  # This field becomes outdated if the workspace is renamed but can
  # be useful for debugging or cleaning out dangling volumes.
  labels {
    label = "coder.workspace_name_at_creation"
    value = data.coder_workspace.me.name
  }
}

resource "docker_volume" "docker_volume" {
  name = "coder-${data.coder_workspace.me.id}-docker"
  # Protect the volume from being deleted due to changes in attributes.
  lifecycle {
    ignore_changes = all
  }
  # Add labels in Docker to keep track of orphan resources.
  labels {
    label = "coder.owner"
    value = data.coder_workspace_owner.me.name
  }
  labels {
    label = "coder.owner_id"
    value = data.coder_workspace_owner.me.id
  }
  labels {
    label = "coder.workspace_id"
    value = data.coder_workspace.me.id
  }
  # This field becomes outdated if the workspace is renamed but can
  # be useful for debugging or cleaning out dangling volumes.
  labels {
    label = "coder.workspace_name_at_creation"
    value = data.coder_workspace.me.name
  }
}

resource "docker_container" "workspace" {
  count = data.coder_workspace.me.start_count
  image = local.workspace_image

  # NOTE: The `privileged` mode is one way to run Docker-in-Docker,
  # which is required for the devcontainer to work. If this is not
  # desired, you can remove this line. However, you will need to ensure
  # that the devcontainer can run Docker commands in some other way.
  # Mounting the host Docker socket is strongly discouraged because
  # workspaces will then compete for control of the devcontainers.
  # For more information, see:
  # https://coder.com/docs/admin/templates/extending-templates/docker-in-workspaces
  privileged = true

  # ORCA experiment: publish container 6768 (Orca serve) as host
  # <dind-container>:6769/tcp. NOTE: the Docker daemon here is the dind
  # container, whose netns does NOT have the VPS host IPs — so bind ALL
  # dind-container interfaces (0.0.0.0), then DNAT host
  # tailscale0:6769 to it on the VPS (see experiment notes). Binding a
  # host IP here fails with "cannot assign requested address".
  # Only present when var.orca_publish_ip is non-empty (kept as the
  # on/off switch + documents the intended public face).
  dynamic "ports" {
    for_each = var.orca_publish_ip != "" ? [1] : []
    content {
      internal = 6768
      external = data.coder_parameter.orca_port.value
      ip       = "0.0.0.0"
      protocol = "tcp"
    }
  }

  # Uses lower() to avoid Docker restriction on container names.
  name = "coder-${data.coder_workspace_owner.me.name}-${lower(data.coder_workspace.me.name)}"
  # Hostname makes the shell more user friendly: coder@my-workspace:~$
  hostname = data.coder_workspace.me.name
  # Use the docker gateway if the access URL is 127.0.0.1
  command = ["sh", "-c", replace(coder_agent.main.init_script, "/localhost|127\\.0\\.0\\.1/", "host.docker.internal")]
  env = [
    "CODER_AGENT_TOKEN=${coder_agent.main.token}"
  ]
  host {
    host = "host.docker.internal"
    ip   = "host-gateway"
  }

  # Workspace home volume persists user data across workspace restarts.
  volumes {
    container_path = "/home/coder"
    volume_name    = docker_volume.home_volume.name
    read_only      = false
  }

  # Workspace docker volume persists Docker data across workspace
  # restarts, allowing the devcontainer cache to be reused.
  volumes {
    container_path = "/var/lib/docker"
    volume_name    = docker_volume.docker_volume.name
    read_only      = false
  }

  # Add labels in Docker to keep track of orphan resources.
  labels {
    label = "coder.owner"
    value = data.coder_workspace_owner.me.name
  }
  labels {
    label = "coder.owner_id"
    value = data.coder_workspace_owner.me.id
  }
  labels {
    label = "coder.workspace_name"
    value = data.coder_workspace.me.name
  }
}
