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
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OFZ
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import os
from utility.confirm import get_confirmation
from utility.ux import print_subtitle, print_info, print_ok, print_warn

def enable_ipxe(updates, router_config, router, streamlined=False):
    if not streamlined:
        print_subtitle("Enable iPXE")
    
    # Upload tftproot files
    print_info("Uploading iPXE boot files...")
    
    # Get template path relative to this file
    local_dir = os.path.dirname(os.path.realpath(__file__))
    template_path = os.path.join(os.path.dirname(local_dir), "template/user-data/tftproot")
    
    # Create remote directory
    router.run_os_cmd("sudo mkdir -p /config/user-data/tftproot")
    
    # Upload ipxe.efi
    ipxe_efi_local = os.path.join(template_path, "ipxe.efi")
    ipxe_efi_remote = "/config/user-data/tftproot/ipxe.efi"
    if os.path.exists(ipxe_efi_local):
        router.upload(ipxe_efi_local, ipxe_efi_remote, echo=False)
        print_ok("Uploaded ipxe.efi")
    else:
        print_warn(f"File not found: {ipxe_efi_local}")
    
    # Upload undionly.kpxe
    undionly_local = os.path.join(template_path, "undionly.kpxe")
    undionly_remote = "/config/user-data/tftproot/undionly.kpxe"
    if os.path.exists(undionly_local):
        router.upload(undionly_local, undionly_remote, echo=False)
        print_ok("Uploaded undionly.kpxe")
    else:
        print_warn(f"File not found: {undionly_local}")
    
    # Configure DNS forwarding options for iPXE
    ipxe_options = [
        "options enable-tftp",
        "tftp-root=/config/user-data/tftproot",
        "dhcp-match=set:bios,60,PXEClient:Arch:00000",
        "dhcp-boot=tag:bios,undionly.kpxe",
        "dhcp-match=set:efi32,60,PXEClient:Arch:00002",
        "dhcp-boot=tag:efi32,ipxe.efi",
        "dhcp-match=set:efi32-1,60,PXEClient:Arch:00006",
        "dhcp-boot=tag:efi32-1,ipxe.efi",
        "dhcp-match=set:efi64,60,PXEClient:Arch:00007",
        "dhcp-boot=tag:efi64,ipxe.efi",
        "dhcp-match=set:efi64-1,60,PXEClient:Arch:00008",
        "dhcp-boot=tag:efi64-1,ipxe.efi",
        "dhcp-match=set:efi64-2,60,PXEClient:Arch:00009",
        "dhcp-boot=tag:efi64-2,ipxe.efi",
        "dhcp-userclass=set:ipxe,iPXE",
        "dhcp-boot=tag:ipxe,http://download.creekside.network/ipxe/boot.ipxe"
    ]
    
    config_cmds = []
    for option in ipxe_options:
        # Check if this option already exists
        if not router_config.search(f"service dns forwarding options {option}"):
            config_cmds.append(f"set service dns forwarding options {option}")
    
    if config_cmds:
        updates.add_changes(
            key="ipxe options",
            stage=1,
            description="Enable iPXE network boot",
            cmds=config_cmds
        )
        print_ok("iPXE configuration prepared")
    else:
        print_info("iPXE options already configured")
    
    return True
