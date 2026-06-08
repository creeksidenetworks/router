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

import  sys
import  argparse

from    vyatta.vyatta_router    import VyattaRouter
from    vpn.roadwarrior         import roadwarrior_setup
from    utility.ux              import (print_header, print_dim, graceful_exit)


def setup():
    print_header("IKEv2 VPN Setup Script v1.0", width=60)
    print_dim("        (c) 2020-2024 Jackson Tong, Creekside Networks LLC")

    parser = argparse.ArgumentParser(description='Configure IKEv2 VPN on an EdgeRouter or VyOS router')
    parser.add_argument('hostname', help='Hostname or IP address of the router (optionally with username@hostname)')
    parser.add_argument('-p', '--port', type=int, default=None, help='SSH port (default: 22)')

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    if '@' in args.hostname:
        username, hostname = args.hostname.split('@', 1)
    else:
        username = None
        hostname = args.hostname

    password = "ubnt" if username == "ubnt" else None

    router = VyattaRouter(hostname=hostname, username=username, password=password, port=args.port)
    roadwarrior_setup(router)

    print("\n  *** Thank you for using this script ***\n\n")


if __name__ == '__main__':
    try:
        setup()
    except KeyboardInterrupt:
        graceful_exit()
        sys.exit(0)
