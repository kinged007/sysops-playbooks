<#
.SYNOPSIS
  Probes an OmniRoute instance's MCP endpoints using a Management-Access API
  key, and emits the per-variant MCP access artifact
  (executions/omniroute[/-<suffix>]/mcp/<tag>.mcp.json).

.DESCRIPTION
  Reads-only against the target. Checks:
    - GET  /api/mcp/status        (auth) -> 200
    - GET  /api/mcp/tools         (auth) -> 200 catalog
    - GET  /api/mcp/sse           (auth) -> 200 + SSE handshake (bounded)
    - POST /api/mcp/stream        (auth) -> 200 + mcp-session-id (if transport
      is streamable-http)
    - GET  /api/mcp/status        (anon) -> must NOT be 200 (LOCAL_ONLY gate)
  Writes logs/ and the mcp artifact.

.PARAMETER BaseUrl
  e.g. https://router.example.com  (no trailing slash)
.PARAMETER McpKeyFile
  Path to the secrets/mcp-key-<tag>.txt file containing the bearer key.
.PARAMETER OutDir
  executions/omniroute[/-<suffix>] folder (logs/ and mcp/ subfolders created).
.PARAMETER RunTag
  Short tag used in filenames and the env var name OMNIROUTE_MCP_KEY_<TAG>.
.PARAMETER Transport
  sse | streamable-http
#>
param(
  [Parameter(Mandatory = $true)][string]$BaseUrl,
  [Parameter(Mandatory = $true)][string]$McpKeyFile,
  [Parameter(Mandatory = $true)][string]$OutDir,
  [Parameter(Mandatory = $true)][string]$RunTag,
  [ValidateSet("sse", "streamable-http")][string]$Transport = "sse"
)

$ErrorActionPreference = "Stop"
$logDir = Join-Path $OutDir "logs"
$mcpDir = Join-Path $OutDir "mcp"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
New-Item -ItemType Directory -Path $mcpDir -Force | Out-Null

$key = (Get-Content $McpKeyFile -Raw).Trim()
if (-not $key) { throw "Empty key in $McpKeyFile" }

$log = @()
function Log($msg) { $script:log += $msg; Write-Output $msg }

$base = $BaseUrl.TrimEnd("/")

Log "== MCP reachability probe ($RunTag) at $base =="
Log "Transport: $Transport | key file: $McpKeyFile"

# 1. status (auth)
try {
  $r = Invoke-WebRequest -Uri "$base/api/mcp/status" -Headers @{ Authorization = "Bearer $key" } -UseBasicParsing -TimeoutSec 15
  Log "status (auth)       -> HTTP $($r.StatusCode)"
} catch { Log "status (auth)       -> ERR $($_.Exception.Message)" }

# 2. tools (auth)
try {
  $r = Invoke-WebRequest -Uri "$base/api/mcp/tools" -Headers @{ Authorization = "Bearer $key" } -UseBasicParsing -TimeoutSec 15
  Log "tools  (auth)       -> HTTP $($r.StatusCode) len=$($r.RawContentLength)"
} catch { Log "tools  (auth)       -> ERR $($_.Exception.Message)" }

# 3. SSE handshake (auth, bounded) — POST an MCP initialize. MCP/SSE is
#    sessionful: the FIRST initialize on a connection returns 200 + an
#    "event: message" result; re-initializing an already-initialized session
#    returns 400 {"code":-32600,"message":"Server already initialized"}.
#    Treat 200-with-SSE-event, and 400-already-initialized, both as
#    "endpoint live + auth ok". A bare GET returns 400 "Server not
#    initialized" which is NOT evidence the endpoint works.
$initBody = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"omniroute-probe","version":"1.0"}}}'
try {
  $r = Invoke-WebRequest -Uri "$base/api/mcp/sse" -Method POST -Headers @{
    Authorization = "Bearer $key"
    "Content-Type" = "application/json"
    Accept = "application/json, text/event-stream"
  } -Body $initBody -UseBasicParsing -TimeoutSec 12
  $isSse = $r.Content -match "event: message"
  Log "sse    (auth)       -> HTTP $($r.StatusCode) sseEvent=$isSse (endpoint live)"
} catch {
  $resp = $_.Exception.Response
  if ($resp) {
    $rc = [int]$resp.StatusCode
    $msg = ""
    try {
      $ms = New-Object System.IO.MemoryStream
      $resp.GetResponseStream().CopyTo($ms)
      $msg = [System.Text.Encoding]::UTF8.GetString($ms.ToArray())
    } catch {}
    if ($rc -eq 400 -and $msg -match "already initialized") {
      Log "sse    (auth)       -> HTTP 400 (already initialized = session live, endpoint ok)"
    } else {
      Log "sse    (auth)       -> HTTP $rc $($msg.Substring(0,[Math]::Min(120,$msg.Length)))"
    }
  } else { Log "sse    (auth)       -> ERR $($_.Exception.Message)" }
}

# 4. streamable-http initialize (auth) — only when transport is streamable-http
if ($Transport -eq "streamable-http") {
  $body = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"omniroute-probe","version":"1.0"}}}'
  try {
    $r = Invoke-WebRequest -Uri "$base/api/mcp/stream" -Method POST -Headers @{
      Authorization = "Bearer $key"
      "Content-Type" = "application/json"
      Accept = "application/json, text/event-stream"
    } -Body $body -UseBasicParsing -TimeoutSec 15
    $sid = $r.Headers["mcp-session-id"]
    Log "stream (auth)       -> HTTP $($r.StatusCode) mcp-session-id=$sid"
  } catch {
    $resp = $_.Exception.Response
    if ($resp) { Log "stream (auth)       -> HTTP $([int]$resp.StatusCode)" }
    else { Log "stream (auth)       -> ERR $($_.Exception.Message)" }
  }
} else {
  Log "stream (auth)       -> skipped (transport=sse)"
}

# 5. anonymous must fail (LOCAL_ONLY gate intact)
try {
  $r = Invoke-WebRequest -Uri "$base/api/mcp/status" -UseBasicParsing -TimeoutSec 10
  Log "status (anon)       -> HTTP $($r.StatusCode)  <-- GATE OPEN (bad!)"
} catch {
  $resp = $_.Exception.Response
  if ($resp) { Log "status (anon)       -> HTTP $([int]$resp.StatusCode) (gate intact)" }
  else { Log "status (anon)       -> ERR $($_.Exception.Message)" }
}

# 6. write artifact
$endpoint = if ($Transport -eq "sse") { "sse" } else { "stream" }
$artifact = [ordered]@{
  server  = "omniroute"
  tag     = $RunTag
  url     = "$base/api/mcp/$endpoint"
  transport = $Transport
  auth    = [ordered]@{
    type = "bearer"
    envVar = "OMNIROUTE_MCP_KEY_$($RunTag.ToUpper().Replace('-','_'))"
    keyFile = $McpKeyFile
  }
}
$artifactPath = Join-Path $mcpDir "$RunTag.mcp.json"
$artifact | ConvertTo-Json -Depth 5 | Set-Content -Path $artifactPath -Encoding utf8
Log "Artifact written: $artifactPath"

$stamp = Get-Date -Format "yyyy-MM-ddTHHmmss"
$logPath = Join-Path $logDir "$stamp-09-mcp-test.log"
$log | Set-Content -Path $logPath -Encoding utf8
Log "Log written: $logPath"
