#!/usr/bin/env bash
# ============================================================================
# Teukhos — Start All Example HTTP Servers
# ============================================================================
#
# PURPOSE:
#   Launches all Teukhos example MCP servers in HTTP mode for local testing.
#   Each server wraps CLI tools (git, ffmpeg, docker, etc.) as MCP endpoints
#   that AI clients like VS Code Copilot can connect to.
#
#   The .vscode/mcp.json file references these HTTP endpoints. Unlike stdio
#   servers (which Copilot auto-starts), HTTP servers must be running BEFORE
#   the client connects — this script handles that.
#
# USAGE:
#   bash scripts/start-http-servers.sh        # Start all servers
#   bash scripts/stop-http-servers.sh         # Stop all servers (separate terminal)
#   Ctrl+C                                    # Stop all servers (this terminal)
#
# PORTS: 8770-8779 (one per example config in examples/*.yaml)
#
# SEE ALSO:
#   scripts/start-http-servers.ps1  — Windows PowerShell equivalent
#   .vscode/mcp.json                — VS Code Copilot server definitions
#   .github/mcp.json                — GitHub.com Copilot server definitions
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PIDFILE="$SCRIPT_DIR/.http-servers.pids"

# Port-to-config mapping (must match .vscode/mcp.json)
declare -A SERVERS=(
  [8770]="git-tools"
  [8771]="dev-tools"
  [8772]="media-tools"
  [8773]="gpu-tools"
  [8774]="docker-tools"
  [8775]="image-tools"
  [8776]="network-tools"
  [8777]="database-tools"
  [8778]="kubernetes-tools"
  [8779]="archive-tools"
)

# Clean up any previous PID file
rm -f "$PIDFILE"

echo "Starting Teukhos HTTP servers..."
echo ""

STARTED=0
FAILED=0

for PORT in $(echo "${!SERVERS[@]}" | tr ' ' '\n' | sort -n); do
  CONFIG="${SERVERS[$PORT]}"
  YAML="$PROJECT_DIR/examples/${CONFIG}.yaml"

  if [[ ! -f "$YAML" ]]; then
    echo "  SKIP  $CONFIG — $YAML not found"
    FAILED=$((FAILED + 1))
    continue
  fi

  teukhos serve "$YAML" -t http -p "$PORT" &
  PID=$!
  echo "$PID $PORT $CONFIG" >> "$PIDFILE"
  echo "  OK    $CONFIG on port $PORT (PID $PID)"
  STARTED=$((STARTED + 1))
done

echo ""
echo "$STARTED servers started, $FAILED skipped."
echo "PIDs saved to $PIDFILE"
echo ""
echo "Press Ctrl+C to stop all servers, or run: bash scripts/stop-http-servers.sh"

# Wait for all background processes — Ctrl+C kills them all
trap 'echo ""; echo "Shutting down..."; kill $(jobs -p) 2>/dev/null; wait; rm -f "$PIDFILE"; echo "All servers stopped."' INT TERM
wait
