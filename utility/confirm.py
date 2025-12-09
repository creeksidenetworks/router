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

from utility.ux import Colors, print_warn

def get_confirmation(message, default='no', strict=False):
    while True:
        if strict:
            if default == 'no':
                prompt = f"{message} [yes/{Colors.GREEN}no{Colors.RESET}]: "
            else:
                prompt = f"{message} [{Colors.GREEN}yes{Colors.RESET}/no]: "
            confirm = input(prompt).strip().lower()

            if confirm == '':
                return default == 'yes'
            if confirm == 'yes' or confirm == 'no':
                return confirm == 'yes'
            
            print_warn("Invalid input. Please enter 'yes' or 'no'.")

        else:
            if default == 'no':
                confirm = input(f"{message} [y/{Colors.GREEN}N{Colors.RESET}]: ").strip().lower() or default
            else:
                confirm = input(f"{message} [{Colors.GREEN}Y{Colors.RESET}/n]: ").strip().lower() or default
    
            if confirm in ['yes', 'y']:
                return True
            elif confirm in ['no', 'n']:
                return False

            print_warn("Invalid input. Please enter 'y', 'yes', 'n', or 'no'.")

