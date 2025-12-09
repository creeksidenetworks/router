#!/usr/bin/env python
# Edgerouter/VyOS management scripts
# Copyright (c) 2023 Jackson Tong, Creekside Networks LLC.
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

import  os
import  sys
import  json
import  argparse
import  requests

from    simple_term_menu                import TerminalMenu
from    getpass                         import getpass

from    vyatta.vyatta_router            import VyattaRouter
from    vpn.certs_manager               import certs_mananger
from    update.router_update            import update_router
from    vpn.roadwarrior                 import roadwarrior_setup
from    update.ubnt_firmware            import check_firmware_status, firmware_upgrade
from    utility.ux                      import (Colors, print_header, print_ok, print_error, 
                                                 print_info, print_warn, print_dim, graceful_exit)


def main():
    # main scripts started here
    print_header("EdgeRouter Configuration Script v2.0", width=60)
    print_dim("        (c) 2020-2024 Jackson Tong, Creekside Networks LLC")

    # parse command line arguments
    parser = argparse.ArgumentParser(description='Connect to an EdgeRouter')
    parser.add_argument('hostname', help='The hostname or IP address of the router (optionally with username@hostname)')
    parser.add_argument('-p', '--port', type=int, default=None, help='Specify a port other than the default port 22')

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args  = parser.parse_args()

    # Extract username and hostname
    if '@' in args.hostname:
        username, hostname = args.hostname.split('@', 1)
    else:
        username = None
        hostname = args.hostname

    # Use default password "ubnt" if username is "ubnt"
    password = "ubnt" if username == "ubnt" else None
    port = args.port if args.port is not None else None
 
    router = VyattaRouter(hostname=hostname, username=username, password=password,port=port)

    # Check firmware status for EdgeRouter
    fw_status = None
    if router.hardware:  # Only for EdgeRouter devices
        print_dim("  Checking firmware status...")
        fw_status = check_firmware_status(router)
        
        if fw_status["is_legacy"]:
            # Legacy firmware (1.x or 2.x) - firmware upgrade is mandatory
            if fw_status["needs_upgrade"]:
                print()
                print_warn(f"Legacy firmware detected: {fw_status['current_version']}")
                print_warn(f"Firmware upgrade required before using other features.")
                print_info(f"Latest version available: {fw_status['latest_version']}")
                print()
                
                # Only show firmware upgrade option
                title = "\no Main menu (Firmware Upgrade Required)"
                options = [
                    "[0] Exit",
                    "[1] Firmware Upgrade",
                ]
                
                while True:
                    terminal_menu = TerminalMenu(options, title=title)
                    menu_entry_index = terminal_menu.show()
                    
                    match menu_entry_index:
                        case 0:
                            break
                        case 1:
                            firmware_upgrade(router)
                        case _:
                            break
                
                print("\n  *** Thank you for using this script ***\n\n")
                return
            else:
                # Legacy firmware but already up to date
                print()
                print_ok(f"Firmware {fw_status['current_version']} is already the latest version.")
                print()

    # Normal menu (non-legacy firmware or up-to-date legacy or VyOS)
    title = "\no Main menu"
    
    # Build menu options based on firmware status
    if fw_status and fw_status["needs_upgrade"] and not fw_status["is_legacy"]:
        # Non-legacy firmware with upgrade available - show upgrade option
        options = [
            "[0] Exit",
            "[1] Router Update", 
            "[2] Roadwarrior VPN",
            f"[3] Firmware Upgrade ({fw_status['current_version']} → {fw_status['latest_version']})",
        ]
    else:
        # No upgrade available or VyOS - don't show firmware option
        options = [
            "[0] Exit",
            "[1] Router Update", 
            "[2] Roadwarrior VPN", 
        ]

    while True:
        terminal_menu       = TerminalMenu(options, title=title)
        menu_entry_index    = terminal_menu.show()

        match menu_entry_index:
            case 0:
                break
            case 1:
                update_router(router)
            case 2:
                roadwarrior_setup(router)
            case 3:
                if fw_status and fw_status["needs_upgrade"]:
                    firmware_upgrade(router)
            case _:
                print("\n*** This feature is not implemented yet")

    print("\n  *** Thank you for using this script ***\n\n")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        graceful_exit()
        sys.exit(0)


