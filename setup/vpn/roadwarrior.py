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
import  tempfile
import  ipaddress

from    utility.input               import  input_ipv4, input_passwd
from    utility.global_config       import  GlobalConfig
from    utility.confirm             import  get_confirmation
from    utility.passwd              import  generate_random_pwd
from    utility.menu                import  menu_select
from    utility.ux                  import  (Colors, print_header, print_step, print_ok,
                                             print_warn, print_info, print_error, print_summary,
                                             print_subtitle)
from    vpn.certs_manager           import  certs_mananger
from    vpn.ipsec_config            import  IPSecConfig, DEFAULT_IPSEC_CONF
from    vpn.ipsec_secrets           import  IPSecSecrets, DEFAULT_IPSEC_SECRETS
from    vpn.strongswan_config       import  StrongswanConfig

from    cryptography import x509
from    cryptography.hazmat.primitives import serialization

SUBNET_PRIVATE  = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
SUBNET_INTERNET = "0.0.0.0/0"

# Default class-group IP pools for fresh eap-radius setups
DEFAULT_CLASS_GROUPS = [
    {'name': 'class_a', 'rightgroups': 'class_a', 'rightsourceip': '192.168.88.1/24'},
    {'name': 'class_b', 'rightgroups': 'class_b', 'rightsourceip': '192.168.89.1/24'},
]


def input_rightsourceip(prompt, default=None):
    while True:
        try:
            if default is not None:
                user_input = input(f"{prompt} [{Colors.GREEN}{default}{Colors.RESET}]: ")
                if user_input == '':
                    return default
            else:
                user_input = input(f"{prompt}: ")

            if '/' in user_input:
                network = ipaddress.IPv4Network(user_input, strict=False)
                return str(network)
            else:
                ipv4 = ipaddress.IPv4Address(user_input)
                return str(ipv4)
        except ValueError:
            print_warn("Invalid IPv4 address or CIDR notation")


def subnet_match(str1, str2):
    substrings1 = str1.split(',')
    substrings2 = str2.split(',')
    substrings1.sort()
    substrings2.sort()
    return substrings1 == substrings2


def roadwarrior_setup(router):
    if router.hardware and router.hardware.lower() == "e50":
        print_warn("Roadwarrior VPN is not supported on e50 platform due to limited resources")
        return False

    title = "\no Roadwarrior VPN"
    options = [
        "Exit",
        "IKEv2 VPN server setup",
        "Certificate Management",
    ]

    while True:
        match menu_select(title=title, lists=options, indent=0, index=0):
            case "Exit":
                break
            case "IKEv2 VPN server setup":
                ikev2_setup(router)
            case "Certificate Management":
                certs_mananger(router)
            case _:
                print("\n*** This feature is not implemented yet")

    return True


def get_ca_sans_from_cert(cert):
    san_extension = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    san_names = san_extension.value.get_values_for_type(x509.DNSName)

    cn = None
    for attribute in cert.issuer:
        if attribute.oid == x509.NameOID.COMMON_NAME:
            cn = attribute.value
            break
    expiration_date = cert.not_valid_after_utc.date()
    return cn, san_names, expiration_date


