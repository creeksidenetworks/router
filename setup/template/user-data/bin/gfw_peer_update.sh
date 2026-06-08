#!/bin/sh
# (c) 2022-2025 Creekside Networks LLC, Jackson Tong
# This script will decide the best tunnel for jailbreak based on ping result
# for EdgeOS & VyOS 1.3.4

export PATH="/usr/sbin:/usr/bin:/sbin:/bin"

# Routing table to update
GFW_ROUTING_TABLE="100"

# Log file path
LOG_FILE="/var/log/gfw.log"

# State file to track interface recovery
STATE_FILE="/var/run/gfw_state.txt"

# interface switch decision threshold
LOSS_THRESHOLD="20"

# Consecutive successful pings required for interface recovery
PING_COUNT=30
PING_TARGET_IP="8.8.8.8"
RECOVERY_COUNT="3"

# default interfaces
PRIMARY_IF="wg252"
PRIMARY_LOSS=100
SECONDARY_IF="wg253"
SECONDARY_LOSS=100
BACKUP_IF="wg251"

if [ ! -f "$LOG_FILE" ]; then
    sudo touch "$LOG_FILE"
fi

# Function to parse command line arguments
parse_args() {

    while getopts ":p:s:t:c:b:r:" opt; do
        case $opt in
            c)
                PING_COUNT="$OPTARG"
                ;;
            t)
                # target IP to ping test, default 8.8.8.8
                PING_TARGET_IP="$OPTARG"
                ;;
            p)
                PRIMARY_IF="$OPTARG"
                ;;
            s)
                SECONDARY_IF="$OPTARG"
                ;;
            b)  
                BACKUP_IF="$OPTARG"
                ;;
            r)
                RECOVERY_COUNT="$OPTARG"
                ;;
            \?)
                echo "Usage: $0 [-p <primary i/f>] [-s <secondary if>] [-b <backup if>] [-t <target ping test IP>] [-c <ping counts>] [-r <recovery count>]"
                exit 1
                ;;
        esac
    done
    shift $((OPTIND -1))
}

# Function to get the current default route interface for the specified table
get_current_route_interface() {
    sudo ip -4 -oneline route show table "$GFW_ROUTING_TABLE" | grep -o "dev.*" | awk '{print $2}'
}

# Function to read interface state from state file
read_interface_state() {
    local interface=$1
    if [ -f "$STATE_FILE" ]; then
        grep "^${interface}:" "$STATE_FILE" 2>/dev/null | cut -d':' -f2
    fi
}

# Function to write interface state to state file
write_interface_state() {
    local interface=$1
    local count=$2
        
    # Remove old entry for this interface and add new one
    if grep -q "^${interface}:" "$STATE_FILE" 2>/dev/null; then
        sudo sed -i "/^${interface}:/d" "$STATE_FILE"
    fi
    echo "${interface}:${count}" | sudo tee -a "$STATE_FILE" > /dev/null
}

# Function to check if interface is ready (has enough consecutive successful pings)
is_interface_ready() {
    local interface=$1
    local loss=$2
    
    local success_count=$(read_interface_state "$interface")
    [ -z "$success_count" ] && success_count=0
    
    if [ "$loss" -le "$LOSS_THRESHOLD" ]; then
        # Increment recovery count
        success_count=$((success_count + 1))
        write_interface_state "$interface" "$success_count"
        
        if [ "$success_count" -eq "$RECOVERY_COUNT" ]; then
            log_message "$interface: Now available (${loss}% loss) after ${RECOVERY_COUNT} consecutive tests"
            echo "ready"
            return 0
        elif [ "$success_count" -gt "$RECOVERY_COUNT" ]; then
            echo "ready"
            return 0
        elif [ "$success_count" -lt "$RECOVERY_COUNT" ]; then
            log_message "$interface: Recovering: ${success_count}/${RECOVERY_COUNT}, (${loss}% loss)"
            echo "recovering:${success_count}"
            return 1
        fi
    else
        if [ "$success_count" -gt 0 ]; then
            # Reset recovery count on failure
            write_interface_state "$interface" "0"
            log_message "$interface: Failed (${loss}% loss)"
        fi
        echo "failed"
        return 1
    fi
}

# Function to ping from a specific interface
ping_from_interface() {
    local interface=$1
    local result_file=$2
    sudo ping -q -I "$interface" -c "$PING_COUNT" "$PING_TARGET_IP" > "$result_file" 2>&1
    echo $? > "${result_file}.status"
}

# Function to log messages
log_message() {
    local message=$1
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    printf "%-10s %s\n" "$timestamp" "$message" | sudo tee -a "$LOG_FILE" # > /dev/null

    # Ensure the log file does not exceed 1000 lines
    line_count=$(sudo wc -l < "$LOG_FILE")
    if [ "$line_count" -gt 1000 ]; then
        sudo tail -n 900 "$LOG_FILE" | sudo tee "$LOG_FILE.tmp" > /dev/null
        sudo mv "$LOG_FILE.tmp" "$LOG_FILE"
    fi
}


