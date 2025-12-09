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

import re
import ipaddress
import validators
from    utility.global_config       import  GlobalConfig
from    utility.ux                  import  Colors, print_info, print_warn

def _is_private_ip(ip_str):
    """
    Check if an IP address is private (RFC 1918) or CGNAT (100.64.0.0/10).
    Returns True if private, False if public.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        # Check for private IP (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
        if ip.is_private:
            return True
        # Check for CGNAT range (100.64.0.0/10) - used by service providers
        cgnat_network = ipaddress.ip_network('100.64.0.0/10')
        if ip in cgnat_network:
            return True
        return False
    except ValueError:
        # Invalid IP address
        return False

def _gloabl_get_cloudflare(domain):
    # get global configuration
    global_config = GlobalConfig() 

    if global_config.search(f"cloudflare {domain}.email"):
        email       = global_config.get(f"cloudflare {domain}.email")
        key         = global_config.get(f"cloudflare {domain}.key")
        return email, key
    else:
        return None, None

def _gloabl_set_ssh_key(domain, email, key):
    # get global configuration
    global_config = GlobalConfig() 
    global_config.set(f"cloudflare {domain}.email", email)
    global_config.set(f"cloudflare {domain}.key", key)
    return True

#
#    Get Clouflare DDNS configuration for EdgeRouter
#       :param config   : VyattaConfig object
#       :interface      : Interface name
#
#       :return         : List of configuration commands
#
def ubnt_ddns_cloudflare(updates, config, interface, default_hostname=""):
    ddns_options = {
        "mode": "custom-cloudflare",
        "host-name": default_hostname,
        "login": "",
        "password": "",
        "protocol": "cloudflare",
        "zone": "",
        "existing_web": None
    }

    mode = config.get(f"service dns dynamic interface {interface} service")
    config_changed = False

    if mode is not None:
        # get current configuration
        ddns_options["mode"] = mode[0]
        if ddns_options["mode"] == "custom-cloudflare":
            search_prefix = f"service dns dynamic interface {interface} service custom-cloudflare"
            current_hostname = config.get(f"{search_prefix} host-name")
            current_login = config.get(f"{search_prefix} login")
            current_password = config.get(f"{search_prefix} password")
            current_web = config.get(f"service dns dynamic interface {interface} web")
            other_options = config.get(f"{search_prefix} options")
            current_zone = None
            if other_options:
                current_zone = other_options.split("=")[1] if "=" in other_options else None
            
            # Store existing values as defaults
            ddns_options["host-name"] = current_hostname or default_hostname
            ddns_options["login"] = current_login or ""
            ddns_options["password"] = current_password or ""
            ddns_options["existing_web"] = current_web
            if current_zone:
                ddns_options["zone"] = current_zone
        else:
            print(f"    - Dynamic DNS service is already configured as {mode[0]}, skipping.")
            return []

    # cloudflare configuration
    ddns_options["mode"] == "custom-cloudflare"

    # Set the protocol to Cloudflare
    ddns_options["protocol"] = "cloudflare"
        
    while True:
        ddns_options["host-name"] = input(f"  Hostname [{Colors.GREEN}{ddns_options['host-name']}{Colors.RESET}]: ") or ddns_options["host-name"]
        if validators.domain(ddns_options["host-name"]):
            parts = ddns_options["host-name"].split(".")
            if len(parts) < 2:
                print_warn("  Invalid hostname. Please enter a valid fully qualified domain name.")
            else:
                # Extract domain (last two parts: e.g., creekside.network)
                ddns_options["zone"] = '.'.join(parts[-2:])
                
                # Try to get Cloudflare credentials for this domain
                email, api_key = _gloabl_get_cloudflare(ddns_options["zone"])
                if email and api_key:
                    ddns_options['login'] = email
                    ddns_options['password'] = api_key
                    print_info(f" Using Cloudflare credentials for {ddns_options['zone']}")
                
                break
        else:
            print_warn("  Invalid hostname. Please enter a valid fully qualified domain name.")

    # If credentials weren't found automatically, prompt for them
    if not ddns_options['login'] or not ddns_options['password']:
        while True:
            ddns_options["login"] = input(f"  Cloudflare email [{Colors.GREEN}{ddns_options['login']}{Colors.RESET}]: ") or ddns_options["login"]
            if validators.email(ddns_options["login"]):
                break
            else:
                print_warn("  Invalid email address. Please enter a valid email address.")

        # Regex pattern for Cloudflare API token (37 to 40-character hexadecimal string)
        api_token_pattern = re.compile(r"^[a-fA-F0-9]{37,40}$")

        while True:
            ddns_options["password"] = input(f"  Cloudflare API key [{Colors.GREEN}{ddns_options['password']}{Colors.RESET}]: ") or ddns_options["password"]
            if api_token_pattern.match(ddns_options["password"]):
                break
            else:
                print_warn(f"  Invalid API key. Please enter a valid 37-40 character API key.")

        _gloabl_set_ssh_key(ddns_options["zone"], ddns_options["login"], ddns_options["password"])

    # Check if the interface has a private IP address or needs web-based detection
    # Default to web detection for safety - most home/small business connections need it
    use_web_detection = True
    base_interface = interface.split('.')[0]  # Handle VLANs like eth0.100
    
    # Check various interface types
    interface_address = None
    
    # Try ethernet interface
    if base_interface.startswith('eth'):
        interface_address = config.get(f"interfaces ethernet {base_interface} address")
    # Try pppoe interface
    elif base_interface.startswith('pppoe'):
        interface_address = config.get(f"interfaces pppoe {base_interface} address")
    # Try other interface types as needed
    else:
        interface_address = config.get(f"interfaces {base_interface} address")
    
    # Check if interface has a public IP (only then disable web detection)
    if interface_address:
        # Extract IP from address (could be like "dhcp" or "192.168.1.1/24")
        if isinstance(interface_address, list):
            interface_address = interface_address[0] if interface_address else None
        
        if interface_address and interface_address != "dhcp":
            # Extract IP without CIDR notation
            ip_only = interface_address.split('/')[0]
            if not _is_private_ip(ip_only):
                # Only disable web detection if we found a public IP
                use_web_detection = False
                print_info(f" Interface {interface} has public IP {ip_only}")
            else:
                print_info(f" Interface {interface} has private IP {ip_only}, using web-based IP detection")
        else:
            print_info(f" Interface {interface} uses DHCP, using web-based IP detection")
    else:
        print_info(f" Interface {interface} address not configured, using web-based IP detection")

    # Check if we need to delete existing configuration
    # If service already exists, delete it first to ensure clean update
    if mode is not None and ddns_options["mode"] == "custom-cloudflare":
        # Delete existing service to avoid conflicts
        delete_cmds = [
            f"delete service dns dynamic interface {interface} service custom-cloudflare"
        ]
        updates.add_changes(
            key = f"delete cloudflare ddns {interface}",
            stage = 1,
            description = f"remove existing cloudflare ddns service from {interface}",
            cmds = delete_cmds
        )

    # Add the DDNS configuration commands
    cloudflare_prefix = f"service dns dynamic interface {interface} service custom-cloudflare"
    
    cmds = [
        f"set {cloudflare_prefix} host-name {ddns_options['host-name']}",
        f"set {cloudflare_prefix} login {ddns_options['login']}",
        f"set {cloudflare_prefix} password {ddns_options['password']}",
        f"set {cloudflare_prefix} protocol {ddns_options['protocol']}",
        f"set {cloudflare_prefix} options zone={ddns_options['zone']}",
    ]
    
    # Add web-based IP detection if interface has private IP
    if use_web_detection:
        cmds.append(f"set service dns dynamic interface {interface} web checkip.dyndns.com")
    
    updates.add_changes(
        key = f"cloudflare ddns {interface}", 
        stage = 1, 
        description = f"add cloudflare dynamic dns service to {interface}",
        cmds = cmds
    )
  
    return True