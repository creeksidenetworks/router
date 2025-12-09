# Vyatta Config Parser
#
# Copyright (c) 2023-2025 Jackson Tong, Creekside Networks LLC.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

"""
Pure Python parser for VyOS/EdgeOS config.boot format.

This parser handles the curly-brace hierarchical configuration format used
by VyOS, EdgeOS, and similar systems.
"""

import re
from typing import Union


class ConfigParser:
    """
    Parser for VyOS/EdgeOS configuration files.
    
    Converts the hierarchical config.boot format to a Python dictionary/JSON.
    """
    
    def __init__(self, config_string: str):
        self._raw = config_string
        self._config = self._parse(config_string)
    
    def _strip_comments(self, text: str) -> str:
        """Remove C-style comments from config text."""
        # Remove /* ... */ style comments
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
        # Note: We don't remove // comments because they may appear in URLs (http://)
        # The config.boot format doesn't typically use // comments
        return text
    
    def _tokenize(self, text: str) -> list:
        """
        Tokenize the config text.
        
        Tokens are: identifiers, quoted strings, {, }
        """
        tokens = []
        text = self._strip_comments(text)
        
        # Pattern matches:
        # - Quoted strings (double quotes)
        # - Braces
        # - Unquoted words (including paths with / and . and special chars)
        pattern = r'"[^"]*"|[{}]|[^\s{}"]+'
        
        for match in re.finditer(pattern, text):
            token = match.group()
            # Remove quotes from quoted strings
            if token.startswith('"') and token.endswith('"'):
                token = token[1:-1]
            tokens.append(token)
        
        return tokens
    
    def _parse(self, config_string: str) -> dict:
        """Parse config string into a dictionary."""
        tokens = self._tokenize(config_string)
        result, _ = self._parse_block(tokens, 0)
        return result
    
    def _parse_block(self, tokens: list, pos: int) -> tuple:
        """
        Parse a configuration block.
        
        Returns (dict, new_position)
        """
        result = {}
        
        while pos < len(tokens):
            token = tokens[pos]
            
            if token == '}':
                return result, pos + 1
            
            if token == '{':
                # Shouldn't happen at block start, skip
                pos += 1
                continue
            
            # This is a key/node name
            key = token
            pos += 1
            
            if pos >= len(tokens):
                # Key with no value at end of file - treat as valueless
                self._add_to_dict(result, key, None)
                break
            
            next_token = tokens[pos]
            
            if next_token == '{':
                # It's a block: key { ... }
                pos += 1  # skip '{'
                block_value, pos = self._parse_block(tokens, pos)
                self._add_to_dict(result, key, block_value)
            elif next_token == '}':
                # Valueless node before closing brace
                self._add_to_dict(result, key, None)
                # Don't consume the '}', let the outer loop handle it
            else:
                # Check if there's a block after the value
                if pos + 1 < len(tokens) and tokens[pos + 1] == '{':
                    # It's a named/tagged block: key name { ... }
                    name = next_token
                    pos += 2  # skip name and '{'
                    block_value, pos = self._parse_block(tokens, pos)
                    self._add_named_block(result, key, name, block_value)
                else:
                    # It's a simple key-value pair
                    value = next_token
                    pos += 1
                    self._add_to_dict(result, key, value)
        
        return result, pos
    
    def _add_to_dict(self, d: dict, key: str, value) -> None:
        """Add a key-value pair to dict, handling multi-value nodes."""
        if key in d:
            existing = d[key]
            if isinstance(existing, list):
                existing.append(value)
            else:
                d[key] = [existing, value]
        else:
            d[key] = value
    
    def _add_named_block(self, d: dict, key: str, name: str, block: dict) -> None:
        """Add a named/tagged block (e.g., 'interface eth0 { ... }')."""
        if key not in d:
            d[key] = {}
        
        if isinstance(d[key], dict):
            d[key][name] = block
        else:
            # If key was previously a simple value, convert to dict
            d[key] = {name: block}
    
    def get_config(self) -> dict:
        """Return the parsed configuration as a dictionary."""
        return self._config
    
    def to_json(self) -> str:
        """Return the configuration as a JSON string."""
        import json
        return json.dumps(self._config)


def parse_config_file(filepath: str) -> dict:
    """
    Parse a config.boot file and return as dictionary.
    
    Args:
        filepath: Path to the config.boot file
        
    Returns:
        Dictionary representation of the configuration
    """
    with open(filepath, 'r') as f:
        config_string = f.read()
    
    parser = ConfigParser(config_string)
    return parser.get_config()


def parse_config_string(config_string: str) -> dict:
    """
    Parse a config string and return as dictionary.
    
    Args:
        config_string: Configuration in VyOS/EdgeOS format
        
    Returns:
        Dictionary representation of the configuration
    """
    parser = ConfigParser(config_string)
    return parser.get_config()


