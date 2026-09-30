# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Specialist Agent for GCP Infrastructure Protection (bdr-orchestrator)."""

import os
import sys
import json
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import ToolContext, load_artifacts
from google.genai import types

from .app_utils.artifacts import save_files_as_artifacts, save_json_artifact

MODEL = os.environ.get("MODEL_NAME", "gemini-2.5-flash")


def _get_auth_context() -> tuple[Optional[Any], Optional[str], Optional[Dict[str, Any]]]:
    """Retrieves Google OAuth2 credentials and access token or returns a structured error."""
    try:
        import google.auth
        from google.auth.transport.requests import Request
    except ImportError:
        return None, None, {
            "status": "ERROR",
            "error_type": "MISSING_DEPENDENCY_ERROR",
            "component": "bdr-orchestrator (GCP Auth)",
            "cause": "Package 'google-auth' is required to authenticate against GCP APIs.",
            "remediation": "Install google-auth by running: pip install google-auth"
        }

    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(Request())
        return credentials, credentials.token, None
    except Exception as e:
        return None, None, {
            "status": "ERROR",
            "error_type": "AUTH_CREDENTIALS_ERROR",
            "component": "bdr-orchestrator (GCP Auth)",
            "cause": f"Failed to acquire Application Default Credentials: {str(e)}",
            "remediation": "Run 'gcloud auth application-default login' or set GOOGLE_APPLICATION_CREDENTIALS."
        }


async def scan_live_gce_instances(project_id: str, tool_context: Optional[ToolContext] = None) -> str:
    """Discovers active Google Compute Engine instances, machine types, zones, and attached disks
    and registers 'live_cloud_inventory.json' as an ADK artifact.

    Args:
        project_id: The target GCP Project ID to scan.

    Returns:
        JSON string listing discovered instances, protection tier classifications, and protection gaps.
    """
    try:
        from google.cloud import compute_v1
    except ImportError:
        return json.dumps({
            "status": "ERROR",
            "error_type": "MISSING_DEPENDENCY_ERROR",
            "component": "bdr-orchestrator (GCE Scanner)",
            "cause": "Package 'google-cloud-compute' is not installed.",
            "remediation": "Install the Google Cloud Compute SDK by running: pip install google-cloud-compute"
        }, indent=2)

    credentials, token, auth_err = _get_auth_context()
    if auth_err:
        return json.dumps(auth_err, indent=2)

    try:
        instance_client = compute_v1.InstancesClient(credentials=credentials)
        zone_client = compute_v1.ZonesClient(credentials=credentials)
        zones = [z.name for z in zone_client.list(project=project_id, timeout=30.0)]

        instances = []
        for zone in zones:
            request = compute_v1.ListInstancesRequest(project=project_id, zone=zone)
            for instance in instance_client.list(request=request, timeout=30.0):
                disks = []
                total_disk_gb = 0
                for d in instance.disks:
                    disk_size = getattr(d, 'disk_size_gb', 50)
                    total_disk_gb += disk_size
                    disks.append({
                        "name": d.device_name or "disk",
                        "size_gb": disk_size
                    })

                labels = dict(instance.labels) if instance.labels else {}
                mtype = instance.machine_type.split('/')[-1] if instance.machine_type else "unknown"

                # Classify Tier
                if labels.get("role") == "db" or labels.get("tier") == "critical" or total_disk_gb >= 1024:
                    tier, plan = "Tier 1", "Gold"
                elif labels.get("env") in ["prod", "production", "staging"] or labels.get("role") == "app":
                    tier, plan = "Tier 2", "Silver"
                else:
                    tier, plan = "Tier 3", "Bronze"

                instances.append({
                    "name": instance.name,
                    "zone": zone,
                    "machine_type": mtype,
                    "total_disk_gb": total_disk_gb,
                    "labels": labels,
                    "classification": tier,
                    "recommended_bdr_plan": plan,
                    "self_link": instance.self_link
                })

        output_payload = {
            "status": "SUCCESS",
            "project_id": project_id,
            "scanned_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "total_instances_found": len(instances),
            "instances": instances
        }

        # Save to local file & register into ADK ArtifactService
        if tool_context:
            await save_json_artifact(tool_context, "live_cloud_inventory.json", output_payload)
        else:
            os.makedirs("assets", exist_ok=True)
            with open("assets/live_cloud_inventory.json", "w", encoding="utf-8") as f:
                json.dump(output_payload, f, indent=2)

        return json.dumps(output_payload, indent=2)

    except Exception as e:
        return json.dumps({
            "status": "ERROR",
            "error_type": "GCE_SCAN_FAILED",
            "component": "bdr-orchestrator",
            "cause": str(e),
            "remediation": f"Verify IAM permissions: Ensure caller has 'roles/compute.viewer' on project '{project_id}'."
        }, indent=2)


