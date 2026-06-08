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

import  os
import  re
import  base64
import  struct
import  subprocess
import  configparser
import  validators

from    simple_term_menu                            import TerminalMenu
from    cryptography                                import x509
from    cryptography.x509.oid                       import NameOID, ExtendedKeyUsageOID
from    cryptography.hazmat.primitives              import hashes, serialization
from    cryptography.hazmat.primitives.asymmetric   import rsa
from    datetime                                    import datetime, timedelta
from    utility.ux                                  import (Colors, print_header, print_step, 
                                                             print_ok, print_error, print_info, 
                                                             print_warn, print_summary)


# Define the global variable for the base path
CERTS_BASE_PATH     = os.path.expanduser("~/.router/certs")
ROUTER_IPSEC_ROOT   = "/config/ipsec.d"
ROUTER_ACME_ROOT    = "/config/user-data/acme"

class CertManager:
    def __init__(self, ca_name, ca_path, vpn_cert_path):
        self.ca_name = ca_name
        self.ca_path = os.path.expanduser(ca_path)
        self.server_cert_path = os.path.expanduser(vpn_cert_path)
        self.ca_cert_path = os.path.join(self.ca_path, "ca.crt")
        self.ca_key_path = os.path.join(self.ca_path, "ca.key")
        os.makedirs(self.ca_path, exist_ok=True)
        os.makedirs(self.server_cert_path, exist_ok=True)

    def create_self_signed_ca(self, country, state, locality, organization, common_name):
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, country),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, state),
            x509.NameAttribute(NameOID.LOCALITY_NAME, locality),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])
        ca_cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=365*20)
        ).add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True,
        ).sign(key, hashes.SHA256())

        with open(self.ca_cert_path, "wb") as f:
            f.write(ca_cert.public_bytes(serialization.Encoding.PEM))

        with open(self.ca_key_path, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))

        print_ok(f"Self-signed CA created at {self.ca_path}")

    def load_existing_ca(self, ca_cert_path, ca_key_path):
        with open(ca_cert_path, "rb") as f:
            ca_cert = f.read()
        with open(ca_key_path, "rb") as f:
            ca_key = f.read()

        with open(self.ca_cert_path, "wb") as f:
            f.write(ca_cert)
        with open(self.ca_key_path, "wb") as f:
            f.write(ca_key)

        #print(f"Existing CA loaded from {ca_cert_path} and {ca_key_path}")

    #
    #    rsa_rfc3110:
    #        Extract RSA public key and convert it to RFC3110 format
    #    return: rfc3110_key in text format
    #
    def rsa_rfc3110(self, private_key):
        # Extract the public key from the private key
        public_key = private_key.public_key()

        # Extract the public key components
        n = public_key.public_numbers().n
        e = public_key.public_numbers().e

        # Convert the components to bytes
        e_bytes = e.to_bytes((e.bit_length() + 7) // 8, 'big')
        n_bytes = n.to_bytes((n.bit_length() + 7) // 8, 'big')
        len_e = len(e_bytes)
        len_n = len(n_bytes)

        # Construct the RFC3110 public key in base64 format
        #rfc3110_key = f"0s" + base64.b64encode(struct.pack(f'1s{len_e}s{len_n}s', len_e.to_bytes(1,'big'), e_bytes, n_bytes)).decode()
        rfc3110_key = f"0s" + base64.b64encode(struct.pack(f'B{len_e}s{len_n}s', len_e, e_bytes, n_bytes)).decode()

        # Return the RFC3110 public key
        return rfc3110_key

    #
    #    issue_vpn_server_cert:
    #        generate a VPN server certificate signed by the given self-signed CA
    #    return: cert, key 
    #
    def issue_vpn_server_cert(self, server_name, dns_names, country, state, locality, organization):
        with open(self.ca_key_path, "rb") as f:
            ca_key = serialization.load_pem_private_key(f.read(), password=None)

        with open(self.ca_cert_path, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())

        # Create a list of x509.DNSName objects from dns_names
        san_list = [x509.DNSName(dns_name) for dns_name in dns_names]

        # Create directory for server_name if it doesn't exist
        server_dir = os.path.join(self.server_cert_path, server_name)
        if not os.path.isdir(server_dir):
            print_info(f"Creating directory for {server_name} at {server_dir}")
            os.makedirs(server_dir, exist_ok=True)

        server_key_path = os.path.join(server_dir, "server.key")

        # Check if server.key exists and load it, otherwise generate a new RSA key
        if os.path.exists(server_key_path):
            print_ok(f"Found existing server.key at {server_key_path}")
            with open(server_key_path, "rb") as f:
                key = serialization.load_pem_private_key(f.read(), password=None)
        else:
            print_info(f"No existing server.key found, generating new RSA key")
            key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
            )
            with open(server_key_path, "wb") as f:
                f.write(key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                ))

        subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, country),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, state),
            x509.NameAttribute(NameOID.LOCALITY_NAME, locality),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
            x509.NameAttribute(NameOID.COMMON_NAME, server_name),
        ])

        # Issue the server certificate from the CA
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            ca_cert.subject
        ).public_key(
            key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=365*20)
        ).add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False,
        ).add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]), 
            critical=False,
        ).add_extension(x509.KeyUsage( 
                digital_signature=True, 
                content_commitment=True, 
                key_encipherment=True, 
                data_encipherment=True, 
                key_agreement=False, 
                key_cert_sign=False, 
                crl_sign=False, 
                encipher_only=False, 
                decipher_only=False), 
            critical=True
        ).sign(ca_key, hashes.SHA256())

        server_cert_root = os.path.join(server_dir, "server.crt")

        with open(server_cert_root, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        # Copy the CA certificate to the VPN cert folder as ca.crt
        ca_cert_dest_path = os.path.join(server_dir, "ca.crt")
        with open(self.ca_cert_path, "rb") as f_src:
            with open(ca_cert_dest_path, "wb") as f_dest:
                f_dest.write(f_src.read())

        # Generate RFC3110 public key and save to server.pub
        rfc3110_pubkey = self.rsa_rfc3110(key)
        server_pub_path = os.path.join(server_dir, "server.pub")
        with open(server_pub_path, "w") as f:
            f.write(rfc3110_pubkey)

        print_ok(f"VPN server certificate for {server_name} issued at {server_dir}")

        return cert, key

# Helper functions
def is_valid_domain(domain):
    # Regular expression to validate domain
    regex = r'^(?!-)[A-Za-z0-9-]{1,63}(?<!-)\.(?!-)[A-Za-z0-9-]{1,63}(?<!-)$'
    return re.match(regex, domain) is not None

def is_valid_email(email):
    # Regular expression to validate email
    regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return re.match(regex, email) is not None

# local CA certificate management & VPN server certificate generation
def gen_certs_from_local_ca(ca_base_path, vpn_cert_path, router=None):
    router_ca_cert_path = f"{ROUTER_IPSEC_ROOT}/cacerts/ca.crt"
    router_ca_key_path  = f"{ROUTER_IPSEC_ROOT}/cacerts/ca.key"
    cert_manager = None
    ca_key_on_router = False

    # If the router already has a CA key, download and reuse it — no menu needed
    if router is not None:
        try:
            router.sftp_client.stat(router_ca_key_path)
            ca_key_on_router = True
        except Exception:
            pass

        if ca_key_on_router:
            print_step("", "Reusing Existing CA from Router")
            tmp_key = "/tmp/.ca_key_tmp"
            router.run_os_cmd(
                f"sudo cp {router_ca_key_path} {tmp_key} && sudo chmod 644 {tmp_key}",
                echo=False
            )
            ca_key_content  = router.download(tmp_key)
            router.run_os_cmd(f"sudo rm -f {tmp_key}", echo=False)
            ca_cert_content = router.download(router_ca_cert_path)

            if ca_key_content and ca_cert_content:
                ca_name = "router_ca"
                ca_path = os.path.join(ca_base_path, ca_name)
                os.makedirs(ca_path, exist_ok=True)
                with open(os.path.join(ca_path, "ca.key"), "w") as f:
                    f.write(ca_key_content)
                with open(os.path.join(ca_path, "ca.crt"), "w") as f:
                    f.write(ca_cert_content)
                cert_manager = CertManager(ca_name, ca_path, vpn_cert_path)
                print_ok(f"Router CA cached locally at {ca_path}")
            else:
                print_warn("Could not download CA from router — falling back to local CA selection")

    if cert_manager is None:
        # read existing CAs
        ca_directories = [" "]
        i=1
        options =[
            "[0] Return to the main menu",
        ]

        # Check for existing CA directories
        for d in os.listdir(ca_base_path):
            if os.path.isdir(os.path.join(ca_base_path, d)):
                options.append(f"[{i}] "+ d)
                ca_directories.append(d)
                i += 1

        options.append("-----------------------------")  # Separation line
        options.append(f"[{i}] Create a new CA (self-signed)")

        ca_menu = TerminalMenu(options, title="Choose a CA")
        ca_index = ca_menu.show()

        if ca_index == 0:
            return
        elif ca_index == i+1:
            print_step("", "Create New Self-Signed CA")
            ca_name         = input(f"  CA name [{Colors.GREEN}Creekside_CA{Colors.RESET}]: ") or "Creekside_CA"
            country         = input(f"  Country [{Colors.GREEN}US{Colors.RESET}]: ") or "US"
            state           = input(f"  State/Province [{Colors.GREEN}California{Colors.RESET}]: ") or "California"
            locality        = input(f"  Locality [{Colors.GREEN}San Jose{Colors.RESET}]: ") or "San Jose"
            organization    = input(f"  Organization [{Colors.GREEN}Creekside Networks LLC.{Colors.RESET}]: ") or "Creekside Networks LLC."
            common_name     = input(f"  Common Name [{Colors.GREEN}VPN CA{Colors.RESET}]: ") or "VPN CA"

            ca_path = os.path.join(ca_base_path, ca_name)
            cert_manager = CertManager(ca_name, ca_path, vpn_cert_path)
            cert_manager.create_self_signed_ca(country, state, locality, organization, common_name)
        else:
            selected_ca = ca_directories[ca_index]
            print_ok(f"Existing CA \"{selected_ca}\" selected")
            ca_path = os.path.join(ca_base_path, selected_ca)
            ca_cert_path = os.path.join(ca_path, "ca.crt")
            ca_key_path = os.path.join(ca_path, "ca.key")

            if not os.path.exists(ca_cert_path) or not os.path.exists(ca_key_path):
                print_error(f"CA files not found in {ca_path}")
                return

            cert_manager = CertManager(selected_ca, ca_path, vpn_cert_path)
            cert_manager.load_existing_ca(ca_cert_path, ca_key_path)

    # Get default VPN server name from DDNS or hostname
    default_vpn_name = "vpn.example.com"
    if router is not None:
        from vyatta.vyatta_config import VyattaConfig
        router_config = VyattaConfig()
        router_config.load(router)
        
        # Try to get DDNS hostname first
        interfaces = router_config.get("service dns dynamic interface")
        if interfaces:
            for interface in interfaces:
                ddns_service = router_config.get(f"service dns dynamic interface {interface} service")
                if ddns_service:
                    for service in ddns_service:
                        hostname = router_config.get(f"service dns dynamic interface {interface} service {service} host-name")
                        if hostname:
                            default_vpn_name = hostname
                            break
                    if default_vpn_name != "vpn.example.com":
                        break
        
        # If no DDNS, use router hostname + domain
        if default_vpn_name == "vpn.example.com":
            hostname = router_config.get("system host-name")
            domain = router_config.get("system domain-name")
            if hostname and domain:
                default_vpn_name = f"{hostname}.{domain}"

    print_step("", "Issue VPN Server Certificate")
    country     = input(f"  Country [{Colors.GREEN}US{Colors.RESET}]: ") or "US"
    state       = input(f"  State/Province [{Colors.GREEN}California{Colors.RESET}]: ") or "California"
    locality    = input(f"  Locality [{Colors.GREEN}San Jose{Colors.RESET}]: ") or "San Jose"
    organization= input(f"  Organization [{Colors.GREEN}Creekside Networks LLC.{Colors.RESET}]: ") or "Creekside Networks LLC."
    server_name = input(f"  VPN server name [{Colors.GREEN}{default_vpn_name}{Colors.RESET}]: ") or default_vpn_name

    # Initialize DNS names with the server name as the first entry
    dns_names = [server_name]

    # Prompt for up to 3 additional DNS names
    for i in range(3):
        dns_name = input(f"  Additional DNS name (Enter to skip): ")
        if dns_name:
            dns_names.append(dns_name)
        else:
            break

    # Get vpn server certificate path
    server_cert_root = os.path.join(vpn_cert_path, server_name)
    server_key_path  = os.path.join(server_cert_root, "server.key")
    server_cert_path = os.path.join(server_cert_root, "server.crt")
    server_pub_path  = os.path.join(server_cert_root, "server.pub")

    router_rsakey_path = f"{ROUTER_IPSEC_ROOT}/rsa-keys/localhost.key"
    router_rsapub_path = f"{ROUTER_IPSEC_ROOT}/rsa-keys/localhost.pub"

    if router is not None:
        # Check if localhost.key exists (may be root-owned — use sftp.stat on directory-accessible path)
        key_exists = False
        try:
            router.sftp_client.stat(router_rsakey_path)
            key_exists = True
        except Exception:
            key_exists = False

        if key_exists:
            # localhost.key is root:root 600 — copy to temp with readable perms, download, clean up
            print_step("", "Using Existing Router RSA Key")
            tmp_key = "/tmp/.ipsec_rsa_key_tmp"
            router.run_os_cmd(
                f"sudo cp {router_rsakey_path} {tmp_key} && sudo chmod 644 {tmp_key}",
                echo=False
            )
            key_content = router.download(tmp_key)
            router.run_os_cmd(f"sudo rm -f {tmp_key}", echo=False)

            if key_content:
                os.makedirs(os.path.dirname(server_key_path), exist_ok=True)
                with open(server_key_path, "w") as f:
                    f.write(key_content)
                print_ok(f"Router localhost.key downloaded to {server_key_path}")
            else:
                print_warn("Could not read localhost.key — generating a new key instead")
                key_exists = False
        else:
            print_info("No localhost.key found — a new RSA key will be generated and uploaded")

    # Issue the VPN server certificate (uses server_key_path if it exists locally)
    cert, key = cert_manager.issue_vpn_server_cert(server_name, dns_names, country, state, locality, organization)

    if router is not None:
        try:
            # Upload CA certificate and key (key stored at 600 for future cert re-issuance)
            router.upload(cert_manager.ca_cert_path, router_ca_cert_path, permission="0644")
            if not ca_key_on_router:
                router.upload(cert_manager.ca_key_path, router_ca_key_path, permission="0600")
                print_ok("CA key uploaded to cacerts/ca.key")

            # Upload server certificate (key stays in rsa-keys/, NOT duplicated to certs/)
            router.upload(server_cert_path, f"{ROUTER_IPSEC_ROOT}/certs/server.crt", permission="0644")

            # Upload key to rsa-keys/localhost.key only if it wasn't already there
            if not key_exists:
                router.upload(server_key_path, router_rsakey_path, permission="0600")
                print_ok("New RSA key uploaded to rsa-keys/localhost.key")

            # Always regenerate and upload the RFC3110 public key
            router.upload(server_pub_path, router_rsapub_path, permission="0644")

            print_ok("VPN certificates uploaded — CA: cacerts/ca.key+ca.crt, cert: certs/server.crt")
        except Exception as e:
            print_error(f"Failed to upload VPN certificates: {e}")

    return cert

# Generate VPN server certificates with Let's Encrypt
def gen_certs_with_lets_encrypt(router):
    print_step("", "Let's Encrypt Certificate Setup")
    domain = input(f"  VPN server domain [{Colors.GREEN}vpn.example.com{Colors.RESET}]: ") or "vpn.example.com"

    # Validate domain
    while not validators.domain(domain):
        print_warn(f"Invalid domain name \"{domain}\". Please try again.")
        domain = input(f"  VPN server domain [{Colors.GREEN}vpn.example.com{Colors.RESET}]: ") or "vpn.example.com"

    # Define paths
    local_cert_path             = os.path.join(CERTS_BASE_PATH, "server", domain)
    acme_cache_path             = os.path.join(CERTS_BASE_PATH, "acme")
    remote_acme_script_path     = os.path.join(ROUTER_ACME_ROOT, "scripts", "acme.sh")
    remote_dns_cf_script_path   = os.path.join(ROUTER_ACME_ROOT, "scripts", "dnsapi", "dns_cf.sh")
    remote_acme_home            = os.path.join(ROUTER_ACME_ROOT, "home")
    
    if not os.path.isdir(local_cert_path):
        os.makedirs(local_cert_path)
    if not os.path.isdir(acme_cache_path):
        os.makedirs(acme_cache_path)

    # Load or create Cloudflare configuration
    cloudflare_conf_path = os.path.join(acme_cache_path, ".cloudflare.conf")
    config = configparser.ConfigParser()
    if os.path.isfile(cloudflare_conf_path):
        config.read(cloudflare_conf_path)

    # Extract the base domain
    base_domain = '.'.join(domain.split('.')[-2:])
    cf_email    = ""
    cf_api_key  = ""
    # Check if the base domain exists in the config
    if base_domain in config:
        cf_email = config[base_domain]['CF_Email']
        cf_api_key = config[base_domain]['CF_Key']
        print_ok(f"Found Cloudflare credentials for \"{base_domain}\"")
        with open(cloudflare_conf_path, 'w') as configfile:
            config.write(configfile)

    # Prompt for Cloudflare credentials
    print_step("", "Cloudflare API Configuration")
    cf_email    = input(f"  Cloudflare email [{Colors.GREEN}{cf_email}{Colors.RESET}]: ") or cf_email

    # Validate email
    while not validators.email(cf_email):
        print_warn("Invalid email address. Please try again.")
        cf_email    = input(f"  Cloudflare email [{Colors.GREEN}{cf_email}{Colors.RESET}]: ") or cf_email

    cf_api_key  = input(f"  Cloudflare global API key [{Colors.GREEN}{cf_api_key}{Colors.RESET}]: ") or cf_api_key   

    # Update the config
    config[base_domain] = {
        'CF_Email': cf_email,
        'CF_Key': cf_api_key
    }

    # Save Cloudflare credentials to a configuration file
    with open(cloudflare_conf_path, "w") as cf_conf:
        config.write(cf_conf)

    # Check if acme.sh is cached locally
    acme_script_path = os.path.join(acme_cache_path, "acme.sh")
    if not os.path.isfile(acme_script_path):
        print_info("Downloading acme.sh script...")
        subprocess.run(["curl", "-#o", acme_script_path, "https://raw.githubusercontent.com/acmesh-official/acme.sh/master/acme.sh"])
        #subprocess.run(["chmod", "+x", acme_script_path])

        # Use sed to replace the curl command in acme.sh
        subprocess.run(["sed", "-i", "", "s/curl --silent --dump-header \\$HTTP_HEADER/curl -2 --silent --dump-header \\$HTTP_HEADER/g", acme_script_path])

    # Upload acme.sh to the remote router
    router.upload(acme_script_path, remote_acme_script_path, echo=True)

    # Check if dns_cf.sh is cached, if not, download and cache it
    dns_cf_script_path = os.path.join(acme_cache_path, "dns_cf.sh")
    if not os.path.isfile(dns_cf_script_path):
        print_info("Downloading dns_cf.sh script...")
        subprocess.run(["curl", "-#o", dns_cf_script_path, "https://raw.githubusercontent.com/acmesh-official/acme.sh/master/dnsapi/dns_cf.sh"])
        #subprocess.run(["chmod", "+x", dns_cf_script_path])

    # Upload dns_cf.sh to the remote router
    router.upload(dns_cf_script_path, remote_dns_cf_script_path, echo=True)


    # Execute the issue command on the remote router
    print_step("", "Requesting Let's Encrypt Certificate")
    issue_command = f"""
    export CF_Email='{cf_email}'
    export CF_Key='{cf_api_key}'
    sudo -E {remote_acme_script_path} --issue -m {cf_email} --dns dns_cf -d {domain} --accountemail {cf_email} --home {remote_acme_home}
    """

    issue_output, issue_error = router.run_os_cmd(issue_command, echo=True)

    if issue_error and "error code: 60" not in issue_error:
        print (f"\n\n{issue_error}\n\n")
        raise Exception("Error issuing certificate with acme.sh")

    # Execute the install command on the remote router if the issue command was successful
    router.run_os_cmd("sudo mkdir -p /config/ipsec.d/{cacerts,certs}")
    install_command = f"""
    sudo {remote_acme_script_path} --install-cert -d {domain} --key-file /config/ipsec.d/certs/server.key --fullchain-file /config/ipsec.d/certs/server.crt --ca-file /config/ipsec.d/cacerts/ca.crt --home {remote_acme_home}
    """

    install_output, install_error = router.run_os_cmd(install_command, echo=True)

    if install_error:
        raise Exception("Error installing certificate with acme.sh")

    print_ok("VPN certificates and CA certificate generated and uploaded successfully")

    # Download the server certificate and return
    certs = router.download("/config/ipsec.d/certs/server.crt")
    cert = x509.load_pem_x509_certificate(certs.encode('utf-8'))
    return cert

# Certificate management menu
def certs_mananger (router):
    ca_base_path = os.path.expanduser(f"{CERTS_BASE_PATH}/ca")
    vpn_cert_path = os.path.expanduser(f"{CERTS_BASE_PATH}/server")
    os.makedirs(ca_base_path, exist_ok=True)
    os.makedirs(vpn_cert_path, exist_ok=True)

    title = "\n  o Certificate Management Menu"
    options = [
        "[0] Exit",
        "[1] Generate VPN server certs with a local CA",
        "[2] Generate VPN server certs with Let's Encrypt",
    ]

    terminal_menu = TerminalMenu(options, title=title)
    menu_entry_index = terminal_menu.show()

    match menu_entry_index:
        case 0:
            cert = None
        case 1:
            cert = gen_certs_from_local_ca(ca_base_path, vpn_cert_path, router)
        case 2:
            cert = gen_certs_with_lets_encrypt(router)
        case _:
            print("\n  *** This feature is not implemented yet")

    return cert

if __name__ == "__main__":
    certs_mananger()