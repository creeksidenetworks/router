# Edgerouter/VyOS management scripts
# Copyright (c) 2024 Jackson Tong, Creekside Networks LLC.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import  json
import  pytz
import  simple_term_menu

from    utility.confirm             import  get_confirmation
from    utility.input               import  input_ipv4
from    utility.ux                  import  Colors, print_ok, print_warn, print_info, print_step

def regional_settings(updates, router_config, countrycode, timezone, streamlined=False):
    # regional settings
    if not streamlined:
        print_step("", "Configure Regional Settings")
    
    prompt_prefix = "    "
    while True:
        countrycode = input(f"{prompt_prefix}Country code [{Colors.GREEN}{countrycode}{Colors.RESET}]: ") or countrycode
        if len(countrycode) == 2 and countrycode.upper() in pytz.country_names:
            break
        else:
            print_warn("Invalid country code. Please enter a valid 2-letter country code.")

    # Get the list of timezones for the given country code
    timezones       = pytz.country_timezones.get(countrycode.upper())
    tz_in_cfg       = router_config.get("system time-zone")
    new_time_zone   = tz_in_cfg

    # For US, use simplified timezone list
    if countrycode.upper() == "US":
        timezones = [
            "US/Eastern",
            "US/Central", 
            "US/Mountain",
            "US/Pacific",
            "US/Alaska",
            "US/Hawaii",
        ]

    if tz_in_cfg and tz_in_cfg in timezones and get_confirmation(f"{prompt_prefix}Keep timezone {Colors.GREEN}{tz_in_cfg}{Colors.RESET}?", default="yes"):
        new_time_zone = tz_in_cfg
    else:
        # Move the current time zone to the top of the list if it exists
        if timezone in timezones:
            timezones.remove(timezone)
            timezones.insert(0, timezone)

        # Prepend each timezone entry with 3 spaces for alignment
        aligned_timezones = [f"     {tz}" for tz in timezones]

        # Display the list of timezones using simple_term_menu with the default entry pre-selected
        terminal_menu = simple_term_menu.TerminalMenu(aligned_timezones, 
                                    title="    Select timezone:", 
                                    menu_cursor=">", 
                                    menu_cursor_style=("fg_red", "bold"), 
                                    menu_highlight_style=("bg_black", "fg_red"), 
                                    cycle_cursor=True)
        
        menu_entry_index = terminal_menu.show()

        if menu_entry_index is None:
            print_warn("No timezone selected")
            return

        new_time_zone = timezones[menu_entry_index]
    
    if new_time_zone != tz_in_cfg:
        updates.add_changes(
            key = "time zone", 
            stage = 1, 
            description = f"Time zone : {new_time_zone}",
            cmds = [f"set system time-zone {new_time_zone}"]
        )

    # Set the default name servers based on the country
    nameservers_in_cfg   = router_config.get("system name-server")

    if countrycode.lower() == "cn":
        default_nameservers = "223.5.5.5,119.29.29.29,114.114.114.114"
    else:
        default_nameservers = "1.1.1.1,8.8.8.8,8.8.4.4"

    # Allow user to input custom DNS servers
    while True:
        dns_input = input(f"{prompt_prefix}DNS servers [{Colors.GREEN}{default_nameservers}{Colors.RESET}]: ") or default_nameservers
        
        # Split by comma and validate each DNS server
        dns_list = [dns.strip() for dns in dns_input.split(',')]
        
        if len(dns_list) > 3:
            print_warn("Maximum 3 DNS servers allowed")
            continue
        
        # Validate each DNS server
        valid_dns = []
        all_valid = True
        for dns in dns_list:
            if dns:  # Skip empty strings
                try:
                    import ipaddress
                    ipaddress.IPv4Address(dns)
                    valid_dns.append(dns)
                except ValueError:
                    print_warn(f"Invalid IPv4 address: {dns}")
                    all_valid = False
                    break
        
        if all_valid and valid_dns:
            suggested_nameservers = valid_dns
            break
        elif not valid_dns:
            print_warn("At least one DNS server is required")

    # Check if system name servers need updating
    if nameservers_in_cfg and set(nameservers_in_cfg) == set(suggested_nameservers):
        # No changes needed for system name servers
        print_info("System name servers already configured correctly")
    else:
        config_cmds = []
        if nameservers_in_cfg:
            config_cmds.append("delete system name-server") # delete all existing name servers
        for ns in suggested_nameservers:
            config_cmds.append(f"set system name-server {ns}")

        updates.add_changes(
            key = "name servers", 
            stage = 1, 
            description = f"System name servers: {', '.join(suggested_nameservers)}",
            cmds = config_cmds
        )

    # Also update DNS forwarding name servers
    dns_fwd_nameservers = router_config.get("service dns forwarding name-server")
    
    if dns_fwd_nameservers and set(dns_fwd_nameservers) == set(suggested_nameservers):
        # No changes needed for DNS forwarding
        print_info("DNS forwarding name servers already configured correctly")
    else:
        dns_fwd_cmds = []
        if dns_fwd_nameservers:
            dns_fwd_cmds.append("delete service dns forwarding name-server")
        for ns in suggested_nameservers:
            dns_fwd_cmds.append(f"set service dns forwarding name-server {ns}")
        
        updates.add_changes(
            key = "dns forwarding name servers",
            stage = 1,
            description = f"DNS forwarding name servers: {', '.join(suggested_nameservers)}",
            cmds = dns_fwd_cmds
        )

    return True