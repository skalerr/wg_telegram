#!/bin/bash

var_username=$1
specified_ip=$2

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Source configuration files with proper paths
if [ -f "$PARENT_DIR/variables.sh" ]; then
    source "$PARENT_DIR/variables.sh"
elif [ -f "$SCRIPT_DIR/variables.sh" ]; then
    source "$SCRIPT_DIR/variables.sh"
else
    echo "Warning: variables.sh not found, using defaults"
    vap_ip_local=1
    wg_local_ip="10.20.20.1"
    wg_local_ip_hint="10.20.20"
fi

if [ -f "$SCRIPT_DIR/env.sh" ]; then
    source "$SCRIPT_DIR/env.sh"
else
    echo "Warning: env.sh not found, using defaults"
    wg_local_ip_hint="${WG_LOCAL_IP_HINT:-10.20.20}"
fi

var_ip_address_glob2="$ip_address_glob"

# Get server public key
if [ -f "/etc/wireguard/publickey" ]; then
    var_public_key=$(cat /etc/wireguard/publickey)
else
    echo "Error: Server public key not found"
    exit 1
fi

# Get external IP
if [ -z "$ip_address_glob" ]; then
    ip_address_glob=$(curl -s -4 ifconfig.me 2>/dev/null || echo "YOUR_SERVER_IP")
fi

# Use specified IP if provided, otherwise find next available
if [ -n "$specified_ip" ]; then
    # Check if specified IP is already in use
    if grep -q "AllowedIPs = $wg_local_ip_hint.${specified_ip}/32" /etc/wireguard/wg0.conf; then
        echo "Error: IP $wg_local_ip_hint.${specified_ip} is already in use"
        exit 1
    fi
    vap_ip_local=$specified_ip
else
    # Find next available IP (starting from 2, since 1 is server)
    next_ip=2
    while grep -q "AllowedIPs = $wg_local_ip_hint.${next_ip}/32" /etc/wireguard/wg0.conf; do
        ((next_ip++))
    done
    vap_ip_local=$next_ip
fi

# Запрос имени пользователя
#read -p "Введите имя пользователя: " var_username

wg genkey | tee "/etc/wireguard/${var_username}_privatekey" | wg pubkey | tee "/etc/wireguard/${var_username}_publickey" > /dev/null
echo "[Peer]" >> /etc/wireguard/wg0.conf
echo "PublicKey = $(cat "/etc/wireguard/${var_username}_publickey")" >> /etc/wireguard/wg0.conf
echo "AllowedIPs = $wg_local_ip_hint.${vap_ip_local}/32" >> /etc/wireguard/wg0.conf

# Remove existing client config if exists
if [ -e "/etc/wireguard/${var_username}_cl.conf" ]; then
  rm "/etc/wireguard/${var_username}_cl.conf"
fi

# Create client configuration file
echo "[Interface]
PrivateKey = $(cat "/etc/wireguard/${var_username}_privatekey")
Address = $wg_local_ip_hint.${vap_ip_local}/24
DNS = 8.8.8.8
MTU = 1332

[Peer]
PublicKey = ${var_public_key}
Endpoint = ${ip_address_glob}:51830
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 20" > /etc/wireguard/${var_username}_cl.conf

# Restart WireGuard interface only once
echo "Restarting WireGuard interface..."
if ! wg-quick down wg0 2>/dev/null; then
    echo "WireGuard interface was not running"
fi

if wg-quick up wg0; then
    echo "WireGuard interface started successfully"
else
    echo "Failed to start WireGuard interface"
    exit 1
fi

# Update variables in variables.sh file
VARIABLES_FILE="$SCRIPT_DIR/variables.sh"
if [ ! -f "$VARIABLES_FILE" ]; then
    VARIABLES_FILE="$PARENT_DIR/variables.sh"
fi

# Create or update variables.sh
if [ -f "$VARIABLES_FILE" ]; then
    # Update existing file
    grep -q "vap_ip_local=" "$VARIABLES_FILE" && sed -i "s/vap_ip_local=.*/vap_ip_local=${vap_ip_local}/" "$VARIABLES_FILE" || echo "vap_ip_local=${vap_ip_local}" >> "$VARIABLES_FILE"
    grep -q "ip_address_glob=" "$VARIABLES_FILE" && sed -i "s/ip_address_glob=.*/ip_address_glob=${ip_address_glob}/" "$VARIABLES_FILE" || echo "ip_address_glob=${ip_address_glob}" >> "$VARIABLES_FILE"
else
    # Create new file
    cat > "$VARIABLES_FILE" << EOF
vap_ip_local=${vap_ip_local}
wg_local_ip=10.20.20.1
wg_local_ip_hint="10.20.20"
ip_address_glob=${ip_address_glob}
var_public_key="${var_public_key}"
EOF
fi
echo "Новый клиент ${var_username} добавлен."
echo "$wg_local_ip_hint.${vap_ip_local} = ${var_username}" >> cofigs.txt

exit 0

