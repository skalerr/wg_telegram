#!/bin/bash

ip=$1
my_variable=$(grep -n "AllowedIPs = $wg_local_ip_hint.${ip}/32" /etc/wireguard/wg0.conf | cut -d ':' -f 1)

if [ -z "$my_variable" ]; then
    echo "Client IP $wg_local_ip_hint.${ip} not found"
    exit 1
fi

sed -i "$(($my_variable-2)),$my_variable d" /etc/wireguard/wg0.conf
#systemctl restart wg-quick@wg0
wg-quick down wg0
wg-quick up wg0

