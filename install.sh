#!/usr/bin/env bash
set -euo pipefail

# ── Ghost Installer ──────────────────────────────────────────────────
# Works two ways:
#   1. One-liner:  curl -fsSL https://raw.githubusercontent.com/boona13/ghost/main/install.sh | bash
#   2. Local:      cd ghost && bash install.sh
#
# Options:
#   --no-interactive    Skip prompts (Playwright=no, API key=skip)
#   --with-playwright   Auto-install Playwright without asking
#   --api-key KEY       Set the OpenRouter API key non-interactively
# ─────────────────────────────────────────────────────────────────────

GHOST_REPO="https://github.com/boona13/ghost.git"
INSTALL_DIR="${GHOST_INSTALL_DIR:-$HOME/ghost}"

RST="\033[0m"; B="\033[1m"; DIM="\033[2m"
RED="\033[31m"; GRN="\033[32m"; YLW="\033[33m"; CYN="\033[36m"

NO_INTERACTIVE=false
WITH_PLAYWRIGHT=false
API_KEY_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-interactive) NO_INTERACTIVE=true; shift ;;
    --with-playwright) WITH_PLAYWRIGHT=true; shift ;;
    --api-key) API_KEY_ARG="$2"; shift 2 ;;
    *) shift ;;
  esac
done

banner() {
  echo ""
  echo -e "${DIM}"
  echo "   ██████╗ ██╗  ██╗ ██████╗ ███████╗████████╗"
  echo "  ██╔════╝ ██║  ██║██╔═══██╗██╔════╝╚══██╔══╝"
  echo "  ██║  ███╗███████║██║   ██║███████╗   ██║"
  echo "  ██║   ██║██╔══██║██║   ██║╚════██║   ██║"
  echo "  ╚██████╔╝██║  ██║╚██████╔╝███████║   ██║"
  echo "   ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝"
  echo -e "${RST}"
  echo -e "  ${B}Ghost Installer${RST}"
  echo ""
}

step() { echo -e "\n  ${CYN}▸${RST} ${B}$1${RST}"; }
ok()   { echo -e "    ${GRN}✓${RST} $1"; }
warn() { echo -e "    ${YLW}⚠${RST} $1"; }
fail() { echo -e "    ${RED}✗${RST} $1"; exit 1; }

banner

# ── 0. Detect if we're inside the repo or need to clone ───────────────

if [ -f "ghost.py" ] && [ -f "requirements.txt" ]; then
  GHOST_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd || pwd)"
  ok "Running inside Ghost repo: $GHOST_DIR"
