#!/usr/bin/env python
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

import sys
import requests
from packaging import version
from utility.ux import (Colors, print_header, print_subtitle,
                        print_ok, print_error, print_info, print_warn, print_dim)
from utility.confirm import get_confirmation


# Ubiquiti firmware update API
UBNT_FW_API_URL = "https://fw-update.ubnt.com/api/firmware-latest"
VYATTA_OP_CMD_WRAPPER = "/opt/vyatta/bin/vyatta-op-cmd-wrapper"

def get_product_name(router):
    """
    Extract product name from router hardware info.
    e.g., "e300" from "ER-e300"
    """
    if router.hardware:
        # Hardware is like "e300", "e50", "e200", etc.
        return router.hardware.lower()
    return None


def parse_firmware_version(firmware_str):
    """
    Parse firmware version string like "v2.0.9" or "v2.0.9-hotfix.1" to comparable version.
    Returns the version string without the 'v' prefix.
    """
    if firmware_str and firmware_str.startswith('v'):
        return firmware_str[1:]
    return firmware_str


def get_latest_firmware(product, channel="release"):
    """
    Fetch the latest firmware info from Ubiquiti API.
    
    Args:
        product: Product name (e.g., "e300")
        channel: "release" or "public-beta"
    
    Returns:
        dict with version, url, md5 or None if failed
    """
    try:
        params = {
            "filter": [
                f"eq~~platform~~edgerouter",
                f"eq~~channel~~{channel}",
                f"eq~~product~~{product}"
            ]
        }
        
        response = requests.get(UBNT_FW_API_URL, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Parse the response
        firmware_list = data.get("_embedded", {}).get("firmware", [])
        if not firmware_list:
            return None
        
        fw = firmware_list[0]
        return {
            "version": fw.get("version"),
            "url": fw.get("_links", {}).get("data", {}).get("href"),
            "md5": fw.get("md5")
        }
    except Exception as e:
        print_error(f"Failed to fetch firmware info: {e}")
        return None


def check_firmware_status(router):
    """
    Check firmware status for the router.
    
    Returns:
        dict with:
            - current_version: Current firmware version
            - latest_version: Latest available version (or None)
            - needs_upgrade: True if upgrade is needed
            - is_legacy: True if firmware is 1.x or 2.x
            - upgrade_url: URL to download firmware (or None)
            - error: Error message if any
    """
    result = {
        "current_version": router.firmware,
        "latest_version": None,
        "needs_upgrade": False,
        "is_legacy": False,
        "upgrade_url": None,
        "md5": None,
        "error": None
    }
    
    # Check if this is an EdgeRouter
    if not router.hardware:
        result["error"] = "Not an EdgeRouter device"
        return result
    
    # Parse current version
    current = parse_firmware_version(router.firmware)
    if not current:
        result["error"] = "Unable to parse current firmware version"
        return result
    
    # Check if firmware is 1.x or 2.x (legacy)
    try:
        ver = version.parse(current)
        major_version = ver.major if hasattr(ver, 'major') else int(current.split('.')[0])
        result["is_legacy"] = major_version <= 2
    except Exception:
        # Try simple parsing
        try:
            major_version = int(current.split('.')[0])
            result["is_legacy"] = major_version <= 2
        except Exception:
            result["error"] = "Unable to determine firmware version"
            return result
    
    # Get product name
    product = get_product_name(router)
    if not product:
        result["error"] = "Unable to determine product name"
        return result
    
    # Fetch latest firmware
    latest = get_latest_firmware(product)
    if not latest:
        result["error"] = "Unable to fetch latest firmware info"
        return result
    
    result["latest_version"] = latest["version"]
    result["upgrade_url"] = latest["url"]
    result["md5"] = latest["md5"]
    
    # Compare versions
    latest_ver = parse_firmware_version(latest["version"])
    try:
        if version.parse(latest_ver) > version.parse(current):
            result["needs_upgrade"] = True
    except Exception:
        # Simple string comparison fallback
        if latest_ver != current:
            result["needs_upgrade"] = True
    
    return result


def firmware_upgrade(router):
    """
    Perform firmware upgrade on the router.
    """
    print_header("Firmware Upgrade", width=60)
    print_subtitle("EdgeRouter Firmware Update")
    print()
    
    # Check firmware status
    print_info("Checking current firmware status...")
    status = check_firmware_status(router)
    
    if status["error"]:
        print_error(status["error"])
        return False
    
    print_info(f"Current Version : {status['current_version']}")
    print_info(f"Latest Version  : {status['latest_version']}")
    print()
    
    if not status["needs_upgrade"]:
        print_ok("Firmware is already up to date!")
        return True
    
    print_warn(f"Firmware upgrade available: {status['current_version']} → {status['latest_version']}")
    print()
    
    # Confirm upgrade
    if not get_confirmation("Do you want to upgrade the firmware?"):
        print_info("Firmware upgrade cancelled.")
        return False
    
    print()
    print_info("Starting firmware upgrade...")
    print_dim(f"  URL: {status['upgrade_url']}")
    print_dim(f"  MD5: {status['md5']}")
    print()
    
    # Check router internet access using detect_router_env from update.router_update
    from update.router_update import detect_router_env
    import os
    
    print_info("Checking router internet access...")
    external_ip, _, _ = detect_router_env(router)
    
    firmware_url = status['upgrade_url']
    firmware_filename = firmware_url.split('/')[-1]
    router_tmp_path = f"/tmp/{firmware_filename}"
    local_cache_dir = "./cache/firmware"
    local_cache_path = f"{local_cache_dir}/{firmware_filename}"
    
    if external_ip != "Unknown":
        # Router has internet access - download directly to router
        print_ok(f"Router has internet access (public IP: {external_ip})")
        print_info(f"Downloading firmware directly to router {router_tmp_path}...")
        download_cmd = f"curl -L -# -o {router_tmp_path} '{firmware_url}'"
        output, error = router.run_os_cmd(download_cmd, echo=True)
        # Note: curl -# writes progress to stderr, so error will contain progress output
        # Check if file was actually downloaded by verifying it exists
        verify_cmd = f"test -f {router_tmp_path} && echo 'exists' || echo 'missing'"
        verify_output, _ = router.run_os_cmd(verify_cmd)
        if 'exists' not in verify_output:
            print_error(f"Download failed - file not found at {router_tmp_path}")
            if error:
                print_dim(f"  Error output: {error}")
            return False
        print_ok(f"Firmware downloaded to {router_tmp_path}")
    else:
        # Router does NOT have internet access
        print_warn("Router does NOT have internet access.")
        
        # Check if firmware exists in local cache
        if not os.path.exists(local_cache_dir):
            os.makedirs(local_cache_dir)
            print_info(f"Created cache directory: {local_cache_dir}")
        
        if not os.path.exists(local_cache_path):
            print_info(f"Downloading firmware to local cache: {local_cache_path}")
            try:
                with requests.get(firmware_url, stream=True) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get('content-length', 0))
                    downloaded = 0
                    with open(local_cache_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                print(f"\r  Progress: {percent:.1f}% ({downloaded}/{total_size} bytes)", end='', flush=True)
                print()  # New line after progress
                print_ok(f"Firmware downloaded to {local_cache_path}")
            except Exception as e:
                print_error(f"Host download error: {e}")
                return False
        else:
            print_ok(f"Firmware already exists in cache: {local_cache_path}")
        
        # Upload firmware to router /tmp
        print_info(f"Uploading firmware to router /tmp...")
        try:
            router.sftp_client.put(local_cache_path, router_tmp_path)
            print_ok(f"Firmware uploaded to {router_tmp_path}")
        except Exception as e:
            print_error(f"SFTP upload error: {e}")
            return False
    
    # Install firmware using add system image command
    print()
    print_info("Installing firmware on router...")
    print()
    
    install_cmd = f"{VYATTA_OP_CMD_WRAPPER} add system image {router_tmp_path}"
    
    # Execute install command interactively
    try:
        output, error = router.run_os_cmd(install_cmd, echo=True)
        if error:
            print_error(f"Installation error: {error}")
            return False
        print()
        print_ok("Firmware installation completed successfully!")
        print()
        
        # Ask user if they want to reboot now
        if get_confirmation("Reboot the router now to apply the new firmware?"):
            print_info("Rebooting router...")
            reboot_cmd = "sudo reboot"
            router.run_os_cmd(reboot_cmd, echo=False)
            print_ok("Reboot command sent to router.")
            print_warn("The router is rebooting. Connection will be lost.")
        else:
            print_warn("Router reboot skipped. Please reboot manually to apply the new firmware.")
        
        print()
        print_info("Firmware upgrade process completed. Exiting...")
        sys.exit(0)
    except Exception as e:
        print_error(f"Failed to run installation command: {e}")
        return False


def show_firmware_status(router):
    """
    Display firmware status without performing upgrade.
    """
    print_header("Firmware Status", width=60)
    print_subtitle("EdgeRouter Firmware Check")
    print()
    
    status = check_firmware_status(router)
    
    if status["error"]:
        print_error(status["error"])
        return status
    
    print_info(f"Model           : {router.model}")
    print_info(f"Hardware        : {router.hardware}")
    print_info(f"Current Version : {status['current_version']}")
    print_info(f"Latest Version  : {status['latest_version']}")
    print()
    
    if status["is_legacy"]:
        print_warn("Legacy firmware detected (v1.x or v2.x)")
    
    if status["needs_upgrade"]:
        print_warn(f"Upgrade available: {status['current_version']} → {status['latest_version']}")
    else:
        print_ok("Firmware is up to date!")
    
    return status
