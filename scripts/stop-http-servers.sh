#!/usr/bin/env bash
# ============================================================================
# Teukhos — Stop All Example HTTP Servers
# ============================================================================
#
# PURPOSE:
#   Stops all Teukhos example MCP HTTP servers previously started by
#   start-http-servers.sh. Uses the saved PID file for clean shutdown,
#   or falls back to port-based cleanup if no PID file is found.
#
# USAGE:
#   bash scripts/stop-http-servers.sh
#
# PORTS: 8770-8779 (same range as start-http-servers.sh)
#
# SEE ALSO:
#   scripts/start-http-servers.sh   — Starts the servers
#   scripts/stop-http-servers.ps1   — Windows PowerShell equivalent
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$SCRIPT_DIR/.http-servers.pids"

if [[ ! -f "$PIDFILE" ]]; then
  echo "No PID file found at $PIDFILE"
  echo "Falling back to port-based cleanup..."
  echo ""

  KILLED=0
  for PORT in 8770 8771 8772 8773 8774 8775 8776 8777 8778 8779; do
    # Find process listening on this port
    PID=$(lsof -ti :"$PORT" 2>/dev/null || netstat -tlnp 2>/dev/null | grep ":$PORT " | awk '{print $NF}' | cut -d/ -f1 || true)
    if [[ -n "$PID" ]]; then
      kill "$PID" 2>/dev/null && echo "  KILL  port $PORT (PID $PID)" && KILLED=$((KILLED + 1)) || true
    fi
  done

  if [[ $KILLED -eq 0 ]]; then
    echo "No servers found running on ports 8770-8779."
  else
    echo ""
    echo "$KILLED servers stopped."
  fi
  exit 0
fi

echo "Stopping Teukhos HTTP servers..."
echo ""

STOPPED=0
while read -r PID PORT CONFIG; do
  if kill "$PID" 2>/dev/null; then
    echo "  STOP  $CONFIG on port $PORT (PID $PID)"
    STOPPED=$((STOPPED + 1))
  else
    echo "  SKIP  $CONFIG (PID $PID) — already stopped"
  fi
done < "$PIDFILE"

rm -f "$PIDFILE"
echo ""
echo "$STOPPED servers stopped."
