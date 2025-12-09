#!/Users/jtong/python3/bin/python
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

import json

from vyatta.vyatta_router import VyattaRouter
from vyatta.configparser import ConfigParser, ConfigWriter


class VyattaConfig:
    def __init__(self):
        self.config_dict = {}

    # load configuration from a config.boot file 
    def load(self, config_source):
        if isinstance(config_source, str):
            # Assume it's a file path
            with open(config_source, 'r') as f:
                config_string = f.read()
        elif isinstance(config_source, VyattaRouter):
            # Assume it's a VyattaRouter object and get the configuration
            config_string = config_source.download('/config/config.boot')
        else:
            raise TypeError("Unsupported config_source type")

        # Use the new ConfigParser
        parser = ConfigParser(config_string)
        self.config_dict = parser.get_config()

    def save(self, json_file, config_file):
        with open(json_file, 'w') as f:
            json.dump(self.config_dict, f, indent=4)

        # Use the new ConfigWriter
        writer = ConfigWriter(self.config_dict)
        writer.write_file(config_file)

    def set(self, cmd, replace=True):
        # Split the command into parts
        parts = cmd.split()
        
        # Extract keys and value from the command
        keys = parts[:-1]
        value = parts[-1]
        
        # Traverse the configuration dictionary to the appropriate location
        d = self.config_dict
        for key in keys[:-1]:
            if key not in d:
                d[key] = {}
            d = d[key]
        
        # Check if the final key exists and replace is False
        if keys[-1] in d and not replace:
            error_message = f"Error: Configuration path {' '.join(keys)} already exists."
            return False, error_message
        
        # Set the value in the configuration dictionary
        d[keys[-1]] = value
        return True, None

    def get(self, path, key2list=True):
        """
        Get a configuration value from the config_data dictionary
        :param path: Configuration path
        :return: Value of the configuration path or None if not found
        """
        keys = path.split()
        d = self.config_dict
        for key in keys:
            if key in d:
                d = d[key]
            else:
                return None
            
        if isinstance(d, dict):
            # convert the sub dictionary to a list of keys 
            if key2list:
                return list(d.keys())
            else:
                return d
        else:
            return d

    def search(self, path):
        """
        Search for a configuration path in the config dictionary.
        
        Args:
            path (str): Space-separated configuration path (e.g., "system login user jtong")
            
        Returns:
            True if the path exists (partial or complete), False otherwise.
        
        Examples:
            - "system login user jtong" returns True if path exists (partial)
            - "service dns forwarding name-server 1.1.1.1" returns True if value in list
            - "service dns forwarding cache-size 150" returns True if key-value matches
        """
        # Split the path into components
        path_components = path.split()
        
        # Traverse the dictionary using the path components
        current_level = self.config_dict
        
        for i, key in enumerate(path_components):
            if not isinstance(current_level, dict):
                # If current level is not a dict, check if it's the last component
                if i == len(path_components) - 1:
                    # Check if current_level is a list and key is in it
                    if isinstance(current_level, list):
                        return key in current_level
                    # Check if current_level is a string and matches
                    else:
                        return str(current_level) == key
                return False
            
            if key in current_level:
                # Move to the next level
                current_level = current_level[key]
            else:
                # Key not found - check if this is the last component and current_level has a value
                if i == len(path_components) - 1:
                    # This handles the case where we're at a leaf node
                    # Check if the current level is a list or matches the value
                    if isinstance(current_level, list):
                        return key in current_level
                    elif isinstance(current_level, str):
                        return current_level == key
                return False
        
        # Successfully traversed all path components
        return True

    def dump(self):
        writer = ConfigWriter(self.config_dict)
        print(writer.to_string())


def test_config_generation(original_config_file_path, new_config_file_path):
    import difflib

    vyatta_config = VyattaConfig()
    vyatta_config.load(original_config_file_path)

    # Generate new configuration using ConfigWriter
    writer = ConfigWriter(vyatta_config.config_dict)
    writer.write_file(new_config_file_path)

    # Read original and new configuration files, ignoring comments
    def read_config_without_comments(file_path):
        with open(file_path, 'r') as f:
            lines = []
            in_multiline_comment = False
            for line in f:
                line = line.strip()
                if in_multiline_comment:
                    if "*/" in line:
                        in_multiline_comment = False
                    continue
                if line.startswith("/*"):
                    in_multiline_comment = True
                    continue
                if not line or line.startswith("#"):
                    continue
                lines.append(line)
        return lines

    original_lines = read_config_without_comments(original_config_file_path)
    new_lines = read_config_without_comments(new_config_file_path)

    # Compare the two configurations
    diff = list(difflib.unified_diff(original_lines, new_lines, lineterm=''))

    if not diff:
        print("test ok")
    else:
        print("Differences found:")
        i=0
        for line in original_lines:
            if line != new_lines[i]:
                print(f">>> : {line}")
                print(f"    : {new_lines[i]}")
            i+=1


if __name__ == "__main__":
    config_file_path = '/Users/jtong/work/10.1.10.254/config/config.boot'
    json_file_path = '/Users/jtong/work/10.1.10.254/config/config.json'
    new_config_file_path = '/Users/jtong/work/10.1.10.254/config/config_new.boot'

    vyatta_config = VyattaConfig()
    vyatta_config.load(config_file_path)

    #test_config_generation(config_file_path, new_config_file_path)

    #exit(0)

    success, error_message = vyatta_config.set("interfaces ethernet eth0 address 192.168.1.1/24")
    if success:
        vyatta_config.save(json_file_path, new_config_file_path)
    else:
        print(error_message)