def _install_freeradius_utils(router):
    """Install freeradius-utils on the remote router (EdgeRouter or VyOS)."""
    print_step("", "Install FreeRADIUS Utilities")

    # Check by binary presence — dpkg status may show 'iU' (unpacked) on embedded systems
    check_out, _ = router.run_os_cmd("which radtest 2>/dev/null")
    if check_out and "radtest" in check_out:
        print_ok("freeradius-utils already installed")
        return

    if router.hardware:
        # EdgeRouter uses Debian Stretch — needs archive sources
        print_info("Configuring Debian stretch archive repository for EdgeRouter...")
        debian_sources = (
            "deb http://archive.debian.org/debian/ stretch main contrib non-free\\n"
            "deb http://archive.debian.org/debian/ stretch-proposed-updates main contrib non-free"
        )
        router.run_os_cmd(
            f"echo -e '{debian_sources}' | sudo tee /etc/apt/sources.list.d/debian-archive.list",
            echo=False
        )
        print_ok("Debian stretch repository configured")
    else:
        # VyOS uses standard Debian — no extra sources needed
        print_info("Using standard Debian repositories for VyOS...")

    print_info("Updating package lists...")
    router.run_os_cmd("sudo apt-get update -qq", echo=False)
    print_ok("Package lists updated")

    print_info("Installing freeradius-utils...")
    install_cmd = "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends freeradius-utils"
    output, error = router.run_os_cmd(install_cmd, echo=False)
    if error and "debconf" not in error and "WARNING" not in error:
        print_warn(f"Installation warning: {error}")

    # Ensure packages are fully configured (dpkg may leave them in 'unpacked' state)
    router.run_os_cmd("sudo dpkg --configure -a", echo=False)

    # Verify binary is present
    verify_out, _ = router.run_os_cmd("which radtest 2>/dev/null")
    if verify_out and "radtest" in verify_out:
        print_ok("freeradius-utils installed successfully")
    else:
        print_warn("freeradius-utils installed but radtest not found in PATH")


ROUTER_RADIUS_USERS_PATH   = "/config/ipsec.d/radius_users"
FREERADIUS_USERS_LINK_PATH = "/etc/freeradius/3.0/users"

RADIUS_USERS_EXAMPLE = """\
#
# FreeRADIUS users file — IKEv2 VPN with class-group IP pools
#
# strongSwan eap-radius reads the RADIUS 'Class' attribute and maps it to
# an ipsec.conf connection via rightgroups → different IP pool per class.
#
# Pool layout (matches default setup output):
#   class_a  →  192.168.88.0/24  (rightsourceip = 192.168.88.1/24)
#   class_b  →  192.168.89.0/24  (rightsourceip = 192.168.89.1/24)
#   (no Class) → fallback connection pool
#
# After editing, reload FreeRADIUS:
#   sudo systemctl reload freeradius
#   sudo freeradius -X   (debug mode)
#
# Test with radtest:
#   radtest alice password_alice 127.0.0.1 0 testing123
#

# ── Class A users — routed to 192.168.88.0/24 ──────────────────────────────

alice           Cleartext-Password := "password_alice"
                Class := "class_a",
                Reply-Message := "Welcome, Alice"

bob             Cleartext-Password := "password_bob"
                Class := "class_a",
                Reply-Message := "Welcome, Bob"

# ── Class B users — routed to 192.168.89.0/24 ──────────────────────────────

charlie         Cleartext-Password := "password_charlie"
                Class := "class_b",
                Reply-Message := "Welcome, Charlie"

diana           Cleartext-Password := "password_diana"
                Class := "class_b",
                Reply-Message := "Welcome, Diana"

# ── Users without a class — routed to fallback pool ────────────────────────

guest           Cleartext-Password := "password_guest"
                Reply-Message := "Welcome, Guest"
"""


def _install_radius_users(router):
    """
    Upload a default FreeRADIUS users file to /config/ipsec.d/radius_users
    (persistent across firmware upgrades) if one does not already exist,
    then symlink /etc/freeradius/3.0/users → /config/ipsec.d/radius_users.
    """
    print_step("", "Installing FreeRADIUS Users File")

    try:
        router.sftp_client.stat(ROUTER_RADIUS_USERS_PATH)
        print_ok(f"radius_users already exists at {ROUTER_RADIUS_USERS_PATH} — not overwriting")
    except Exception:
        with tempfile.NamedTemporaryFile(mode='w', suffix='_users', delete=False) as tmp:
            tmp.write(RADIUS_USERS_EXAMPLE)
            tmp_path = tmp.name
        try:
            router.upload(tmp_path, ROUTER_RADIUS_USERS_PATH, echo=False)
            router.run_os_cmd(f"sudo chmod 0640 {ROUTER_RADIUS_USERS_PATH}", echo=False)
            print_ok(f"Default radius_users uploaded to {ROUTER_RADIUS_USERS_PATH}")
        finally:
            os.unlink(tmp_path)

    # Create parent dir if freeradius is not installed yet
    router.run_os_cmd(
        f"sudo mkdir -p /etc/freeradius/3.0 && "
        f"sudo ln -fs {ROUTER_RADIUS_USERS_PATH} {FREERADIUS_USERS_LINK_PATH}",
        echo=False
    )
    print_ok(f"FreeRADIUS users symlink: {FREERADIUS_USERS_LINK_PATH} → {ROUTER_RADIUS_USERS_PATH}")


