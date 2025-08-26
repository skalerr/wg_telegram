#!/bin/bash

source scripts/variables.sh

ip=$1
my_variable=$(grep -n "$wg_local_ip_hint.${ip}" /etc/wireguard/wg0.conf | cut -d ':' -f 1)

if [ -z "$my_variable" ]; then
    echo "IP адрес $wg_local_ip_hint.$ip не найден в конфигурации"
    exit 1
fi

sed -i "$(($my_variable-2)),$my_variable d" /etc/wireguard/wg0.conf
#systemctl restart wg-quick@wg0
wg-quick down wg0
wg-quick up wg0

