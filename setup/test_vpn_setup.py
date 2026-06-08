#!/usr/bin/env python3
"""
Non-interactive integration test for the IKEv2 VPN setup flow.
Exercises: router connection, cert generation, ipsec.conf generation,
freeradius-utils install, and config upload.

Usage:
    venv/bin/python3 test_vpn_setup.py [ubnt@]<host> [-p <port>]
"""

import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(__file__))

from vyatta.vyatta_router    import VyattaRouter
from vyatta.vyatta_config    import VyattaConfig
from update.router_id        import get_router_id
from vpn.certs_manager       import CertManager, CERTS_BASE_PATH, ROUTER_IPSEC_ROOT
from vpn.ipsec_config        import IPSecConfig, DEFAULT_IPSEC_CONF
from vpn.ipsec_secrets       import IPSecSecrets
from vpn.strongswan_config   import StrongswanConfig
from vpn.roadwarrior         import (_install_freeradius_utils, _install_strongswan_plugin_hook,
                                      _install_radius_users, ROUTER_RADIUS_USERS_PATH,
                                      FREERADIUS_USERS_LINK_PATH)
from utility.ux              import (print_header, print_step, print_ok,
                                     print_error, print_info, print_warn, Colors)

PASS = f"  {Colors.GREEN}PASS{Colors.RESET}"
FAIL = f"  {Colors.RED}FAIL{Colors.RESET}"

ROUTER_IPSEC_ROOT_PATH    = "/config/ipsec.d"
ROUTER_IPSEC_CONF_PATH    = os.path.join(ROUTER_IPSEC_ROOT_PATH, "ipsec.conf")
ROUTER_IPSEC_SECRETS_PATH = os.path.join(ROUTER_IPSEC_ROOT_PATH, "ipsec.secrets")
CHARON_CONF_PATH          = os.path.join(ROUTER_IPSEC_ROOT_PATH, "charon_roadwarrior.conf")


def check(label, condition, detail=""):
    if condition:
        print(f"{PASS}  {label}" + (f"  ({detail})" if detail else ""))
    else:
        print(f"{FAIL}  {label}" + (f"  — {detail}" if detail else ""))
    return condition


