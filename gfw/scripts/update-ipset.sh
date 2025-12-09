#!/bin/bash

if [[ $# == "0" ]] || [[ $1 == "NETS_CHINA" ]]; then
    IPSET_NAME="NETS_CHINA"
    IPSET_FILE="/config/user-data/gfw/ipset.d/ipv4-cn.ipset"
    URL="https://raw.githubusercontent.com/mayaxcn/china-ip-list/master/chnroute.txt"
    HASH_SIZE=16384
    MAX_ELEM=65536
elif [[ $1 == "NETS_USA" ]]; then
    IPSET_NAME="NETS_USA"
    IPSET_FILE="/config/user-data/gfw/ipset.d/ipv4-usa.ipset"
    URL="http://www.ipdeny.com/ipblocks/data/countries/us.zone"
    HASH_SIZE=131072
    MAX_ELEM=131072
fi

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


# Create a temporary file for the download
TEMP_FILE=$(mktemp)

# Determine the interface for routing to 8.8.8.8
INTERFACE=$(ip -4 --oneline route show 8.8.8.8 | awk '{print $3}')

# Check if the interface was found
if [ -z "$INTERFACE" ]; then
    echo "Downloading $IPSET_NAME from github"
    # Download the file to the temporary file using the default route
    sudo curl -# -L -o "$TEMP_FILE" "$URL"
else
    echo "Downloading $IPSET_NAME from github @ $INTERFACE"
    sudo curl -# -L --interface "$INTERFACE" -o "$TEMP_FILE" "$URL"
fi

# Download the file to the temporary file using the specified interface
if [ $? -eq 0 ]; then
    if [ ! -s "$TEMP_FILE" ]; then 
        echo "Error: Downloaded file failure, use stored ipset file instead"
    else
        # remove comments
        #sed -i '/^#/d' "$TEMP_FILE"
        #NUM_RULES=$(cat $TEMP_FILE | wc -l)
        #if [ $NUM_RULES -gt 6000 ]; then
            log_message "update $IPSET_NAME file $IPSET_FILE." 6
            # Use sed to prepend ipset commands and use sudo to move to the target location
            sed "s/^/add $IPSET_NAME /" "$TEMP_FILE" | sudo tee "$IPSET_FILE" > /dev/null
        #fi
    fi
else 
    echo "Error: Downloaded file failure, use stored ipset file instead"
fi

if sudo ipset list -t $IPSET > /dev/null 2>&1; then
    IPTABLES_TEMP_FILE=$(mktemp)

    # Save current iptables rules to a temporary file
    sudo iptables-save > "$IPTABLES_TEMP_FILE"

    # Remove ipset references from iptables rules
    sudo iptables-save | grep -v "$IPSET_NAME" | sudo iptables-restore

    # Destroy the existing ipset
    sudo ipset destroy "$IPSET_NAME"

    # Create a new ipset with the updated hash size
    sudo ipset create "$IPSET_NAME" hash:net hashsize "$HASH_SIZE" maxelem "$MAX_ELEM"

    # Restore the original iptables rules
    sudo iptables-restore < "$IPTABLES_TEMP_FILE"

    # clear existing ipset
    sudo rm "$IPTABLES_TEMP_FILE"
else
    sudo ipset create $IPSET_NAME hash:net hashsize $HASH_SIZE maxelem $MAX_ELEM 
    log_message "create ipset \"$IPSET_NAME\"." 3
fi

# restore from file
sudo ipset restore -file "$IPSET_FILE"

# check number of entries
NUM_RULES=$(sudo ipset list -t $IPSET_NAME | grep "Number of entries:" | sed 's/[^0-9]*//g')
log_message "ipset \"$IPSET_NAME\": $NUM_RULES rules loaded "


# Cleanup temporary file
rm "$TEMP_FILE"
