"""Stop a single VM on Huawei FusionCompute VRM via REST API."""
import os
from dotenv import load_dotenv

# Load environment variables from a .env file if present
load_dotenv()
import hashlib
import json
import requests
import urllib3
from typing import Optional, Dict, Any, List

# Suppress SSL certificate warnings if your VRM uses self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURATION ---
VRM_IP = "test.1588.co.in"
USERNAME = os.getenv("FC_USERNAME", "")
PASSWORD = os.getenv("FC_PASSWORD", "")
PORT = 7443

BASE_URL = f"https://{VRM_IP}:{PORT}/service"

# Target VM to stop
TARGET_VM_NAME = "tz7w2k22dc-tpl"


def get_vrm_token() -> Optional[str]:
    """Authenticates against Huawei VRM and retrieves the session token."""
    login_url = f"{BASE_URL}/session"
    password_hash = hashlib.sha256(PASSWORD.encode("utf-8")).hexdigest()

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json;version=1.0;charset=UTF-8",
        "X-Auth-User": USERNAME,
        "X-Auth-Key": password_hash,
        "X-Auth-UserType": "2",
    }

    try:
        print("[*] Authenticating with VRM...")
        response = requests.post(
            login_url, headers=headers, verify=False, timeout=30
        )

        if response.status_code in (200, 204):
            token = response.headers.get("X-Auth-Token")
            if token:
                print("[OK] Successfully authenticated.")
                return token

        print(f"[X] Authentication failed. Status: {response.status_code}")
        print(f"    Body: {response.text[:300]}")
        return None
    except Exception as e:
        print(f"[X] Authentication error: {e}")
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
        print(f"[X] Error fetching sites: {e}")
    return None


def list_all_vms(token: str, site_uri: str) -> List[Dict[str, Any]]:
    """Fetches all VMs from the site."""
    if site_uri.startswith("/service"):
        vms_url = f"https://{VRM_IP}:{PORT}{site_uri}/vms"
    else:
        vms_url = f"{BASE_URL}{site_uri}/vms"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Auth-Token": token,
    }

    all_vms = []
    limit = 100
    offset = 0

    try:
        while True:
            params = {"limit": limit, "offset": offset}
            response = requests.get(vms_url, headers=headers, params=params, verify=False, timeout=30)
            if response.status_code == 200:
                data = response.json()
                vms = data.get("vms", [])
                all_vms.extend(vms)
                if len(vms) < limit:
                    break
                offset += limit
            else:
                break
        return all_vms
    except Exception:
        return []


def stop_vm(token: str, vm_uri: str, mode: str = "safe") -> Optional[Dict[str, Any]]:
    """
    Stops a single VM.

    Args:
        token: The X-Auth-Token from authentication.
        vm_uri: The VM URI, e.g. '/service/sites/ECB20D1A/vms/i-00000948'.
        mode: Stop mode - 'safe' (graceful shutdown) or 'force' (power off).

    Returns:
        Task info dict with taskUrn and taskUri on success, None on failure.
    """
    # Build the stop URL: <vm_uri>/action/stop
    if vm_uri.startswith("/service"):
        stop_url = f"https://{VRM_IP}:{PORT}{vm_uri}/action/stop"
    else:
        stop_url = f"{BASE_URL}{vm_uri}/action/stop"

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json;version=1.0;charset=UTF-8",
        "X-Auth-Token": token,
    }

    payload = {
        "mode": mode,
    }

    print(f"\n{'='*60}")
    print(f"[*] Stopping VM: {vm_uri}")
    print(f"    Mode: {mode}")
    print(f"    URL:  {stop_url}")

    try:
        response = requests.post(
            stop_url, json=payload, headers=headers, verify=False, timeout=30
        )

        print(f"    Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            task_urn = data.get("taskUrn", "N/A")
            task_uri = data.get("taskUri", "N/A")
            print(f"[OK] VM stop command accepted.")
            print(f"    Task URN: {task_urn}")
            print(f"    Task URI: {task_uri}")
            return data
        else:
            print(f"[X] Failed to stop VM. Status: {response.status_code}")
            try:
                error_data = response.json()
                error_code = error_data.get("errorCode", "N/A")
                error_desc = error_data.get("errorDes", "N/A")
                if "此虚拟机已经为停止状态" in error_desc:
                    error_desc += " (This VM is already in a stopped state, so this operation cannot be performed.)"
                print(f"    Error Code: {error_code}")
                print(f"    Error Desc: {error_desc}")
            except Exception:
                print(f"    Body: {response.text[:300]}")
            return None

    except requests.exceptions.ConnectTimeout:
        print("[X] Connection timed out.")
        return None
    except requests.exceptions.ConnectionError:
        print("[X] Connection refused/error.")
        return None
    except Exception as e:
        print(f"[X] Error: {e}")
        return None


def check_task_status(token: str, task_uri: str) -> Optional[Dict[str, Any]]:
    """Checks the status of an async task."""
    if task_uri.startswith("/service"):
        task_url = f"https://{VRM_IP}:{PORT}{task_uri}"
    else:
        task_url = f"{BASE_URL}{task_uri}"

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json;charset=UTF-8",
        "X-Auth-Token": token,
    }

    try:
        response = requests.get(
            task_url, headers=headers, verify=False, timeout=30
        )
        if response.status_code == 200:
            return response.json()
        else:
            print(f"[X] Failed to check task. Status: {response.status_code}")
            return None
    except Exception as e:
        print(f"[X] Error checking task: {e}")
        return None


if __name__ == "__main__":
    # 1. Authenticate
    vrm_token = get_vrm_token()

    if not vrm_token:
        print("\n[X] Cannot proceed without authentication.")
        exit(1)

    # 2. Get Site URI
    site_uri = get_site_uri(vrm_token)
    if not site_uri:
        print("\n[X] Cannot proceed without site URI.")
        exit(1)

    # 3. Lookup target VM URI by name
    print(f"[*] Fetching all VMs to find '{TARGET_VM_NAME}'...")
    vms = list_all_vms(vrm_token, site_uri)

    target_vm_uri = None
    for vm in vms:
        if vm.get("name") == TARGET_VM_NAME:
            target_vm_uri = vm.get("uri")
            if not target_vm_uri:
                target_vm_uri = vm.get("urn")
            break

    if not target_vm_uri:
        print(f"[X] Could not find VM with name '{TARGET_VM_NAME}'.")
        exit(1)

    print(f"[OK] Found VM '{TARGET_VM_NAME}' with URI {target_vm_uri}")

    # 4. Stop the VM
    result = stop_vm(vrm_token, target_vm_uri, mode="safe")

    # 3. Check task status if stop was accepted
    if result:
        task_uri = result.get("taskUri")
        if task_uri:
            import time
            print(f"\n[*] Waiting 5 seconds before checking task status...")
            time.sleep(5)
            task_info = check_task_status(vrm_token, task_uri)
            if task_info:
                print(f"\n--- Task Status ---")
                print(json.dumps(task_info, indent=2, ensure_ascii=False))
