#!/bin/bash

var_username=$1
var_ip_address=$2
var_port=$3
var_ip_address_glob2="$ip_address_glob"
source variables.sh
((vap_ip_local++))

# Запрос имени пользователя
#read -p "Введите имя пользователя: " var_username

# Generate keys
wg genkey | tee "/etc/wireguard/${var_username}_privatekey" | wg pubkey | tee "/etc/wireguard/${var_username}_publickey" > /dev/null

# Add peer to server config
echo "[Peer]" >> /etc/wireguard/wg0.conf
echo "PublicKey = $(cat "/etc/wireguard/${var_username}_publickey")" >> /etc/wireguard/wg0.conf
echo "AllowedIPs = ${var_ip_address}/32" >> /etc/wireguard/wg0.conf

# Restart WireGuard interface
wg-quick down wg0
wg-quick up wg0

# Добавим отладочную информацию
ls -la "/etc/wireguard"

# Remove existing client config if exists
if [ -e "/etc/wireguard/${var_username}_cl.conf" ]; then
  rm "/etc/wireguard/${var_username}_cl.conf"
fi

# Добавим отладочную информацию
ls -la "/etc/wireguard"

# Create client config
echo "[Interface]
PrivateKey = $(cat "/etc/wireguard/${var_username}_privatekey")
Address = ${var_ip_address}/24
DNS = 8.8.8.8

[Peer]
PublicKey = ${var_public_key}
Endpoint = ${ip_address_glob}:${var_port}
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 20" | tee -a /etc/wireguard/${var_username}_cl.conf

# Restart WireGuard interface
wg-quick down wg0
wg-quick up wg0

# Перезаписываем значение переменной vap_ip_local в файле variables.sh
grep -q "vap_ip_local=" variables.sh && sed -i "s/vap_ip_local=.*/vap_ip_local=${vap_ip_local}/" variables.sh || echo "vap_ip_local=${vap_ip_local}" >> variables.sh

echo "ip_address_glob=${ip_address_glob}" >> variables.sh
echo "Новый клиент ${var_username} добавлен с IP ${var_ip_address}"
echo "${var_ip_address} = ${var_username}" >> cofigs.txt

exit 0

