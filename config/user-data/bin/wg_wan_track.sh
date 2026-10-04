#!/bin/bash
#
# wg-wan-track.sh  --  EdgeOS load-balance transition-script hook
#
# Pins the *outer* (encrypted transport) fwmark of the listed WireGuard
# interfaces to whichever WAN is currently ACTIVE in the load-balance group.
# When several WANs are active (load-sharing), the FIRST active one -- the
# active interface with the lowest LB route-table number -- is used.
#
# Nothing about the WANs is hardcoded; it is all discovered at runtime:
#
#   * `show load-balance config`  -> interface <-> route-table, and confirms
#     load-balance is actually configured (state-independent, so it works even
#     for a WAN that is currently down).
#   * `ip rule show`              -> route-table <-> fwmark
#     (fallback formula: fwmark = table << 23, e.g. 201 -> 0x64800000).
#   * `show load-balance status`  -> which interface(s) are "active" now.
#
# Wire up:
#   sudo install -m0755 wg-wan-track.sh /config/scripts/wg-wan-track.sh
#   configure
#   set load-balance group WAN_LB_GROUP transition-script /config/scripts/wg-wan-track.sh
#   commit ; save
#
# The hook passes <iface> <group> <status>, but the active WAN is re-derived
# authoritatively every fire; args are only a last-resort fallback + logging.

set -u

# ------------------------------------------------------------------ policy ---
# WireGuard interfaces to steer.
#   wg0 = INITIATOR (fixed endpoint)  -> always safe to track the active WAN.
#   wg1 = RESPONDER (road-warriors)   -> only correct if the clients' DDNS /
#         endpoint follows the active WAN. If clients always dial one fixed
#         WAN address, remove wg1 here and pin it once in config instead
#         (set interfaces wireguard wg1 fwmark 0x65800000).
WG_IFACES=(wg1)

LB_GROUP="WAN_LB_GROUP"      # only used for logging context
LOGTAG="wg-wan-track"
STATE_FILE="/var/run/wg-wan-track.active"

# ------------------------------------------------------------------ helpers --
log() { logger -t "$LOGTAG" -- "$*" 2>/dev/null; }
to_dec() { local v="${1:-}"; { [ -z "$v" ] || [ "$v" = off ]; } && { echo 0; return; }
           printf '%d' "$v" 2>/dev/null || echo 0; }

# Run an EdgeOS op-mode command from script context.
# Run an EdgeOS op-mode command via the official op-cmd wrapper (works from a
# non-interactive/daemon context, per the UBNT guide).
OP_WRAPPER="/opt/vyatta/bin/vyatta-op-cmd-wrapper"
lb_op() { "$OP_WRAPPER" "$@" 2>/dev/null; }

declare -A TBL_IF     # table  -> interface
declare -A TBL_MARK   # table  -> fwmark (0x........)

