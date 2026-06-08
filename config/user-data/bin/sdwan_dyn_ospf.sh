#!/bin/bash
# sdw-dyn-ospf.sh — Adjust OSPF interface cost based on ping loss rate
#
# Usage: sdw-dyn-ospf.sh <interface> <remote_ip> [base_cost]
#
# Arguments:
#   interface   EdgeRouter interface name (e.g. eth0, eth1.10)
#   remote_ip   IP address to ping for loss measurement
#   base_cost   OSPF cost at 0% loss (default: 10, range: 1-65535)
#
# Cost scaling tiers (multiplier × base_cost):
#   loss 0%       → ×1
#   loss 1-10%    → ×2
#   loss 11-25%   → ×4
#   loss 26-50%   → ×8
#   loss 51-75%   → ×16
#   loss 76-100%  → ×32  (capped at 65535)
#
# Cost increases immediately when loss rises to a higher tier.
# Cost decreases one tier at a time to smooth transient recovery.
#
# Intended to run on EdgeRouter as a cron task, e.g. every minute via:
#   set system task-scheduler task sdw-dyn-ospf executable path /config/scripts/sdw-dyn-ospf.sh
#   set system task-scheduler task sdw-dyn-ospf executable arguments "eth0 203.0.113.1 10"
#   set system task-scheduler task sdw-dyn-ospf interval 1m

IFACE="${1}"
REMOTE_IP="${2}"
BASE_COST="${3:-10}"
PING_COUNT=20
MAX_OSPF_COST=65535
LOG_TAG="dyn-ospf"
LOG_FILE="/var/log/sdw.log"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $LOG_TAG: $*" >> "$LOG_FILE"; }

if [[ -f "$LOG_FILE" ]] && [[ "$(wc -l < "$LOG_FILE")" -gt 5000 ]]; then
    tail -n 2500 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
fi

usage() {
    echo "Usage: $0 <interface> <remote_ip> [base_cost]" >&2
    echo "  interface  — EdgeRouter interface (e.g. eth0, eth1.10)" >&2
    echo "  remote_ip  — IP to ping for loss measurement" >&2
    echo "  base_cost  — OSPF cost at 0% loss (default: 10)" >&2
    exit 1
}

if [[ -z "$IFACE" || -z "$REMOTE_IP" ]]; then
    usage
fi

if ! [[ "$BASE_COST" =~ ^[1-9][0-9]*$ ]] || [[ "$BASE_COST" -gt 65535 ]]; then
    echo "Error: base_cost must be an integer between 1 and 65535" >&2
    exit 1
fi

# --- Measure packet loss ---

PING_RESULT=$(ping -c "$PING_COUNT" -W 2 "$REMOTE_IP" 2>/dev/null)

# Extract the loss percentage from the ping summary line, e.g.:
#   "20 packets transmitted, 18 received, 10% packet loss, time 19015ms"
LOSS=$(echo "$PING_RESULT" | sed -n 's/.*[[:space:]]\([0-9]*\)% packet loss.*/\1/p')

if [[ -z "$LOSS" ]]; then
    log "ERROR: could not parse packet loss from ping to $REMOTE_IP"
    exit 1
fi

# --- Map loss to target tier multiplier ---

if   [[ "$LOSS" -eq 0 ]];   then TARGET_M=1
elif [[ "$LOSS" -le 10 ]];  then TARGET_M=2
elif [[ "$LOSS" -le 25 ]];  then TARGET_M=4
elif [[ "$LOSS" -le 50 ]];  then TARGET_M=8
elif [[ "$LOSS" -le 75 ]];  then TARGET_M=16
else                              TARGET_M=32
fi

# --- Get current OSPF cost from vtysh ---

CURRENT_COST=$(vtysh -c "show ip ospf interface $IFACE" 2>/dev/null \
    | awk -F'Cost: ' '/Cost:/{print $2+0; exit}')

CURRENT_M=$(( CURRENT_COST > 0 ? CURRENT_COST / BASE_COST : 0 ))

# --- Determine applied tier: rise immediately, fall one tier at a time ---

if [[ "$TARGET_M" -ge "$CURRENT_M" ]]; then
    APPLY_M=$TARGET_M
else
    STEP_M=$(( CURRENT_M / 2 ))
    [[ "$STEP_M" -lt 1 ]] && STEP_M=1
    # Don't step below the target
    APPLY_M=$(( STEP_M > TARGET_M ? STEP_M : TARGET_M ))
fi

APPLY_COST=$(( BASE_COST * APPLY_M ))
[[ "$APPLY_COST" -gt "$MAX_OSPF_COST" ]] && APPLY_COST=$MAX_OSPF_COST

[[ "$APPLY_COST" -eq "$CURRENT_COST" ]] && exit 0

log "$IFACE loss=${LOSS}% target=×${TARGET_M} → cost ${CURRENT_COST:-?} → $APPLY_COST"

# --- Apply new cost via vtysh (runtime only, does not persist to config) ---

vtysh -c "configure terminal" \
      -c "interface $IFACE" \
      -c "ip ospf cost $APPLY_COST" \
      -c "exit" \
      -c "exit"
