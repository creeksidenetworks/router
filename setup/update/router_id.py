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
from    utility.global_config       import  GlobalConfig
from    utility.ux                  import  Colors, print_warn

def get_router_id(router_config):
    # extract router id from loopback address
    router_id = None
    lo_addresses = router_config.get("interfaces loopback lo address")
    pattern = re.compile(r"^10\.255\.(\d+)\.254/32$")

    if lo_addresses:
        if isinstance(lo_addresses, list):
            for address in lo_addresses:
                match = pattern.match(address)
                if match:
                    router_id = match.group(1)
                    break
        else:
            match = pattern.match(lo_addresses)
            if match:
               router_id = match.group(1)

    return router_id

def router_set_id(updates, router_config, streamlined=False):

    router_id = get_router_id(router_config)
    prompt_prefix = "    "
    while True:
        new_router_id = input(f"{prompt_prefix}Router ID (1-254) [{Colors.GREEN}{router_id}{Colors.RESET}]: ") or router_id
        
        # Handle case where router_id is None and user presses Enter
        if new_router_id is None:
            print_warn("Router ID is required. Please enter a value between 1 and 254.")
            continue

        try:
            new_router_id_int = int(new_router_id)
            if 1 <= new_router_id_int <= 254:
                break
            else:
                print_warn("Invalid router ID. Please enter a value between 1 and 254.")
        except (ValueError, TypeError):
            print_warn("Invalid input. Please enter a numeric value between 1 and 254.")

    if new_router_id != router_id:
        config_cmds = []

        if router_id is not None:
            config_cmds.append(f"delete interfaces loopback lo address 10.255.{router_id}.254/32")
        config_cmds.append(f"set interfaces loopback lo address 10.255.{new_router_id}.254/32") 

        updates.add_changes(
            key = "router id", 
            stage = 1, 
            description = f"New router id set to : {new_router_id}",
            cmds = config_cmds
        )

        """
        # check ospf configuration
        ospf_area = router_config.get("protocols ospf area")
        if ospf_area is not None:
            for area in ospf_area:
                if area != "0" and area != new_router_id:
                    changes[f"update ospf area {area}"] = new_router_id
                    config_cmds.append(f"edit protocols ospf;rename area {area} to area {new_router_id};top")
                    break
        """
    return True

