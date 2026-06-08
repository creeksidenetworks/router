#!/bin/bash
# This script is executed at boot time after VyOS/EdgeOS configuration is fully applied.

if [ -f /config/ipsec.d/radius_auth.conf ]; then 
    if [ ! -f /etc/strongswan.d/radius_auth.conf ]; then
        echo "update strongswan radius auth configuration"
        sudo ln -fs /config/ipsec.d/radius_auth.conf /etc/strongswan.d/radius_auth.conf
        sudo ipsec restart
    else
        echo "existing strongswan radius auth configuration found, bypass"
    fi
else
    echo "source strongswan radius auth not found"
fi
