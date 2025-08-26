#!/bin/bash

var_username=$1
specified_ip=$2
var_ip_address_glob2="$ip_address_glob"
source variables.sh
source scripts/env.sh

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

# Перезаписываем значение переменной vap_ip_local в файле variables.sh
grep -q "vap_ip_local=" variables.sh && sed -i "s/vap_ip_local=.*/vap_ip_local=${vap_ip_local}/" variables.sh || echo "vap_ip_local=${vap_ip_local}" >> variables.sh

echo "ip_address_glob=${ip_address_glob}" >> variables.sh
echo "Новый клиент ${var_username} добавлен."
echo "$wg_local_ip_hint.${vap_ip_local} = ${var_username}" >> cofigs.txt

exit 0

