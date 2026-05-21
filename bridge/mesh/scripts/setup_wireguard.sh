#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# setup_wireguard.sh
# ═══════════════════════════════════════════════════════════════════════════════
#
# SYNOPSIS
#   Installs and configures WireGuard on a Linux cloud node for the SimplePod mesh.
#
# DESCRIPTION
#   ELI5: This is like the trench-digging crew for your underground power lines.
#         They check they have a permit (root), install the conduit (WireGuard),
#         cut the lock-and-key set (private/public keys), and wire both ends
#         into the breaker panels. If the ground is frozen or the permit is missing,
#         they stop immediately and radio the foreman (exit with an error).
#
# USAGE
#   sudo ./setup_wireguard.sh --node-id simplepod-rtx5090-pl-01 --address 10.200.0.10/32
#
# OPTIONS
#   --node-id       Human-readable node identifier.
#   --address       WireGuard tunnel IP address with CIDR.
#   --listen-port   UDP port to listen on (default: 51820).
#   --peer-pubkey   Public key of a peer to add immediately.
#   --peer-endpoint IP:port of that peer.
#   --peer-allowed  Comma-separated CIDRs the peer may route.
#   --keepalive     Persistent keepalive seconds (default: 25).
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Permit check: only the foreman (root) can run this ────────────────────────
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "[ERROR] This script must run as root. Use: sudo $0" >&2
    exit 1
fi

# ── Defaults ──────────────────────────────────────────────────────────────────
NODE_ID=""
ADDRESS=""
LISTEN_PORT=51820
PEER_PUBKEY=""
PEER_ENDPOINT=""
PEER_ALLOWED=""
KEEPALIVE=25
INTERFACE="wg0"

# ── Logging helpers ───────────────────────────────────────────────────────────
log_info()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO]  $*"; }
log_warn()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARN]  $*" >&2; }
log_error() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*" >&2; }
log_success(){ echo "[$(date '+%Y-%m-%d %H:%M:%S')] [OK]    $*"; }

# ── Argument parser ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --node-id)
            NODE_ID="$2"
            shift 2
            ;;
        --address)
            ADDRESS="$2"
            shift 2
            ;;
        --listen-port)
            LISTEN_PORT="$2"
            shift 2
            ;;
        --peer-pubkey)
            PEER_PUBKEY="$2"
            shift 2
            ;;
        --peer-endpoint)
            PEER_ENDPOINT="$2"
            shift 2
            ;;
        --peer-allowed)
            PEER_ALLOWED="$2"
            shift 2
            ;;
        --keepalive)
            KEEPALIVE="$2"
            shift 2
            ;;
        --interface)
            INTERFACE="$2"
            shift 2
            ;;
        -h|--help)
            sed -n '3,30p' "$0"
            exit 0
            ;;
        *)
            log_error "Unknown argument: $1"
            exit 1
            ;;
    esac
done

# ── Validation ────────────────────────────────────────────────────────────────
if [[ -z "${NODE_ID}" ]]; then
    log_error "--node-id is required."
    exit 1
fi

if [[ -z "${ADDRESS}" ]]; then
    log_error "--address is required (e.g., 10.200.0.10/32)."
    exit 1
fi

# Quick CIDR sanity check using ipcalc if available, otherwise basic regex.
if command -v ipcalc &>/dev/null; then
    if ! ipcalc -c "$ADDRESS" 2>/dev/null; then
        log_error "Invalid CIDR address: $ADDRESS"
        exit 1
    fi
else
    if [[ ! "$ADDRESS" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$ ]]; then
        log_error "Address does not look like a CIDR: $ADDRESS"
        exit 1
    fi
fi

log_info "Starting WireGuard setup for node '$NODE_ID'"

# ── Detect package manager and install WireGuard ──────────────────────────────
install_wireguard() {
    if command -v apt-get &>/dev/null; then
        log_info "Detected apt (Debian/Ubuntu)."
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq wireguard wireguard-tools
    elif command -v dnf &>/dev/null; then
        log_info "Detected dnf (RHEL/Fedora)."
        dnf install -y -q wireguard-tools
    elif command -v yum &>/dev/null; then
        log_info "Detected yum (legacy RHEL/CentOS)."
        yum install -y -q wireguard-tools
    elif command -v pacman &>/dev/null; then
        log_info "Detected pacman (Arch)."
        pacman -Sy --noconfirm --quiet wireguard-tools
    elif command -v zypper &>/dev/null; then
        log_info "Detected zypper (openSUSE)."
        zypper --quiet install -y wireguard-tools
    else
        log_error "No supported package manager found. Install WireGuard manually."
        exit 1
    fi
}

if ! command -v wg &>/dev/null; then
    log_warn "WireGuard not found. Installing..."
    install_wireguard
    log_success "WireGuard installed."
else
    log_info "WireGuard already installed."
fi

# ── Enable IP forwarding (required for mesh routing) ──────────────────────────
log_info "Enabling IP forwarding..."
sysctl -w net.ipv4.ip_forward=1 >/dev/null
sysctl -w net.ipv6.conf.all.forwarding=1 >/dev/null