class ConfigWriter:
    """
    Writer for VyOS/EdgeOS configuration files.
    
    Converts a Python dictionary/JSON back to the config.boot format.
    """
    
    def __init__(self, config: dict):
        self._config = config
    
    def _needs_quotes(self, value: str) -> bool:
        """Check if a value needs to be quoted."""
        if not value:
            return True
        # Quote if contains whitespace, special chars, or is empty
        if ' ' in value or '\t' in value or '\n' in value:
            return True
        # Quote if contains characters that could be confused with syntax
        if '{' in value or '}' in value or '"' in value:
            return True
        return False
    
    def _format_value(self, value: str) -> str:
        """Format a value, adding quotes if necessary."""
        if self._needs_quotes(value):
            # Escape any quotes in the value
            escaped = value.replace('\\', '\\\\').replace('"', '\\"')
            return f'"{escaped}"'
        return value
    
    def _is_named_block_container(self, data: dict) -> bool:
        """
        Check if a dict represents a named block container.
        
        Named block containers have keys that are instance names (like eth0, wg0, 
        ADDR_CHINA_SITES, rule names like "1", "9999"), not config keywords 
        (like address-group, network-group, firewall, in, local, group).
        
        This is a heuristic that may not be 100% accurate for all edge cases.
        """
        if not data or not all(isinstance(v, dict) for v in data.values()):
            return False
        
        keys = list(data.keys())
        
        # Common config keywords that should NOT be treated as instance names
        config_keywords = {
            'in', 'out', 'local', 'global', 'all', 'default', 'group',
            'firewall', 'destination', 'source', 'state', 'options',
            'parameters', 'executable', 'facility', 'poe', 'ip', 'ipv4',
            'authentication', 'forward-to', 'start', 'subnet', 'mss-clamp'
        }
        
        # Check if keys look like instance names:
        # - Numeric keys (like rule "1", "9999")
        # - Keys that are mostly uppercase (like ADDR_CHINA_SITES, PUBLIC_LOCAL)
        # - Keys that look like interface names (eth0, wg0, tun5)
        # - Keys that contain special chars like @ or =
        
        instance_like = 0
        keyword_like = 0
        
        for key in keys:
            # Explicit config keywords
            if key in config_keywords:
                keyword_like += 1
            # Numeric keys are instance names
            elif key.isdigit():
                instance_like += 1
            # All uppercase (possibly with underscores) are likely instance names
            elif key.replace('_', '').replace('-', '').isupper():
                instance_like += 1
            # Interface patterns like eth0, wg0, tun5, vif10, eth4.10
            elif re.match(r'^[a-z]+[0-9]+(\.[0-9]+)?$', key):
                instance_like += 1
            # Keys with special chars like = or @ or + are likely instance values
            elif '=' in key or '@' in key or '+' in key:
                instance_like += 1
            # Hyphenated lowercase keys are likely config keywords
            elif '-' in key and key.islower():
                keyword_like += 1
            else:
                # For other keys, lean towards keyword if short
                if len(key) <= 6 and key.islower():
                    keyword_like += 1
                else:
                    instance_like += 1
        
        # If more instance-like keys than keyword-like, it's a named block container
        return instance_like > keyword_like
    
    def _write_block(self, data: dict, indent: int = 0) -> list:
        """
        Write a configuration block.
        
        Returns list of lines.
        """
        lines = []
        indent_str = '    ' * indent
        
        for key, value in data.items():
            if value is None:
                # Valueless node
                lines.append(f'{indent_str}{key}')
            elif isinstance(value, dict):
                # Check if this is a named block container
                if self._is_named_block_container(value):
                    # Named blocks (e.g., ethernet eth0 { ... })
                    for name, block in value.items():
                        lines.append(f'{indent_str}{key} {name} {{')
                        lines.extend(self._write_block(block, indent + 1))
                        lines.append(f'{indent_str}}}')
                else:
                    # Regular block
                    lines.append(f'{indent_str}{key} {{')
                    lines.extend(self._write_block(value, indent + 1))
                    lines.append(f'{indent_str}}}')
            elif isinstance(value, list):
                # Multi-value node
                for item in value:
                    if item is None:
                        lines.append(f'{indent_str}{key}')
                    elif isinstance(item, dict):
                        lines.append(f'{indent_str}{key} {{')
                        lines.extend(self._write_block(item, indent + 1))
                        lines.append(f'{indent_str}}}')
                    else:
                        lines.append(f'{indent_str}{key} {self._format_value(str(item))}')
            else:
                # Simple key-value
                lines.append(f'{indent_str}{key} {self._format_value(str(value))}')
        
        return lines
    
    def to_string(self) -> str:
        """Convert the configuration to config.boot format string."""
        lines = self._write_block(self._config, 0)
        return '\n'.join(lines) + '\n'
    
    def write_file(self, filepath: str) -> None:
        """Write the configuration to a file."""
        with open(filepath, 'w') as f:
            f.write(self.to_string())


def dict_to_config_string(config: dict) -> str:
    """
    Convert a dictionary to config.boot format string.
    
    Args:
        config: Dictionary representation of the configuration
        
    Returns:
        Configuration string in VyOS/EdgeOS format
    """
    writer = ConfigWriter(config)
    return writer.to_string()


def dict_to_config_file(config: dict, filepath: str) -> None:
    """
    Write a dictionary to a config.boot file.
    
    Args:
        config: Dictionary representation of the configuration
        filepath: Path to write the config.boot file
    """
    writer = ConfigWriter(config)
    writer.write_file(filepath)


def json_file_to_config_file(json_filepath: str, config_filepath: str) -> None:
    """
    Convert a JSON file to config.boot format.
    
    Args:
        json_filepath: Path to the JSON file
        config_filepath: Path to write the config.boot file
    """
    import json
    
    with open(json_filepath, 'r') as f:
        config = json.load(f)
    
    dict_to_config_file(config, config_filepath)


def json_string_to_config_string(json_string: str) -> str:
    """
    Convert a JSON string to config.boot format.
    
    Args:
        json_string: JSON string representation of the configuration
        
    Returns:
        Configuration string in VyOS/EdgeOS format
    """
    import json
    
    config = json.loads(json_string)
    return dict_to_config_string(config)
