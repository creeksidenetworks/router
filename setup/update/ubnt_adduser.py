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

import  re
import  configparser
import  os
from    utility.global_config       import  GlobalConfig
from    utility.confirm             import  get_confirmation
from    utility.passwd              import  generate_random_pwd
from    utility.ux                  import  Colors, print_ok, print_warn, print_step, print_subtitle, print_info


def _gloabl_get_ssh_key(user):
    # get global configuration
    global_config = GlobalConfig() 

    if global_config.search(f"ssh-keys {user}"):
        key_name    = global_config.get(f"ssh-keys {user} key-name")
        key_type    = global_config.get(f"ssh-keys {user} key-type")
        key         = global_config.get(f"ssh-keys {user} key")
        return key_name, key_type, key
    else:
        return None, None, None

def _gloabl_set_ssh_key(user, key_name, key_type, key):
    # get global configuration
    global_config = GlobalConfig() 

    global_config.set(f"ssh-keys {user} key-name", key_name)
    global_config.set(f"ssh-keys {user} key-type", key_type)
    global_config.set(f"ssh-keys {user} key", key)
    return True

def validate_ssh_key(ssh_key):
    # Regular expression to validate SSH public key format
    ssh_key_pattern = re.compile(r"^(ssh-(rsa|dss|ed25519)|ecdsa-sha2-nistp(256|384|521)) [A-Za-z0-9+/=]+ ?.*$")
    return ssh_key_pattern.match(ssh_key) is not None

def extract_ssh_key_parts(ssh_key):
    parts = ssh_key.split()
    if len(parts) < 2:
        return None, None, None
    key_type = parts[0]
    key_name = parts[-1] if len(parts) > 2 else "default"
    key      = parts[1]
    return key_type, key_name, key

def _edit_user(updates, router_config, user, prompt_prefix="    "):
    # Add 2 more spaces for sub-function indent
    sub_prefix = prompt_prefix + "  "
    default_password = generate_random_pwd()
    new_password = input(f"{sub_prefix}Password [{Colors.GREEN}{default_password}{Colors.RESET}]: ") or default_password
    if new_password and len(new_password) >= 4:
        updates.add_changes(
            key = f"{user} password", 
            stage = 1, 
            description = f"user {user} password = xxxxxxxx",
            cmds = [f"set system login user {user} authentication plaintext-password {new_password}"]
        )

    if not router_config.search(f"system login user {user} authentication public-keys"):
        # search exising ssh keys
        key_name, key_type, key = _gloabl_get_ssh_key(user)
        if key is None:
            while True:
                new_ssh_key = input(f"{sub_prefix}SSH key (Enter to skip): ")
                if not new_ssh_key:
                    break
                elif validate_ssh_key(new_ssh_key):
                    key_type, key_name, key = extract_ssh_key_parts(new_ssh_key)
                    if key_type and key_name and key:
                        # Save the SSH key in the global configuration
                        _gloabl_set_ssh_key(user, key_name, key_type, key)
                        break
                else:
                    print_warn("Invalid SSH key format. Please enter a valid SSH public key.")

        if key is not None:
            updates.add_changes(
                key = f"{user} ssh key", 
                stage = 1, 
                description = f"user {user} ssh key = xxxxxxxx",
                cmds = [f"set system login user {user} authentication public-keys {key_name} type {key_type}",
                        f"set system login user {user} authentication public-keys {key_name} key {key}"]
            )

    return True

def _delete_user(updates, user):
    updates.add_changes(
        key = f"delete {user}", 
        stage = 1, 
        description = f"Delete user {user}",
        cmds = [f"delete system login user {user}"]
    )
    return True

def _prompt_user_action(prompt_prefix, user):
    """Prompt for user action: update, delete, or skip
    Returns: 'update', 'delete', or None
    """
    while True:
        action = input(f"{prompt_prefix}User {Colors.GREEN}{user}{Colors.RESET} [y/N/d]: ").strip().lower()
        if action in ['', 'n', 'no']:
            return None
        elif action in ['y', 'yes']:
            return 'update'
        elif action in ['d', 'delete']:
            return 'delete'
        else:
            print_warn("Invalid input. Enter 'y' to update, 'd' to delete, or 'n' to skip.")

