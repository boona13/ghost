# Ghost Installer for Windows
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"

$GHOST_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$VENV_DIR = Join-Path $GHOST_DIR ".venv"
$GHOST_HOME = Join-Path $env:USERPROFILE ".ghost"
$CONFIG_FILE = Join-Path $GHOST_HOME "config.json"

function Banner {
    Write-Host ""
    Write-Host "   ██████╗ ██╗  ██╗ ██████╗ ███████╗████████╗" -ForegroundColor DarkGray
    Write-Host "  ██╔════╝ ██║  ██║██╔═══██╗██╔════╝╚══██╔══╝" -ForegroundColor DarkGray
    Write-Host "  ██║  ███╗███████║██║   ██║███████╗   ██║   " -ForegroundColor DarkGray
    Write-Host "  ██║   ██║██╔══██║██║   ██║╚════██║   ██║   " -ForegroundColor DarkGray
    Write-Host "  ╚██████╔╝██║  ██║╚██████╔╝███████║   ██║   " -ForegroundColor DarkGray
    Write-Host "   ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝   " -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Ghost Installer (Windows)" -ForegroundColor White
    Write-Host ""
}

function Step($msg) { Write-Host "`n  > $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    [!] $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "    [X] $msg" -ForegroundColor Red; exit 1 }

Banner

# 1. Check Python
Step "Checking Python..."

$PY = $null
foreach ($cmd in @("python3", "python")) {
    try {
        $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $ver) {
            $major, $minor = $ver.Split(".")
            if ([int]$major -ge 3 -and [int]$minor -ge 10) {
                $PY = $cmd
                break
            }
        }
    } catch {}
}

if (-not $PY) {
    Fail "Python 3.10+ is required. Install it from https://python.org"
}

$PY_VERSION = & $PY -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
Ok "Python $PY_VERSION ($PY)"

# 2. Create virtual environment
Step "Setting up virtual environment..."
if (Test-Path $VENV_DIR) {
    Ok "Virtual environment already exists at .venv\"
} else {
    & $PY -m venv $VENV_DIR
    if ($LASTEXITCODE -ne 0) { Fail "Failed to create virtual environment" }
    Ok "Created .venv\"
}

$VENV_PY = Join-Path $VENV_DIR "Scripts\python.exe"
$VENV_PIP = Join-Path $VENV_DIR "Scripts\pip.exe"

if (-not (Test-Path $VENV_PY)) {
    Fail "Virtual environment python not found at $VENV_PY"
}
Ok "Activated .venv\"

# 3. Install dependencies
Step "Installing Python dependencies..."
& $VENV_PIP install --upgrade pip -q 2>$null
& $VENV_PIP install -r (Join-Path $GHOST_DIR "requirements.txt") -q 2>$null
if ($LASTEXITCODE -ne 0) { Fail "pip install failed" }
Ok "Core dependencies installed (flask, requests, pyyaml, croniter)"

# 4. Optional: PinchTab (browser automation)
Step "Browser automation (optional)..."
Write-Host ""
Write-Host "    PinchTab enables Ghost to control a real browser."
Write-Host "    Standalone binary, uses your existing Chrome."
Write-Host ""
$reply = Read-Host "    Install PinchTab? [y/N]"
if ($reply -match "^[Yy]$") {
    npm install -g pinchtab 2>$null
    Ok "PinchTab installed (run 'pinchtab' to start the browser server)"
} else {
    Ok "Skipped (install later: npm install -g pinchtab)"
}

# 5. Create ~/.ghost directory
Step "Setting up Ghost home directory..."
$dirs = @(
    $GHOST_HOME,
    (Join-Path $GHOST_HOME "cron"),
    (Join-Path $GHOST_HOME "skills"),
    (Join-Path $GHOST_HOME "plugins"),
    (Join-Path $GHOST_HOME "screenshots"),
    (Join-Path $GHOST_HOME "evolve\backups")
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
    Write-Host "    Get a free key at: https://openrouter.ai/keys" -ForegroundColor Cyan
    Write-Host ""
    $API_KEY = Read-Host "    Enter your OpenRouter API key (or press Enter to skip)"
    if ($API_KEY) {
        [System.Environment]::SetEnvironmentVariable("OPENROUTER_API_KEY", $API_KEY, "User")
        $env:OPENROUTER_API_KEY = $API_KEY
        Ok "Saved to user environment variables (persistent across sessions)"
    } else {
        Warn "Skipped - set it later: `$env:OPENROUTER_API_KEY = 'sk-or-v1-...'"
    }
}

# 7. Summary
Write-Host ""
Write-Host "  ════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "    Installation complete!" -ForegroundColor Green
Write-Host "  ════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  Quick start:" -ForegroundColor White
Write-Host ""
Write-Host "    .\start.bat" -ForegroundColor Cyan
Write-Host "                               Start Ghost (with supervisor)"
Write-Host "    .\stop.bat" -ForegroundColor Cyan
Write-Host "                               Stop Ghost"
Write-Host ""
Write-Host "  Or manually:" -ForegroundColor White
Write-Host ""
Write-Host "    .venv\Scripts\activate" -ForegroundColor Cyan
Write-Host "    python ghost_supervisor.py" -ForegroundColor Cyan
Write-Host "                               Start with supervisor"
Write-Host "    python ghost.py" -ForegroundColor Cyan
Write-Host "                               Start without supervisor"
Write-Host ""
Write-Host "  Dashboard:  http://localhost:3333" -ForegroundColor Cyan
Write-Host ""
Write-Host "  On first launch, Ghost creates default SOUL.md and USER.md."
Write-Host "  If no API key is set, the dashboard opens a setup wizard."
Write-Host ""
Write-Host "  Docs: README.md | docs\ARCHITECTURE.md" -ForegroundColor DarkGray
Write-Host ""