# Make it survive reboot.
if [[ -f /etc/sysctl.conf ]]; then
    if ! grep -q "^net.ipv4.ip_forward=1" /etc/sysctl.conf; then
        echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
    fi
    if ! grep -q "^net.ipv6.conf.all.forwarding=1" /etc/sysctl.conf; then
        echo "net.ipv6.conf.all.forwarding=1" >> /etc/sysctl.conf
    fi
fi

# ── Generate key pair ─────────────────────────────────────────────────────────
CONFIG_DIR="/etc/wireguard"
PRIVATE_KEY_FILE="${CONFIG_DIR}/${INTERFACE}.private"
PUBLIC_KEY_FILE="${CONFIG_DIR}/${INTERFACE}.public"
CONFIG_FILE="${CONFIG_DIR}/${INTERFACE}.conf"

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

if [[ -f "$PRIVATE_KEY_FILE" ]]; then
    log_warn "Existing private key found. Re-using it."
    PRIVATE_KEY=$(cat "$PRIVATE_KEY_FILE")
    PUBLIC_KEY=$(cat "$PUBLIC_KEY_FILE")
else
    log_info "Generating new WireGuard key pair..."
    PRIVATE_KEY=$(wg genkey)
    PUBLIC_KEY=$(echo "$PRIVATE_KEY" | wg pubkey)
    echo "$PRIVATE_KEY" > "$PRIVATE_KEY_FILE"
    echo "$PUBLIC_KEY" > "$PUBLIC_KEY_FILE"
    chmod 600 "$PRIVATE_KEY_FILE"
    log_success "Keys generated. Public key: ${PUBLIC_KEY}"
fi

# ── Build configuration file ──────────────────────────────────────────────────
log_info "Writing WireGuard config to $CONFIG_FILE"

# Ensure old config doesn't leak.
rm -f "$CONFIG_FILE"

cat > "$CONFIG_FILE" <<EOF
# SimplePod mesh configuration for ${NODE_ID}
# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
# ELI5: This is the wiring diagram for this node's breaker panel.

[Interface]
Address = ${ADDRESS}
ListenPort = ${LISTEN_PORT}
PrivateKey = ${PRIVATE_KEY}
MTU = 1280

# NAT traversal & keepalive
PostUp = iptables -A FORWARD -i ${INTERFACE} -j ACCEPT; iptables -A FORWARD -o ${INTERFACE} -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE 2>/dev/null || true
PostDown = iptables -D FORWARD -i ${INTERFACE} -j ACCEPT; iptables -D FORWARD -o ${INTERFACE} -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE 2>/dev/null || true
EOF

# Add peer if provided.
if [[ -n "${PEER_PUBKEY}" ]]; then
    log_info "Adding initial peer ${PEER_PUBKEY}"
    {
        echo ""
        echo "[Peer]"
        echo "PublicKey = ${PEER_PUBKEY}"
        if [[ -n "${PEER_ENDPOINT}" ]]; then
            echo "Endpoint = ${PEER_ENDPOINT}"
        fi
        if [[ -n "${PEER_ALLOWED}" ]]; then
            # Normalize commas to spaces then join with comma.
            allowed=$(echo "$PEER_ALLOWED" | tr ',' ' ' | tr -s ' ' | sed 's/ /, /g')
            echo "AllowedIPs = ${allowed}"
        else
            echo "AllowedIPs = 0.0.0.0/0"
        fi
        echo "PersistentKeepalive = ${KEEPALIVE}"
    } >> "$CONFIG_FILE"
fi

chmod 600 "$CONFIG_FILE"

# ── Start / restart the tunnel ────────────────────────────────────────────────
log_info "Bringing interface ${INTERFACE} UP..."
if systemctl is-active --quiet "wg-quick@${INTERFACE}" 2>/dev/null; then
    systemctl restart "wg-quick@${INTERFACE}"
else
    systemctl enable --now "wg-quick@${INTERFACE}"
fi

# ── Verify ────────────────────────────────────────────────────────────────────
if ! wg show "$INTERFACE" >/dev/null 2>&1; then
    log_error "WireGuard interface $INTERFACE failed to come up. Check 'dmesg' and 'journalctl -u wg-quick@${INTERFACE}'."
    exit 1
fi

log_success "Interface ${INTERFACE} is UP."
log_info "$(wg show "$INTERFACE" | head -n 4)"

# ── Persist metadata for mesh_configurator ────────────────────────────────────
META_DIR="/var/lib/simplepod"
mkdir -p "$META_DIR"
chmod 755 "$META_DIR"

cat > "${META_DIR}/node.json" <<EOF
{
  "node_id": "${NODE_ID}",
  "interface": "${INTERFACE}",
  "address": "${ADDRESS}",
  "listen_port": ${LISTEN_PORT},
  "public_key": "${PUBLIC_KEY}",
  "keepalive": ${KEEPALIVE},
  "role": "simplepod_rtx5090",
  "gpu_type": "RTX 5090",
  "status": "online",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

log_success "Setup complete. Node '${NODE_ID}' is wired into the mesh."
log_info "Public key (share with peers): ${PUBLIC_KEY}"
