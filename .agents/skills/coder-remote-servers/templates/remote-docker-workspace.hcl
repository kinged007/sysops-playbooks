terraform {
  required_providers {
    coder = {
      source = "coder/coder"
    }

    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 4.5"
    }
  }
}

# ------------------------------------------------------------------
# Remote Docker daemon endpoint + mutual-TLS material.
#
# One template per remote server. The variable VALUES are set at the
# template level (sensitive) — see playbooks/coder-remote-servers/playbook.md.
# The cert/key are NEVER committed to this repo; they live only in
# Coder's encrypted template variable store.
# ------------------------------------------------------------------

variable "docker_host" {
  description = "Docker daemon endpoint (tcp://<tailscale-ip>:2376)"
  type        = string
}

variable "docker_ca" {
  description = "Docker CA certificate (contents of ca.pem)"
  type        = string
  sensitive   = true
}

variable "docker_cert" {
  description = "Docker client certificate (contents of cert.pem)"
  type        = string
  sensitive   = true
}

variable "docker_key" {
  description = "Docker client private key (contents of key.pem)"
  type        = string
  sensitive   = true
}

# ------------------------------------------------------------------
# Workspace image + resource sizing. Adjust to match your existing
# local template. Default tooling like npm, python, uv, gh
# (GitHub CLI), go, and rust is ensured at workspace start via
# startup_script (installed if missing — see ../scripts/install-*.sh).
# ------------------------------------------------------------------

variable "docker_image" {
  description = "What Docker image would you like to use for your workspace?"
  default     = "codercom/universal:latest"
}

variable "home_directory" {
  description = "Container home directory, where /home/coder mounts"
  default     = "/home/coder"
}

data "coder_provisioner" "me" {}
data "coder_workspace" "me" {}

provider "docker" {
  host = var.docker_host

  ca_material   = var.docker_ca
  cert_material = var.docker_cert
  key_material  = var.docker_key
}

resource "docker_image" "workspace" {
  name = var.docker_image
}

resource "docker_volume" "home_volume" {
  name = "coder-${data.coder_workspace.me.id}-home"
}

resource "coder_agent" "main" {
  arch = data.coder_provisioner.me.arch
  os   = "linux"

  startup_script = <<-EOT
    set -e

    # Ensure GitHub CLI (gh) is installed — required by default like npm, python, uv, go, rust.
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

    # install and start code-server
    if ! command -v code-server >/dev/null 2>&1; then
      echo "Installing code-server..."
      curl -fsSL https://code-server.dev/install.sh | sh -s -- --method=standalone --prefix=/tmp/code-server
    fi

    # start code-server
    /tmp/code-server/bin/code-server --auth none --port 13337 >/tmp/code-server.log 2>&1 &
  EOT

  metadata {
    display_name = "CPU Usage"
    interval     = 5
    timeout      = 5
    script       = "coder stat cpu"
  }

  metadata {
    display_name = "RAM Usage"
    interval     = 5
    timeout      = 5
    script       = "coder stat mem"
  }

  metadata {
    display_name = "Home Disk"
    interval     = 60
    timeout      = 5
    script       = "coder stat disk --path $${var.home_directory}"
  }
}

resource "coder_app" "code-server" {
  agent_id     = coder_agent.main.id
  slug         = "code-server"
  display_name = "VS Code"
  url          = "http://localhost:13337/?folder=$${var.home_directory}"
  icon         = "/icon/code.svg"
  subdomain    = false
  share        = "owner"
}

resource "docker_container" "workspace" {
  count = data.coder_workspace.me.start_count

  image = docker_image.workspace.name
  name  = "coder-${data.coder_workspace.me.id}"
  hostname = data.coder_workspace.me.name
  env = [
    "CODER_AGENT_TOKEN=${coder_agent.main.token}",
  ]
  volumes {
    container_path = var.home_directory
    volume_name    = docker_volume.home_volume.name
    read_only      = false
  }
}
