#Requires -Version 5.1
<#
.SYNOPSIS
    One-click PowerShell script to start the SimplePod Swarm control plane.

.DESCRIPTION
    Starts a single uvicorn process serving the FastAPI backend
    and static HTML dashboard on port 8000.
    No more Streamlit spinners. No more separate frontend process.
#>

$ErrorActionPreference = "Stop"
$SwarmRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $SwarmRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log([string]$Message) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts | $Message" | Tee-Object -FilePath (Join-Path $LogDir "swarm.log") -Append
}

Write-Log "=== SimplePod Swarm Startup ==="
Write-Log "Root: $SwarmRoot"

# Find Python
$Python = Join-Path $SwarmRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
    Write-Log "Note: .venv not found, falling back to system python"
}

# Check Tailscale status (optional mesh diagnostics)
$Tailscale = Get-Command tailscale -ErrorAction SilentlyContinue
if ($Tailscale) {
    $TsStatus = & tailscale status --json 2>$null | ConvertFrom-Json -ErrorAction SilentlyContinue
    if ($TsStatus.Self) {
        Write-Log "Tailscale IP: $($TsStatus.Self.TailscaleIPs -join ', ')"
    }
}

# Single process: FastAPI serves API + static dashboard
Write-Log "Starting Control Plane on http://0.0.0.0:8000 ..."
& $Python -m uvicorn interfaces.web_ui.backend.main:app `
    --host 0.0.0.0 `
    --port 8000 `
    --log-level info
