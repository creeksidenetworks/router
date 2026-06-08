
#!/bin/sh
# (c) 2022-2025 Creekside Networks LLC, Jackson Tong
# This script will update the wireguard peer endpoint if the peer uses a FQDN
# for EdgeOS & VyOS 1.3.4 and openwrt
 
export PATH="/usr/sbin:/usr/bin:/sbin:/bin"

# Configuration file path
CONFIG_FILE="/config/config.boot"
LOG_FILE="/var/log/wg.log"

# Function to log messages
log_message() {
    local message=$1
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    printf "%-10s %s\n" "$timestamp" "$message" | sudo tee -a "$LOG_FILE" # > /dev/null

    # Ensure the log file does not exceed 1000 lines
    line_count=$(sudo wc -l < "$LOG_FILE")
    if [ "$line_count" -gt 1000 ]; then
        sudo tail -n 500 "$LOG_FILE" | sudo tee "$LOG_FILE.tmp" > /dev/null
        sudo mv "$LOG_FILE.tmp" "$LOG_FILE"
    fi
}

# Function to check if a string is a valid FQDN
is_fqdn() {
    local fqdn="$1"
    # POSIX regex match using case
    case "$fqdn" in
        *.*)
            # Check for at least one dot and valid TLD
            if echo "$fqdn" | grep -Eq '^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'; then
                return 0
            else
                return 1
            fi
            ;;
        *)
            return 1
            ;;
    esac
}

# Function to update the WireGuard peer endpoint
update_peer_endpoint() {
    local interface="$1"
    local peer_pubkey="$2"
    local new_ip="$3"
    local listen_port="$4"

    echo "Updating peer with public key $peer_pubkey endpoint to $new_ip on port $listen_port for interface $interface"

    # Update the WireGuard peer endpoint
    sudo wg set "$interface" peer "$peer_pubkey" endpoint "$new_ip:$listen_port"
}

# Detect OS type
detect_os_type() {
    if [ -f /etc/openwrt_release ]; then
        os="OpenWrt"
    elif [ -f /etc/version ] && grep -q "EdgeRouter" /etc/version 2>/dev/null; then
        os="EdgeOS"
    elif [ -f /etc/os-release ]; then
        if grep -q "VyOS" /etc/os-release 2>/dev/null; then
            os="VyOS"
            version=$(grep VERSION_ID /etc/os-release | awk -F'"' '{print $2}')
            if [[ "$version" != "1.3.4" ]]; then
                echo "Error: Only VyOS 1.3.4 is supported. Detected version: $version"
                exit 1
            fi
        else
            # Generic Linux with standard WireGuard config location
            os="Linux"
            #os_name=$(grep '^NAME=' /etc/os-release | cut -d'=' -f2 | tr -d '"')
        fi
    else
        echo "Error: Unsupported OS. WireGuard configs not found in /etc/wireguard and system is not VyOS, EdgeOS, or OpenWrt."
        exit 1
    fi
    echo "$os"
}

# dns lookup use different tools on different OS
# host is available on EdgeOS
# nslookup is available on VyOS and OpenWrt
dns_lookup() {
    local fqdn="$1"
    local os="$2"

    case "$os" in
        "EdgeOS")
            host -4 "$fqdn" | awk '/has IPv4 address/ { print $5; exit }'
            ;;
        *)
            nslookup "$fqdn"  | grep "Address" | tail -1 | cut -d ":" -f 2 | awk '{$1=$1;print}'
            #nslookup "$fqdn" | awk '/^Address [0-9]+: / { print $3; exit }'
            ;;
    esac
}

# Function to parse WireGuard peers from EdgeOS config
EdgeOS_Parse_Wireguard() {
    awk '
        BEGIN {
            in_wireguard_block = 0;
            current_interface = "";
            in_peer_block = 0;
            first_peer_in_interface = 1;
        }
        /^ *wireguard/ {
            current_interface = $2;
            in_wireguard_block = 1;
            first_peer_in_interface = 1;
        }
        in_wireguard_block && /^ *peer/ {
            if (first_peer_in_interface) {
                first_peer_in_interface = 0;
            }
            peer_key = $2;
            in_peer_block = 1;
            description = "";
            endpoint = "";
        }
        in_peer_block && /^ *description/ {
            description = substr($0, index($0, "description ") + length("description "));
            gsub(/^ *| *$/, "", description);
            gsub(/^"|"$/, "", description);
        }
        in_peer_block && /^ *endpoint/ {
            endpoint = $2;
            gsub(/^ *| *$/, "", endpoint);
            gsub(/^"|"$/, "", endpoint);
        }
        in_peer_block && /^ *}/ {
            if (description != "" && endpoint != "") {
                split(endpoint, parts, ":");
                print current_interface, peer_key, "\"" description "\"", parts[2]
            }
            in_peer_block = 0;
        }
    ' "/config/config.boot"
}

# Function to parse WireGuard peers from VyOS config
VyOS_Parse_Wireguard() {
    awk '
        BEGIN {
            in_wireguard_block = 0;
            current_interface = "";
            in_peer_block = 0;
            peer_name = "";
            peer_pubkey = "";
            peer_port = "";
        }
        /^ *wireguard/ {
            current_interface = $2;
            in_wireguard_block = 1;
        }
        in_wireguard_block && /^ *peer/ {
            peer_name = $2;
            in_peer_block = 1;
            peer_pubkey = "";
            peer_port = "";
        }
        in_peer_block && /^ *pubkey/ {
            peer_pubkey = $2;
        }
        in_peer_block && /^ *port/ {
            peer_port = $2;
        }
        in_peer_block && /^ *}/ {
            if (peer_name ~ /\./ && peer_pubkey != "" && peer_port != "") {
                print current_interface, peer_pubkey, "\"" peer_name "\"", peer_port
            }
            in_peer_block = 0;
        }
    ' "/config/config.boot"
}


