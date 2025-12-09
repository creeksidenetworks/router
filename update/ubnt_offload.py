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

from    utility.ux                  import  print_step, print_ok, print_info

def ubnt_enable_offload(updates, router_config, router, streamlined=False):

    if not streamlined:
        print_step("", "Enable Hardware Offloading")

    if not router_config.search("system offload ipsec enable"):
        if (router.hardware in ["e50"]):
            updates.add_changes(
                key = "offload", 
                stage = 1, 
                description = f"Enable hardware offloading",
                cmds = [f"set system offload ipsec enable",
                        f"set system offload hwnat enable"],
            )
        else:
            updates.add_changes(
                key = "offload", 
                stage = 1, 
                description = f"Enable hardware offloading",
                cmds = [f"set system offload ipsec enable",
                        f"set system offload ipv4 forwarding enable",
                        f"set system offload ipv4 gre enable",
                        f"set system offload ipv4 pppoe enable",
                        f"set system offload ipv4 vlan enable"],
            )
    else:
        if streamlined:
            print_info("Hardware offloading already enabled")

    return True