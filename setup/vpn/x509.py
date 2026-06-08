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

from    cryptography import x509
from    cryptography.x509.oid import ExtensionOID
from    cryptography.hazmat.primitives import serialization, hashes
from    cryptography.hazmat.primitives.asymmetric import rsa
from    cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from    cryptography.hazmat.backends import default_backend
from    cryptography.hazmat.primitives.asymmetric import rsa as rsa_x509
import  base64
import  datetime
import  ipaddress
import  struct


def gen_ca(ca_path, common_name, issuer_name=None, days=3650):
    # Generate a new private key
    ca_private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    ca_cname = common_name
    # Create a self-signed certificate
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, ca_cname),
    ])

    if issuer_name is None:
        issuer  = subject
    else:
        issuer  = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, issuer_name),
    ])
        
    ca_certificate = x509.CertificateBuilder().subject_name(
        subject
        ).issuer_name(
            issuer
        ).public_key(
            ca_private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.datetime.utcnow()
        ).not_valid_after(
            datetime.datetime.utcnow() + datetime.timedelta(days=days)
        ).add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        ).add_extension(x509.KeyUsage( 
                digital_signature=True, 
                content_commitment=False, 
                key_encipherment=False, 
                data_encipherment=False, 
                key_agreement=False, 
                key_cert_sign=True, 
                crl_sign=True, 
                encipher_only=False, 
                decipher_only=False), 
            critical=True
        ).sign(ca_private_key, hashes.SHA256())

    # Serialize the private key and certificate
    key_bytes = ca_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    cert_bytes = ca_certificate.public_bytes(serialization.Encoding.PEM)
    # Write the private key and certificate to files
    with open(f"{ca_path}/ca.key", 'wb') as f:
        f.write(key_bytes)
    with open(f"{ca_path}/ca.crt", 'wb') as f:
        f.write(cert_bytes)

"""
    description:
        generate a 2048bits RSA key 
    return:
        private key in PEM format
"""
def gen_rsa_key():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )    

    # Serialize the private key and certificate
    key_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    return key_bytes

"""
    description:
        generate a server ertifcate by given CA
        if private key is not give (by default), it will generate one
    return:
        private key and certificate in PEM format
"""
def gen_certificate(ca_path, dns_names, ip_addresses=[], private_key_pem=None, valid_days=3650):
    # Load the CA key and certificate from files
    try:
        with open(f"{ca_path}/ca.key", 'rb') as f:
            ca_private_key = serialization.load_pem_private_key(
                f.read(),
                password=None,
            )
    except FileNotFoundError:
        print("File not found error:", f"{ca_path}/ca.key")
    except Exception as e:
        print("Error: ", e)

    try:
        with open(f"{ca_path}/ca.crt", 'rb') as f:
            ca_certificate = x509.load_pem_x509_certificate(f.read())
    except FileNotFoundError:
        print("File not found error:", f"{ca_path}/ca.crt")
    except Exception as e:
        print("Error: ", e)

    # Generate a new private key
    if private_key_pem is None:
        print("*** generate private key")
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
    else:
        print("*** load private key")
        print(private_key_pem.decode())
        private_key = serialization.load_pem_private_key(
            private_key_pem,
            password=None,
        )

    subjects = []
    for dns in dns_names:
        if (dns == "" or dns == "-"):
            break
        else:
            subjects.append(x509.DNSName(dns))
    for ip_address in ip_addresses:
        if (ip_address == "" or ip_address == "-"):
            break
        else:
            subjects.append(x509.IPAddress(ipaddress.ip_address(ip_address)))

    # Create a certificate signing request (CSR)
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, dns_names[0])
        ])
        ).add_extension( 
            x509.SubjectAlternativeName(subjects), 
            critical=False,
        ).sign(private_key, hashes.SHA256())

    # Issue the server certificate from the CA
    cert_builder = x509.CertificateBuilder().subject_name(
        csr.subject
        ).issuer_name(
            ca_certificate.subject
        ).public_key(
            csr.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.datetime.utcnow()
        ).not_valid_after(
            datetime.datetime.utcnow() + datetime.timedelta(days=valid_days)
        ).add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        ).add_extension(
            x509.SubjectAlternativeName(subjects),
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
        )
    
    server_certificate = cert_builder.sign(
        private_key=ca_private_key,
        algorithm=hashes.SHA256(),
        backend=default_backend(),
    )

    # Serialize the private key and certificate
    key_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    cert_bytes = server_certificate.public_bytes(serialization.Encoding.PEM)

    return key_bytes, cert_bytes

"""
    description:
        convert PEM rsa public key to RFC3110 format
"""
def rsa_rfc3110(private_key_pem):

    # Parse the PEM data and extract the RSA private key
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    public_key  = private_key.public_key()

    # Extract the public key components
    n = public_key.public_numbers().n
    e = public_key.public_numbers().e

    # Construct the RFC3110 public key in base64 format
    e_bytes = e.to_bytes((e.bit_length() + 7) // 8, 'big')
    n_bytes = n.to_bytes((n.bit_length() + 7) // 8, 'big')
    len_e = len(e_bytes)
    len_n = len(n_bytes)
    rfc3110_key = f"0s" + base64.b64encode(struct.pack(f'1s{len_e}s{len_n}s', len_e.to_bytes(1,'big'), e_bytes, n_bytes)).decode()

    # Print the RFC3110 public key
    return rfc3110_key


def print_crt(cert_data, title="certificate summary", indent = 4):

    indent_spaces = ' '*indent
    print(indent_spaces + "------------------------------------------------------------")
    print(indent_spaces + title)
    print(indent_spaces + "------------------------------------------------------------")

    # Load the X.509 certificate from 
    x509_cert = x509.load_pem_x509_certificate(cert_data)

    # Print the subject name
    print(indent_spaces+"Subject:       ", x509_cert.subject.rfc4514_string())

    # Print the issuer name
    print(indent_spaces+"Issuer:        ", x509_cert.issuer.rfc4514_string())

    # Print the serial number
    print(indent_spaces+"Serial number: ", x509_cert.serial_number)

    # Print the validity period
    print(indent_spaces+"Valid from:    ", x509_cert.not_valid_before)
    print(indent_spaces+"Valid until:   ", x509_cert.not_valid_after)

    # Print the subject alternative names
    ext = x509_cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    san = ext.value
    print(indent_spaces+"Subject alternative names:")
    for name in san:
        if isinstance(name, x509.DNSName):
            print(indent_spaces+"  DNS Name:    ", name.value)
        elif isinstance(name, x509.IPAddress):
            print(indent_spaces+"  IP Address:  ", name.value)
    # Print the public key details
    pub_key = x509_cert.public_key()
    pub_key_details = pub_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    print(indent_spaces + "------------------------------------------------------------")
    