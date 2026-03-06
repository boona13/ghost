# Start Ghost with the supervisor (recommended) — Windows
# Usage: powershell -ExecutionPolicy Bypass -File start.ps1 [--api-key sk-or-...]

$GhostDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$GhostHome = Join-Path $env:USERPROFILE ".ghost"
$VenvDir   = Join-Path $GhostDir ".venv"

# Activate virtual environment if it exists
$activateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
if (Test-Path $activateScript) {
    . $activateScript
}

# Check if Ghost is already running
$supPid = Join-Path $GhostHome "supervisor.pid"
if (Test-Path $supPid) {
    $pid = [int](Get-Content $supPid -ErrorAction SilentlyContinue)
    if ($pid -and (Get-Process -Id $pid -ErrorAction SilentlyContinue)) {
        Write-Host "Ghost is already running (supervisor PID $pid)"
        Write-Host "Dashboard: http://localhost:3333"
        Write-Host "To stop: .\stop.ps1"
        exit 0
    }
}

$ghostPid = Join-Path $GhostHome "ghost.pid"
if (Test-Path $ghostPid) {
    $pid = [int](Get-Content $ghostPid -ErrorAction SilentlyContinue)
    if ($pid -and (Get-Process -Id $pid -ErrorAction SilentlyContinue)) {
        Write-Host "Ghost is already running (PID $pid) without supervisor."
        Write-Host "Dashboard: http://localhost:3333"
        Write-Host "To stop: .\stop.ps1"
        exit 0
    }
}

$supervisorScript = Join-Path $GhostDir "ghost_supervisor.py"
& python $supervisorScript @args