# Populate TBL_IF (from LB config) and TBL_MARK (from ip rule, or table<<23).
# Returns non-zero if load-balance is not configured / nothing discovered.
discover_map() {
  local cfg ifc tbl mark n=0

  cfg="$(lb_op show load-balance config)"
  # `show load-balance config` prints "load-balance is not configured" (no
  # interface/table lines) when the group is absent -> n stays 0 -> return 1.
  # interface <-> table  (interface = a bare, indented, single-token line)
  while read -r ifc tbl; do
    [ -n "$ifc" ] && [ -n "$tbl" ] || continue
    TBL_IF[$tbl]="$ifc"
    n=$((n + 1))
  done < <(printf '%s\n' "$cfg" | awk '
    /^[[:space:]]+[^[:space:]:]+[[:space:]]*$/ { ifc=$1; next }
    ifc!="" && /^[[:space:]]*table[[:space:]]*:/ { print ifc, $NF }')

  # Count via a scalar; expanding ${#TBL_IF[@]} on an empty associative array
  # trips `set -u` ("unbound variable") on bash 4.x/5.x alike.
  [ "$n" -gt 0 ] || return 1

  # table <-> fwmark from ip rule
  while read -r tbl mark; do
    [ -n "$tbl" ] && [ -n "$mark" ] || continue
    [ -n "${TBL_IF[$tbl]:-}" ] && TBL_MARK[$tbl]="$mark"
  done < <(ip rule show | awk '
    /fwmark/ && /lookup/ {
      m=""; t="";
      for (i=1;i<=NF;i++) {
        if ($i=="fwmark") { split($(i+1),a,"/"); m=a[1] }
        if ($i=="lookup") { t=$(i+1) }
      }
      if (m!="" && t ~ /^[0-9]+$/) print t, m
    }')

  # any table still lacking a fwmark -> compute it (fwmark = table << 23)
  for tbl in "${!TBL_IF[@]}"; do
    [ -n "${TBL_MARK[$tbl]:-}" ] || TBL_MARK[$tbl]="$(printf '0x%08x' $(( tbl << 23 )))"
  done
  return 0
}

# Active tables via op-mode status (the sole active-set source). status line
# precedes the route-table line in each block, so we latch it and emit on the
# table line.
active_tables_status() {
  lb_op show load-balance status | awk '
    /interface[[:space:]]*:/   { st="" }
    /status[[:space:]]*:/      { st=$NF }
    /route table[[:space:]]*:/ { if (st=="active") print $NF }'
}

# Chosen = lowest-numbered active LB table (= first active interface).
choose_active_table() {
  active_tables_status | sort -un | sed '/^$/d' | head -n1
}

# ------------------------------------------------------------------ main -----
# EdgeOS transition-script arg contract:  $1 = interface, $2 = up|down.
# These only say which interface changed and its direction -- NOT which WAN is
# now active (on a down event $1 is the interface that just left). The active
# WAN is therefore always derived from `show load-balance status`; the args are
# informational only.
TRIG_IF="${1:-}"; TRIG_STATE="${2:-}"

if ! discover_map; then
  log "load-balance not configured (no interface/table pairs); leaving fwmark unchanged"
  exit 0
fi

CT="$(choose_active_table)"

if [ -z "$CT" ] || [ -z "${TBL_MARK[$CT]:-}" ]; then
  log "could not determine active WAN${TRIG_IF:+ (trigger: $TRIG_IF ${TRIG_STATE:-?})}; leaving fwmark unchanged"
  exit 0
fi

ACTIVE_IF="${TBL_IF[$CT]}"; MARK="${TBL_MARK[$CT]}"; TGT=$(to_dec "$MARK")
log "active WAN = $ACTIVE_IF (table $CT, fwmark $MARK)"

changed=0
for wg in "${WG_IFACES[@]}"; do
  wg show "$wg" >/dev/null 2>&1 || { log "$wg absent, skip"; continue; }
  cur="$(wg show "$wg" fwmark 2>/dev/null)"
  if [ "$(to_dec "$cur")" -ne "$TGT" ]; then
    if wg set "$wg" fwmark "$MARK"; then
      log "$wg fwmark ${cur:-off} -> $MARK ($ACTIVE_IF)"; changed=1
    else
      log "ERROR: wg set $wg fwmark $MARK failed"
    fi
  fi
done

# On change, flush each tunnel's outer-UDP conntrack so existing flows re-pin
# (and, for responders, re-source) via the new WAN instead of a stale
# [UNREPLIED] entry carrying the old interface's address.
if [ "$changed" -eq 1 ] && command -v conntrack >/dev/null 2>&1; then
  for wg in "${WG_IFACES[@]}"; do
    p="$(wg show "$wg" listen-port 2>/dev/null)"; [ -n "$p" ] || continue
    conntrack -D -p udp --dport "$p" >/dev/null 2>&1 || true
    conntrack -D -p udp --sport "$p" >/dev/null 2>&1 || true
  done
  log "flushed wg outer-udp conntrack after fwmark change"
fi

echo "$ACTIVE_IF" > "$STATE_FILE" 2>/dev/null || true
exit 0
