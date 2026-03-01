#!/usr/bin/env bash
# Start Ghost with the supervisor (recommended)
# Usage: ./start.sh [--api-key sk-or-...]

GHOST_DIR="$(cd "$(dirname "$0")" && pwd)"

# Use virtual environment if it exists
if [ -d "$GHOST_DIR/.venv" ]; then
  source "$GHOST_DIR/.venv/bin/activate"
fi

# Check if Ghost is already running
GHOST_HOME="$HOME/.ghost"
if [ -f "$GHOST_HOME/supervisor.pid" ]; then
  PID=$(cat "$GHOST_HOME/supervisor.pid")
  if kill -0 "$PID" 2>/dev/null; then
    echo "Ghost is already running (supervisor PID $PID)"
    echo "Dashboard: http://localhost:3333"
    echo "To stop: ./stop.sh"
    exit 0
  fi
fi

if [ -f "$GHOST_HOME/ghost.pid" ]; then
  PID=$(cat "$GHOST_HOME/ghost.pid")
  if kill -0 "$PID" 2>/dev/null; then
    echo "Ghost is already running (PID $PID) without supervisor."
    echo "Dashboard: http://localhost:3333"
    echo "To stop: ./stop.sh"
    exit 0
  fi
fi

exec python3 "$GHOST_DIR/ghost_supervisor.py" "$@"
