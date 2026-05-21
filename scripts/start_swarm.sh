#!/usr/bin/env bash
# start_swarm.sh
# =============
# One-click bash script to activate the SimplePod control plane.
# No more broken nohup modules — just one clean uvicorn process.
#
# ELI5: Like a portable generator with one big red START button.
#       Pull the cord and the whole building powers up.

set -euo pipefail

SWARM_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$SWARM_ROOT/logs"
mkdir -p "$LOG_DIR"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') | $1" | tee -a "$LOG_DIR/swarm.log"
}

log "=== SimplePod Swarm Startup ==="
log "Root: $SWARM_ROOT"

PYTHON="${SWARM_ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON="python3"
    log "Note: .venv not found, falling back to system python3"
fi

# Single process: FastAPI serves API + static dashboard on port 8000
log "Starting Control Plane (FastAPI + Static Dashboard)..."
exec "$PYTHON" -m uvicorn interfaces.web_ui.backend.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level info
