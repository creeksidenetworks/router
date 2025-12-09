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

DEFAULT_STRONGSWAN_CONF = """
charon {
    plugins {
        eap-radius {
            class_group = yes
        }
        dhcp {
            identity_lease = yes
        }
    }
}
"""

class StrongswanConfig:
    def __init__(self, config_str=DEFAULT_STRONGSWAN_CONF):
        self.config = {}
        self.loads(config_str)

    def loads(self, config_str):
        lines = config_str.split('\n')
        self.config = self._parse_config(lines)

    def get(self, path):
        keys = path.split(' ')
        value = self.config
        
        for key in keys:
            if key not in value:
                return None
            else:
                value = value[key]
        return value

    def set(self, path, value=None):
        keys = path.split(' ')
        config = self.config
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            if not isinstance(config[key], dict):
                # covert other type to dict
                config[key] = {}
            config = config[key]
        if value is not None:
            config[keys[-1]] = value
        else:
            config[keys[-1]] = {}

    def remove(self, path):
        keys = path.split(' ')
        config = self.config
        for key in keys[:-1]:
            if key not in config:
                return
            config = config[key]
        del config[keys[-1]]

    def ensure_charon_plugin_support(self):
        if 'charon' not in self.config:
            self.config['charon'] = {}
        if 'plugins' not in self.config['charon']:
            self.config['charon']['plugins'] = {}
        if 'eap-radius' not in self.config['charon']['plugins']:
            self.config['charon']['plugins']['eap-radius'] = {}

    def _parse_config(self, lines):
        config = {}
        stack = [config]
        for line in lines:
            line = line.strip()
            if line.startswith('#') or not line:
                continue
            if line.endswith('{'):
                key = line[:-1].strip()
                new_dict = {}
                stack[-1][key] = new_dict
                stack.append(new_dict)
            elif line == '}':
                stack.pop()
            else:
                key, value = map(str.strip, line.split('=', 1))
                stack[-1][key] = value
        return config

    def dumps(self, config, indent=0):
        lines = []
        for key, value in config.items():
            if isinstance(value, dict):
                lines.append(' ' * indent + f"{key} {{")
                lines.append(self.dumps(value, indent + 2))
                lines.append(' ' * indent + '}')
            else:
                lines.append(' ' * indent + f"{key} = {value}")
        return '\n'.join(lines)

