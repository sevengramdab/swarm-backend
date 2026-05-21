#!/usr/bin/env bash
# bootstrap_mesh.sh
# =================
# One-shot mesh join script for cloud/ephemeral nodes.
# Detects Tailscale, joins the mesh, prints health, starts control plane.
#
# ELI5: Like a new construction crew showing up at the site.
#       They check in at the gate (Tailscale), get their badge
#       (mesh IP), and walk straight to their trailer (start working).

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SWARM_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

log() { echo -e "${BLUE}[MESH]${NC} $1"; }
ok()  { echo -e "${GREEN}[OK]${NC}   $1"; }
warn(){ echo -e "${YELLOW}[WARN]${NC} $1"; }
fail(){ echo -e "${RED}[FAIL]${NC} $1"; }

log "=== SimplePod Mesh Bootstrap ==="
log "Node: $(hostname)"
log "Time: $(date -Iseconds)"

# ---------------------------------------------------------------------------
# 1. Tailscale Check
# ---------------------------------------------------------------------------
if command -v tailscale &>/dev/null; then
    ok "Tailscale CLI found"

    if [[ -n "${TAILSCALE_AUTH_KEY:-}" ]]; then
        log "Authenticating with Tailscale..."
        tailscale up --authkey "$TAILSCALE_AUTH_KEY" --accept-routes 2>/dev/null || true
        sleep 2
    else
        warn "TAILSCALE_AUTH_KEY not set. Assuming already authenticated."
    fi

    MESH_IP=$(tailscale ip -4 2>/dev/null || echo "unknown")
    if [[ "$MESH_IP" != "unknown" ]]; then
        ok "Mesh IP assigned: $MESH_IP"
    else
        fail "Could not get Tailscale IP. Mesh may not be functional."
    fi

    # Show peers
    PEERS=$(tailscale status | grep -c "^100\." || echo "0")
    ok "Mesh peers visible: $PEERS"
else
    warn "Tailscale not installed. Run bridge/mesh/scripts/setup_wireguard.sh for alternative."
fi

# ---------------------------------------------------------------------------
# 2. Environment Check
# ---------------------------------------------------------------------------
PYTHON="${SWARM_ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON="python3"
fi

$PYTHON --version >/dev/null 2>&1 || { fail "Python not found"; exit 1; }
ok "Python: $($PYTHON --version 2>&1)"

# ---------------------------------------------------------------------------
# 3. Start Control Plane
# ---------------------------------------------------------------------------
log "Starting SimplePod Control Plane..."
exec "$PYTHON" -m uvicorn interfaces.web_ui.backend.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level info
