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
  # (Docker-in-Docker) and Node.js.
  workspace_image = "codercom/enterprise-node:ubuntu"

  has_repo           = data.coder_parameter.repo_url.value != ""
  repo_folder        = try(module.git-clone[0].folder_name, "")
  workspace_folder   = local.has_repo ? "~/${local.repo_folder}" : "~"
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
  arch            = data.coder_provisioner.me.arch
  os              = "linux"
  dir             = local.workspace_folder
  startup_script  = <<-EOT
    set -e

    # Prepare user home with default files on first start.
    if [ ! -f ~/.init_done ]; then
      cp -rT /etc/skel ~
      touch ~/.init_done
    fi

    # Add any commands that should be executed at workspace startup
    # (e.g. install requirements, start a program, etc) here.
  EOT
  shutdown_script = <<-EOT
    set -e

    # Clean up the docker volume from unused resources to keep storage
    # usage low.
    #
    # WARNING! This will remove:
    #   - all stopped containers
    #   - all networks not used by at least one container
    #   - all images without at least one container associated to them
    #   - all build cache
    docker system prune -a -f

    # Stop the Docker service.
    sudo service docker stop
  EOT

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
    "dracula-theme.theme-dracula"
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