else
  step "Cloning Ghost..."
  if ! command -v git &>/dev/null; then
    fail "git is required. Install it first: https://git-scm.com"
  fi
  if [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/ghost.py" ]; then
    ok "Ghost already cloned at $INSTALL_DIR — pulling latest"
    git -C "$INSTALL_DIR" pull --ff-only 2>/dev/null || true
  else
    git clone "$GHOST_REPO" "$INSTALL_DIR"
    ok "Cloned to $INSTALL_DIR"
  fi
  GHOST_DIR="$INSTALL_DIR"
  cd "$GHOST_DIR"
fi

VENV_DIR="$GHOST_DIR/.venv"
GHOST_HOME="$HOME/.ghost"

# ── 1. Check Python ───────────────────────────────────────────────────

step "Checking Python..."
PY=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    PY_MAJOR=$($cmd -c 'import sys; print(sys.version_info.major)' 2>/dev/null || echo 0)
    PY_MINOR=$($cmd -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo 0)
    if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
      PY="$cmd"
      break
    fi
  fi
done

if [ -z "$PY" ]; then
  fail "Python 3.10+ is required. Install it from https://python.org"
fi

PY_VERSION=$($PY -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
ok "Python $PY_VERSION ($PY)"

# ── 2. Create virtual environment ─────────────────────────────────────

step "Setting up virtual environment..."
if [ -d "$VENV_DIR" ]; then
  ok "Virtual environment already exists at .venv/"
else
  $PY -m venv "$VENV_DIR" || fail "Failed to create virtual environment. Install python3-venv if on Linux."
  ok "Created .venv/"
fi

# Activate (works on macOS and Linux)
source "$VENV_DIR/bin/activate"
ok "Activated .venv/ ($(python --version 2>&1))"

# ── 3. Install dependencies ──────────────────────────────────────────

step "Installing Python dependencies..."
pip install --upgrade pip -q 2>&1 | tail -1 || true
pip install -r "$GHOST_DIR/requirements.txt" -q 2>&1 | tail -1 || fail "pip install failed — check requirements.txt"
ok "Dependencies installed"

# ── 4. Optional: Playwright ──────────────────────────────────────────

step "Browser automation (optional)..."
INSTALL_PW=false

if [ "$WITH_PLAYWRIGHT" = true ]; then
  INSTALL_PW=true
elif [ "$NO_INTERACTIVE" = false ]; then
  echo ""
  echo -e "    Playwright enables Ghost to control a real browser."
  echo -e "    This downloads ~150MB of browser binaries."
  echo ""
  read -p "    Install Playwright? [y/N] " -n 1 -r
  echo ""
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    INSTALL_PW=true
  fi
fi

if [ "$INSTALL_PW" = true ]; then
  pip install playwright -q 2>/dev/null
  python -m playwright install chromium 2>/dev/null
  ok "Playwright + Chromium installed"
else
  ok "Skipped (install later: pip install playwright && python -m playwright install chromium)"
fi

# ── 5. Create ~/.ghost directory ─────────────────────────────────────

step "Setting up Ghost home directory..."
mkdir -p "$GHOST_HOME"/{cron,skills,plugins,screenshots,evolve/backups}
ok "Created ~/.ghost/"

# ── 6. API Key ───────────────────────────────────────────────────────

step "OpenRouter API key..."

if [ -n "${OPENROUTER_API_KEY:-}" ]; then
  ok "Found OPENROUTER_API_KEY in environment"
elif [ -n "$API_KEY_ARG" ]; then
  export OPENROUTER_API_KEY="$API_KEY_ARG"
  ok "API key set from --api-key flag"
elif [ "$NO_INTERACTIVE" = false ]; then
  echo ""
  echo -e "    Ghost uses OpenRouter to access LLMs (GPT-4o, Claude, Gemini, etc.)"
  echo -e "    Get a free key at: ${CYN}https://openrouter.ai/keys${RST}"
  echo -e "    Or skip — the dashboard has a setup wizard for all providers."
  echo ""
  read -p "    Enter your OpenRouter API key (or press Enter to skip): " API_KEY
  echo ""
  if [ -n "$API_KEY" ]; then
    SHELL_NAME="$(basename "${SHELL:-bash}")"
    if [ "$SHELL_NAME" = "zsh" ]; then
      RC_FILE="$HOME/.zshrc"
    elif [ "$SHELL_NAME" = "bash" ]; then
      RC_FILE="$HOME/.bashrc"
    else
      RC_FILE="$HOME/.profile"
    fi

    if ! grep -q "OPENROUTER_API_KEY" "$RC_FILE" 2>/dev/null; then
      echo "" >> "$RC_FILE"
      echo "# Ghost AI — OpenRouter API key" >> "$RC_FILE"
      echo "export OPENROUTER_API_KEY=\"$API_KEY\"" >> "$RC_FILE"
      ok "Saved to $RC_FILE"
    else
      warn "OPENROUTER_API_KEY already exists in $RC_FILE — not overwriting"
    fi
    export OPENROUTER_API_KEY="$API_KEY"
  else
    warn "Skipped — the dashboard will walk you through setup on first launch"
  fi
else
  warn "No API key — configure via dashboard setup wizard after launch"
fi

# ── 7. Mark scripts executable ───────────────────────────────────────

chmod +x "$GHOST_DIR/start.sh" "$GHOST_DIR/stop.sh" 2>/dev/null || true

# ── 8. Done — start Ghost and open dashboard ─────────────────────────

echo ""
echo -e "  ${GRN}${B}════════════════════════════════════════════════════${RST}"
echo -e "  ${GRN}${B}  Ghost installed successfully!${RST}"
echo -e "  ${GRN}${B}════════════════════════════════════════════════════${RST}"
echo ""
echo -e "  ${B}Commands:${RST}"
echo ""
echo -e "    ${CYN}cd $GHOST_DIR && ./start.sh${RST}    Start Ghost"
echo -e "    ${CYN}./stop.sh${RST}                      Stop Ghost"
echo ""
echo -e "  ${B}Dashboard:${RST}  ${CYN}http://localhost:3333${RST}"
echo ""
echo -e "  ${DIM}Docs: README.md | docs/ARCHITECTURE.md${RST}"
echo ""

step "Starting Ghost..."

cd "$GHOST_DIR"
nohup "$GHOST_DIR/start.sh" > /dev/null 2>&1 &
GHOST_PID=$!

ok "Ghost is starting in the background (PID $GHOST_PID)"
echo ""

# Wait for the dashboard to become available, then open it
DASHBOARD_URL="http://localhost:3333"
MAX_WAIT=60
WAITED=0
echo -e "    ${DIM}Waiting for dashboard...${RST}"

while [ $WAITED -lt $MAX_WAIT ]; do
  if curl -s -o /dev/null -w "%{http_code}" "$DASHBOARD_URL" 2>/dev/null | grep -q "200"; then
    break
  fi
  sleep 2
  WAITED=$((WAITED + 2))
done

if [ $WAITED -lt $MAX_WAIT ]; then
  ok "Dashboard is live at ${CYN}${DASHBOARD_URL}${RST}"
  echo ""
  # Open browser (works on macOS and most Linux desktops)
  if command -v open &>/dev/null; then
    open "$DASHBOARD_URL"
  elif command -v xdg-open &>/dev/null; then
    xdg-open "$DASHBOARD_URL"
  fi
  echo -e "  ${GRN}${B}Ghost is running! The dashboard should open in your browser.${RST}"
else
  warn "Dashboard not yet responding — Ghost may still be booting."
  echo -e "    Open ${CYN}${DASHBOARD_URL}${RST} in your browser once it's ready."
fi
echo ""
