# SimplePod VS Code Auto-Reloader
# Kills VS Code gracefully and restarts it with the swarm project open

$ErrorActionPreference = "Stop"
$SwarmPath = "D:\vs code project files\outputs\simplepod_swarm"
$ExtJunction = "$env:USERPROFILE\.vscode\extensions\simplepod.simplepod-swarm-0.2.0"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  SimplePod Swarm -- VS Code Auto-Reloader" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Verify extension junction exists
if (-not (Test-Path $ExtJunction)) {
    Write-Host "[ERROR] Extension junction not found at:" -ForegroundColor Red
    Write-Host "        $ExtJunction" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Extension junction verified" -ForegroundColor Green

# 2. Find VS Code executable
$CodePath = $null
$possiblePaths = @(
    "$env:LOCALAPPDATA\Programs\Microsoft VS Code\bin\code.cmd"
    "$env:LOCALAPPDATA\Programs\Microsoft VS Code\bin\code"
    "$env:ProgramFiles\Microsoft VS Code\bin\code.cmd"
    "$env:ProgramFiles\Microsoft VS Code\bin\code"
)

foreach ($p in $possiblePaths) {
    if (Test-Path $p) {
        $CodePath = $p
        break
    }
}

if (-not $CodePath) {
    $codeInPath = Get-Command "code" -ErrorAction SilentlyContinue
    if ($codeInPath) {
        $CodePath = $codeInPath.Source
    }
}

if (-not $CodePath) {
    Write-Host "[ERROR] VS Code executable not found." -ForegroundColor Red
    exit 1
}
Write-Host "[OK] VS Code found: $CodePath" -ForegroundColor Green

# 3. Check running VS Code processes
$codeProcs = Get-Process -Name "Code" -ErrorAction SilentlyContinue
$hadVSCode = $false
if ($codeProcs) {
    $hadVSCode = $true
    Write-Host "[INFO] Found VS Code process(es). Stopping..." -ForegroundColor Yellow
    $codeProcs | ForEach-Object { $_.CloseMainWindow() | Out-Null }
    Start-Sleep -Milliseconds 2000
    $remaining = Get-Process -Name "Code" -ErrorAction SilentlyContinue
    if ($remaining) {
        $remaining | Stop-Process -Force
        Start-Sleep -Milliseconds 500
    }
    Write-Host "[OK] VS Code stopped." -ForegroundColor Green
} else {
    Write-Host "[INFO] No VS Code running -- starting fresh." -ForegroundColor Yellow
}

# 4. Verify backend
Write-Host ""
Write-Host "[CHECK] Verifying backend on port 8000..." -ForegroundColor Cyan
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    $health = $resp.Content | ConvertFrom-Json
    Write-Host "[OK] Backend healthy: $($health.status)" -ForegroundColor Green
} catch {
    Write-Host "[WARN] Backend not responding on port 8000." -ForegroundColor Yellow
    Write-Host "       Dashboard may show OFFLINE until started." -ForegroundColor DarkGray
}

# 5. Restart VS Code
Write-Host ""
Write-Host "[LAUNCH] Starting VS Code with SimplePod Swarm..." -ForegroundColor Cyan
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $CodePath
$psi.Arguments = '"' + $SwarmPath + '"'
$psi.WorkingDirectory = $SwarmPath
$psi.UseShellExecute = $true
$psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
[System.Diagnostics.Process]::Start($psi) | Out-Null

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  SUCCESS -- VS Code reloaded with SimplePod Swarm" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps inside VS Code:" -ForegroundColor White
Write-Host "  1. Look for the circuit-board icon in the Activity Bar" -ForegroundColor White
Write-Host "  2. Press Ctrl+Shift+S to open the Swarm Dashboard" -ForegroundColor White
Write-Host "  3. Press Ctrl+Shift+C to capture screenshot" -ForegroundColor White
Write-Host ""
