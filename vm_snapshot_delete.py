"""Delete a snapshot for a specific VM on Huawei FusionCompute VRM via REST API."""
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
from typing import Optional, List, Dict, Any

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

    headers_v2 = {
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json;version=1.0;charset=UTF-8",
        "X-Auth-User": USERNAME,
        "X-Auth-Key": password_hash,
        "X-Auth-UserType": "2",
    }

    try:
        print("[*] Authenticating with VRM...")
        response = requests.post(
            login_url, headers=headers_v2, verify=False, timeout=30
        )

        if response.status_code in (200, 204):
            token = response.headers.get("X-Auth-Token")
            if token:
                print("[OK] Successfully authenticated with VRM.")
                return token

        print(f"[-] Authentication failed with status {response.status_code}.")
    except Exception as e:
        print(f"[X] Error during authentication: {e}")

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


def list_vm_snapshots(token: str, vm_uri: str) -> Optional[Dict[str, Any]]:
    """Queries and lists all snapshots for the specified VM."""
    if vm_uri.startswith("/service"):
        snapshot_url = f"https://{VRM_IP}:7443{vm_uri}/snapshots"
    elif vm_uri.startswith("/sites") or vm_uri.startswith("urn:sites"):
        if vm_uri.startswith("urn:"):
            vm_uri = "/" + vm_uri.replace(":", "/")
        snapshot_url = f"{BASE_URL}{vm_uri}/snapshots"
    else:
        snapshot_url = f"{BASE_URL}/sites/{vm_uri}/snapshots"

    if "/service/" not in snapshot_url and "https://" not in snapshot_url:
        snapshot_url = f"{BASE_URL}{vm_uri}/snapshots"

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json;version=1.0;charset=UTF-8",
        "X-Auth-Token": token,
    }

    try:
        response = requests.get(
            snapshot_url, headers=headers, verify=False, timeout=30
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"[X] Error listing snapshots: {e}")

    return None


def delete_vm_snapshot(token: str, vm_uri: str, snapshot_id: str) -> Optional[Dict[str, Any]]:
    """Deletes a snapshot for the specified VM."""
    if vm_uri.startswith("/service"):
        snapshot_url = f"https://{VRM_IP}:7443{vm_uri}/snapshots"
    elif vm_uri.startswith("/sites") or vm_uri.startswith("urn:sites"):
        if vm_uri.startswith("urn:"):
            vm_uri = "/" + vm_uri.replace(":", "/")
        snapshot_url = f"{BASE_URL}{vm_uri}/snapshots"
    else:
        snapshot_url = f"{BASE_URL}/sites/{vm_uri}/snapshots"

    if "/service/" not in snapshot_url and "https://" not in snapshot_url:
        snapshot_url = f"{BASE_URL}{vm_uri}/snapshots"

    delete_url = f"{snapshot_url}/{snapshot_id}"

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json;version=1.0;charset=UTF-8",
        "X-Auth-Token": token,
    }

    print(f"\n[*] Deleting snapshot ID '{snapshot_id}' for VM at {vm_uri}...")
    try:
        response = requests.delete(
            delete_url, headers=headers, verify=False, timeout=30
        )
        if response.status_code in (200, 202):
            data = response.json()
            print("[OK] Snapshot deletion command accepted.")
            print(json.dumps(data, indent=2))
            return data
        else:
            print(f"[X] Failed to delete snapshot. Status: {response.status_code}")
            try:
                print(response.json())
            except:
                print(response.text)
            return None
    except Exception as e:
        print(f"[X] Error deleting snapshot: {e}")
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete a VM snapshot on FusionCompute.")
    parser.add_argument("--vm-name", required=True, help="The name of the VM")
    parser.add_argument("--snapshot-name", default=None, help="The name of the snapshot to delete (default: deletes the first available)")
    args = parser.parse_args()

    TARGET_VM_NAME = args.vm_name
    TARGET_SNAPSHOT_NAME = args.snapshot_name

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

        snapshots_data = list_vm_snapshots(vrm_token, vm_uri)

        if not snapshots_data:
            result = {
                'messageId': 'ERROR',
                'messageText': "Failed to list snapshots.",
                'scriptCode': 1,
                'data': {}
            }
            print(json.dumps(result, indent=2))
            sys.exit(1)

        def flatten_snapshots(nodes):
            snaps = []
            for node in nodes:
                snaps.append(node)
                if "childSnapshots" in node and node["childSnapshots"]:
                    snaps.extend(flatten_snapshots(node["childSnapshots"]))
            return snaps

        root_snapshots = snapshots_data.get("rootSnapshots", [])
        snapshots = flatten_snapshots(root_snapshots)

        if not snapshots:
            result = {
                'messageId': 'ERROR',
                'messageText': "No snapshots found for this VM. Nothing to delete.",
                'scriptCode': 1,
                'data': {}
            }
            print(json.dumps(result, indent=2))
            sys.exit(1)

        target_snapshot_id = None

        if TARGET_SNAPSHOT_NAME:
            for snap in snapshots:
                if snap.get("name") == TARGET_SNAPSHOT_NAME:
                    target_snapshot_id = snap.get("id") or snap.get("urn")
                    break
            if not target_snapshot_id:
                result = {
                    'messageId': 'ERROR',
                    'messageText': f"Could not find snapshot with name '{TARGET_SNAPSHOT_NAME}'.",
                    'scriptCode': 1,
                    'data': {}
                }
                print(json.dumps(result, indent=2))
                sys.exit(1)
        else:
            # Default to deleting the first snapshot found
            target_snapshot = snapshots[0]
            target_snapshot_id = target_snapshot.get("id") or target_snapshot.get("urn")
            target_snapshot_name = target_snapshot.get("name", "Unknown")

        # urn is sometimes the full urn, we might just need the id.
        # Typically the id is a string suffix.
        if target_snapshot_id and target_snapshot_id.startswith("urn:"):
            target_snapshot_id = target_snapshot_id.split(":")[-1]
            
        if not target_snapshot_id:
            result = {
                'messageId': 'ERROR',
                'messageText': "Could not determine snapshot ID.",
                'scriptCode': 1,
                'data': {}
            }
            print(json.dumps(result, indent=2))
            sys.exit(1)

        # Delete the snapshot
        deleted_data = delete_vm_snapshot(vrm_token, vm_uri, target_snapshot_id)

        if deleted_data:
            result = {
                'messageId': 'OK',
                'messageText': "Operation Completed Successfully",
                'scriptCode': 0,
                'data': deleted_data
            }
            print(json.dumps(result, indent=2))
        else:
            result = {
                'messageId': 'ERROR',
                'messageText': "Failed to delete snapshot.",
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
