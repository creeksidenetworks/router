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

import random
import string

def generate_random_pwd(len=12, special=False):
    # Define character sets
    uppercase_letters = ''.join([c for c in string.ascii_uppercase if c not in 'OI'])
    lowercase_letters = ''.join([c for c in string.ascii_lowercase if c not in 'ol'])

    digits = string.digits
    special_chars = "&+!$@#"

    # Generate each part of the password
    first_char  = random.choice(uppercase_letters)
    second_char = random.choice(lowercase_letters)
    third_char  = random.choice(lowercase_letters)
    digit_chars = ''.join(random.choices(digits, k=(len-4)))
    # Always include at least one special character to meet password requirements
    last_char = random.choice(special_chars)

    # Combine all parts to form the password
    password = first_char + second_char + third_char + digit_chars + last_char
    return password

if __name__ == '__main__':
    # Example usage
    print(generate_random_pwd(special=True))
    print(generate_random_pwd(special=False))