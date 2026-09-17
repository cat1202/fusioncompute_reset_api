import argparse
import os
from dotenv import load_dotenv

# Load environment variables from a .env file if present
load_dotenv()
import hashlib
import json
import requests
import urllib3
import sys
from typing import Optional, Dict, Any, List

# Suppress SSL certificate warnings if your VRM uses self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURATION ---
VRM_IP = "test.1588.co.in"              # Your Huawei VRM management IP address
USERNAME = os.getenv("FC_USERNAME", "") # Your FusionCompute username (from env)
PASSWORD = os.getenv("FC_PASSWORD", "") # Your FusionCompute password (from env)

BASE_URL = f"https://{VRM_IP}:7443/service"


def get_vrm_token() -> Optional[str]:
    """Authenticates against Huawei VRM and retrieves the session token."""
    login_url = f"{BASE_URL}/session"

    password_hash = hashlib.sha256(PASSWORD.encode("utf-8")).hexdigest()

    # Strategy 1: Header-based with UserType '2' (API User)
    headers_v2 = {
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json;version=1.0;charset=UTF-8",
        "X-Auth-User": USERNAME,
        "X-Auth-Key": password_hash,
        "X-Auth-UserType": "2",
    }

    # Strategy 2: Header-based with UserType '1' (Portal User)
    headers_v1 = dict(headers_v2)
    headers_v1["X-Auth-UserType"] = "1"

    # Strategy 3: Original Payload-based
    headers_payload = {
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json;version=1.0;charset=UTF-8",
    }
    payload_data = {
        "userName": USERNAME,
        "password": PASSWORD
    }

    strategies = [
        ("Header-based (UserType 2)", headers_v2, None),
        ("Header-based (UserType 1)", headers_v1, None),
        ("Payload-based", headers_payload, payload_data)
    ]

    for name, headers, payload in strategies:
        try:
            response = requests.post(
                login_url, json=payload, headers=headers, verify=False, timeout=30
            )

            if response.status_code in (200, 204):
                token = response.headers.get("X-Auth-Token")
                if token:
                    return token

        except Exception:
            pass

    print("[X] All authentication strategies failed.", file=sys.stderr)
    return None


def get_site_uri(token: str) -> Optional[str]:
    """Retrieves the first available site URI."""
    sites_url = f"{BASE_URL}/sites"
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json;charset=UTF-8",
        "Accept-Language": "zh_CN",
        "X-Auth-Token": token,
    }

    try:
        response = requests.get(sites_url, headers=headers, verify=False, timeout=30)
        if response.status_code == 200:
            data = response.json()
            sites = data.get("sites", [])
            if sites and "uri" in sites[0]:
                return sites[0]["uri"]
    except Exception as e:
        print(f"[X] Error fetching sites: {e}", file=sys.stderr)
    return None


def get_vm_uri_by_name(token: str, site_uri: str, vm_name: str) -> Optional[str]:
    """Finds a VM by name and returns its URI."""
    if site_uri.startswith("/service"):
        vms_url = f"https://{VRM_IP}:7443{site_uri}/vms"
    elif site_uri.startswith("/sites"):
        vms_url = f"{BASE_URL}{site_uri}/vms"
    else:
        vms_url = f"{BASE_URL}/sites/{site_uri}/vms"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Auth-Token": token,
    }

    limit = 100
    offset = 0

    try:
        while True:
            # We attempt to filter by name directly via params to optimize query
            params = {"limit": limit, "offset": offset, "name": vm_name}
            response = requests.get(
                vms_url, headers=headers, params=params, verify=False, timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                vms = data.get("vms", [])

                # Check for match
                for vm in vms:
                    if vm.get("name") == vm_name:
                        return vm.get("uri")

                if len(vms) < limit:
                    break
                offset += limit
            else:
                print(f"[X] Failed to fetch VMs for name matching. Status: {response.status_code}", file=sys.stderr)
                break
    except Exception as e:
        print(f"[X] Error fetching VM list: {e}", file=sys.stderr)

    return None


def get_vm_status(token: str, vm_uri: str) -> Optional[Dict[str, Any]]:
    """
    Fetches the VM status using its URI.
    """
    if vm_uri.startswith("/service"):
        vm_url = f"https://{VRM_IP}:7443{vm_uri}"
    elif vm_uri.startswith("/sites"):
        vm_url = f"{BASE_URL}{vm_uri}"
    else:
        # Assuming just the ID or partial URI was provided
        vm_url = f"{BASE_URL}/{vm_uri.strip('/')}"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Auth-Token": token,
    }

    try:
        response = requests.get(
            vm_url, headers=headers, verify=False, timeout=30
        )

        if response.status_code == 200:
            return response.json()
        else:
            print(f"[X] Failed to fetch VM status. Status code: {response.status_code}", file=sys.stderr)
            print(response.text, file=sys.stderr)
            return None
    except Exception as e:
        print(f"[X] Error fetching VM status: {e}", file=sys.stderr)
        return None


if __name__ == "__main__":
    TARGET_VM_NAME = "tz7w2k22dc-tpl"

    vrm_token = get_vrm_token()

    if vrm_token:
        site_uri = get_site_uri(vrm_token)
        if not site_uri:
            result = {
                'messageId': 'ERROR',
                'messageText': "Failed to get site URI.",
                'scriptCode': 1,
                'data': {}
            }
            print(json.dumps(result, indent=2))
            sys.exit(1)

        vm_uri = get_vm_uri_by_name(vrm_token, site_uri, TARGET_VM_NAME)

        if not vm_uri:
            result = {
                'messageId': 'ERROR',
                'messageText': f"VM '{TARGET_VM_NAME}' not found.",
                'scriptCode': 1,
                'data': {}
            }
            print(json.dumps(result, indent=2))
            sys.exit(1)

        vm_info = get_vm_status(vrm_token, vm_uri)

        if vm_info:
            result = {
                'messageId': 'OK',
                'messageText': "Operation Completed Successfully",
                'scriptCode': 0,
                'data': vm_info
            }
            print(json.dumps(result, indent=2))
        else:
            result = {
                'messageId': 'ERROR',
                'messageText': "Failed to fetch VM status.",
                'scriptCode': 1,
                'data': {}
            }
            print(json.dumps(result, indent=2))
            sys.exit(1)
    else:
        result = {
            'messageId': 'ERROR',
            'messageText': "Authentication failed.",
            'scriptCode': 1,
            'data': {}
        }
        print(json.dumps(result, indent=2))
        sys.exit(1)