def _install_strongswan_plugin_hook(router, charon_conf_path):
    """
    Install a persistent boot script in /config/scripts/post-config.d/ that
    recreates /etc/strongswan.d/ and /etc/freeradius/ symlinks after firmware
    upgrades.  /etc is rebuilt on every boot; /config persists across upgrades.
    """
    print_step("", "Installing Persistent strongSwan Plugin Hook")

    ss_symlink  = f'ln -fs {charon_conf_path} /etc/strongswan.d/charon_roadwarrior.conf'
    rad_symlink = f'ln -fs {ROUTER_RADIUS_USERS_PATH} {FREERADIUS_USERS_LINK_PATH}'
    hook_script = (
        "#!/bin/sh\n"
        "# Recreate strongSwan and FreeRADIUS symlinks after firmware upgrade\n"
        f"{ss_symlink}\n"
        f"mkdir -p /etc/freeradius/3.0\n"
        f"{rad_symlink}\n"
    )

    hook_path = "/config/scripts/post-config.d/ipsec-plugin-symlinks.sh"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as tmp:
        tmp.write(hook_script)
        tmp_hook_path = tmp.name
    try:
        router.upload(tmp_hook_path, hook_path, echo=False)
        router.run_os_cmd(f"sudo chmod 0755 {hook_path}", echo=False)
        print_ok(f"Boot hook installed at {hook_path}")
    finally:
        os.unlink(tmp_hook_path)

    # Apply symlinks immediately for the current session
    router.run_os_cmd(f"sudo {ss_symlink}", echo=False)
    print_ok("strongSwan plugin symlink created")


