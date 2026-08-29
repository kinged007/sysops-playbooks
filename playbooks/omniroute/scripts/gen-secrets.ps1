<#
.SYNOPSIS
  Generates all OmniRoute secrets/salts and writes them into the run's
  secrets/ folder (executions/<run>/secrets/). Local file writes only —
  no production write.

.DESCRIPTION
  Uses .NET RNG (no openssl dependency). Writes one file per secret plus a
  secrets/manifest.md with filenames, prefixes (first 8 chars), and a
  generation timestamp. Full values never appear in runbook or logs.

.PARAMETER SecretsDir
  Target secrets folder (default: <repo>/executions/<run>/secrets).
.PARAMETER RunTag
  Short tag used for the MCP key filename and env var name (e.g. "demo").
#>
param(
  [Parameter(Mandatory = $true)][string]$SecretsDir,
  [Parameter(Mandatory = $true)][string]$RunTag
)

$ErrorActionPreference = "Stop"
function New-RandomBase64([int]$Bytes) {
  $buf = New-Object byte[] $Bytes
  [System.Security.Cryptography.RandomNumberGenerator]::Fill($buf)
  return [Convert]::ToBase64String($buf)
}
function New-RandomHex([int]$Bytes) {
  $buf = New-Object byte[] $Bytes
  [System.Security.Cryptography.RandomNumberGenerator]::Fill($buf)
  return -join ($buf | ForEach-Object { $_.ToString("x2") })
}

if (-not (Test-Path $SecretsDir)) { New-Item -ItemType Directory -Path $SecretsDir -Force | Out-Null }

$secrets = [ordered]@{
  "INITIAL_PASSWORD"              = (New-RandomBase64 16)      # admin dashboard bootstrap
  "JWT_SECRET"                    = (New-RandomBase64 48)      # dashboard session cookies
  "API_KEY_SECRET"                = (New-RandomHex 32)         # AES at-rest for API keys
  "OMNIROUTE_WS_BRIDGE_SECRET"    = (New-RandomBase64 32)      # WS bridge (prod-required)
  "MACHINE_ID_SALT"               = (New-RandomHex 16)         # per-deployment fingerprint salt
  "OMNIROUTE_CLI_SALT"            = (New-RandomBase64 24)      # CLI token HMAC salt
  "STORAGE_ENCRYPTION_KEY"        = (New-RandomHex 32)         # optional SQLite at-rest (losing it = data loss)
}

$manifest = @()
$manifest += "# OmniRoute secrets manifest ($RunTag)"
$manifest += ""
$manifest += "Generated: $(Get-Date -Format o)"
$manifest += "Full values live in the files below (gitignored via executions/)."
$manifest += ""
$manifest += "| Secret file | Purpose | Prefix (first 8) |"
$manifest += "|---|---|---|"

foreach ($k in $secrets.Keys) {
  $v = $secrets[$k]
  $f = Join-Path $SecretsDir "$k.txt"
  Set-Content -Path $f -Value $v -NoNewline -Encoding utf8
  $prefix = if ($v.Length -ge 8) { $v.Substring(0, 8) } else { $v }
  $manifest += "| `secrets/$k.txt` | $k | ``$prefix`` |"
}

# Management MCP key is created later via the API (POST /api/keys) and stored
# here once returned. This file is reserved/absent until then.
$mcpKeyFile = Join-Path $SecretsDir "mcp-key-$RunTag.txt"
if (-not (Test-Path $mcpKeyFile)) {
  $manifest += "| `secrets/mcp-key-$RunTag.txt` | MCP Management-Access API key (created in step 8) | (pending) |"
}

$manifest += ""
$manifest += "## Usage notes"
$manifest += "- INITIAL_PASSWORD is for first dashboard login only; rotate after."
$manifest += "- Keep a backup of STORAGE_ENCRYPTION_KEY; losing it loses the DB."
$manifest += "- Never commit any file in this folder."

$manifestPath = Join-Path $SecretsDir "manifest.md"
Set-Content -Path $manifestPath -Value $manifest -Encoding utf8

Write-Output "Secrets written to $SecretsDir"
Get-ChildItem $SecretsDir | Select-Object Name, Length | Format-Table -AutoSize