def list_gcp_backup_vaults(project_id: str, location: str, timeout: int = 30) -> str:
    """Lists configured Backup Vaults and their retention locks from Backup & DR API.

    Args:
        project_id: Target GCP project ID.
        location: GCP region/location (e.g., us-central1).

    Returns:
        JSON string listing active backup vaults.
    """
    _, token, auth_err = _get_auth_context()
    if auth_err:
        return json.dumps(auth_err, indent=2)

    url = f"https://backupdr.googleapis.com/v1/projects/{project_id}/locations/{location}/backupVaults"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    req = urllib.request.Request(url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return json.dumps({"status": "SUCCESS", "vaults": data.get("backupVaults", [])}, indent=2)
    except urllib.error.HTTPError as e:
        return json.dumps({
            "status": "ERROR",
            "error_type": f"GCP_API_HTTP_{e.code}",
            "cause": e.read().decode("utf-8"),
            "remediation": f"Verify Backup and DR API is enabled and caller has 'roles/backupdr.viewer' on project '{project_id}'."
        }, indent=2)
    except TimeoutError:
        return json.dumps({
            "status": "ERROR",
            "error_type": "TIMEOUT_ERROR",
            "cause": f"Request timed out after {timeout}s querying Backup Vaults."
        }, indent=2)
    except Exception as e:
        return json.dumps({"status": "ERROR", "error_type": "NETWORK_ERROR", "cause": str(e)}, indent=2)


def list_gcp_backup_plans(project_id: str, location: str, timeout: int = 30) -> str:
    """Lists configured Backup Plans (Gold, Silver, Bronze schedules).

    Args:
        project_id: Target GCP project ID.
        location: GCP region/location (e.g., us-central1).

    Returns:
        JSON string listing available backup plans.
    """
    _, token, auth_err = _get_auth_context()
    if auth_err:
        return json.dumps(auth_err, indent=2)

    url = f"https://backupdr.googleapis.com/v1/projects/{project_id}/locations/{location}/backupPlans"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    req = urllib.request.Request(url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return json.dumps({"status": "SUCCESS", "plans": data.get("backupPlans", [])}, indent=2)
    except urllib.error.HTTPError as e:
        return json.dumps({
            "status": "ERROR",
            "error_type": f"GCP_API_HTTP_{e.code}",
            "cause": e.read().decode("utf-8"),
            "remediation": f"Ensure caller has 'roles/backupdr.viewer' on project '{project_id}'."
        }, indent=2)
    except TimeoutError:
        return json.dumps({
            "status": "ERROR",
            "error_type": "TIMEOUT_ERROR",
            "cause": f"Request timed out after {timeout}s querying Backup Plans."
        }, indent=2)
    except Exception as e:
        return json.dumps({"status": "ERROR", "error_type": "NETWORK_ERROR", "cause": str(e)}, indent=2)


def create_gcp_backup_vault(project_id: str, location: str, vault_id: str, retention_days: int, user_confirmed: bool = False, timeout: int = 30) -> str:
    """Creates a new Backup Vault with minimum enforced retention lock (requires explicit user confirmation).

    Args:
        project_id: Target GCP project ID.
        location: GCP region (e.g., us-central1).
        vault_id: ID/Name for the new Backup Vault.
        retention_days: Minimum immutable retention lock in days.
        user_confirmed: True only if the user explicitly confirmed this mutation in chat.

    Returns:
        JSON string with creation status or confirmation request notice.
    """
    if not user_confirmed:
        return json.dumps({
            "status": "MUTATION_CONFIRMATION_REQUIRED",
            "message": "Safeguard Guard: User approval is required before provisioning infrastructure.",
            "mutation_details": {
                "action": "CREATE_BACKUP_VAULT",
                "project_id": project_id,
                "location": location,
                "vault_id": vault_id,
                "retention_days": retention_days,
                "enforced_retention_duration": f"{retention_days * 86400}s"
            },
            "remediation": "Prompt the user in chat to confirm this operation before re-invoking with user_confirmed=True."
        }, indent=2)

    _, token, auth_err = _get_auth_context()
    if auth_err:
        return json.dumps(auth_err, indent=2)

    url = f"https://backupdr.googleapis.com/v1/projects/{project_id}/locations/{location}/backupVaults?backupVaultId={vault_id}"
    payload = {
        "description": "Provisioned via bdr-orchestrator",
        "backupMinimumEnforcedRetentionDuration": f"{retention_days * 86400}s"
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return json.dumps({"status": "SUCCESS", "result": data}, indent=2)
    except urllib.error.HTTPError as e:
        return json.dumps({
            "status": "ERROR",
            "error_type": f"GCP_API_HTTP_{e.code}",
            "cause": e.read().decode("utf-8"),
            "remediation": f"Ensure caller has 'roles/backupdr.admin' on project '{project_id}'."
        }, indent=2)
    except TimeoutError:
        return json.dumps({
            "status": "ERROR",
            "error_type": "TIMEOUT_ERROR",
            "cause": f"Request timed out after {timeout}s creating Backup Vault."
        }, indent=2)
    except Exception as e:
        return json.dumps({"status": "ERROR", "error_type": "NETWORK_ERROR", "cause": str(e)}, indent=2)


async def create_gcp_plan_association(
    project_id: str,
    location: str,
    plan_id: str,
    instance_name: str,
    instance_self_link: str,
    user_confirmed: bool = False,
    tool_context: Optional[ToolContext] = None,
    timeout: int = 30
) -> str:
    """Binds a Compute Engine instance to a target Backup Plan (requires explicit user confirmation)
    and saves association report as an ADK artifact.

    Args:
        project_id: Target GCP project ID.
        location: GCP region (e.g., us-central1).
        plan_id: Target Backup Plan ID (e.g., gold-db-policy).
        instance_name: GCE instance name.
        instance_self_link: Full GCE instance self link or resource path.
        user_confirmed: True only if the user explicitly confirmed this binding in chat.

    Returns:
        JSON string describing the BackupPlanAssociation outcome.
    """
    if not user_confirmed:
        return json.dumps({
            "status": "MUTATION_CONFIRMATION_REQUIRED",
            "message": "Safeguard Guard: User approval is required before binding backup policies.",
            "mutation_details": {
                "action": "CREATE_BACKUP_PLAN_ASSOCIATION",
                "project_id": project_id,
                "location": location,
                "instance_name": instance_name,
                "target_plan": plan_id,
                "instance_self_link": instance_self_link
            },
            "remediation": "Prompt the user in chat to confirm this policy association before re-invoking with user_confirmed=True."
        }, indent=2)

    _, token, auth_err = _get_auth_context()
    if auth_err:
        return json.dumps(auth_err, indent=2)

    bpa_id = f"bpa-{instance_name.lower()}"
    url = f"https://backupdr.googleapis.com/v1/projects/{project_id}/locations/{location}/backupPlanAssociations?backupPlanAssociationId={bpa_id}"
    payload = {
        "resourceType": "compute.googleapis.com/Instance",
        "resource": instance_self_link,
        "backupPlan": f"projects/{project_id}/locations/{location}/backupPlans/{plan_id}"
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            result = {"status": "SUCCESS", "bpa": data}
            if tool_context:
                await save_json_artifact(tool_context, f"bdr_association_{instance_name}.json", result)
            return json.dumps(result, indent=2)
    except urllib.error.HTTPError as e:
        return json.dumps({
            "status": "ERROR",
            "error_type": f"GCP_API_HTTP_{e.code}",
            "cause": e.read().decode("utf-8"),
            "remediation": f"Ensure caller has 'roles/backupdr.admin' on project '{project_id}'."
        }, indent=2)
    except TimeoutError:
        return json.dumps({
            "status": "ERROR",
            "error_type": "TIMEOUT_ERROR",
            "cause": f"Request timed out after {timeout}s creating Backup Plan Association."
        }, indent=2)
    except Exception as e:
        return json.dumps({"status": "ERROR", "error_type": "NETWORK_ERROR", "cause": str(e)}, indent=2)


def send_chat_summary(title: str, protected_vms_count: int, total_storage_gib: float, monthly_cost: float, console_link: Optional[str] = None, timeout: int = 30) -> str:
    """Dispatches operational milestone summary cards to Google Chat or Slack webhook.

    Args:
        title: Title of the summary card.
        protected_vms_count: Number of protected instances.
        total_storage_gib: Protected storage size in GiB.
        monthly_cost: Estimated monthly spend in USD.
        console_link: Optional deep link to GCP Console.

    Returns:
        JSON string indicating delivery outcome.
    """
    webhook_url = os.environ.get("WEBHOOK_URL") or os.environ.get("BDR_CHAT_WEBHOOK_URL")
    if not webhook_url:
        return json.dumps({
            "status": "ERROR",
            "error_type": "CONFIG_ERROR",
            "cause": "Environment variable 'WEBHOOK_URL' or 'BDR_CHAT_WEBHOOK_URL' is not set.",
            "remediation": "Set WEBHOOK_URL in your environment before dispatching chat notifications."
        }, indent=2)

    payload = {
        "text": f"*{title}*\n- Protected VMs: {protected_vms_count}\n- Storage: {total_storage_gib:.2f} GiB\n- Est. Monthly Cost: ${monthly_cost:.2f}"
    }
    if console_link:
        payload["text"] += f"\n<{console_link}|Open GCP Console>"

    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.dumps({"status": "SUCCESS", "message": "Notification dispatched successfully."}, indent=2)
    except urllib.error.HTTPError as e:
        return json.dumps({
            "status": "ERROR",
            "error_type": f"WEBHOOK_HTTP_{e.code}",
            "cause": e.read().decode("utf-8"),
            "remediation": "Verify that the webhook URL is correct and accepts incoming POST requests."
        }, indent=2)
    except TimeoutError:
        return json.dumps({
            "status": "ERROR",
            "error_type": "TIMEOUT_ERROR",
            "cause": f"Webhook delivery timed out after {timeout}s."
        }, indent=2)
    except Exception as e:
        return json.dumps({"status": "ERROR", "error_type": "WEBHOOK_DELIVERY_FAILED", "cause": str(e)}, indent=2)


root_agent = Agent(
    name="bdr_orchestrator",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the BDR Orchestrator Specialist Agent (bdr-orchestrator).
Your purpose is to discover live GCP infrastructure, audit backup compliance gaps, manage Backup Vaults, bind Compute Engine instances to Backup Plans (BPA), and send operational chat notifications.

Follow these strict operating rules:
1. Scan live GCP resources with scan_live_gce_instances and cross-reference with list_gcp_backup_plans and list_gcp_backup_vaults.
2. Flag any live VM without an active Backup Plan Association as 'Unprotected'.
3. CRITICAL SAFEGUARD: Never mutate infrastructure or bind policies (create_gcp_backup_vault or create_gcp_plan_association) without explicit user confirmation in chat.
4. When dependencies or credentials fail, return developer-friendly error messages with remediation instructions.
5. Notify teams using send_chat_summary when onboarding operations complete.
6. All scanned inventories and association reports are automatically saved to ADK Artifacts.
""",
    tools=[
        scan_live_gce_instances,
        list_gcp_backup_vaults,
        list_gcp_backup_plans,
        create_gcp_backup_vault,
        create_gcp_plan_association,
        send_chat_summary,
        load_artifacts,
    ],
    before_model_callback=save_files_as_artifacts,
)

app = App(
    root_agent=root_agent,
    name="app",
)