def ikev2_setup(router):
    ROUTER_IPSEC_ROOT_PATH    = "/config/ipsec.d"
    ROUTER_IPSEC_CONF_PATH    = os.path.join(ROUTER_IPSEC_ROOT_PATH, "ipsec.conf")
    ROUTER_IPSEC_SECRETS_PATH = os.path.join(ROUTER_IPSEC_ROOT_PATH, "ipsec.secrets")

    server_certs = None
    default_rightdns = "8.8.8.8"
    existing_ipsec_config  = IPSecConfig()
    existing_ipsec_secrets = IPSecSecrets()
    remote_cert_path = os.path.join(ROUTER_IPSEC_ROOT_PATH, "certs/server.crt")

    from vyatta.vyatta_config import VyattaConfig
    from update.router_id import get_router_id
    temp_config = VyattaConfig()
    temp_config.load(router)
    router_id = get_router_id(temp_config) or "12"

    while True:
        print_step("", "Checking IPSec Configuration")
        ipsec_conf_str = router.download(ROUTER_IPSEC_CONF_PATH)
        if ipsec_conf_str is not None:
            print_ok("Existing IPSec configuration found")
            existing_ipsec_config.loads(ipsec_conf_str)
        else:
            existing_ipsec_config.loads(DEFAULT_IPSEC_CONF)

        existing_ipsec_secrets_str = router.download(ROUTER_IPSEC_SECRETS_PATH)
        if existing_ipsec_secrets_str is not None:
            print_ok("Existing IPSec secrets found")
            existing_ipsec_secrets.loads(existing_ipsec_secrets_str)

        remote_cert_path = existing_ipsec_config.get_conn_parameter("leftcert")
        if remote_cert_path:
            server_certs = router.download(remote_cert_path[0])

        if server_certs:
            cert = x509.load_pem_x509_certificate(server_certs.encode('utf-8'))
            cn, san_names, expiration_date = get_ca_sans_from_cert(cert)
            print_ok(f"VPN certs issued by \"{cn}\", valid until {expiration_date}")
            break
        else:
            print_warn("No VPN server certs found, starting certificate manager")
            certs = certs_mananger(router)
            if certs is None:
                print_error("No VPN server certs available, exiting")
                return False

    print_step("", "VPN Server Configuration")
    if len(san_names) > 1:
        dns = menu_select(title=f"  {Colors.CYAN}Select DNS name:{Colors.RESET}",
                          lists=san_names,
                          index=1)
    else:
        dns = san_names[0]

    print_ok(f"DNS name: {dns}")

    # eap-radius is the default; existing config may override
    existing_auth = existing_ipsec_config.get_conn_parameter("rightauth")
    available_auth_methods = ["eap-radius", "eap-mschapv2"]

    auth_method = menu_select(
        title   = "  Select authentication method:",
        lists   = available_auth_methods,
        default = existing_auth[0] if existing_auth else "eap-radius",
        index   = 1
    )
    print_ok(f"Authentication method: {auth_method}")

    leftsubnet = existing_ipsec_config.get_conn_parameter("leftsubnet")
    if leftsubnet:
        leftsubnet = leftsubnet[0]
        if subnet_match(leftsubnet, SUBNET_PRIVATE):
            leftsubnet_type = "Private"
        elif subnet_match(leftsubnet, SUBNET_INTERNET):
            leftsubnet_type = "Internet"
        else:
            leftsubnet_type = "Custom"
        print_info(f"Existing left network: {leftsubnet_type} | {leftsubnet}")
    else:
        leftsubnet_type = "Internet"
        leftsubnet = SUBNET_INTERNET

    leftsubnet_types = ["Private", "Internet", "Custom"]
    leftsubnet_type = menu_select(
        title   = f"  {Colors.CYAN}Select left network type:{Colors.RESET}",
        lists   = leftsubnet_types,
        default = leftsubnet_type,
        index   = 1
    )

    match leftsubnet_type:
        case "Private":
            leftsubnet = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
        case "Internet":
            leftsubnet = "0.0.0.0/0"
        case "Custom":
            while True:
                valid = False
                leftsubnet = input(f"  Remote subnets (comma separated) [{Colors.GREEN}{leftsubnet}{Colors.RESET}]: ") or leftsubnet
                subnets = leftsubnet.split(",")
                for i, subnet in enumerate(subnets):
                    subnet = subnet.strip()
                    if '/' not in subnet:
                        try:
                            ipaddress.ip_address(subnet)
                            subnets[i] = f"{subnet}/32"
                            valid = True
                        except ValueError:
                            print_error(f"{subnet} is not a valid IPv4 address")
                            valid = False
                            break
                    else:
                        try:
                            ipaddress.ip_network(subnet, strict=True)
                            valid = True
                        except ValueError:
                            print_error(f"{subnet} is NOT a valid IPv4 subnetwork")
                            valid = False
                            break
                if valid:
                    leftsubnet = ",".join(subnets)
                    break

    print_ok(f"Left network: {leftsubnet}")

    rightdns = existing_ipsec_config.get_conn_parameter("rightdns")
    rightdns = rightdns[0] if rightdns else default_rightdns

    if auth_method == "eap-mschapv2":
        print_step("", "Connection Settings")
        default_sourceip = f"10.{router_id}.240.1/24"
        rightsourceip = input_rightsourceip("  Right source IP", default=default_sourceip)
        rightdns = input_ipv4("  DNS IP address", default=rightdns)
        new_conn_lists = [{'name': 'fallback', 'rightgroups': '-', 'rightsourceip': rightsourceip, 'rightdns': rightdns}]

        users = existing_ipsec_secrets.get('EAP')
        if not users:
            users = {}
            existing_ipsec_secrets.secrets['EAP'] = users

        print_step("", "Update VPN Users")
        for user, pwd in list(users.items()):
            new_user = input(f"  Username ('-' to delete) [{Colors.GREEN}{user}{Colors.RESET}]: ") or user
            if new_user == '-':
                del users[user]
                continue
            elif new_user != user:
                users[new_user] = users.pop(user)
            new_pwd = input(f"  Password [{Colors.GREEN}{pwd}{Colors.RESET}]: ") or pwd
            users[new_user] = new_pwd

        print_step("", "Add New VPN Users")
        while True:
            new_user = input("  Username ('-' to finish): ") or '-'
            if new_user == '-':
                break
            new_pwd = generate_random_pwd()
            users[new_user] = input(f"  Password [{Colors.GREEN}{new_pwd}{Colors.RESET}]: ") or new_pwd

    elif auth_method == "eap-radius":
        print_step("", "RADIUS Server Configuration")

        charon_conf_path = "/config/ipsec.d/charon_roadwarrior.conf"
        charon_config = StrongswanConfig(config_str="")
        existing_charon_config = StrongswanConfig()
        new_conn_lists = []

        eap_radius_conf_str = router.download(charon_conf_path)
        if eap_radius_conf_str is not None:
            print_ok("Existing charon configuration found")
            existing_charon_config.loads(eap_radius_conf_str)

        existing_servers = existing_charon_config.get("charon plugins eap-radius servers")

        existing_server_name = "radius_server"
        address = None
        secret = ""

        if existing_servers and isinstance(existing_servers, dict):
            existing_server_name = list(existing_servers.keys())[0]
            address = existing_charon_config.get(f"charon plugins eap-radius servers {existing_server_name} address")
            secret  = existing_charon_config.get(f"charon plugins eap-radius servers {existing_server_name} secret")

        new_server_name = input(f"  RADIUS server name [{Colors.GREEN}{existing_server_name}{Colors.RESET}]: ") or existing_server_name

        while True:
            address = input_ipv4("  RADIUS server address", default=address)
            if address:
                break
            print_warn("RADIUS server address cannot be empty")

        while True:
            secret = input_passwd("  RADIUS server secret", default=secret)
            if secret:
                break
            print_warn("RADIUS server secret cannot be empty")

        # Build combined charon config: DHCP identity-lease + eap-radius
        charon_config.set("charon load_modular", "yes")
        charon_config.set("charon plugins dhcp identity_lease", "yes")
        charon_config.set("charon plugins eap-radius class_group", "yes")
        charon_config.set("charon plugins eap-radius servers", new_server_name)
        charon_config.set(f"charon plugins eap-radius servers {new_server_name} address", address)
        charon_config.set(f"charon plugins eap-radius servers {new_server_name} secret",  secret)

        # Load and present existing connections for editing
        conns = existing_ipsec_config.get_conns()
        if conns is not None:
            print_step("", "Update Existing Connections")
            for conn in conns:
                rightgroups = existing_ipsec_config.get_conn_parameter(key='rightgroups', conn=conn)
                if rightgroups is None:
                    rightgroups = '-'
                rightsourceip = existing_ipsec_config.get_conn_parameter(key='rightsourceip', conn=conn)

                if rightgroups == '-' and rightsourceip is None:
                    continue

                conn_rightdns = existing_ipsec_config.get_conn_parameter(key='rightdns', conn=conn)
                if conn_rightdns is None:
                    conn_rightdns = default_rightdns

                new_conn = {
                    'name': conn,
                    'rightgroups': rightgroups,
                    'rightsourceip': rightsourceip,
                    'rightdns': conn_rightdns,
                }
                new_conn_lists.append(new_conn)

                if rightgroups == '-' and rightsourceip is not None:
                    break

            for i, conn in enumerate(new_conn_lists):
                conn['name']         = input(f"\n  Connection name [{Colors.GREEN}{conn['name']}{Colors.RESET}]: ") or conn['name']
                conn['rightsourceip'] = input_rightsourceip("    Right source IP", default=conn['rightsourceip'])
                conn['rightgroups']   = input(f"    RADIUS group ('-' for fallback) [{Colors.GREEN}{conn['rightgroups']}{Colors.RESET}]: ") or conn['rightgroups']
                conn['rightdns']      = input_ipv4("    DNS IP address", default=rightdns)
                rightdns = conn['rightdns']
                if conn['rightgroups'] == "-":
                    new_conn_lists = new_conn_lists[:i + 1]
                    break

        # Add new connections if no fallback yet
        if not new_conn_lists or '-' not in new_conn_lists[-1]['rightgroups']:
            print_step("", "Add New Connections")
            conn_index = len(new_conn_lists)

            # Pre-seed default class-group connections for fresh setups
            pending_defaults = list(DEFAULT_CLASS_GROUPS) if not new_conn_lists else []
            if pending_defaults:
                print_info("Pre-populating default class-group connections (edit as needed)")

            while True:
                if pending_defaults:
                    d = pending_defaults.pop(0)
                    default_name     = d['name']
                    default_groups   = d['rightgroups']
                    default_sourceip = d['rightsourceip']
                else:
                    default_name     = 'fallback'
                    default_groups   = ''
                    default_sourceip = f"10.{router_id}.24{conn_index}.1/24"

                conn = {}
                conn['name']          = input(f"\n  Connection name [{Colors.GREEN}{default_name}{Colors.RESET}]: ") or default_name
                conn['rightsourceip'] = input_rightsourceip("    Right source IP", default=default_sourceip)
                conn['rightgroups']   = input(f"    RADIUS group ('-' for fallback) [{Colors.GREEN}{default_groups or '-'}{Colors.RESET}]: ") or default_groups or '-'
                conn['rightdns']      = input_ipv4("    DNS IP address", default=rightdns)
                new_conn_lists.append(conn)
                rightdns = conn['rightdns']
                if conn['rightgroups'] == "-":
                    break
                conn_index += 1

    # Build new ipsec.conf
    new_ipsec_config = IPSecConfig()
    new_ipsec_config.set_conn_parameter(key='rightauth',  value=auth_method,         conn='%default')
    new_ipsec_config.set_conn_parameter(key='leftsubnet', value=leftsubnet,           conn='%default')
    new_ipsec_config.set_conn_parameter(key='leftid',     value=f"@{san_names[0]}",  conn='%default')
    new_ipsec_config.set_conn_parameter(key='auto',       value='ignore',             conn='%default')

    if 'RSA' not in existing_ipsec_secrets.secrets:
        existing_ipsec_secrets.secrets['RSA'] = ['/config/ipsec.d/rsa-keys/localhost.key']

    for conn in new_conn_lists:
        conn_name     = conn['name']
        rightsourceip = conn['rightsourceip']
        rightgroups   = conn['rightgroups']
        conn_dns      = conn['rightdns']

        new_ipsec_config.set_conn_parameter(key='also',         value='%default',    conn=conn_name)
        new_ipsec_config.set_conn_parameter(key='rightsourceip', value=rightsourceip, conn=conn_name)
        new_ipsec_config.set_conn_parameter(key='rightdns',      value=conn_dns,      conn=conn_name)
        new_ipsec_config.set_conn_parameter(key='auto',          value='add',         conn=conn_name)
        if rightgroups != '-':
            new_ipsec_config.set_conn_parameter(key='rightgroups', value=rightgroups, conn=conn_name)

    if not get_confirmation("\nApply configuration to router?", default=True):
        print_warn("Configuration cancelled")
        return False

    # Install freeradius-utils and users file for RADIUS authentication
    if auth_method == "eap-radius":
        _install_freeradius_utils(router)
        _install_radius_users(router)

    # Upload IPSec configuration
    print_step("", "Uploading Configuration Files")

    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as tmp:
        tmp.write(new_ipsec_config.dumps())
        tmp_ipsec_path = tmp.name
    try:
        router.upload(tmp_ipsec_path, ROUTER_IPSEC_CONF_PATH, echo=False)
        print_ok("IPSec configuration uploaded")
    finally:
        os.unlink(tmp_ipsec_path)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.secrets', delete=False) as tmp:
        tmp.write(existing_ipsec_secrets.dumps())
        tmp_secrets_path = tmp.name
    try:
        router.upload(tmp_secrets_path, ROUTER_IPSEC_SECRETS_PATH, echo=False)
        print_ok("IPSec secrets uploaded")
    finally:
        os.unlink(tmp_secrets_path)

    # Combined strongSwan plugin config (DHCP + optionally eap-radius)
    charon_conf_path = "/config/ipsec.d/charon_roadwarrior.conf"
    if auth_method == "eap-mschapv2":
        # eap-mschapv2 only needs DHCP identity-lease
        charon_config = StrongswanConfig(config_str="")
        charon_config.set("charon load_modular", "yes")
        charon_config.set("charon plugins dhcp identity_lease", "yes")

    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as tmp:
        tmp.write(charon_config.dumps(charon_config.config))
        tmp_charon_path = tmp.name
    try:
        router.upload(tmp_charon_path, charon_conf_path, echo=False)
        print_ok("strongSwan plugin configuration uploaded (charon_roadwarrior.conf)")
    finally:
        os.unlink(tmp_charon_path)

    # Persistent boot hook: recreates /etc/strongswan.d/ symlink after firmware upgrades
    _install_strongswan_plugin_hook(router, charon_conf_path)

    # Configure VyOS/EdgeRouter
    print_step("", "Configuring Router")
    from vyatta.vyatta_config import VyattaConfig
    router_config = VyattaConfig()
    router_config.load(router)

    config_commands = []

    if not router_config.search(f"vpn ipsec include-ipsec-conf {ROUTER_IPSEC_CONF_PATH}"):
        config_commands.append(f"set vpn ipsec include-ipsec-conf {ROUTER_IPSEC_CONF_PATH}")

    if not router_config.search(f"vpn ipsec include-ipsec-secrets {ROUTER_IPSEC_SECRETS_PATH}"):
        config_commands.append(f"set vpn ipsec include-ipsec-secrets {ROUTER_IPSEC_SECRETS_PATH}")

    ipsec_interface = None
    ethernet_ifaces = router_config.get("interfaces ethernet")
    if ethernet_ifaces:
        for iface_name in ethernet_ifaces:
            if router_config.get(f"interfaces ethernet {iface_name} address"):
                ipsec_interface = iface_name
                break

    if not ipsec_interface and ethernet_ifaces:
        for eth in ethernet_ifaces:
            pppoe_ids = router_config.get(f"interfaces ethernet {eth} pppoe")
            if pppoe_ids:
                ipsec_interface = f"pppoe{pppoe_ids[0]}"
                break

    if ipsec_interface:
        if not router_config.search(f"vpn ipsec ipsec-interfaces interface {ipsec_interface}"):
            config_commands.append(f"set vpn ipsec ipsec-interfaces interface {ipsec_interface}")
            print_info(f"IPSec interface: {ipsec_interface}")
        else:
            print_info(f"IPSec interface already configured: {ipsec_interface}")
    else:
        print_warn("No suitable interface found for IPSec — please configure manually")

    if config_commands:
        print_step("", "Applying Configuration")
        router.config(config_commands, indent=2)
    else:
        print_info("VPN configuration already up to date")

    # Restart IPSec
    print_step("", "Restarting IPSec Service")
    restart_output, restart_error = router.run_os_cmd("sudo ipsec restart")
    if restart_error:
        print_warn(f"Restart warning: {restart_error}")

    import time
    time.sleep(2)
    status_output, status_error = router.run_os_cmd("sudo ipsec status")

    if status_error or "failed" in status_output.lower() or "error" in status_output.lower():
        print_error("IPSec service has errors:")
        print(status_output)
        if status_error:
            print(status_error)
    else:
        print_ok("IPSec service restarted successfully")

    print_ok("VPN configuration complete")
    return True
