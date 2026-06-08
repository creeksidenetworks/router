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
import json

from cryptography import x509
from cryptography.hazmat.primitives import serialization


DEFAULT_IPSEC_CONF           = f"""
config setup
    uniqueids=never

ca rootca
    cacert=/config/ipsec.d/cacerts/ca-cert.cer
    auto=add

conn %default
    ike=aes256-sha1-modp1024,aes128-sha1-modp1024,aes256-sha1-modp2048,aes128-sha1-modp2048
    esp=aes256-sha1,aes128-sha1,3des-sha1
    keyexchange=ikev2
    compress=no
    type=tunnel
    fragmentation=yes
    forceencaps=yes
    ikelifetime=4h
    lifetime=2h
    dpddelay=180s
    dpdtimeout=30s
    dpdaction=clear
    rekey=no
    left=%any
    leftcert=/config/ipsec.d/certs/server.crt
    leftsendcert=always
    right=%any
    rightid=%any
    rightsendcert=never
    rightauth=eap-radius
    rightdns=8.8.8.8
    eap_identity=%identity

"""

class IPSecConfig:
    def __init__(self, config_str=DEFAULT_IPSEC_CONF):
        self.config = self.loads(config_str)

    def loads(self, ipsec_conf_str):
        self.config = {}
        current_section = None
        current_conn = None

        ipsec_conf_lines = ipsec_conf_str.split('\n')

        for line in ipsec_conf_lines:
            line = line.rstrip()
            if not line or line.startswith('#'):
                continue

            if not line[0].isspace():
                if line.startswith('config') or line.startswith('ca') or line.startswith('conn')  or line.startswith('include'):
                    section_type    = line.split()[0]
                    section_name    = line.split()[1]

                    if section_type not in self.config:
                        self.config[section_type] = {}

                    if section_name not in self.config[section_type]:
                        self.config[section_type][section_name] = {}
   
                else:
                    print(f"Unknown section: {line}")
                    section_type = None
                    section_name = None
            else:
                if section_type and section_name:
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"')  # Remove surrounding quotes if present
                        self.config[section_type][section_name][key] = value
                    else:
                        print(f"\n   *** Invalid key-value pair: {line}")
                else:
                    print(f"\n   *** Key-value pair outside of section: {line}")

        return self.config

    def _topological_sort(self):
        from collections import defaultdict, deque

        # Build the graph (exclude %default as it's handled separately)
        graph = defaultdict(list)
        in_degree = defaultdict(int)
        
        # Only process non-default connections
        conns_to_sort = {k: v for k, v in self.config.get('conn', {}).items() if k != '%default'}
        
        for conn_name, conn_content in conns_to_sort.items():
            if 'also' in conn_content:
                referenced_conns = conn_content['also'].split()
                for ref in referenced_conns:
                    # Skip %default references in the graph
                    if ref != '%default':
                        graph[ref].append(conn_name)
                        in_degree[conn_name] += 1

        # Topological sort using Kahn's algorithm
        queue = deque([conn for conn in conns_to_sort if in_degree[conn] == 0])
        sorted_conns = []

        while queue:
            conn = queue.popleft()
            sorted_conns.append(conn)
            for neighbor in graph[conn]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(sorted_conns) != len(conns_to_sort):
            raise ValueError("Cycle detected in connection references")

        return sorted_conns

    def _quoted_value(self, value):
        if ' ' in value or '\t' in value:
            return f'"{value}"'
        return value

    # find a connection's parameter, 
    # if conn is not specified, search all connections and return a list of values
    def get_conn_parameter(self, key, conn = None):
        values = []
        if 'conn' in self.config:
            if conn is not None:
                if conn in self.config['conn']:
                    if key in self.config['conn'][conn]:
                        return self.config['conn'][conn][key]
                    else:
                        return None
            else:
                conns = self.config['conn']
                for conn_name in conns:
                    if key in conns[conn_name]:
                        values.append(conns[conn_name][key])
                return values
        else:
            return None
    
    # find all connections
    def get_conns(self):
        if 'conn' in self.config:
            return self.config['conn']
        else:
            return None

    # find all connections
    def dell_all_conns(self):
        for conn_name in list(self.config['conn']):
            if "default" in conn_name:
                continue
            else:
                del self.config['conn'][conn_name]
                  
    def set_conn_parameter(self, key, value, conn=None):
        if conn is not None:
            if conn not in self.config['conn']:
                self.config['conn'][conn]={}
            self.config['conn'][conn][key] = value
        else:
            for conn_name in self.config['conn']:
                self.config['conn'][conn_name][key] = value
    # 
    def dumps(self):
        from datetime import datetime

        # Format the timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Add the timestamp to the string
        output = [f"#\n# IPSec.conf generated by Creekside Networks LLC on {timestamp}\n#\n"]

        # Handle "ca" sections
        for section_type in self.config:
            if section_type.startswith('ca') or section_type.startswith('config'):
                for section_name in self.config[section_type]:
                    output.append(f"{section_type} {section_name}")
                    for key, value in self.config[section_type][section_name].items():
                        value = self._quoted_value(value)
                        output.append(f"    {key} = {value}")
                    output.append(f"")
 
        # Handle "conn" sections with topological sort
        if 'conn' in self.config:
            if '%default' in self.config['conn']:
                output.append("conn %default")
                for key, value in self.config['conn']['%default'].items():
                    value = self._quoted_value(value)
                    output.append(f"    {key} = {value}")
                self.config['conn'].pop('%default')
                output.append(f"\n")

            sorted_conns = self._topological_sort()
            for conn_name in sorted_conns:
                output.append(f"conn {conn_name}")
                for key, value in self.config['conn'][conn_name].items():
                    value = self._quoted_value(value)
                    output.append(f"    {key} = {value}")
                output.append(f"\n")

        # Handle "include" sections
        for section in self.config:
            if section.startswith('include'):
               for section_name in self.config[section_type]:
                    output.append(f"{section_type} {section_name}")
                    output.append(f"")

        output.append(f"\n")
        return '\n'.join(output)




