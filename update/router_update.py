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

import os
import re
import sys
import json
import subprocess

from utility.confirm                import  get_confirmation
from utility.ux                     import  (Colors, print_header, print_step, print_ok, 
                                             print_error, print_info, print_warn, 
                                             print_summary, print_changes, print_action,
                                             print_subtitle)

from vyatta.vyatta_config           import  VyattaConfig
from utility.global_config          import  GlobalConfig
from utility.menu                   import  menu_select

from update.ubnt_wireguard          import  ubnt_enable_wg_peer_update
from update.ubnt_adduser            import  ubnt_update_user
from update.router_id               import  router_set_id
from update.ddns                    import  add_ddns_service
from update.regional                import  regional_settings
from update.hostname                import  update_hostname
from update.ubnt_offload            import  ubnt_enable_offload
from update.ubnt_dns_fwd            import  ubnt_dns_fwd
from update.ipxe                    import  enable_ipxe

def detect_router_env(router):
    # Get router configuration
    router_config = VyattaConfig()
    router_config.load(router)   

    # Get the external IP address
    # Try multiple IP detection services for better reliability, especially in China
    ip_services = [
        "curl -s --max-time 5 https://api.ipify.org",
        "curl -s --max-time 5 https://icanhazip.com",
        "curl -s --max-time 5 https://ifconfig.me",
        "curl -s --max-time 5 https://myip.ipip.net",
    ]
    
    response = None
    for cmd in ip_services:
        response, err = router.run_os_cmd(cmd)
        if response and not err:
            break
    
    ip_pattern = r'\d+\.\d+\.\d+\.\d+'
    
    # Search for the IP address in the response string
    match = re.search(ip_pattern, response)
    
    # If a match is found, return the IP address
    if match:
        external_ip     = match.group(0)
        # Get geographic information based on the external IP address

        command = f"curl -s --max-time 5 https://ipapi.co/{external_ip}/json/"
        
        # Run the command
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        response = result.stdout

        data            = json.loads(response)

        country_code    = data.get("country_code", "Unknown")
        time_zone       = data.get("timezone", "Unknown")
    else:
        external_ip     = "Unknown"
        country_code    = "Unknown"
        time_zone       = "Unknown"

    return external_ip, country_code, time_zone

# RouterUpdate class

class RouterUpdate:
    def __init__(self, router):
        self.router = router
        self.config_cmds = {}
        self.changes = {}
        self.router_config = None

    def is_changed(self):
        return bool(self.changes)

    def add_changes(self, key, stage, description, cmds):
        """
        Add configuration changes, filtering out commands that 
           1) The configuration path already exists for set commands
           2) The configuration path doesn't exist for delete commands
        """
        # Load router config if not already loaded
        if not self.router_config:
            self.router_config = VyattaConfig()
            self.router_config.load(self.router)
        
        # Filter commands to only include those that don't already exist
        filtered_cmds = []
        
        for cmd in cmds:
            # Handle delete commands - only execute if config exists
            if cmd.startswith("delete "):
                cmd_without_delete = cmd[7:]  # Remove "delete " prefix
                if self.router_config.search(cmd_without_delete):
                    filtered_cmds.append(cmd)
                continue
            
            # Handle set commands - only execute if config doesn't exist
            if cmd.startswith("set "):
                cmd_without_set = cmd[4:]  # Remove "set " prefix
                if not self.router_config.search(cmd_without_set):
                    filtered_cmds.append(cmd)
                continue
            
            # Keep other commands as-is
            filtered_cmds.append(cmd)
        
        # Only add to changes if there are commands remaining after filtering
        if filtered_cmds:
            if stage not in self.changes:
                self.changes[stage] = {}
            self.changes[stage][key] = {
                "description" : description,
                "cmds"   : filtered_cmds
            }
        
        return self.changes

    def get_cmds_by_stage(self, stage):
        cmds = []
        if stage not in self.changes: 
            return None
        else:       
            for key in self.changes[stage]:
                cmds += self.changes[stage][key]["cmds"]
            return cmds
    
    def apply_changes(self):
        # Check if there are any changes
        if not self.changes:
            print_info("All configurations are already up to date. No changes needed.")
            return True
        
        print_changes("Pending Configuration Changes", self.changes)
        
        if get_confirmation("\n  Proceed with these settings?", strict=True):
            for stage, details in sorted(self.changes.items()):
                print_step("", "Applying Configuration")
                cmds = self.get_cmds_by_stage(stage)             
                self.router.config(cmds, indent=4)
            print("")
            print_ok("Configuration applied successfully")
        else:
            print_warn("Configuration changes cancelled")
            return False


def update_router(router):
    print_header("Router Update")

    print_step("", "Gathering Router Information")
    router_config = VyattaConfig()
    router_config.load(router)

    external_ip, country_code, time_zone = detect_router_env(router)

    # print information as summary
    summary_items = [
        f"External IP:   {Colors.GREEN}{external_ip}{Colors.RESET}",
        f"Country Code:  {Colors.GREEN}{country_code}{Colors.RESET}",
        f"Time Zone:     {Colors.GREEN}{time_zone}{Colors.RESET}"
    ]
    print_summary("Detected Environment", summary_items)

    # Run all basic setup steps directly without menu
    updates = RouterUpdate(router)
    
    print_subtitle("Router Basic Setup")
    
    router_set_id(updates, router_config, streamlined=True)
    update_hostname(updates, router_config, streamlined=True)
    regional_settings(updates, router_config, country_code, time_zone, streamlined=True)
    ubnt_enable_offload(updates, router_config, router, streamlined=True)
    ubnt_update_user(updates, router_config, streamlined=True)
    ubnt_dns_fwd(updates, router_config)
    add_ddns_service(updates, router_config)
    ubnt_enable_wg_peer_update(updates, router_config, router)
    enable_ipxe(updates, router_config, router, streamlined=True)

    # Check if the configuration has been changed
    if updates.is_changed():
        updates.apply_changes()

    print_subtitle("Install Extra Utilities")
    
    # Check for nano editor
    check_nano = "dpkg -l | grep '^ii' | grep -w nano"
    output, error = router.run_os_cmd(check_nano)
    if not output or "nano" not in output:
        # Configure Debian package repositories
        print_info("Configuring Debian package repositories...")
        debian_sources = "deb http://archive.debian.org/debian/ stretch main contrib non-free\\ndeb http://archive.debian.org/debian/ stretch-proposed-updates main contrib non-free"
        config_apt_cmd = f"echo -e '{debian_sources}' | sudo tee /etc/apt/sources.list.d/debian-archive.list"
        router.run_os_cmd(config_apt_cmd, echo=False)
        print_ok("Debian repository sources configured")
        
        # Run apt update
        print_info("Updating package lists...")
        router.run_os_cmd("sudo apt-get update", echo=False)
        print_ok("Package lists updated")
        
        # Install nano
        print_info("Installing nano...")
        install_nano = "sudo apt-get install -y nano"
        output, error = router.run_os_cmd(install_nano, echo=False)
        if error and "debconf" not in error:
            print_warn(f"Installation warning: {error}")
        else:
            print_ok("Nano installed successfully")
    else:
        print_ok("Nano already installed")



    


