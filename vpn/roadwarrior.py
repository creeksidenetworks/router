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

from    utility.input               import  input_ipv4,input_passwd
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

def input_rightsourceip(prompt, default=None):
    while True:
        try:
            if default is not None:
                user_input = input(f"{prompt} [{Colors.GREEN}{default}{Colors.RESET}]: ")
                if user_input == '':
                    return default
            else:
                user_input = input(f"{prompt}: ")

            # Check if the input is a valid IPv4 address or CIDR notation
            if '/' in user_input:
                # Validate CIDR notation
                network = ipaddress.IPv4Network(user_input, strict=False)
                return str(network)
            else:
                # Validate single IPv4 address
                ipv4 = ipaddress.IPv4Address(user_input)
                return str(ipv4)
        except ValueError:
            print_warn("Invalid IPv4 address or CIDR notation")

def subnet_match(str1, str2):
    # Split the strings into substrings
    substrings1 = str1.split(',')
    substrings2 = str2.split(',')
    
    # Sort the substrings
    substrings1.sort()
    substrings2.sort()
    
    # Compare the sorted lists of substrings
    return substrings1 == substrings2

def roadwarrior_setup(router):
    # Check if platform is e50 (not supported for VPN)
    if router.hardware and router.hardware.lower() == "e50":
        print_warn("Roadwarrior VPN is not supported on e50 platform due to limited resources")
        return False
    
    title="\no Roadwarrior VPN"
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

# get CA CNAME and SANs from the certificate
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