def _load_default_config():
    """Load default.conf file if it exists"""
    config_path = "./default.conf"
    if not os.path.exists(config_path):
        return None
    
    config = configparser.ConfigParser()
    config.read(config_path)
    return config

def _add_default_users(updates, router_config, prompt_prefix="      "):
    """Add default users from default.conf if they don't exist on router"""
    config = _load_default_config()
    if not config or 'users' not in config:
        return 0
    
    existing_users = router_config.get("system login user") or []
    added_count = 0
    
    # Parse users from config
    users_config = config['users']
    users_data = {}
    
    # Group user properties
    for key, value in users_config.items():
        if '.' in key:
            username, prop = key.split('.', 1)
            if username not in users_data:
                users_data[username] = {}
            users_data[username][prop] = value
    
    # Add missing users with confirmation
    for username, props in users_data.items():
        if username not in existing_users:
            # Prompt user to confirm adding this default user
            action = input(f"{prompt_prefix}Add default user {Colors.GREEN}{username}{Colors.RESET} from default.conf? [Y/n]: ").strip().lower()
            if action in ['', 'y', 'yes']:
                cmds = []
                
                # Add encrypted password
                if 'encrypted-password' in props:
                    cmds.append(f"set system login user {username} authentication encrypted-password '{props['encrypted-password']}'")
                
                # Add level
                if 'level' in props:
                    cmds.append(f"set system login user {username} level {props['level']}")
                
                # Add SSH public key
                if 'public-key.name' in props and 'public-key.type' in props and 'public-key.key' in props:
                    key_name = props['public-key.name']
                    key_type = props['public-key.type']
                    key = props['public-key.key']
                    cmds.append(f"set system login user {username} authentication public-keys {key_name} type {key_type}")
                    cmds.append(f"set system login user {username} authentication public-keys {key_name} key {key}")
                
                if cmds:
                    updates.add_changes(
                        key=f"add_default_user_{username}",
                        stage=1,
                        description=f"Add default user {username}",
                        cmds=cmds
                    )
                    added_count += 1
    
    return added_count

def _configure_unms(updates, router_config):
    """Configure UNMS if not already configured"""
    config = _load_default_config()
    if not config or 'unms' not in config:
        return False
    
    # Check if UNMS is already configured
    if router_config.search("service unms connection"):
        return False
    
    connection = config['unms'].get('connection')
    if connection:
        updates.add_changes(
            key="configure_unms",
            stage=1,
            description=f"Configure UNMS connection",
            cmds=[f"set service unms connection '{connection}'"]
        )
        print_info("      Configuring UNMS service")
        return True
    
    return False

def ubnt_update_user(updates, router_config, streamlined=False):
    # find out the existing users
    if not streamlined:
        print_step("", "Configure System Users")
    else:
        print_subtitle("Administrators")
    
    # Define prompt prefix based on mode
    prompt_prefix = "    "
    
    # Add default users from default.conf if they don't exist
    added_count = _add_default_users(updates, router_config, prompt_prefix)
    if added_count > 0:
        print_ok(f"  {added_count} default user(s) will be added")
    
    # Configure UNMS if not already configured
    if _configure_unms(updates, router_config):
        print_ok("  UNMS will be configured")
    
    users = router_config.get("system login user") or []

    for user in users:
        action = _prompt_user_action(prompt_prefix, user)
        if action == 'update':
            _edit_user(updates, router_config, user, prompt_prefix)
        elif action == 'delete':
            _delete_user(updates, user)

    while True:
        user = input(f"{prompt_prefix}Add new admin (Enter to skip): ")
        if not user:
            break
        if user in users:
            print_warn("User already exists. Please enter a new username.")
        elif len(user) < 4:
            print_warn("Username must be at least 4 characters long.")
        else:
            _edit_user(updates, router_config, user, prompt_prefix)

    return True