# Process the results
get_loss_rate() {
    local result_file=$1
    local loss=""

    # Extract packet loss percentage
    loss=$(grep 'packet loss' "$result_file" | cut -d % -f 1 | cut -d "," -f 3 | sed 's/^ *//')
    # Convert to integer
    loss=${loss%.*}   

    if [ -z "$loss" ]; then
        loss="100"
    fi

    #echo "$result_file" : "$loss" : "$(grep 'packet loss' "$result_file")" 

    echo "$loss"
}

clean_and_exit(){
    # Clean up temp files

    rm -rf "$TMP_DIR"
    [ $1 -eq 0 ] || printf 'Exit with Error code '$1'.\n'
    exit $1
}

main() {
    parse_args "$@"

    TMP_DIR=$(mktemp -d)
    PRIMARY_RESULT_FILE="$TMP_DIR/primary_ping_result.txt"
    SECONDARY_RESULT_FILE="$TMP_DIR/secondary_ping_result.txt"
 
    # Print message indicating start of pings
    echo "$(date '+%Y-%m-%d %H:%M:%S') Ping test: ${PRIMARY_IF}, ${SECONDARY_IF}."

    # init state file if not exists
    if [ ! -f "$STATE_FILE" ]; then
        sudo touch "$STATE_FILE"
        write_interface_state "$PRIMARY_IF" "0"
        write_interface_state "$SECONDARY_IF" "0"
    fi

    # Ping from each interface in the background and store the result files
    ping_from_interface "$PRIMARY_IF" "$PRIMARY_RESULT_FILE" &
    ping_from_interface "$SECONDARY_IF" "$SECONDARY_RESULT_FILE" &

    # Wait for all background jobs to complete
    wait

    PRIMARY_LOSS=$(get_loss_rate "$PRIMARY_RESULT_FILE")
    SECONDARY_LOSS=$(get_loss_rate "$SECONDARY_RESULT_FILE")

    # Check interface readiness for primary and secondary
    PRIMARY_STATUS=$(is_interface_ready "$PRIMARY_IF" "$PRIMARY_LOSS" | tail -1)
    SECONDARY_STATUS=$(is_interface_ready "$SECONDARY_IF" "$SECONDARY_LOSS" | tail -1)

    echo "Ping results: $PRIMARY_IF: $PRIMARY_LOSS%, $SECONDARY_IF: $SECONDARY_LOSS%"

    # Get current interface
    CURRENT_IF=$(sudo ip -4 -oneline route show table "$GFW_ROUTING_TABLE" | grep -o "dev.*" | awk '{print $2}')

    # Check if backup interface exists, if not, set to empty
    if ! ip link show "$BACKUP_IF" > /dev/null 2>&1; then
        BACKUP_IF=""
    fi

    # Make the interface switch decision by following rules
    NEXT_IF="$CURRENT_IF"
    if [ "$PRIMARY_STATUS" != "ready" ] && [ "$SECONDARY_STATUS" != "ready" ]; then
        # If both interfaces are not ready, then switch to backup interface
        # if no backup interface available, do nothing
        if [ -n "$BACKUP_IF" ] ; then
            NEXT_IF="$BACKUP_IF"
        elif [ "$PRIMARY_LOSS" -lt "$SECONDARY_LOSS" ]; then
            NEXT_IF="$PRIMARY_IF"
        else
            NEXT_IF="$SECONDARY_IF"
        fi
    elif [ "$PRIMARY_STATUS" = "ready" ] && [ "$SECONDARY_STATUS" != "ready" ]; then
        NEXT_IF="$PRIMARY_IF"
    elif [ "$PRIMARY_STATUS" != "ready" ] && [ "$SECONDARY_STATUS" = "ready" ]; then
        NEXT_IF="$SECONDARY_IF"
    elif [ "$CURRENT_IF" = "$BACKUP_IF" ]; then
        # Switch to primary if both are ready
        NEXT_IF="$PRIMARY_IF"
    fi

    if [ "$NEXT_IF" = "$CURRENT_IF" ]; then
        echo "Staying on current interface: $CURRENT_IF"
    else
        # Delete all routes in the specified table first
        sudo ip route flush table "$GFW_ROUTING_TABLE"

        # Replace existing routes
        sudo ip route replace default dev "$NEXT_IF" table "$GFW_ROUTING_TABLE"
        sudo ip route replace "$PING_TARGET_IP" dev "$NEXT_IF"

        # Log the switch decision
        log_message "Switching: $CURRENT_IF -> $NEXT_IF (Primary: ${PRIMARY_LOSS}%, Secondary: ${SECONDARY_LOSS}%)"
    fi

    clean_and_exit 0

}

main "$@"