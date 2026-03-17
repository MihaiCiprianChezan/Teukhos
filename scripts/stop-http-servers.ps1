# ============================================================================
# Teukhos — Stop All Example HTTP Servers
# ============================================================================
#
# PURPOSE:
#   Stops all Teukhos example MCP HTTP servers previously started by
#   start-http-servers.ps1. Uses the saved PID file for clean shutdown,
#   or falls back to port-based cleanup if no PID file is found.
#
# USAGE:
#   .\scripts\stop-http-servers.ps1
#
# PORTS: 8770-8779 (same range as start-http-servers.ps1)
#
# SEE ALSO:
#   scripts/start-http-servers.ps1  — Starts the servers
#   scripts/stop-http-servers.sh    — Linux/macOS equivalent
# ============================================================================

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $ScriptDir ".http-servers.pids"

if (-not (Test-Path $PidFile)) {
    Write-Host "No PID file found at $PidFile"
    Write-Host "Falling back to port-based cleanup..."
    Write-Host ""

    $Killed = 0
    $Ports = 8770..8779

    foreach ($Port in $Ports) {
        $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        if ($connections) {
            foreach ($conn in $connections | Select-Object -Unique OwningProcess) {
                $procId = $conn.OwningProcess
                Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                Write-Host "  KILL  port $Port (PID $procId)"
                $Killed++
            }
        }
    }

    if ($Killed -eq 0) {
        Write-Host "No servers found running on ports 8770-8779."
    } else {
        Write-Host ""
        Write-Host "$Killed servers stopped."
    }
    exit 0
}

Write-Host "Stopping Teukhos HTTP servers..."
Write-Host ""

$Stopped = 0
foreach ($line in Get-Content $PidFile) {
    $parts = $line.Trim() -split '\s+'
    $procId = $parts[0]
    $port = $parts[1]
    $config = $parts[2]

    try {
        Stop-Process -Id $procId -Force -ErrorAction Stop
        Write-Host "  STOP  $config on port $port (PID $procId)"
        $Stopped++
    } catch {
        Write-Host "  SKIP  $config (PID $procId) - already stopped"
    }
}

Remove-Item $PidFile
Write-Host ""
Write-Host "$Stopped servers stopped."
