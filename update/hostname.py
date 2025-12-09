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

import  validators

from    utility.ux                  import  Colors, print_ok, print_warn, print_step

def update_hostname(updates, router_config, streamlined=False):
    new_domain = None
    if not streamlined:
        print_step("", "Configure System Hostname")

    hostname_in_cfg = router_config.get("system host-name")
    domain_in_cfg = router_config.get("system domain-name")

    prompt_prefix = "    "
    while True:
        new_hostname = input(f"{prompt_prefix}Hostname [{Colors.GREEN}{hostname_in_cfg}{Colors.RESET}]: ") or hostname_in_cfg

        # Check if the new hostname is a FQDN
        if validators.domain(new_hostname):
            new_hostname, new_domain = new_hostname.split('.', 1)
            break

        if validators.hostname(new_hostname):
            break

    if not new_domain and domain_in_cfg:
        new_domain = domain_in_cfg
    
    while True:
        new_domain = input(f"{prompt_prefix}Domain [{Colors.GREEN}{new_domain}{Colors.RESET}]: ") or new_domain
        if validators.domain(new_domain):
            break
        else:
            print_warn("Invalid domain name. Please enter a valid domain name.")

    if new_hostname != hostname_in_cfg:
        updates.add_changes(
                    key = "hostname", 
                    stage = 1, 
                    description = f"Hostname: {new_hostname}",
                    cmds = [
                            f"set system host-name {new_hostname}",
                            f"set system login banner post-login \"\\n*** Welcome to {new_hostname}\\n*** Proudly managed by Creekside Networks LLC\\n\\n\""
                        ],
            )
        
    if new_domain != domain_in_cfg:
        updates.add_changes(
                    key = "domain", 
                    stage = 1, 
                    description = f"Domain: {new_domain}",
                    cmds = [
                            f"set system domain-name {new_domain}"
                    ],
            )

    return True