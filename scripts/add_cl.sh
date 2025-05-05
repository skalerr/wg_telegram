#!/bin/bash
set -e
USERNAME="$1"
IP_OCTET="$2"

# Загружаем переменные окружения (public_key, endpoint и т.д.)
source variables.sh

# Пути для ключей клиента
PRIVATE_KEY_PATH="/etc/wireguard/${USERNAME}_privatekey"
PUBLIC_KEY_PATH="/etc/wireguard/${USERNAME}_publickey"

# Генерация ключей клиента
wg genkey | tee "${PRIVATE_KEY_PATH}" | wg pubkey | tee "${PUBLIC_KEY_PATH}" > /dev/null

# Добавляем peer в основной конфиг
cat <<EOF >> /etc/wireguard/wg0.conf

[Peer]
PublicKey = $(cat "${PUBLIC_KEY_PATH}")
AllowedIPs = 10.10.0.${IP_OCTET}/32
EOF

# Перезапуск интерфейса
wg-quick down wg0 && wg-quick up wg0

# Создаём конфиг клиента
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

# Перезапуск интерфейса после добавления
wg-quick down wg0 && wg-quick up wg0

# Сохранение в списке конфигов
echo "10.10.0.${IP_OCTET} = ${USERNAME}" >> cofigs.txt

echo "Клиент ${USERNAME} (${IP_OCTET}) добавлен."