OpenWrt_Parse_Wireguard() {
    for id in 251 252 253; do
        # Get the WireGuard interface config string
        if [ -z $(uci show network | grep "wg${id}=") ]; then
            continue
        fi

        # Get the peer public key, endpoint host, and endpoint port
        pubkey=$(uci get network.@wireguard_wg${id}[0].public_key 2>/dev/null)
        endpoint_host=$(uci get network.@wireguard_wg${id}[0].endpoint_host 2>/dev/null)
        endpoint_port=$(uci get network.@wireguard_wg${id}[0].endpoint_port 2>/dev/null)

        echo "wg${id}" "$pubkey" "\"$endpoint_host\"" "$endpoint_port"
    done
}

# Function to parse WireGuard peers from standard Linux config files (/etc/wireguard)
Linux_Parse_Wireguard() {
    # Look for .conf files in /etc/wireguard
    if [ ! -d /etc/wireguard ]; then
        echo "Warning: /etc/wireguard directory not found" >&2
        return
    fi

    for conf_file in /etc/wireguard/*.conf; do
        if [ ! -f "$conf_file" ]; then
            continue
        fi

        # Extract interface name from filename (e.g., wg0.conf -> wg0)
        interface=$(basename "$conf_file" .conf)

        # Parse [Peer] sections in the config file
        awk -v interface="$interface" '
            BEGIN {
                in_peer = 0
                pubkey = ""
                endpoint = ""
            }
            /^\[Peer\]/ {
                # Output previous peer if we have the required fields
                if (in_peer && pubkey != "" && endpoint != "") {
                    split(endpoint, parts, ":")
                    host = parts[1]
                    port = parts[2]
                    # Check if host contains a dot (likely FQDN or IP)
                    if (host ~ /\./) {
                        print interface, pubkey, "\"" host "\"", port
                    }
                }
                in_peer = 1
                pubkey = ""
                endpoint = ""
            }
            in_peer && /^PublicKey/ {
                sub(/^PublicKey[[:space:]]*=[[:space:]]*/, "")
                gsub(/[[:space:]]/, "")
                pubkey = $0
            }
            in_peer && /^Endpoint/ {
                sub(/^Endpoint[[:space:]]*=[[:space:]]*/, "")
                gsub(/[[:space:]]/, "")
                endpoint = $0
            }
            /^\[/ && !/^\[Peer\]/ {
                # Output current peer when entering a new non-Peer section
                if (in_peer && pubkey != "" && endpoint != "") {
                    split(endpoint, parts, ":")
                    host = parts[1]
                    port = parts[2]
                    if (host ~ /\./) {
                        print interface, pubkey, "\"" host "\"", port
                    }
                }
                in_peer = 0
            }
            END {
                # Output last peer
                if (in_peer && pubkey != "" && endpoint != "") {
                    split(endpoint, parts, ":")
                    host = parts[1]
                    port = parts[2]
                    if (host ~ /\./) {
                        print interface, pubkey, "\"" host "\"", port
                    }
                }
            }
        ' "$conf_file"
    done
}

main() {
    echo "Starting WireGuard peer update process..."
    echo "----------------------------------------"

    os=$(detect_os_type)
    echo "Operating System detected: $os"

    # Select parser based on OS type
    if [ "$os" = "EdgeOS" ]; then
        echo "Detected OS: EdgeOS"
        peers=$(EdgeOS_Parse_Wireguard)
    elif [ "$os" = "OpenWrt" ]; then
        echo "Detected OS: OpenWrt"
        peers=$(OpenWrt_Parse_Wireguard)
    elif [ "$os" = "Linux" ]; then
        # Generic Linux with /etc/wireguard configs
        peers=$(Linux_Parse_Wireguard)
    else
        echo "Detected OS: VyOS"
        peers=$(VyOS_Parse_Wireguard)
    fi

    if [ -n "$peers" ]; then
        echo "$peers" | while IFS= read -r line; do
            interface=$(echo "$line" | awk '{print $1}')
            pubkey=$(echo "$line" | awk '{print $2}')
            description=$(echo "$line" | awk -F'"' '{print $2}')
            port=$(echo "$line" | awk '{print $NF}')

            printf "Processing interface: %s, pubkey: %s, description: %s, port: %s\n" "$interface" "$pubkey" "$description" "$port"

            # Check if description is a valid FQDN
            if is_fqdn "$description"; then
                # Perform DNS lookup for FQDN
                new_ip=$(dns_lookup "$description" "$os")

                # get current IP
                current_ip=$(sudo wg show "$interface" endpoints | grep "$pubkey" | awk '{print $2}' | awk -F':' '{print $1}')

                echo "interface: $interface, pubkey: $pubkey, description: $description, resolved IP: $new_ip, current IP: $current_ip"

                # Update if the new IP differs from the current one
                if [ -n "$new_ip" ] && [ "$new_ip" != "$current_ip" ]; then
                    update_peer_endpoint "$interface" "$pubkey" "$new_ip" "$port"
                    log_message "Updated $interface - $pubkey ($description) endpoint to $new_ip:$port (was $current_ip)"
                else 
                    echo "$interface" "-" "$pubkey" "$description:$port" "is current"
                fi
            fi
        done
    else
        echo "No WireGuard peers found in the configuration."
    fi

}

main "$@"
