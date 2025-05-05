#!/bin/bash

ip=$1
source variables.sh

# Get the network prefix from vpn_network
network_prefix=${vpn_network%.*}

# Find and remove the peer configuration
my_variable=$(grep -n "${network_prefix}.${ip}" /etc/wireguard/wg0.conf | cut -d ':' -f 1)

if [ ! -z "$my_variable" ]; then
    sed -i "$(($my_variable-2)),$my_variable d" /etc/wireguard/wg0.conf
    wg-quick down wg0
    wg-quick up wg0

    # Update the vap_ip_local to the next available IP
    # Read all used IPs from cofigs.txt
    used_ips=$(grep -o "${network_prefix}\.[0-9]*" cofigs.txt | cut -d'.' -f4 | sort -n)
    
    # Find the first available IP
    next_ip=2
    for used_ip in $used_ips; do
        if [ "$used_ip" -eq "$next_ip" ]; then
            next_ip=$((next_ip + 1))
        else
            break
        fi
    done
    
    # Update vap_ip_local in variables.sh
    sed -i "s/vap_ip_local=.*/vap_ip_local=$next_ip/" variables.sh
fi

