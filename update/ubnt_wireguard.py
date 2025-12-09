#!/usr/bin/env python
# Edgerouter/VyOS management scripts
# Copyright (c) 2023-2024 Jackson Tong, Creekside Networks LLC.
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

import os

def ubnt_enable_wg_peer_update(updates, router_config, router):
    """
    Enable wireguard peer update task scheduler
    - Upload wg_peer_update.sh script to /config/user-data/bin/
    - Make it executable
    - Configure task scheduler to run every 2 minutes
    """
    from utility.ux import print_subtitle, print_info
    
    print_subtitle("WireGuard Peer Update")
    
    # Check if task already exists
    if router_config.search("system task-scheduler task wg-update"):
        print_info("WireGuard peer update task already configured")
        return False
    
    # Upload the script
    local_dir = os.path.dirname(os.path.realpath(__file__))
    local_dir = os.path.join(os.path.dirname(local_dir), "template")
    script_relative_path = "user-data/bin/wg_peer_update.sh"
    
    router.upload(
        os.path.join(local_dir, script_relative_path),
        os.path.join("/config", script_relative_path),
        echo=False
    )
    
    # Make it executable
    router.run_os_cmd("sudo chmod +x /config/user-data/bin/wg_peer_update.sh")
    
    print_info("Configuring WireGuard peer update task (runs every 2 minutes)")
    
    # Add task scheduler configuration
    updates.add_changes(
        key = "wg-peer-update-task",
        stage = 1,
        description = "Enable WireGuard peer update task scheduler",
        cmds = [
            "set system task-scheduler task wg-update executable path /config/user-data/bin/wg_peer_update.sh",
            "set system task-scheduler task wg-update executable arguments ''",
            "set system task-scheduler task wg-update interval 2m"
        ]
    )
    
    return True
