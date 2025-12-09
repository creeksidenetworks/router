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

import  os
import  re
import  json
import  ipaddress
from    utility.passwd              import  generate_random_pwd
from    utility.ux                  import  Colors, print_warn

def input_ipv4(prompt, default=None):
    while True:
        try:
            if default is not None:
                ipv4 = input(f"{prompt} [{Colors.GREEN}{default}{Colors.RESET}]: ")
                if ipv4 == '':
                    return default
            else:
                ipv4 = input(f"{prompt}: ")

            if ipv4 == '' or ipv4 == "-":
                return None
            ipv4 = ipaddress.IPv4Address(ipv4)
            return str(ipv4)
        except ValueError:
            print_warn("Invalid IPv4 address")
                     
def input_passwd(prompt, default=None):
    if default is None:
        default = generate_random_pwd()

    return input(f"{prompt} [{Colors.GREEN}{default}{Colors.RESET}]: ") or default

