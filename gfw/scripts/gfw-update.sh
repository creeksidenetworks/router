#!/bin/bash
# (c) 2022-2024 Creekside Networks LLC, Jackson Tong
# This script will decide the best tunnel for jailbreak based on ping result
# for Edgerouter & VyOS 1.3.x

PING_TARGET_IP="8.8.8.8"
# Number of ping attempts
PING_COUNT=10
# Routing table to update
GFW_ROUTING_TABLE="100"
# Log file path
LOG_FILE="/var/log/gfw.log"
LOG_CAT="gfw"

# Check for interface arguments and set default if none are provided
if [ $# -eq 0 ]; then
  TUNNEL_IF=("wg253" "wg252" "wg251")
else
  TUNNEL_IF=("$@")
fi

# Function to get the current default route interface for the specified table
get_current_route_interface() {
    ip -4 -oneline route show table "$GFW_ROUTING_TABLE" | grep -o "dev.*" | awk '{print $2}'
}

# Function to ping from a specific interface
ping_from_interface() {
    local interface=$1
    local result_file=$2
    ping -I "$interface" -c "$PING_COUNT" "$PING_TARGET_IP" > "$result_file" 2>&1
    echo $? > "${result_file}.status"
}

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

# Function to delete all routes in the specified table
delete_routes() {
    sudo ip route flush table "$GFW_ROUTING_TABLE"
    echo "Flushed all routes in table $GFW_ROUTING_TABLE"
}

# Array to hold the result files
result_files=()

# Print message indicating start of pings
echo "Starting pings from all TUNNEL_IF..."

# Ping from each interface in the background and store the result files
for interface in "${TUNNEL_IF[@]}"; do
    result_file=$(mktemp)
    result_files+=("$result_file")
    ping_from_interface "$interface" "$result_file" &
done

# Wait for all background jobs to complete
wait

# Process the results
results=()
for i in "${!TUNNEL_IF[@]}"; do
    interface="${TUNNEL_IF[$i]}"
    result_file="${result_files[$i]}"
    status=$(cat "${result_file}.status")
    if [ "$status" -ne 0 ]; then
        # Handle the case where the interface is down
        results+=("$interface 100 Unreachable")
    else
        output=$(cat "$result_file")
        transmitted=$(echo "$output" | grep -oP '\d+(?= packets transmitted)')
        received=$(echo "$output" | grep -oP '\d+(?= received)')
        loss=$(echo "$output" | grep -oP '\d+(?=% packet loss)')
        avg_latency=$(echo "$output" | grep -oP '(?<=time=)[0-9.]+ ms' | awk '{sum+=$1; PING_COUNT+=1} END {print (sum/PING_COUNT)}')
        rounded_latency=$(echo "$avg_latency" | awk '{print ($1 == int($1)) ? $1 : int($1)+1}')
        if [ "$loss" -gt 40 ]; then
            results+=("$interface 100 Unreachable")
        else
            results+=("$interface $loss $rounded_latency")
        fi
    fi
    rm "$result_file" "${result_file}.status"
done

# Sort the results by loss rate and then by average latency
sorted_results=$(printf "%s\n" "${results[@]}" | sort -k2,2n -k3,3n)

# Print the sorted results in fixed-width columns
echo "Interface     LossRate(%) AvgLatency(ms)"
printf "%-12s %-10s %s\n" $(echo "$sorted_results" | awk '{printf "%-12s %-10s %s\n", $1, $2, $3}')

# Determine the best interface
best_interface=$(echo "$sorted_results" | awk '{print $1, $2, $3}' | sort -k2,2n -k3,3n | head -n 1)

# Extract best interface values
best_interface_name=$(echo "$best_interface" | awk '{print $1}')
best_interface_loss=$(echo "$best_interface" | awk '{print $2}')
best_interface_status=$(echo "$best_interface" | awk '{print $3}')

# Get the current route interface for the specified table
current_route_interface=$(get_current_route_interface)

# Debug prints
printf "Current route interface in table %s: %s\n" "$GFW_ROUTING_TABLE" "$current_route_interface"
printf "Best interface: %s, LossRate(%%): %s, AvgLatency(ms): %s\n" "$best_interface_name" "$best_interface_loss" "$best_interface_status"
# Determine if the route needs to be updated
update_needed=false

if [ -z "$best_interface_name" ] || [ "$best_interface_loss" -ge 40 ] || [ "$best_interface_status" = "Unreachable" ]; then
    # If all TUNNEL_IF are down, set route to main default route
    
    str=$(ip -4 -oneline route show default 0.0.0.0/0)
    default_route_interface=$(echo $str  | grep -oP 'dev \K\S+')
    new_route=$(echo $str | grep -o "via.*" | awk '{print $1 " " $2}' )
    new_route=$new_route" "$(echo "$str " | grep -o "dev.*" | awk '{print $1 " " $2}' )

    if [ "$current_route_interface" != "$default_route_interface" ]; then
        update_needed=true
        log_message "All gfw tunnels are down." 1
    else
        echo "Route is already set to default interface: $default_route_interface in table $GFW_ROUTING_TABLE"
    fi
else
    # Set route to the best interface
    new_route="dev $best_interface_name"
    if [ "$current_route_interface" != "$best_interface_name" ]; then
        update_needed=true
        echo "Preparing to update route to the best interface: $best_interface_name in table $GFW_ROUTING_TABLE"
    else
        echo "Route is already set to the best interface: $best_interface_name in table $GFW_ROUTING_TABLE"
    fi
fi

# Update the route if needed
if $update_needed; then
    delete_routes
    sudo ip route replace default $new_route table "$GFW_ROUTING_TABLE"
    sudo ip route replace "$PING_TARGET_IP" $new_route
    log_message "Updated global route to $new_route"
else
    echo "No update needed."
fi
