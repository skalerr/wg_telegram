#!/bin/bash
# add_cl.sh
set -e
USERNAME="$1"
IP_OCTET="$2"

# Подтягиваем переменные
source variables.sh

# Пути к ключам
PRIVATE_KEY_PATH="/etc/wireguard/${USERNAME}_privatekey"
PUBLIC_KEY_PATH="/etc/wireguard/${USERNAME}_publickey"

# Генерация ключей клиента
wg genkey | tee "${PRIVATE_KEY_PATH}" | wg pubkey | tee "${PUBLIC_KEY_PATH}" > /dev/null

# Добавление peer
cat <<EOF >> /etc/wireguard/wg0.conf

[Peer]
PublicKey = $(cat "${PUBLIC_KEY_PATH}")
AllowedIPs = 10.10.0.${IP_OCTET}/32
EOF

wg-quick down wg0 && wg-quick up wg0

# Создание клиентского конфига
CLIENT_CONF="/etc/wireguard/${USERNAME}_cl.conf"
cat <<EOF > "${CLIENT_CONF}"
[Interface]
PrivateKey = $(cat "${PRIVATE_KEY_PATH}")
Address = 10.10.0.${IP_OCTET}/24
DNS = 8.8.8.8

[Peer]
PublicKey = ${var_public_key}
Endpoint = ${ip_address_glob}:51830
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 20
EOF

wg-quick down wg0 && wg-quick up wg0

# Запись в cofigs.txt
echo "10.10.0.${IP_OCTET} = ${USERNAME}" >> cofigs.txt

echo "Клиент ${USERNAME} (${IP_OCTET}) добавлен."
