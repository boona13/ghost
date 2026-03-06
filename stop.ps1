# Stop the Ghost system (supervisor + daemon) — Windows
# Usage: powershell -ExecutionPolicy Bypass -File stop.ps1

$GhostHome = Join-Path $env:USERPROFILE ".ghost"
$stopped = $false

$supPidFile = Join-Path $GhostHome "supervisor.pid"
if (Test-Path $supPidFile) {
    $pid = [int](Get-Content $supPidFile -ErrorAction SilentlyContinue)
    if ($pid) {
        $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($proc) {
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            Write-Host "Supervisor (PID $pid) stopped."
            $stopped = $true
        }
    }
    Remove-Item $supPidFile -Force -ErrorAction SilentlyContinue
}

$ghostPidFile = Join-Path $GhostHome "ghost.pid"
if (Test-Path $ghostPidFile) {
    $pid = [int](Get-Content $ghostPidFile -ErrorAction SilentlyContinue)
    if ($pid) {
        $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($proc) {
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            Write-Host "Ghost (PID $pid) stopped."
            $stopped = $true
        }
    }
    Remove-Item $ghostPidFile -Force -ErrorAction SilentlyContinue
}

if (-not $stopped) {
    Write-Host "Ghost is not running."
}
