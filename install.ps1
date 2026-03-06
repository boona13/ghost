# Ghost Installer — Windows (PowerShell)
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"

$GhostDir   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$VenvDir    = Join-Path $GhostDir ".venv"
$GhostHome  = Join-Path $env:USERPROFILE ".ghost"
$ConfigFile = Join-Path $GhostHome "config.json"

function Banner {
    Write-Host ""
    Write-Host "   GHOST Installer" -ForegroundColor Cyan
    Write-Host ""
}

function Step($msg)  { Write-Host "`n  > $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "    [!] $msg" -ForegroundColor Yellow }
function Fail($msg)  { Write-Host "    [X] $msg" -ForegroundColor Red; exit 1 }

Banner

# 1. Check Python
Step "Checking Python..."
$py = $null
foreach ($cmd in @("python3", "python")) {
    try {
        $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        $major = & $cmd -c "import sys; print(sys.version_info.major)" 2>$null
        $minor = & $cmd -c "import sys; print(sys.version_info.minor)" 2>$null
        if ([int]$major -ge 3 -and [int]$minor -ge 10) {
            $py = $cmd
            break
        }
    } catch {}
}
if (-not $py) { Fail "Python 3.10+ is required. Install from https://python.org" }
Ok "Python $ver ($py)"

# 2. Create virtual environment
Step "Setting up virtual environment..."
if (Test-Path $VenvDir) {
    Ok "Virtual environment already exists at .venv\"
} else {
    & $py -m venv $VenvDir
    Ok "Created .venv\"
}

$activateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
. $activateScript
Ok "Activated .venv\"

# 3. Install dependencies
Step "Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r (Join-Path $GhostDir "requirements.txt") -q
Ok "Core dependencies installed"

# 4. Optional: Playwright
Step "Browser automation (optional)..."
Write-Host ""
Write-Host "    Playwright enables Ghost to control a real browser."
Write-Host "    This downloads ~150MB of browser binaries."
Write-Host ""
$reply = Read-Host "    Install Playwright? [y/N]"
if ($reply -match '^[Yy]$') {
    pip install playwright -q
    python -m playwright install chromium
    Ok "Playwright + Chromium installed"
} else {
    Ok "Skipped (install later: pip install playwright; python -m playwright install chromium)"
}

# 5. Create ~/.ghost directory
Step "Setting up Ghost home directory..."
$dirs = @(
    $GhostHome,
    (Join-Path $GhostHome "cron"),
    (Join-Path $GhostHome "skills"),
    (Join-Path $GhostHome "plugins"),
    (Join-Path $GhostHome "screenshots"),
    (Join-Path $GhostHome "evolve\backups")
)
foreach ($d in $dirs) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}
Ok "Created ~/.ghost/"

# 6. API Key
Step "OpenRouter API key..."
Write-Host ""
if ($env:OPENROUTER_API_KEY) {
    Ok "Found OPENROUTER_API_KEY in environment"
} else {
    Write-Host "    Ghost uses OpenRouter to access LLMs (GPT-4o, Claude, Gemini, etc.)"
    Write-Host "    Get a free key at: https://openrouter.ai/keys"
    Write-Host ""
    $apiKey = Read-Host "    Enter your OpenRouter API key (or press Enter to skip)"
    if ($apiKey) {
        [System.Environment]::SetEnvironmentVariable("OPENROUTER_API_KEY", $apiKey, "User")
        $env:OPENROUTER_API_KEY = $apiKey
        Ok "Saved OPENROUTER_API_KEY to user environment variables"
    } else {
        Warn "Skipped -- set it later: `$env:OPENROUTER_API_KEY = 'sk-or-v1-...'"
    }
}

# 7. Summary
Write-Host ""
Write-Host "  ================================================" -ForegroundColor Green
Write-Host "    Installation complete!" -ForegroundColor Green
Write-Host "  ================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Quick start:" -ForegroundColor White
Write-Host ""
Write-Host "    .\start.ps1                   Start Ghost (with supervisor)" -ForegroundColor Cyan
Write-Host "    .\stop.ps1                    Stop Ghost" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Or manually:" -ForegroundColor White
Write-Host ""
Write-Host "    .\.venv\Scripts\Activate.ps1" -ForegroundColor Cyan
Write-Host "    python ghost_supervisor.py    Start with supervisor" -ForegroundColor Cyan
Write-Host "    python ghost.py               Start without supervisor" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Dashboard:  http://localhost:3333" -ForegroundColor Cyan
Write-Host ""
