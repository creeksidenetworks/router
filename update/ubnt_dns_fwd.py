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


from    utility.confirm             import  get_confirmation
from    utility.input               import  input_ipv4
from    utility.ux                  import  print_subtitle, print_info

def update_name_server(updates, router_config, existing_name_servers=None):
    name_servers = []

    # Only delete existing name servers if they actually exist
    if existing_name_servers:
        # Check if name-server configuration actually exists
        if router_config.search("service dns forwarding name-server"):
            cmds = ["delete service dns forwarding name-server"]
        else:
            cmds = []
    else:
        cmds = []

    system_name_servers = router_config.get("system name-server")
    if existing_name_servers is None:
        if system_name_servers:
            # if no default name servers given, use system name servers
            default_name_servers = system_name_servers
        else:
            default_name_servers = []
    else:
        # use given default name servers
        default_name_servers = existing_name_servers

    # Automatically use system DNS servers without prompting
    name_servers = default_name_servers if default_name_servers else []

    if name_servers:
        updates.add_changes(
            key = "dns fwd name-server", 
            stage = 1, 
            description = f"Update DNS forwarding name-server",
            cmds =  cmds + [*[f"set service dns forwarding name-server {ns}" for ns in name_servers]]
        )

def ubnt_dns_fwd(updates, router_config):
    print_subtitle("DNS Forwarding")

    # Set cache-size
    print_info("Setting cache-size to 150")
    updates.add_changes(
        key = "dns fwd cache-size",
        stage = 1,
        description = f"Set DNS forwarding cache-size to 150",
        cmds = ["set service dns forwarding cache-size 150"]
    )

    # Set listen-on lo (loopback interface)
    print_info("Setting listen-on to lo")
    updates.add_changes(
        key = "dns fwd listen-on",
        stage = 1,
        description = f"Set DNS forwarding listen-on to lo",
        cmds = ["set service dns forwarding listen-on lo"]
    )

    # listen on loopback interface
    lo_addrs = router_config.get("interfaces loopback lo address")
    if lo_addrs:
        lo_addrs = lo_addrs if isinstance(lo_addrs, list) else [lo_addrs]
        for addr in lo_addrs:
            addr = addr.split("/")[0]   # remove subnet
            if not router_config.search(f"service dns forwarding options listen-address={addr}"):
                print_info(f"Listening on {addr}")
                updates.add_changes(
                    key =f"dns fwd {addr}", 
                    stage = 1, 
                    description = f"Listen on loopback address {addr}",
                    cmds = [f"set service dns forwarding options listen-address={addr}"]
                )

    return True