#!/bin/sh
# This script is executed at boot time after EdgeOS/VyOS configuration is fully applied.
# (c) 2024 Creekside Networks LLC, Jackson Tong

#!/bin/bash

# Define the configuration file path and the port to check
CONFIG_FILE="/config/user-data/gfw/dnsmasq-global.conf"
PORT=53053
LOG_FILE="/var/log/gfw.log"
LOG_CAT="gfw"

# Function to log messages
log_message() {
    local message=$1
    local priority=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    if [ -z $priority ]; then
        priority=6
    fi

    case $priority in
        "1" | "2")
            log_level="crtc";;
        "3" | "4" | "5")
            log_level="warn";;
        *)
            log_level="info";;
    esac

    printf "%-10s %s %s: %s\n" "$timestamp" "[$LOG_CAT]" "$log_level" "$message" | sudo tee -a "$LOG_FILE" # > /dev/null
    logger -t gfw -p $priority "$message"

    # Ensure the log file does not exceed 1000 lines
    line_count=$(sudo wc -l < "$LOG_FILE")
    if [ "$line_count" -gt 1000 ]; then
        sudo tail -n 500 "$LOG_FILE" | sudo tee "$LOG_FILE.tmp" > /dev/null
        sudo mv "$LOG_FILE.tmp" "$LOG_FILE"
    fi
}

load_ipset() {
    IPSET=$1
    IPSET_CONF_FILE=$2
    if [ ! -f $IPSET_CONF_FILE ]; then
        log_message "Load ipset $IPSET: File \"$IPSET_CONF_FILE\" not exist." 3
        return 1
    fi

    if sudo ipset list -t $IPSET > /dev/null 2>&1; then
        # clear existing ipset
        sudo ipset flush $IPSET
    else
        sudo ipset create $IPSET hash:net
        log_message "create ipset \"$IPSET\"." 6
    fi

    # restore from file
    sudo ipset restore -file "$IPSET_CONF_FILE"
    # check number of entries
    NUM_RULES=$(sudo ipset list -t $IPSET | grep "Number of entries:" | sed 's/[^0-9]*//g')
    log_message "ipset \"$IPSET\": $NUM_RULES rules loaded "

    return 0
}

launch_dnsmasq() {
    # Check if the port is already in use
    process_id=$(sudo lsof -ti udp:$PORT)

    if [ -n "$process_id" ]; then
        # Kill the process using the specified port
        sudo kill -9 "$process_id"
        log_message "Killed the process using port $PORT" 5
    fi

    # Launch dnsmasq with the custom configuration file
    if sudo dnsmasq --conf-file="$CONFIG_FILE"; then
        # Log a message indicating dnsmasq has been started
        log_message "start dnsmasq global on port $PORT" 6
    else
        # Log an error message if dnsmasq fails to start
        log_message "Failed to start dnsmasq on port $PORT" 3
    fi
}


#load_ipset NETS_USA "/config/user-data/gfw/ipset.d/ipv4-usa.ipset"
load_ipset NETS_CHINA "/config/user-data/gfw/ipset.d/ipv4-cn.ipset"
launch_dnsmasq
