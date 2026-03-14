#!/usr/bin/env bash
# Stop the Ghost system (supervisor + daemon)
# Usage: ./stop.sh

GHOST_HOME="$HOME/.ghost"

stopped=false

if [ -f "$GHOST_HOME/supervisor.pid" ]; then
  PID=$(cat "$GHOST_HOME/supervisor.pid")
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null
    echo "Supervisor (PID $PID) stopped."
    stopped=true
  fi
  rm -f "$GHOST_HOME/supervisor.pid"
fi

if [ -f "$GHOST_HOME/ghost.pid" ]; then
  PID=$(cat "$GHOST_HOME/ghost.pid")
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null
    echo "Ghost (PID $PID) stopped."
    stopped=true
  fi
  rm -f "$GHOST_HOME/ghost.pid"
fi

# Stop PinchTab if Ghost started it
if [ -f "$GHOST_HOME/pinchtab.pid" ]; then
  PID=$(cat "$GHOST_HOME/pinchtab.pid")
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null
    echo "PinchTab (PID $PID) stopped."
    stopped=true
  fi
  rm -f "$GHOST_HOME/pinchtab.pid"
fi

if [ "$stopped" = false ]; then
  echo "Ghost is not running."
fi