def run_tests(hostname, username, password, port):
    results = []

    # ── 1. Router connection ──────────────────────────────────────────────────
    print_step("1", "Router Connection")
    try:
        router = VyattaRouter(hostname=hostname, username=username,
                              password=password, port=port)
        results.append(check("SSH connected", router.is_connected))
        results.append(check("Hardware detected", bool(router.hardware),
                             detail=router.hardware))
        results.append(check("Firmware detected", bool(router.firmware),
                             detail=router.firmware))
        results.append(check("Model", bool(router.model), detail=router.model))
    except Exception as e:
        print_error(f"Connection failed: {e}")
        return

    # ── 2. VyattaConfig / router_id ──────────────────────────────────────────
    print_step("2", "VyattaConfig & Router ID")
    try:
        vcfg = VyattaConfig()
        vcfg.load(router)
        router_id = get_router_id(vcfg)
        results.append(check("VyattaConfig loaded", vcfg.config_dict is not None))
        results.append(check("Router ID", True, detail=str(router_id)))
    except Exception as e:
        print_error(f"VyattaConfig failed: {e}")
        results.append(False)

    # ── 3. Cert generation using router's localhost.key + upload to router ──────
    print_step("3", "Cert Generation (router RSA key) + Upload")
    test_ca_dir   = tempfile.mkdtemp(prefix="test_ca_")
    test_cert_dir = tempfile.mkdtemp(prefix="test_certs_")
    server_name   = "vpn.test.local"
    try:
        # --- Download router's localhost.key via sudo (root-owned 600) ---
        rsakey_remote = "/config/ipsec.d/rsa-keys/localhost.key"
        server_dir     = os.path.join(test_cert_dir, server_name)
        os.makedirs(server_dir, exist_ok=True)
        server_key_local = os.path.join(server_dir, "server.key")

        tmp_remote = "/tmp/.test_rsa_dl_tmp"
        router.run_os_cmd(
            f"sudo cp {rsakey_remote} {tmp_remote} && sudo chmod 644 {tmp_remote}",
            echo=False
        )
        key_pem = router.download(tmp_remote)
        router.run_os_cmd(f"sudo rm -f {tmp_remote}", echo=False)
        results.append(check("Router localhost.key downloaded", bool(key_pem and "BEGIN" in key_pem)))
        with open(server_key_local, "w") as f:
            f.write(key_pem)

        # --- Create local CA and issue cert for the router's key ---
        mgr = CertManager("TestCA", test_ca_dir, test_cert_dir)
        mgr.create_self_signed_ca("US", "California", "San Jose",
                                   "Test Org", "Test VPN CA")
        results.append(check("CA cert created",
                             os.path.exists(os.path.join(test_ca_dir, "ca.crt"))))

        cert, key = mgr.issue_vpn_server_cert(
            server_name, [server_name],
            "US", "California", "San Jose", "Test Org"
        )
        server_cert_local = os.path.join(server_dir, "server.crt")
        server_pub_local  = os.path.join(server_dir, "server.pub")
        results.append(check("Server cert issued",   os.path.exists(server_cert_local)))
        results.append(check("RFC3110 pub generated", os.path.exists(server_pub_local)))

        # --- Upload CA cert+key, server cert, and RFC3110 pub key to router ---
        router.upload(mgr.ca_cert_path,    "/config/ipsec.d/cacerts/ca.crt",         permission="0644")
        router.upload(mgr.ca_key_path,     "/config/ipsec.d/cacerts/ca.key",          permission="0600")
        router.upload(server_cert_local,    "/config/ipsec.d/certs/server.crt",        permission="0644")
        router.upload(server_pub_local,     "/config/ipsec.d/rsa-keys/localhost.pub",  permission="0644")

        # --- Verify all files are present and non-empty on router ---
        ca_back   = router.download("/config/ipsec.d/cacerts/ca.crt")
        cert_back = router.download("/config/ipsec.d/certs/server.crt")
        pub_back  = router.download("/config/ipsec.d/rsa-keys/localhost.pub")

        results.append(check("cacerts/ca.crt on router",
                             bool(ca_back and "BEGIN CERTIFICATE" in ca_back)))
        results.append(check("certs/server.crt on router",
                             bool(cert_back and "BEGIN CERTIFICATE" in cert_back)))
        results.append(check("rsa-keys/localhost.pub on router",
                             bool(pub_back and pub_back.strip().startswith("0s"))))
        results.append(check("server.key NOT in certs/ (stays in rsa-keys/)",
                             router.download("/config/ipsec.d/certs/server.key") is None))

        # --- Verify ca.key is on router (root-owned 600 — check via sftp.stat) ---
        ca_key_stat_ok = False
        try:
            router.sftp_client.stat("/config/ipsec.d/cacerts/ca.key")
            ca_key_stat_ok = True
        except Exception:
            pass
        results.append(check("cacerts/ca.key on router", ca_key_stat_ok))

        # --- Second run: verify router CA key is reused (not regenerated) ---
        tmp_ca2   = tempfile.mkdtemp(prefix="test_ca2_")
        tmp_cert2 = tempfile.mkdtemp(prefix="test_certs2_")
        try:
            ca_key_content2 = None
            tmp_rk = "/tmp/.ca_key_tmp2"
            router.run_os_cmd(
                f"sudo cp /config/ipsec.d/cacerts/ca.key {tmp_rk} && sudo chmod 644 {tmp_rk}",
                echo=False
            )
            ca_key_content2 = router.download(tmp_rk)
            router.run_os_cmd(f"sudo rm -f {tmp_rk}", echo=False)
            results.append(check("cacerts/ca.key readable via sudo",
                                 bool(ca_key_content2 and "BEGIN" in ca_key_content2)))
        finally:
            shutil.rmtree(tmp_ca2,   ignore_errors=True)
            shutil.rmtree(tmp_cert2, ignore_errors=True)

    except Exception as e:
        print_error(f"Cert generation/upload failed: {e}")
        results.append(False)
    finally:
        shutil.rmtree(test_ca_dir,   ignore_errors=True)
        shutil.rmtree(test_cert_dir, ignore_errors=True)

    # ── 4. IPSec config generation ────────────────────────────────────────────
    print_step("4", "IPSec Config Generation")
    try:
        cfg = IPSecConfig()
        cfg.loads(DEFAULT_IPSEC_CONF)
        results.append(check("DEFAULT_IPSEC_CONF has eap-radius",
                             cfg.get_conn_parameter("rightauth", "%default") == "eap-radius",
                             detail=cfg.get_conn_parameter("rightauth", "%default")))

        # Simulate two class-group connections + fallback
        new_cfg = IPSecConfig()
        new_cfg.set_conn_parameter('rightauth',  'eap-radius',     '%default')
        new_cfg.set_conn_parameter('leftsubnet', '0.0.0.0/0',       '%default')
        new_cfg.set_conn_parameter('leftid',     '@vpn.test.local', '%default')
        new_cfg.set_conn_parameter('auto',       'ignore',          '%default')

        for conn_def in [
            ('class_a', 'class_a', '192.168.88.1/24', '8.8.8.8'),
            ('class_b', 'class_b', '192.168.89.1/24', '8.8.8.8'),
            ('fallback', '-',       '10.99.240.1/24',  '8.8.8.8'),
        ]:
            name, groups, srcip, dns = conn_def
            new_cfg.set_conn_parameter('also',          '%default', name)
            new_cfg.set_conn_parameter('rightsourceip', srcip,      name)
            new_cfg.set_conn_parameter('rightdns',      dns,        name)
            new_cfg.set_conn_parameter('auto',          'add',      name)
            if groups != '-':
                new_cfg.set_conn_parameter('rightgroups', groups, name)

        dumped = new_cfg.dumps()
        results.append(check("ipsec.conf has class_a",   'conn class_a' in dumped))
        results.append(check("ipsec.conf has class_b",   'conn class_b' in dumped))
        results.append(check("ipsec.conf has fallback",  'conn fallback' in dumped))
        results.append(check("class_a rightgroups",      'rightgroups = class_a' in dumped))
        results.append(check("class_b rightgroups",      'rightgroups = class_b' in dumped))
        results.append(check("192.168.88 pool",          '192.168.88.1/24' in dumped))
        results.append(check("192.168.89 pool",          '192.168.89.1/24' in dumped))
    except Exception as e:
        print_error(f"IPSec config generation failed: {e}")
        results.append(False)

    # ── 5. StrongswanConfig / RADIUS config ───────────────────────────────────
    print_step("5", "StrongSwan RADIUS Config")
    try:
        # Combined charon config (DHCP identity_lease + eap-radius) — mirrors roadwarrior.py eap-radius branch
        rcfg = StrongswanConfig(config_str="")
        rcfg.set("charon load_modular", "yes")
        rcfg.set("charon plugins dhcp identity_lease", "yes")
        rcfg.set("charon plugins eap-radius class_group", "yes")
        rcfg.set("charon plugins eap-radius servers", "radius_server")
        rcfg.set("charon plugins eap-radius servers radius_server address", "192.168.1.1")
        rcfg.set("charon plugins eap-radius servers radius_server secret", "testing123")
        rdump = rcfg.dumps(rcfg.config)
        results.append(check("identity_lease in combined dump", "identity_lease = yes" in rdump))
        results.append(check("class_group = yes in combined dump", "class_group = yes" in rdump))
        results.append(check("RADIUS address in combined dump",    "192.168.1.1" in rdump))
    except Exception as e:
        print_error(f"RADIUS config failed: {e}")
        results.append(False)

    # ── 6. freeradius-utils installation ─────────────────────────────────────
    print_step("6", "freeradius-utils Installation")
    try:
        _install_freeradius_utils(router)
        out, _ = router.run_os_cmd("which radtest 2>/dev/null")
        results.append(check("radtest binary present",
                             bool(out and "radtest" in out), detail=out.strip()[:60]))
    except Exception as e:
        print_error(f"freeradius-utils install failed: {e}")
        results.append(False)

    # ── 7. Router RSA key handling ────────────────────────────────────────────
    print_step("7", "Router RSA Key (localhost.key)")
    rsakey_path = "/config/ipsec.d/rsa-keys/localhost.key"
    rsapub_path = "/config/ipsec.d/rsa-keys/localhost.pub"
    try:
        # Check existence via sftp.stat (works even for root-owned 600 files)
        try:
            router.sftp_client.stat(rsakey_path)
            key_exists = True
        except Exception:
            key_exists = False

        results.append(check("localhost.key exists on router", key_exists,
                             detail="pre-generated by 'generate vpn rsa-key'" if key_exists else "will be generated"))

        if key_exists:
            # Read via sudo temp copy
            tmp_key = "/tmp/.test_rsa_key_tmp"
            router.run_os_cmd(f"sudo cp {rsakey_path} {tmp_key} && sudo chmod 644 {tmp_key}", echo=False)
            key_content = router.download(tmp_key)
            router.run_os_cmd(f"sudo rm -f {tmp_key}", echo=False)
            results.append(check("localhost.key readable via sudo", bool(key_content and len(key_content) > 100)))
            results.append(check("localhost.key is PEM format",
                                 bool(key_content and "BEGIN" in key_content),
                                 detail=key_content[:27].strip() if key_content else ""))

            # Load the key — supports both PKCS#8 (BEGIN PRIVATE KEY) and PKCS#1 (BEGIN RSA PRIVATE KEY)
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            loaded_key = load_pem_private_key(key_content.encode(), password=None)
            results.append(check("localhost.key loads as RSA key",
                                 bool(loaded_key), detail=f"{loaded_key.key_size} bits"))

            # Generate RFC3110 pub key from loaded key (same as cert_manager.rsa_rfc3110)
            import base64, struct
            pub = loaded_key.public_key().public_numbers()
            e_bytes = pub.e.to_bytes((pub.e.bit_length() + 7) // 8, 'big')
            n_bytes = pub.n.to_bytes((pub.n.bit_length() + 7) // 8, 'big')
            rfc3110 = "0s" + base64.b64encode(
                struct.pack(f'B{len(e_bytes)}s{len(n_bytes)}s', len(e_bytes), e_bytes, n_bytes)
            ).decode()
            results.append(check("RFC3110 pub key generated", rfc3110.startswith("0s")))

    except Exception as e:
        print_error(f"RSA key test failed: {e}")
        results.append(False)

    # ── 8. Config upload + ipsec.secrets references rsa-keys/ ────────────────
    print_step("8", "Config Upload to Router")
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as tmp:
            tmp.write(dumped)
            tmp_path = tmp.name
        router.upload(tmp_path, ROUTER_IPSEC_CONF_PATH, echo=True)
        os.unlink(tmp_path)

        # ipsec.secrets must reference rsa-keys/localhost.key (not certs/server.key)
        secrets = IPSecSecrets()
        secrets.secrets['RSA'] = ['/config/ipsec.d/rsa-keys/localhost.key']
        secrets_dump = secrets.dumps()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.secrets', delete=False) as tmp:
            tmp.write(secrets_dump)
            tmp_path = tmp.name
        router.upload(tmp_path, ROUTER_IPSEC_SECRETS_PATH, echo=True)
        os.unlink(tmp_path)

        # Combined charon plugin config (DHCP + eap-radius in one file)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as tmp:
            tmp.write(rdump)   # rdump already has DHCP + RADIUS merged via StrongswanConfig
            tmp_path = tmp.name
        router.upload(tmp_path, CHARON_CONF_PATH, echo=True)
        os.unlink(tmp_path)

        conf_back   = router.download(ROUTER_IPSEC_CONF_PATH)
        sec_back    = router.download(ROUTER_IPSEC_SECRETS_PATH)
        charon_back = router.download(CHARON_CONF_PATH)
        results.append(check("ipsec.conf on router",
                             conf_back is not None and 'class_a' in conf_back))
        results.append(check("ipsec.secrets references rsa-keys/",
                             sec_back is not None and 'rsa-keys/localhost.key' in sec_back,
                             detail=sec_back.strip()[:60] if sec_back else ""))
        results.append(check("charon_roadwarrior.conf on router",
                             charon_back is not None))
        results.append(check("charon_roadwarrior.conf has class_group",
                             charon_back is not None and 'class_group' in charon_back))
        results.append(check("charon_roadwarrior.conf has identity_lease",
                             charon_back is not None and 'identity_lease' in charon_back))
        results.append(check("ipsec.secrets NOT referencing certs/server.key",
                             sec_back is not None and 'certs/server.key' not in sec_back))
    except Exception as e:
        print_error(f"Upload failed: {e}")
        results.append(False)

    # ── 9. Persistent post-config.d boot hook ────────────────────────────────
    print_step("9", "Persistent strongSwan Plugin Boot Hook")
    try:
        _install_strongswan_plugin_hook(router, CHARON_CONF_PATH)
        hook_path = "/config/scripts/post-config.d/ipsec-plugin-symlinks.sh"
        hook_content = router.download(hook_path)
        results.append(check("boot hook script created",
                             bool(hook_content), detail=hook_path))
        results.append(check("hook references charon_roadwarrior.conf",
                             bool(hook_content and "charon_roadwarrior" in hook_content)))

        # Verify /etc/strongswan.d/ symlink was created immediately
        out, _ = router.run_os_cmd("ls -la /etc/strongswan.d/charon_roadwarrior.conf 2>/dev/null")
        results.append(check("/etc/strongswan.d/charon_roadwarrior.conf symlink active",
                             bool(out and "charon_roadwarrior" in out), detail=out.strip()[:80]))
    except Exception as e:
        print_error(f"Boot hook test failed: {e}")
        results.append(False)

    # ── 10. FreeRADIUS users file ─────────────────────────────────────────────
    print_step("10", "FreeRADIUS Users File")
    try:
        _install_radius_users(router)
        users_content = router.download(ROUTER_RADIUS_USERS_PATH)
        results.append(check("radius_users on router",
                             bool(users_content and len(users_content) > 50),
                             detail=ROUTER_RADIUS_USERS_PATH))
        results.append(check("radius_users has class_a entry",
                             bool(users_content and 'class_a' in users_content)))
        results.append(check("radius_users has class_b entry",
                             bool(users_content and 'class_b' in users_content)))
        out, _ = router.run_os_cmd(f"ls -la {FREERADIUS_USERS_LINK_PATH} 2>/dev/null")
        results.append(check("freeradius/3.0/users symlink active",
                             bool(out and 'radius_users' in out), detail=out.strip()[:80]))
        results.append(check("boot hook includes freeradius symlink",
                             bool(hook_content and 'radius_users' in hook_content)))
    except Exception as e:
        print_error(f"FreeRADIUS users file test failed: {e}")
        results.append(False)

    # ── 11. radeapclient binary check ─────────────────────────────────────────
    print_step("11", "radeapclient binary check")
    try:
        out, _ = router.run_os_cmd("which radeapclient 2>/dev/null")
        results.append(check("radeapclient binary present",
                             bool(out and "radeapclient" in out), detail=out.strip()[:60]))
    except Exception as e:
        print_error(f"radeapclient check failed: {e}")
        results.append(False)

    # ── Summary ───────────────────────────────────────────────────────────────
    passed = sum(1 for r in results if r is True)
    total  = len(results)
    print()
    print(f"{'═'*60}")
    status = Colors.GREEN if passed == total else Colors.YELLOW
    print(f"  {status}Results: {passed}/{total} passed{Colors.RESET}")
    print(f"{'═'*60}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('hostname')
    parser.add_argument('-p', '--port', type=int, default=22)
    args = parser.parse_args()

    if '@' in args.hostname:
        username, hostname = args.hostname.split('@', 1)
    else:
        username, hostname = None, args.hostname

    password = "ubnt" if username == "ubnt" else None

    print_header("VPN Setup Integration Test", width=60)
    run_tests(hostname, username, password, args.port)
