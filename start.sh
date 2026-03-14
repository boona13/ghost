#!/usr/bin/env bash
# Start Ghost with the supervisor (recommended)
# Usage: ./start.sh [--api-key sk-or-...]

GHOST_DIR="$(cd "$(dirname "$0")" && pwd)"

# Use virtual environment if it exists
if [ -d "$GHOST_DIR/.venv" ]; then
  source "$GHOST_DIR/.venv/bin/activate"
fi

GHOST_HOME="$HOME/.ghost"
GHOST_PORT="${GHOST_PORT:-3333}"

# PinchTab: enable JS evaluate endpoint for browser automation fallbacks
export PINCHTAB_ALLOW_EVALUATE="${PINCHTAB_ALLOW_EVALUATE:-true}"

# ── Ensure PinchTab is running (browser automation server) ────────
PINCHTAB_PORT="${PINCHTAB_PORT:-9867}"
if command -v pinchtab &>/dev/null; then
  if ! curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PINCHTAB_PORT/health" 2>/dev/null | grep -q "200"; then
    echo "Starting PinchTab browser server..."
    PINCHTAB_ALLOW_EVALUATE=true nohup pinchtab server > "$GHOST_HOME/pinchtab.log" 2>&1 &
    echo $! > "$GHOST_HOME/pinchtab.pid"
    sleep 2
  fi
fi

# ── Kill any running Ghost instances (PID files + port) ──────────
killed=false

if [ -f "$GHOST_HOME/supervisor.pid" ]; then
  PID=$(cat "$GHOST_HOME/supervisor.pid")
  if kill -0 "$PID" 2>/dev/null; then
    echo "Stopping existing supervisor (PID $PID)..."
    kill "$PID" 2>/dev/null
    for _ in $(seq 1 10); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
    kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null
    killed=true
  fi
  rm -f "$GHOST_HOME/supervisor.pid"
fi

if [ -f "$GHOST_HOME/ghost.pid" ]; then
  PID=$(cat "$GHOST_HOME/ghost.pid")
  if kill -0 "$PID" 2>/dev/null; then
    echo "Stopping existing Ghost daemon (PID $PID)..."
    kill "$PID" 2>/dev/null
    for _ in $(seq 1 10); do kill -0 "$PID" 2>/dev/null || break; sleep 1; done
    kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null
    killed=true
  fi
  rm -f "$GHOST_HOME/ghost.pid"
fi

# Kill any ghost_supervisor.py processes (catches orphaned supervisors whose
# PID files were lost — a live supervisor will respawn ghost after we kill it).
if command -v pgrep &>/dev/null; then
  ORPHAN_SUPS=$(pgrep -f "ghost_supervisor\\.py" 2>/dev/null)
  if [ -n "$ORPHAN_SUPS" ]; then
    echo "Killing orphaned supervisor(s): $ORPHAN_SUPS"
    echo "$ORPHAN_SUPS" | xargs kill 2>/dev/null
    sleep 2
    ORPHAN_SUPS=$(pgrep -f "ghost_supervisor\\.py" 2>/dev/null)
    if [ -n "$ORPHAN_SUPS" ]; then
      echo "$ORPHAN_SUPS" | xargs kill -9 2>/dev/null
      sleep 1
    fi
    killed=true
  fi
fi

# Kill anything still holding the dashboard port (catches orphaned ghost
# processes whose PID files and supervisors are gone).
if command -v lsof &>/dev/null; then
  PORT_PIDS=$(lsof -ti:"$GHOST_PORT" 2>/dev/null)
  if [ -n "$PORT_PIDS" ]; then
    echo "Killing process(es) on port $GHOST_PORT: $PORT_PIDS"
    echo "$PORT_PIDS" | xargs kill 2>/dev/null
    sleep 2
    PORT_PIDS=$(lsof -ti:"$GHOST_PORT" 2>/dev/null)
    if [ -n "$PORT_PIDS" ]; then
      echo "$PORT_PIDS" | xargs kill -9 2>/dev/null
      sleep 1
    fi
    killed=true
  fi
fi

if [ "$killed" = true ]; then
  echo "Previous Ghost instance stopped."
  sleep 2
fi

exec python3 "$GHOST_DIR/ghost_supervisor.py" "$@"
