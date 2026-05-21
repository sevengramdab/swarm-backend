#requires -Version 5.1
<#
.SYNOPSIS
    Installs and configures Tailscale on a Windows node for the SimplePod mesh.

.DESCRIPTION
    ELI5: This is like calling the smart-home company to install their
          wireless bridge box on your Windows house. We download the installer,
          plug it in, enter your account PIN (auth key), and register the house
          in the neighborhood directory. If anything goes wrong, we flip the
          breaker back off and scream into the log so the electrician knows.

.PARAMETER AuthKey
    Tailscale authentication key (tskey-...).

.PARAMETER NodeId
    Human-readable identifier for this node (e.g., "local-msi-gtx1650").

.PARAMETER Tailnet
    Tailnet domain (default: simplepod.ts.net).

.PARAMETER AcceptRoutes
    Accept subnet routes from other nodes (default: $true).

.PARAMETER AdvertiseRoutes
    Comma-separated CIDRs to advertise (e.g., "192.168.1.0/24,10.0.0.0/24").

.PARAMETER SshEnabled
    Enable Tailscale SSH (default: $true).

.PARAMETER ExitNode
    Advertise as an exit node (default: $false).

.EXAMPLE
    .\setup_tailscale.ps1 -AuthKey "tskey-auth-xxxxxxxxxxxxxxxx" -NodeId "local-msi"
#>
[CmdletBinding()]
param (
    [Parameter(Mandatory = $true)]
    [string]$AuthKey,

    [Parameter(Mandatory = $true)]
    [string]$NodeId,

    [string]$Tailnet = "simplepod.ts.net",

    [bool]$AcceptRoutes = $true,

    [string]$AdvertiseRoutes = "",

    [bool]$SshEnabled = $true,

    [bool]$ExitNode = $false
)

# ── Error handling: treat every mistake like a live wire ──────────────────────
$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"

function Write-Log {
    param(
        [string]$Message,
        [ValidateSet("INFO", "WARN", "ERROR", "SUCCESS")]
        [string]$Level = "INFO"
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] [$Level] $Message"
    Write-Host $line
    # Also append to a rolling log file next to the script.
    $logDir = Join-Path $PSScriptRoot ".." "logs"
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }
    $logFile = Join-Path $logDir "tailscale_setup.log"
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

try {
    Write-Log "Starting Tailscale setup for node '$NodeId' on tailnet '$Tailnet'" -Level "INFO"

    # ── Sanity checks ─────────────────────────────────────────────────────────
    if (-not ($AuthKey -match '^tskey-auth-')) {
        throw "AuthKey does not look like a Tailscale auth key. Expected prefix 'tskey-auth-'."
    }

    $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).
        IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")
    if (-not $isAdmin) {
        throw "This script must run as Administrator. Right-click -> Run as Administrator."
    }

    # ── Download Tailscale MSI if not present ─────────────────────────────────
    $installDir = "${env:ProgramFiles}\Tailscale IPN"
    $tailscaleExe = Join-Path $installDir "tailscale.exe"

    if (-not (Test-Path $tailscaleExe)) {
        Write-Log "Tailscale not found. Downloading installer..." -Level "WARN"
        $downloadUrl = "https://pkgs.tailscale.com/stable/tailscale-setup-latest-amd64.msi"
        $msiPath = "$env:TEMP\tailscale-setup.msi"

        try {
            Invoke-WebRequest -Uri $downloadUrl -OutFile $msiPath -UseBasicParsing -TimeoutSec 120
        }
        catch {
            throw "Failed to download Tailscale MSI from $downloadUrl. $_"
        }

        Write-Log "Installing Tailscale MSI..." -Level "INFO"
        $msiArgs = "/i `"$msiPath`" /quiet /norestart"
        $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList $msiArgs -Wait -PassThru
        if ($proc.ExitCode -ne 0) {
            throw "MSI installation failed with exit code $($proc.ExitCode)."
        }
        Write-Log "Tailscale installed successfully." -Level "SUCCESS"
    }
    else {
        Write-Log "Tailscale already installed at $tailscaleExe" -Level "INFO"
    }

    # ── Build Tailscale CLI arguments ─────────────────────────────────────────
    $tsArgs = @(
        "up",
        "--authkey", $AuthKey,
        "--hostname", $NodeId,
        "--operator", $env:USERNAME
    )

    if ($AcceptRoutes) {
        $tsArgs += "--accept-routes"
    }

    if ($SshEnabled) {
        $tsArgs += "--ssh"
    }

    if ($ExitNode) {
        $tsArgs += "--advertise-exit-node"
    }

    if ($AdvertiseRoutes -ne "") {
        # Validate each CIDR before passing it.
        $routeList = $AdvertiseRoutes -split ',' | ForEach-Object { $_.Trim() }
        foreach ($r in $routeList) {
            try {
                $null = [System.Net.IPNetwork]::Parse($r)
            }
            catch {
                throw "Invalid route advertisement: '$r'. Must be a valid CIDR."
            }
        }
        $tsArgs += "--advertise-routes"
        $tsArgs += ($routeList -join ',')
    }

    # ── Bring the interface UP ────────────────────────────────────────────────
    Write-Log "Bringing Tailscale UP with args: $tsArgs" -Level "INFO"
    & $tailscaleExe @tsArgs
    if ($LASTEXITCODE -ne 0) {
        throw "tailscale up failed with exit code $LASTEXITCODE."
    }
    Write-Log "Tailscale interface is UP." -Level "SUCCESS"

    # ── Verify connectivity ───────────────────────────────────────────────────
    Write-Log "Verifying Tailscale status..." -Level "INFO"
    $statusJson = & $tailscaleExe "status" "--json" 2>$null | Out-String
    if ($LASTEXITCODE -ne 0 -or -not $statusJson) {
        throw "Unable to retrieve Tailscale status."
    }

    $status = $statusJson | ConvertFrom-Json -ErrorAction Stop
    $self = $status.Self
    if (-not $self) {
        throw "Tailscale status JSON missing 'Self' node."
    }

    Write-Log "Node registered: $($self.HostName) / IPs: $($self.TailscaleIPs -join ', ')" -Level "SUCCESS"

    # ── Write local config snapshot for Python mesh_configurator ──────────────
    $configDir = Join-Path $PSScriptRoot ".." "configs"
    if (-not (Test-Path $configDir)) {
        New-Item -ItemType Directory -Path $configDir -Force | Out-Null
    }
    $configPath = Join-Path $configDir "tailscale_${NodeId}.json"
    $snapshot = @{
        node_id    = $NodeId
        auth_key   = $AuthKey
        tailnet    = $Tailnet
        advertise_routes = @($routeList)
        accept_routes    = $AcceptRoutes
        ssh_enabled      = $SshEnabled
        exit_node        = $ExitNode
        tailscale_ips    = $self.TailscaleIPs
        backend_state    = $status.BackendState
    } | ConvertTo-Json -Depth 4
    Set-Content -Path $configPath -Value $snapshot -Encoding UTF8
    Write-Log "Local config snapshot written to $configPath" -Level "INFO"

    Write-Log "Setup complete for '$NodeId'. Mesh join successful." -Level "SUCCESS"
}
catch {
    Write-Log "FATAL: $_" -Level "ERROR"
    exit 1
}
