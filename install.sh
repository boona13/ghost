#!/usr/bin/env bash
set -euo pipefail

# ── Ghost Installer ──────────────────────────────────────────────────
# Sets up a Python virtual environment, installs dependencies,
# and walks you through first-time configuration.
# Usage:  bash install.sh
# ─────────────────────────────────────────────────────────────────────

GHOST_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$GHOST_DIR/.venv"
GHOST_HOME="$HOME/.ghost"
CONFIG_FILE="$GHOST_HOME/config.json"

RST="\033[0m"; B="\033[1m"; DIM="\033[2m"
RED="\033[31m"; GRN="\033[32m"; YLW="\033[33m"; CYN="\033[36m"

banner() {
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

# ── Start ─────────────────────────────────────────────────────────────

banner

# 1. Check Python
step "Checking Python..."
if command -v python3 &>/dev/null; then
  PY="python3"
elif command -v python &>/dev/null; then
  PY="python"
else
  fail "Python 3.10+ is required. Install it from https://python.org"
fi

PY_VERSION=$($PY -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$($PY -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$($PY -c 'import sys; print(sys.version_info.minor)')

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
  fail "Python 3.10+ required (found $PY_VERSION)"
fi
ok "Python $PY_VERSION"

# 2. Create virtual environment
step "Setting up virtual environment..."
if [ -d "$VENV_DIR" ]; then
  ok "Virtual environment already exists at .venv/"
else
  $PY -m venv "$VENV_DIR"
  ok "Created .venv/"
fi

# Activate
source "$VENV_DIR/bin/activate"
ok "Activated .venv/"

# 3. Install dependencies
step "Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r "$GHOST_DIR/requirements.txt" -q
ok "Core dependencies installed (flask, requests, pyyaml, croniter)"

# 4. Optional: Playwright
step "Browser automation (optional)..."
echo ""
echo -e "    Playwright enables Ghost to control a real browser."
echo -e "    This downloads ~150MB of browser binaries."
echo ""
read -p "    Install Playwright? [y/N] " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
  pip install playwright -q
  python -m playwright install chromium
  ok "Playwright + Chromium installed"
else
  ok "Skipped (you can install later with: pip install playwright && python -m playwright install chromium)"
fi

# 5. Create ~/.ghost directory
step "Setting up Ghost home directory..."
mkdir -p "$GHOST_HOME"
mkdir -p "$GHOST_HOME/cron"
mkdir -p "$GHOST_HOME/skills"
mkdir -p "$GHOST_HOME/plugins"
mkdir -p "$GHOST_HOME/screenshots"
mkdir -p "$GHOST_HOME/evolve/backups"
ok "Created ~/.ghost/"

# 6. API Key
step "OpenRouter API key..."
echo ""
if [ -n "${OPENROUTER_API_KEY:-}" ]; then
  ok "Found OPENROUTER_API_KEY in environment"
else
  echo -e "    Ghost uses OpenRouter to access LLMs (GPT-4o, Claude, Gemini, etc.)"
  echo -e "    Get a free key at: ${CYN}https://openrouter.ai/keys${RST}"
  echo ""
  read -p "    Enter your OpenRouter API key (or press Enter to skip): " API_KEY
  echo ""
  if [ -n "$API_KEY" ]; then
    SHELL_NAME="$(basename "$SHELL")"
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
    warn "Skipped — set it later: export OPENROUTER_API_KEY=sk-or-v1-..."
  fi
fi

# 7. Verify launch scripts
step "Checking launch scripts..."
chmod +x "$GHOST_DIR/start.sh" "$GHOST_DIR/stop.sh" 2>/dev/null
ok "start.sh — launches Ghost with supervisor"
ok "stop.sh — stops Ghost"

# 8. Summary
echo ""
echo -e "  ${GRN}${B}════════════════════════════════════════════════════${RST}"
echo -e "  ${GRN}${B}  Installation complete!${RST}"
echo -e "  ${GRN}${B}════════════════════════════════════════════════════${RST}"
echo ""
echo -e "  ${B}Quick start:${RST}"
echo ""
echo -e "    ${CYN}./start.sh${RST}                     Start Ghost (with supervisor)"
echo -e "    ${CYN}./stop.sh${RST}                      Stop Ghost"
echo ""
echo -e "  ${B}Or manually:${RST}"
echo ""
echo -e "    ${CYN}source .venv/bin/activate${RST}"
echo -e "    ${CYN}python ghost_supervisor.py${RST}      Start with supervisor"
echo -e "    ${CYN}python ghost.py${RST}                 Start without supervisor"
echo ""
echo -e "  ${B}Dashboard:${RST}  ${CYN}http://localhost:3333${RST}"
echo ""
echo -e "  On first launch, Ghost creates default SOUL.md and USER.md."
echo -e "  If no API key is set, the dashboard opens a ${B}setup wizard${RST}."
echo ""
echo -e "  ${DIM}Docs: README.md | docs/ARCHITECTURE.md${RST}"
echo ""
