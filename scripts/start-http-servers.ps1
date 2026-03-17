# ============================================================================
# Teukhos — Start All Example HTTP Servers
# ============================================================================
#
# PURPOSE:
#   Launches all Teukhos example MCP servers in HTTP mode for local testing.
#   Each server wraps CLI tools (git, ffmpeg, docker, etc.) as MCP endpoints
#   that AI clients like VS Code Copilot can connect to.
#
#   The .vscode/mcp.json file references these HTTP endpoints. Unlike stdio
#   servers (which Copilot auto-starts), HTTP servers must be running BEFORE
#   the client connects — this script handles that.
#
# USAGE:
#   .\scripts\start-http-servers.ps1          # Start all servers
#   .\scripts\stop-http-servers.ps1           # Stop all servers (separate terminal)
#   Ctrl+C                                    # Stop all servers (this terminal)
#
# PORTS: 8770-8779 (one per example config in examples/*.yaml)
#
# SEE ALSO:
#   scripts/start-http-servers.sh   — Linux/macOS equivalent
#   .vscode/mcp.json                — VS Code Copilot server definitions
# ============================================================================

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$PidFile = Join-Path $ScriptDir ".http-servers.pids"

# Port-to-config mapping (must match .vscode/mcp.json)
$Servers = @(
    @{ Port = 8770; Config = "git-tools" },
    @{ Port = 8771; Config = "dev-tools" },
    @{ Port = 8772; Config = "media-tools" },
    @{ Port = 8773; Config = "gpu-tools" },
    @{ Port = 8774; Config = "docker-tools" },
    @{ Port = 8775; Config = "image-tools" },
    @{ Port = 8776; Config = "network-tools" },
    @{ Port = 8777; Config = "database-tools" },
    @{ Port = 8778; Config = "kubernetes-tools" },
    @{ Port = 8779; Config = "archive-tools" }
)

# Kill any orphaned processes on our ports before starting
Write-Host "Checking for orphaned processes on ports 8770-8779..."
$Cleaned = 0
foreach ($entry in $Servers) {
    $p = $entry.Port
    $conns = Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue
    if ($conns) {
        foreach ($c in $conns | Select-Object -Property OwningProcess -Unique) {
            try {
                Stop-Process -Id $c.OwningProcess -Force -ErrorAction Stop
                Write-Host "  KILL  orphan on port $p (PID $($c.OwningProcess))"
                $Cleaned++
            } catch { }
        }
    }
}
if ($Cleaned -gt 0) {
    Write-Host "  Cleaned $Cleaned orphaned process(es)."
    Start-Sleep -Seconds 1
} else {
    Write-Host "  Ports are clean."
}
Write-Host ""

# Clean up any previous PID file
if (Test-Path $PidFile) { Remove-Item $PidFile }

Write-Host "Starting Teukhos HTTP servers..."
Write-Host ""

$Started = 0
$Failed = 0
$Processes = @()

foreach ($entry in $Servers) {
    $Port = $entry.Port
    $Config = $entry.Config
    $Yaml = Join-Path $ProjectDir "examples\$Config.yaml"

    if (-not (Test-Path $Yaml)) {
        Write-Host "  SKIP  $Config - $Yaml not found"
        $Failed++
        continue
    }

    $proc = Start-Process -FilePath "teukhos" `
        -ArgumentList "serve", "`"$Yaml`"", "-t", "http", "-p", "$Port" `
        -PassThru -NoNewWindow

    $Processes += $proc
    "$($proc.Id) $Port $Config" | Out-File -Append -FilePath $PidFile -Encoding UTF8
    Write-Host "  OK    $Config on port $Port (PID $($proc.Id))"
    $Started++
}

Write-Host ""
Write-Host "$Started servers started, $Failed skipped."
Write-Host "PIDs saved to $PidFile"
Write-Host ""
Write-Host "Press Ctrl+C to stop all servers, or run: powershell scripts\stop-http-servers.ps1"

# Wait and handle Ctrl+C cleanup
try {
    while ($true) {
        $allExited = $true
        foreach ($proc in $Processes) {
            if (-not $proc.HasExited) {
                $allExited = $false
                break
            }
        }
        if ($allExited) { break }
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Host ""
    Write-Host "Shutting down..."
    # Kill parent teukhos processes
    foreach ($proc in $Processes) {
        if (-not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
    # Also kill any child uvicorn processes still holding ports
    foreach ($entry in $Servers) {
        $p = $entry.Port
        $conns = Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue
        if ($conns) {
            foreach ($c in $conns | Select-Object -Property OwningProcess -Unique) {
                Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
            }
        }
    }
    if (Test-Path $PidFile) { Remove-Item $PidFile }
    Write-Host "All servers stopped."
}
