"""Start a single VM on Huawei FusionCompute VRM via REST API."""
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

# Target VM to start
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


def start_vm(token: str, vm_uri: str) -> Optional[Dict[str, Any]]:
    """
    Starts a single VM.

    No request body is required for the start action.

    Args:
        token: The X-Auth-Token from authentication.
        vm_uri: The VM URI, e.g. '/service/sites/ECB20D1A/vms/i-00000948'.

    Returns:
        Task info dict with taskUrn and taskUri on success, None on failure.
    """
    # Build the start URL: <vm_uri>/action/start
    if vm_uri.startswith("/service"):
        start_url = f"https://{VRM_IP}:{PORT}{vm_uri}/action/start"
    else:
        start_url = f"{BASE_URL}{vm_uri}/action/start"

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json;version=1.0;charset=UTF-8",
        "X-Auth-Token": token,
    }

    print(f"\n{'='*60}")
    print(f"[*] Starting VM: {vm_uri}")
    print(f"    URL:  {start_url}")

    try:
        # No request body for start action
        response = requests.post(
            start_url, headers=headers, verify=False, timeout=30
        )

        print(f"    Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            task_urn = data.get("taskUrn", "N/A")
            task_uri = data.get("taskUri", "N/A")
            print("[OK] VM start command accepted.")
            print(f"    Task URN: {task_urn}")
            print(f"    Task URI: {task_uri}")
            return data
        else:
            print(f"[X] Failed to start VM. Status: {response.status_code}")
            try:
                error_data = response.json()
                error_code = error_data.get("errorCode", "N/A")
                error_desc = error_data.get("errorDes", "N/A")
                print(f"    Error Code: {error_code}")
                print(f"    Error Desc: {error_desc}")
                _print_known_error_hint(error_code)
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


def _print_known_error_hint(error_code: str) -> None:
    """Prints a human-readable hint for known start-VM error codes."""
    known_errors: Dict[str, str] = {
        "10200130": "主机处于维护模式，请将主机退出维护模式后重试。",
        "10300094": "此虚拟机已经为运行状态，不能启动。",
        "10300096": "虚拟机正在执行此操作，请不要重复执行。",
        "10300101": "虚拟机正忙，请稍后重试。",
        "10800125": "CPU资源不足，请检查CPU核数、预留、上限。",
        "10800126": "内存资源不足，请检查内存大小、预留、上限。",
        "10800128": "供选择的主机均异常。",
        "10800129": "供选择的主机均处于维护模式。",
        "10800130": "供选择的主机均不可用。",
        "10800131": "无供选择的主机。",
        "10300015": "虚拟机不允许此操作。",
        "10300612": "CPU设置与异构迁移集群IMC模式配置不兼容。",
        "10300421": "虚拟机磁盘存在未完成任务，请任务结束后重试。",
        "10512001": "虚拟交换端口资源不足。",
        "10800180": "安全虚拟机启动失败，请检查安全虚拟机类型是否与主机防病毒配置一致。",
        "10800183": "主机的安全用户虚拟机个数已达上限或者主机安全开关未打开。",
        "10800184": "安全服务/安全用户虚拟机启动，预留内存必须是100%。",
        "10300770": "共享磁盘已绑定虚拟机，且存在导出任务，不支持当前操作。",
        "10300271": "虚拟机已绑定共享磁盘，且存在导出任务，不支持当前操作。",
        "10300915": "主机上虚拟机总数或磁盘、网卡、vcpu总数超过上限。",
        "10321131": "该主机上运行态虚拟机数量已经达到上限。",
        "10420170": "磁盘正在扩容中，不允许此操作。",
        "10420171": "磁盘存在卷快照任务，不允许此操作。",
        "10420172": "磁盘存在快照恢复卷任务，不允许此操作。",
        "10420173": "磁盘存在卷导入/导出镜像任务，不允许此操作。",
        "10420174": "磁盘存在备份或恢复任务，不允许此操作。",
        "10300950": "虚拟机大页类型与主机大页类型不一致，请修改配置。",
        "10380006": "绑定USB设备失败，请检查主机USB设备是否正常。",
        "10321119": "EVS亲和虚拟机申请目标主机资源不足，请重新配置。",
        "10300017": "虚拟机包含NVMe协议策略的磁盘，需要开启1G大页内存。",
        "10420187": "使用NVMe存储策略的磁盘的总线类型只能为VIRTIO。",
    }
    hint = known_errors.get(str(error_code))
    if hint:
        print(f"    Hint: {hint}")


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

    # 4. Start the VM
    result = start_vm(vrm_token, target_vm_uri)

    # 3. Check task status if start was accepted
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
