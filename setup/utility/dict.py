#!/usr/bin/env python
# Edgerouter/VyOS management scripts
# Copyright (c) 2023-2024 Jackson Tong, Creekside Networks LLC.
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

def set(dictionary, cmd, replace=True):
    # Split the command into parts
    parts = cmd.split()
    
    # Extract keys and value from the command
    keys = parts[:-1]
    value = parts[-1]
    
    # Traverse the configuration dictionary to the appropriate location
    d = dictionary
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

def get(dictionary, path, key2list=True):
    """
    Get a configuration value from the config_data dictionary
    :param path: Configuration path
    :param key2list: If the value is a dictionary, return a list of keys

    :return: Value of the configuration path or None if not found
    """
    keys = path.split()
    d = dictionary
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

def search(dictionary, path):
    # Search for a value in the configuration based on the given path.
    
    # Args:
    #     config (dict): The configuration dictionary.
    #     path (str): The path to search for. It is a dot-separated string.
        
    # Returns:
    #     True if the value exists at the given path, False otherwise.
    
    # Split the path into components
    path_components = path.split(' ')
    
    # Initialize the current level of the configuration
    current_level = dictionary
    
    # Traverse the dictionary using the path components
    for i, key in enumerate(path_components):
        if key in current_level:
            if i == len(path_components) - 2:
                # Last component of the path
                next_level = current_level[key]

                if isinstance(next_level, list):
                    # If the next_level is a list, check if the last part of the path is in the list
                    if ( path_components[-1].split()[-1] in next_level):
                        return True
                    else:
                        return False
                elif isinstance(next_level, dict) and path_components[-1].split()[-1] in next_level:
                    # If the next_level is a dictionary, return True
                    return True
                elif path_components[-1].split()[-1] == next_level:
                    # If the next_level is not a string and it match the last value, return True
                    return True
                else:
                    return False
            elif isinstance(current_level, dict):
                # Move to the next level
                current_level = current_level[key]
                continue
            else:
                return False
        else:
            return False
    
    return False