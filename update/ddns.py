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

import  re
import  ipaddress

from    utility.global_config           import  GlobalConfig
from    utility.menu                    import  menu_select
from    update.ubnt_ddns                import  ubnt_ddns_cloudflare
from    utility.confirm                 import  get_confirmation
from    utility.ux                      import  Colors, print_ok, print_warn, print_info, print_subtitle

def is_public_ip(address):
    try:
        # Validate if the address is a valid IP with subnet
        network = ipaddress.ip_network(address, strict=False)
        # Check if the IP is public
        return not network.network_address.is_private
    except ValueError:
        return False

def add_ddns_service(updates, config):
    print_subtitle("Dynamic DNS")

    prompt_prefix = "    "    # Menu for DDNS provider selection
    ddns_providers = [
        "Skip DDNS configuration",
        "Cloudflare",
        "DynDNS"
    ]
    
    selected_provider = menu_select(
        title=f"{prompt_prefix}Select DDNS provider:",
        lists=ddns_providers,
        default="Skip DDNS configuration",
        indent=2
    )
    
    if selected_provider is None or selected_provider == "Skip DDNS configuration":
        print_info("Skipping DDNS configuration")
        return None
    
    if selected_provider == "DynDNS":
        print_info("DynDNS support not yet implemented")
        return None
    
    # Continue with Cloudflare configuration
    eligible_interfaces = []

    # Get router hostname and domain for default DDNS hostname
    router_hostname = config.get("system host-name") or ""
    router_domain = config.get("system domain-name") or ""
    if router_hostname and router_domain:
        default_ddns_hostname = f"{router_hostname}.{router_domain}"
    else:
        default_ddns_hostname = ""
    
    # add all ethernet interfaces
    eths = config.get("interfaces ethernet")

    # add pppoe interfaces first
    for eth in eths:
        pppoe = config.get(f"interfaces ethernet {eth} pppoe")
        if pppoe:
            for id in pppoe:
                eligible_interfaces.append(f"pppoe{id}")

    # add remaining ethernet interfaces with address assigned
    for eth in eths:
        #if addresses and not config.get(f"service dns dynamic interface {eth} service"):
        if config.get(f"interfaces ethernet {eth} address"):
            # add the interface which is assigned a address or dhcp
            eligible_interfaces.append(f"{eth}")
                    
    if not eligible_interfaces:
        print_info(" No eligible interfaces found for dynamic DNS service")
        return None
    else:
        # Find the first interface with DDNS configured as default
        default_interface = None
        for interface in eligible_interfaces:
            if config.get(f"service dns dynamic interface {interface} service"):
                default_interface = interface
                break
        
        selected_interface = menu_select(
            title=f"{prompt_prefix}Select interface for DDNS:",
            lists=eligible_interfaces,
            default=default_interface,
            indent=2
        )

    if selected_interface is None:
        return False
    
    # Configure DDNS for the selected interface
    if config.get(f"service dns dynamic interface {selected_interface} service"):
        if not get_confirmation(f"{prompt_prefix}DDNS already configured on {Colors.GREEN}{selected_interface}{Colors.RESET}, reconfigure?", default="no"):
            return False

    ubnt_ddns_cloudflare(updates, config, selected_interface, default_ddns_hostname)
    return True
