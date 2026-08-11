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
# local template.
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