def ikev2_setup(router):
    ROUTER_IPSEC_ROOT_PATH       = "/config/ipsec.d"
    ROUTER_IPSEC_CONF_PATH       = os.path.join(ROUTER_IPSEC_ROOT_PATH, "ipsec.conf")
    ROUTER_IPSEC_SECRETS_PATH    = os.path.join(ROUTER_IPSEC_ROOT_PATH, "ipsec.secrets")

    server_certs = None
    default_rightdns = "8.8.8.8"
    existing_ipsec_config  = IPSecConfig()
    existing_ipsec_secrets = IPSecSecrets()
    remote_cert_path = os.path.join(ROUTER_IPSEC_ROOT_PATH, "certs/server.crt")

    # Get router ID for default IP addresses
    from vyatta.vyatta_config import VyattaConfig
    from update.router_id import get_router_id
    temp_config = VyattaConfig()
    temp_config.load(router)
    router_id = get_router_id(temp_config) or "12"  # fallback to 12 if not found


    while True:
        print_step("", "Checking IPSec Configuration")
        ipsec_conf_str = router.download(ROUTER_IPSEC_CONF_PATH)
        if ipsec_conf_str is not None:
            # load the existing IPSec configuration
            print_ok("Existing IPSec configuration found")
            existing_ipsec_config.loads(ipsec_conf_str)
        else:
            # Use the default IPSec configuration
            existing_ipsec_config.loads(DEFAULT_IPSEC_CONF)

        # try to load the existing IPSec secrets
        existing_ipsec_secrets_str = router.download(ROUTER_IPSEC_SECRETS_PATH)
        if existing_ipsec_secrets_str is not None:
            # load the existing IPSec secrets
            print_ok("Existing IPSec secrets found")
            existing_ipsec_secrets.loads(existing_ipsec_secrets_str)
            #existing_ipsec_secrets.dumps()

        # Check if the remote certificate exists
        remote_cert_path = existing_ipsec_config.get_conn_parameter("leftcert")
        if remote_cert_path:
            server_certs=router.download(remote_cert_path[0])

        if server_certs:
            cert = x509.load_pem_x509_certificate(server_certs.encode('utf-8'))
            cn, san_names, expiration_date = get_ca_sans_from_cert(cert)
            print_ok(f"VPN certs issued by \"{cn}\", valid until {expiration_date}")
            break
        else:
            # No available certs, prompt for new certs
            print_warn("No VPN server certs found, starting certificate manager")
            certs = certs_mananger (router)
            if certs is None:
                print_error("No VPN server certs available, exiting")
                return False

    print_step("", "VPN Server Configuration")
    if len(san_names) > 1:
        dns = menu_select(title =f"  {Colors.CYAN}Select DNS name:{Colors.RESET}", 
                          lists = san_names,
                          index = 1)
    else:
        dns = san_names[0]

    print_ok(f"DNS name: {dns}")

    auth_methods = existing_ipsec_config.get_conn_parameter("rightauth")
    available_auth_methods = ["eap-mschapv2", "eap-radius"]
    
    title = "  Select authentication method:"
    auth_method = menu_select(title     = title, 
                              lists     = available_auth_methods, 
                              default   = auth_methods[0], 
                              index     = 1)
    
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

    # choose left network
    leftsubnet_types = ["Private", "Internet", "Custom"]

    leftsubnet_type = menu_select(
                        title     = f"  {Colors.CYAN}Select left network type:{Colors.RESET}", 
                        lists     = leftsubnet_types, 
                        default   = leftsubnet_type, 
                        index     = 1)
    
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
    if rightdns:
        rightdns = rightdns[0]
    else:
        rightdns = default_rightdns

    if auth_method == "eap-mschapv2":
        # add a fallback connection
        print_step("", "Connection Settings")
        default_sourceip = f"10.{router_id}.240.1/24"
        rightsourceip = input_rightsourceip(f"  Right source IP", default=default_sourceip)
        rightdns = input_ipv4(f"  DNS IP address", default=rightdns)
        new_conn_lists = [{'name': 'fallback', 'rightgroups': '-', 'rightsourceip': rightsourceip, 'rightdns':rightdns}]

        users = existing_ipsec_secrets.get('EAP')
        if not users:
            users = {}
            existing_ipsec_secrets.secrets['EAP'] = users
        
        print_step("", "Update VPN Users")
        #print(json.dumps(users, indent=4))
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
        
        # RADIUS configuration path
        radius_conf_path = "/config/ipsec.d/roadwarrior_radius.conf"
        # Create fresh RADIUS config without DHCP settings (DHCP is in separate file)
        radius_config = StrongswanConfig(config_str="")
        existing_radius_config = StrongswanConfig()
        new_conn_lists = []

        # try to load the existing RADIUS configuration
        eap_radius_conf_str = router.download(radius_conf_path)

        if eap_radius_conf_str is not None:
            # load the existing eap-radius configuration
            print_ok("Existing RADIUS configuration found")
            existing_radius_config.loads(eap_radius_conf_str)
            #print(json.dumps(radius_config.config, indent=4))

        # Read existing RADIUS configuration
        existing_servers = existing_radius_config.get("charon plugins eap-radius servers")
        
        # Set defaults
        existing_server_name = "radius_server"
        address = None
        secret = ""
        
        if existing_servers and isinstance(existing_servers, dict):
            existing_server_name = list(existing_servers.keys())[0]
            address = existing_radius_config.get(f"charon plugins eap-radius servers {existing_server_name} address")
            secret  = existing_radius_config.get(f"charon plugins eap-radius servers {existing_server_name} secret")

        new_server_name = input(f"  RADIUS server name [{Colors.GREEN}{existing_server_name}{Colors.RESET}]: ") or existing_server_name
        
        # Ensure address is not empty
        while True:
            address = input_ipv4(f"  RADIUS server address", default=address)
            if address:
                break
            print_warn("RADIUS server address cannot be empty")
        
        # Ensure secret is not empty
        while True:
            secret = input_passwd(f"  RADIUS server secret", default=secret)
            if secret:
                break
            print_warn("RADIUS server secret cannot be empty")
        
        # Build RADIUS configuration
        radius_config.set(f"charon load_modular", "yes")
        radius_config.set(f"charon plugins eap-radius class_group", "yes")
        radius_config.set(f"charon plugins eap-radius servers", new_server_name)
        radius_config.set(f"charon plugins eap-radius servers {new_server_name} address", address)
        radius_config.set(f"charon plugins eap-radius servers {new_server_name} secret",  secret)

        #print(json.dumps(radius_config.config, indent=4))
        # get existing connections and groups
        conns = existing_ipsec_config.get_conns()
        if conns is not None:
            print_step("", "Update Existing Connections")
            for conn in conns:
                # get the connection name & group & rightsourceip
                rightgroups = existing_ipsec_config.get_conn_parameter(
                        key = 'rightgroups', 
                        conn=conn)
                if rightgroups is None:
                    rightgroups =  '-'  # fallback to '-'
                rightsourceip = existing_ipsec_config.get_conn_parameter(
                        key = 'rightsourceip', 
                        conn=conn)

                if rightgroups == '-' and rightsourceip is None:
                    continue

                rightdns = existing_ipsec_config.get_conn_parameter(
                        key = 'rightdns',
                        conn=conn)
                
                if rightdns is None:
                    rightdns = default_rightdns

                new_conn = {'name': conn, 
                            'rightgroups': rightgroups, 
                            'rightsourceip': rightsourceip,
                            'rightdns':rightdns}
                new_conn_lists.append(new_conn)

                if rightgroups == '-' and rightsourceip is not None:
                    # fallback connection detected, break the loop
                    break

            # update existing
            for i, conn in enumerate(new_conn_lists):
                conn['name'] = input(f"\n  Connection name [{Colors.GREEN}{conn['name']}{Colors.RESET}]: ") or conn['name']
                conn['rightsourceip'] = input_rightsourceip(f"    Right source IP", default = conn['rightsourceip'])
                conn['rightgroups'] = input(f"    RADIUS group ('-' to finish) [{Colors.GREEN}{conn['rightgroups']}{Colors.RESET}]: ") or conn['rightgroups']
                conn['rightdns'] = input_ipv4(f"    DNS IP address", default=rightdns)
                rightdns = conn['rightdns']
                if conn['rightgroups'] == "-":
                    new_conn_lists = new_conn_lists[:i+1]  # Slice the list to keep elements up to and including the current one
                    break

        # Check if we need to add new connections
        if not new_conn_lists or '-' not in new_conn_lists[-1]['rightgroups']:
            print_step("", "Add New Connections")
            conn_index = len(new_conn_lists)
            while True:
                default_sourceip = f"10.{router_id}.24{conn_index}.1/24"
                conn = {'name': '', 'rightgroups': '', 'rightsourceip': '', 'rightdns': ''}
                conn['name'] = input(f"\n  Connection name [{Colors.GREEN}fallback{Colors.RESET}]: ") or 'fallback'
                conn['rightsourceip'] = input_rightsourceip(f"    Right source IP", default=default_sourceip)
                conn['rightgroups'] = input(f"    RADIUS group ('-' to finish): ") or '-'
                conn['rightdns'] = input_ipv4(f"    DNS IP address", default=rightdns)
                new_conn_lists.append(conn)
                if conn['rightgroups'] == "-":
                    break
                conn_index += 1

    # add the new connections to the configuration
    new_ipsec_config = IPSecConfig()
    new_ipsec_config.set_conn_parameter(
            key = 'rightauth',
            value = auth_method,
            conn = '%default'
    )
    
    # Ensure RSA key is in secrets (required for certificate authentication)
    if 'RSA' not in existing_ipsec_secrets.secrets:
        existing_ipsec_secrets.secrets['RSA'] = ['/config/ipsec.d/certs/server.key']
    new_ipsec_config.set_conn_parameter(
            key = 'leftid',
            value = f"@{san_names[0]}",
            conn = '%default'
    )
    new_ipsec_config.set_conn_parameter(
            key = 'auto',
            value = 'ignore',
            conn = '%default'
    )
    for conn in new_conn_lists:
        conn_name = conn['name']
        rightsourceip = conn['rightsourceip']
        rightgroups = conn['rightgroups']

        # add the connection to the configuration
        # leftid is inherited from %default, works for both Windows and macOS
        new_ipsec_config.set_conn_parameter(
                key = 'also',
                value = '%default',
                conn = conn_name)
        new_ipsec_config.set_conn_parameter(
                key = 'rightsourceip',
                value = rightsourceip,
                conn = conn_name)
        new_ipsec_config.set_conn_parameter(
                key = 'auto',
                value = 'add',
                conn = conn_name)
        if rightgroups != '-':
            new_ipsec_config.set_conn_parameter(
                key = 'rightgroups',
                value = rightgroups,
                conn = conn_name)
    
    # Confirm before applying
    if not get_confirmation("\nApply configuration to router?", default=True):
        print_warn("Configuration cancelled")
        return False

    # Install freeradius-utils if using RADIUS authentication
    if auth_method == "eap-radius":
        print_step("", "Install FreeRADIUS Utilities")
        
        # Check if freeradius-utils is installed
        check_cmd = "dpkg -l | grep '^ii' | grep -w freeradius-utils"
        output, error = router.run_os_cmd(check_cmd)
        
        if not output or "freeradius-utils" not in output:
            # Configure Debian package repositories
            print_info("Configuring Debian package repositories...")
            debian_sources = "deb http://archive.debian.org/debian/ stretch main contrib non-free\\ndeb http://archive.debian.org/debian/ stretch-proposed-updates main contrib non-free"
            config_apt_cmd = f"echo -e '{debian_sources}' | sudo tee /etc/apt/sources.list.d/debian-archive.list"
            router.run_os_cmd(config_apt_cmd, echo=False)
            print_ok("Debian repository sources configured")
            
            # Run apt update
            print_info("Updating package lists...")
            router.run_os_cmd("sudo apt-get update", echo=False)
            print_ok("Package lists updated")
            
            # Install freeradius-utils
            print_info("Installing freeradius-utils...")
            install_cmd = "sudo apt-get install -y --no-install-recommends freeradius-utils"
            output, error = router.run_os_cmd(install_cmd, echo=False)
            if error and "debconf" not in error:
                print_warn(f"Installation warning: {error}")
            else:
                print_ok("freeradius-utils installed successfully")
        else:
            print_ok("freeradius-utils already installed")

    # Upload configurations
    print_step("", "Uploading Configuration Files")
    
    # Upload IPSec configuration
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as tmp:
        tmp.write(new_ipsec_config.dumps())
        tmp_ipsec_path = tmp.name
    try:
        router.upload(tmp_ipsec_path, ROUTER_IPSEC_CONF_PATH, echo=False)
        print_ok("IPSec configuration uploaded")
    finally:
        os.unlink(tmp_ipsec_path)

    # Upload IPSec secrets (contains RSA key reference + optional user credentials)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.secrets', delete=False) as tmp:
        tmp.write(existing_ipsec_secrets.dumps())
        tmp_secrets_path = tmp.name
    try:
        router.upload(tmp_secrets_path, ROUTER_IPSEC_SECRETS_PATH, echo=False)
        print_ok("IPSec secrets uploaded")
    finally:
        os.unlink(tmp_secrets_path)

    # Upload DHCP configuration (for identity-based DHCP leases)
    dhcp_conf_path = "/config/ipsec.d/roadwarrior_dhcp.conf"
    dhcp_config = """charon {
    load_modular = yes
    plugins {
        dhcp {
            # Derive user-defined MAC address from hash of IKE identity and send client
            # identity DHCP option.
            identity_lease = yes
        }
    }
}"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as tmp:
        tmp.write(dhcp_config)
        tmp_dhcp_path = tmp.name
    try:
        router.upload(tmp_dhcp_path, dhcp_conf_path, echo=False)
        print_ok("DHCP configuration uploaded")
    finally:
        os.unlink(tmp_dhcp_path)
    
    # Create symlink for DHCP configuration
    router.run_os_cmd(
        f"sudo ln -fs {dhcp_conf_path} /etc/strongswan.d/roadwarrior_dhcp.conf"
    )

    if auth_method == "eap-radius":
        # Upload RADIUS configuration
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as tmp:
            tmp.write(radius_config.dumps(radius_config.config))
            tmp_radius_path = tmp.name
        try:
            router.upload(tmp_radius_path, radius_conf_path, echo=False)
            print_ok("RADIUS configuration uploaded")
        finally:
            os.unlink(tmp_radius_path)
        
        # Create symlink for RADIUS configuration
        router.run_os_cmd(
            f"sudo ln -fs {radius_conf_path} /etc/strongswan.d/roadwarrior_radius.conf"
        )

    # Configure VyOS
    print_step("", "Configuring Router")
    from vyatta.vyatta_config import VyattaConfig
    router_config = VyattaConfig()
    router_config.load(router)

    # Build configuration commands
    config_commands = []
    
    # Add IPSec include configs only if not already present
    if not router_config.search(f"vpn ipsec include-ipsec-conf {ROUTER_IPSEC_CONF_PATH}"):
        config_commands.append(f"set vpn ipsec include-ipsec-conf {ROUTER_IPSEC_CONF_PATH}")
    
    if not router_config.search(f"vpn ipsec include-ipsec-secrets {ROUTER_IPSEC_SECRETS_PATH}"):
        config_commands.append(f"set vpn ipsec include-ipsec-secrets {ROUTER_IPSEC_SECRETS_PATH}")

    # Get the interface for IPSec - find first interface with address
    ipsec_interface = None
    
    # Try ethernet interfaces first
    ethernet_ifaces = router_config.get("interfaces ethernet")
    if ethernet_ifaces:
        for iface_name in ethernet_ifaces:
            if router_config.get(f"interfaces ethernet {iface_name} address"):
                ipsec_interface = iface_name
                break
    
    # If no ethernet interface found, try pppoe
    if not ipsec_interface:
        if ethernet_ifaces:
            for eth in ethernet_ifaces:
                pppoe_ids = router_config.get(f"interfaces ethernet {eth} pppoe")
                if pppoe_ids:
                    ipsec_interface = f"pppoe{pppoe_ids[0]}"
                    break

    if ipsec_interface:
        # Only add if not already configured
        if not router_config.search(f"vpn ipsec ipsec-interfaces interface {ipsec_interface}"):
            config_commands.append(f"set vpn ipsec ipsec-interfaces interface {ipsec_interface}")
            print_info(f"IPSec interface: {ipsec_interface}")
        else:
            print_info(f"IPSec interface already configured: {ipsec_interface}")
    else:
        print_warn("No suitable interface found for IPSec - please configure manually")

    # Apply configuration only if there are changes
    if config_commands:
        print_step("", "Applying Configuration")
        router.config(config_commands, indent=2)
    else:
        print_info("VPN configuration already up to date")
    
    # Restart IPSec service
    print_step("", "Restarting IPSec Service")
    restart_output, restart_error = router.run_os_cmd("sudo ipsec restart")
    if restart_error:
        print_warn(f"Restart warning: {restart_error}")
    
    # Check IPSec status
    import time
    time.sleep(2)  # Wait for service to restart
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
