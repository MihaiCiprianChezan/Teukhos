# ============================================================================
# Teukhos — Install Optional CLI Tools (Windows)
# ============================================================================
#
# PURPOSE:
#   Installs the CLI tools that Teukhos example servers wrap as MCP endpoints.
#   Each tool group is optional — you only need the ones for the servers you
#   plan to use. Run this before start-http-servers.ps1 to eliminate warnings.
#
# USAGE:
#   .\scripts\install-tools.ps1                # Install all available tools
#   .\scripts\install-tools.ps1 -Check         # Just check what's installed
#   .\scripts\install-tools.ps1 -Group gpu     # Install only gpu tools
#
# GROUPS: git, media, gpu, docker, image, network, database, archive, kubernetes
#
# NOTE: Some installs require administrator privileges (winget/choco).
#       Run PowerShell as Administrator if installs fail.
#
# SEE ALSO:
#   scripts/install-tools.sh        — Linux/macOS equivalent
#   scripts/start-http-servers.ps1  — Start the example HTTP servers
# ============================================================================

param(
    [switch]$Check,
    [string]$Group
)

# ── Tool groups ──────────────────────────────────────────────────────────────
# Each group maps to an example YAML config in examples/
$ToolGroups = [ordered]@{
    git        = @("git")
    media      = @("ffmpeg", "ffprobe")
    gpu        = @("nvidia-smi", "nvcc")
    docker     = @("docker")
    image      = @("magick")
    network    = @("curl", "dig", "tracert", "whois")
    database   = @("sqlite3", "psql")
    archive    = @("tar", "zip", "unzip", "sha256sum")
    kubernetes = @("kubectl")
}

# Winget package IDs for each tool
$WingetPackages = @{
    "git"         = "Git.Git"
    "ffmpeg"      = "Gyan.FFmpeg"
    "ffprobe"     = ""  # included with ffmpeg
    "nvidia-smi"  = ""  # included with NVIDIA driver
    "nvcc"        = "Nvidia.CUDA"
    "docker"      = "Docker.DockerDesktop"
    "magick"      = "ImageMagick.ImageMagick"
    "curl"        = ""  # built into Windows
    "dig"         = "ISC.BIND.Tools"
    "tracert"     = ""  # built into Windows
    "whois"       = "Microsoft.Sysinternals.WhoIs"
    "sqlite3"     = "SQLite.SQLite"
    "psql"        = "PostgreSQL.PostgreSQL.17"
    "tar"         = ""  # built into Windows
    "zip"         = "GnuWin32.Zip"
    "unzip"       = ""  # built into Windows (Expand-Archive)
    "sha256sum"   = ""  # use Get-FileHash in PowerShell
    "kubectl"     = "Kubernetes.kubectl"
}

# ── Check a single tool ─────────────────────────────────────────────────────
function Test-Tool {
    param([string]$Name)

    $found = Get-Command $Name -ErrorAction SilentlyContinue
    if ($found) {
        $path = $found.Source
        Write-Host "  OK      " -ForegroundColor Green -NoNewline
        Write-Host ("{0,-14} {1}" -f $Name, $path)
        return $true
    } else {
        Write-Host "  MISSING  " -ForegroundColor Red -NoNewline
        Write-Host ("{0,-14}" -f $Name)
        return $false
    }
}

# ── Check all tools ─────────────────────────────────────────────────────────
function Show-Status {
    Write-Host ""
    Write-Host "Teukhos Example Tools - Status"
    Write-Host "=============================="
    Write-Host ""

    $total = 0
    $found = 0

    foreach ($groupName in $ToolGroups.Keys) {
        Write-Host "-- $groupName-tools --" -ForegroundColor DarkGray
        foreach ($tool in $ToolGroups[$groupName]) {
            $total++
            if (Test-Tool $tool) { $found++ }
        }
        Write-Host ""
    }

    Write-Host "Found $found / $total tools."
    if ($found -lt $total) {
        Write-Host "Run .\scripts\install-tools.ps1 to install missing tools." -ForegroundColor DarkGray
    } else {
        Write-Host "All tools installed!" -ForegroundColor Green
    }
}

# ── Install tools for a group ────────────────────────────────────────────────
function Install-ToolGroup {
    param([string]$GroupName)

    if (-not $ToolGroups.Contains($GroupName)) {
        Write-Host "Unknown group: $GroupName" -ForegroundColor Red
        Write-Host "Available groups: $($ToolGroups.Keys -join ', ')"
        return
    }

    Write-Host "-- $GroupName-tools --" -ForegroundColor DarkGray

    $toInstall = @()

    foreach ($tool in $ToolGroups[$GroupName]) {
        $exists = Get-Command $tool -ErrorAction SilentlyContinue
        if ($exists) {
            Write-Host "  OK      " -ForegroundColor Green -NoNewline
            Write-Host ("{0,-14} (already installed)" -f $tool)
        } else {
            $pkg = $WingetPackages[$tool]
            if ($pkg) {
                $toInstall += $pkg
                Write-Host "  QUEUE   " -ForegroundColor Yellow -NoNewline
                Write-Host ("{0,-14} -> $pkg" -f $tool)
            } else {
                Write-Host "  SKIP    " -ForegroundColor DarkGray -NoNewline
                Write-Host ("{0,-14} (no package / built-in alternative)" -f $tool)
            }
        }
    }

    if ($toInstall.Count -eq 0) {
        Write-Host "  Nothing to install."
        return
    }

    # Deduplicate
    $unique = $toInstall | Select-Object -Unique

    Write-Host ""
    Write-Host "  Installing via winget: $($unique -join ', ')"
    Write-Host ""

    foreach ($pkg in $unique) {
        Write-Host "  > winget install --id $pkg --accept-source-agreements --accept-package-agreements" -ForegroundColor DarkGray
        try {
            winget install --id $pkg --accept-source-agreements --accept-package-agreements
        } catch {
            Write-Host "  FAILED to install $pkg — try running as Administrator" -ForegroundColor Red
        }
    }
    Write-Host ""
}

# ── Main ─────────────────────────────────────────────────────────────────────

if ($Check) {
    Show-Status
    exit 0
}

Write-Host ""
Write-Host "Teukhos Example Tools - Installer"
Write-Host "=================================="
Write-Host "Package manager: winget" -ForegroundColor DarkGray
Write-Host ""

if ($Group) {
    Install-ToolGroup $Group
} else {
    # Ask about GPU/CUDA before running
    $installGpu = $false
    $gpuAnswer = Read-Host "Do you have an NVIDIA GPU with CUDA? (y/n)"
    if ($gpuAnswer -match '^[yY]') {
        $installGpu = $true
    } else {
        Write-Host "  Skipping GPU/CUDA tools." -ForegroundColor DarkGray
    }
    Write-Host ""

    # Install all groups (already-installed tools are detected and skipped)
    foreach ($groupName in $ToolGroups.Keys) {
        if ($groupName -eq "gpu" -and -not $installGpu) { continue }
        Install-ToolGroup $groupName
        Write-Host ""
    }
}

Write-Host ""
Write-Host "Done. Run '.\scripts\install-tools.ps1 -Check' to verify."
Write-Host "NOTE: You may need to restart your terminal for new tools to appear on PATH." -ForegroundColor Yellow
