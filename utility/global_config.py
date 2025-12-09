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
import configparser

DEFAULT_CONFIG_PATH = "./default.conf"


class GlobalConfig:
    _instance = None

    def __new__(cls, config_path=DEFAULT_CONFIG_PATH):
        if cls._instance is None:
            cls._instance = super(GlobalConfig, cls).__new__(cls)
            cls._instance._initialize(config_path)
        return cls._instance

    def _initialize(self, config_path):
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        
        if os.path.exists(self.config_path):
            # Load existing configuration
            self.config.read(self.config_path)
        else:
            # Create empty config file if it doesn't exist
            with open(self.config_path, 'w') as f:
                self.config.write(f)

    def get(self, key, default=None):
        """
        Get a configuration value by key path.
        Key format: "section key" or just "section" to get all keys in section
        Examples:
            get("ssh-keys user1 key-name") -> returns key-name value
            get("unms connection") -> returns connection string
        """
        keys = key.split()
        
        if len(keys) == 0:
            return default
        
        section = keys[0]
        
        if not self.config.has_section(section):
            return default
        
        if len(keys) == 1:
            # Return all keys in the section as a dict
            return dict(self.config.items(section))
        
        # Build the full key for nested values (e.g., "user1.key-name")
        config_key = '.'.join(keys[1:])
        
        if self.config.has_option(section, config_key):
            return self.config.get(section, config_key)
        
        return default

    def search(self, path):
        """
        Check if a configuration path exists.
        Path format: "section key" or "section key.subkey"
        Examples:
            search("ssh-keys user1") -> True if user1 exists in ssh-keys section
            search("unms connection") -> True if connection exists in unms section
        """
        keys = path.split()
        
        if len(keys) == 0:
            return False
        
        section = keys[0]
        
        if not self.config.has_section(section):
            return False
        
        if len(keys) == 1:
            # Just checking if section exists
            return True
        
        # Build the full key for nested values
        config_key = '.'.join(keys[1:])
        
        return self.config.has_option(section, config_key)
    
    def set(self, key, value):
        """
        Set a configuration value by key path.
        Key format: "section key" or "section key.subkey"
        Examples:
            set("ssh-keys user1.key-name", "id_rsa")
            set("unms connection", "wss://example.com")
        """
        keys = key.split()
        
        if len(keys) < 2:
            raise ValueError("Key must have at least section and key name")
        
        section = keys[0]
        config_key = '.'.join(keys[1:])
        
        # Ensure section exists
        if not self.config.has_section(section):
            self.config.add_section(section)
        
        # Set the value
        self.config.set(section, config_key, str(value))
        self._save_config()

    def _save_config(self):
        with open(self.config_path, 'w') as f:
            self.config.write(f)