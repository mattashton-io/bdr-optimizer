#!/usr/bin/env python3
"""
backupdr_mcp.py

FastMCP Python server exposing tool bindings for the GCP Backup and DR REST API.
Enforces zero-tolerance error handling and structured JSON error responses per spec.md.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from typing import Optional, Dict, Any

# Strict Dependency Check: FastMCP / MCPServer (MCP 1.x & 2.x compatible)
try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise ImportError(
            "\n================================================================================\n"
            "[BDR-OPTIMIZER ERROR] MISSING_DEPENDENCY_ERROR: 'mcp' package is not installed.\n"
            "================================================================================\n"
            "Component:   backupdr_mcp (FastMCP Server)\n"
            "Cause:       ModuleNotFoundError: No module named 'mcp'\n"
            "Impact:      Cannot initialize FastMCP tool bindings for Backup and DR.\n\n"
            "Remediation:\n"
            "  1. Install the mcp package: pip install \"mcp>=1.0.0\"\n"
            "  2. Ensure the active virtual environment (.venv-bdr) is activated.\n"
            "================================================================================\n"
        ) from exc

# Strict Dependency Check: google-auth
try:
    import google.auth
    from google.auth.transport.requests import Request
    GCP_AUTH_AVAILABLE = True
except ImportError:
    GCP_AUTH_AVAILABLE = False


# Initialize FastMCP Server
mcp = FastMCP("backupdr_mcp")


def get_auth_token() -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Acquires Google OAuth2 access token via Application Default Credentials (ADC).
    Returns (token, None) on success or (None, error_payload) on failure.
    """
    if not GCP_AUTH_AVAILABLE:
        return None, {
            "status": "ERROR",
            "error_type": "MISSING_DEPENDENCY_ERROR",
            "component": "backupdr_mcp (GCP Auth)",
            "message": "Package 'google-auth' is required to authenticate against GCP APIs.",
            "remediation": "Install google-auth by running: pip install google-auth"
        }
    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(Request())
        return credentials.token, None
    except Exception as e:
        return None, {
            "status": "ERROR",
            "error_type": "AUTH_CREDENTIALS_ERROR",
            "component": "backupdr_mcp (GCP Auth)",
            "message": f"Unable to acquire Google OAuth2 access token: {str(e)}",
            "remediation": "Run 'gcloud auth application-default login' or set the GOOGLE_APPLICATION_CREDENTIALS environment variable."
        }


def execute_rest_call(url: str, token: str, method: str = "GET", data: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Dict[str, Any]:
    """
    Dispatches a direct HTTP REST request to backupdr.googleapis.com with timeout.
    Returns parsed JSON dict or raises RuntimeError with actionable context.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    req_data = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        try:
            err_json = json.loads(err_msg)
            message = err_json.get("error", {}).get("message", err_msg)
        except ValueError:
            message = err_msg

        if e.code == 403:
            raise RuntimeError(f"GCP API Error 403 (IAM Permission Missing): The caller lacks permission for this operation. Details: {message}")
        elif e.code == 409:
            raise RuntimeError(f"GCP API Error 409 (Conflict/Already Exists): The target resource already exists. Details: {message}")
        elif e.code == 404:
            raise RuntimeError(f"GCP API Error 404 (Not Found): Resource not found. Details: {message}")
        elif e.code == 400:
            raise RuntimeError(f"GCP API Error 400 (Bad Request): Invalid parameters. Details: {message}")
        else:
            raise RuntimeError(f"GCP API Error HTTP {e.code}: {message}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error executing REST call: {e.reason}")
    except TimeoutError:
        raise RuntimeError(f"Request timed out after {timeout} seconds executing REST call to {url}.")


# --- FASTMCP TOOL BINDINGS ---

@mcp.tool()
def list_backup_vaults(project_id: str, location: str) -> str:
    """
    Lists all active Backup Vaults in a project and location from Backup & DR API.

    Args:
        project_id: The target GCP Project ID.
        location: The target GCP region/location (e.g., us-central1).

    Returns:
        JSON string containing the list of backup vaults with names, states, and retention profiles.
    """
    token, auth_err = get_auth_token()
    if auth_err:
        return json.dumps(auth_err, indent=2)

    url = f"https://backupdr.googleapis.com/v1/projects/{project_id}/locations/{location}/backupVaults"

    try:
        res = execute_rest_call(url, token, "GET")
        return json.dumps({"status": "SUCCESS", "backupVaults": res.get("backupVaults", [])}, indent=2)
    except Exception as e:
        return json.dumps({
            "status": "ERROR",
            "error_type": "GCP_API_CALL_FAILED",
            "component": "backupdr_mcp.list_backup_vaults",
            "message": str(e),
            "remediation": f"Ensure Backup and DR API is enabled and caller has 'roles/backupdr.viewer' on project '{project_id}'."
        }, indent=2)


@mcp.tool()
def create_backup_vault(project_id: str, location: str, vault_id: str, retention_days: int, user_confirmed: bool = False) -> str:
    """
    Creates a new Backup Vault with a minimum enforced retention in days.
    Requires explicit user confirmation before mutating cloud infrastructure.

    Args:
        project_id: The target GCP Project ID.
        location: The target GCP region/location (e.g., us-central1).
        vault_id: Name/ID of the Backup Vault to create.
        retention_days: Number of days for the minimum enforced immutable retention lock.
        user_confirmed: True only if the user explicitly confirmed this mutation in chat.

    Returns:
        JSON string with creation details or confirmation request payload.
    """
    if not user_confirmed:
        return json.dumps({
            "status": "MUTATION_CONFIRMATION_REQUIRED",
            "message": "Safeguard Guard: User approval is required before provisioning Backup Vault infrastructure.",
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

    token, auth_err = get_auth_token()
    if auth_err:
        return json.dumps(auth_err, indent=2)

    url = f"https://backupdr.googleapis.com/v1/projects/{project_id}/locations/{location}/backupVaults?backupVaultId={vault_id}"
    payload = {
        "description": "Created via Backup & DR Custom FastMCP Server",
        "backupMinimumEnforcedRetentionDuration": f"{retention_days * 86400}s"
    }

    try:
        res = execute_rest_call(url, token, "POST", data=payload)
        return json.dumps({"status": "SUCCESS", "result": res}, indent=2)
    except Exception as e:
        return json.dumps({
            "status": "ERROR",
            "error_type": "VAULT_CREATION_FAILED",
            "component": "backupdr_mcp.create_backup_vault",
            "message": str(e),
            "remediation": f"Verify project '{project_id}' permissions: ensure caller has 'roles/backupdr.admin'."
        }, indent=2)


@mcp.tool()
def list_backup_plans(project_id: str, location: str) -> str:
    """
    Lists active Backup Plans configured in a target location.

    Args:
        project_id: The target GCP Project ID.
        location: The target GCP region/location (e.g., us-central1).

    Returns:
        JSON string containing the configured Backup Plans.
    """
    token, auth_err = get_auth_token()
    if auth_err:
        return json.dumps(auth_err, indent=2)

    url = f"https://backupdr.googleapis.com/v1/projects/{project_id}/locations/{location}/backupPlans"

    try:
        res = execute_rest_call(url, token, "GET")
        return json.dumps({"status": "SUCCESS", "backupPlans": res.get("backupPlans", [])}, indent=2)
    except Exception as e:
        return json.dumps({
            "status": "ERROR",
            "error_type": "GCP_API_CALL_FAILED",
            "component": "backupdr_mcp.list_backup_plans",
            "message": str(e),
            "remediation": f"Ensure caller has 'roles/backupdr.viewer' on project '{project_id}'."
        }, indent=2)


@mcp.tool()
def create_plan_association(project_id: str, location: str, plan_id: str, resource_uri: str, user_confirmed: bool = False) -> str:
    """
    Binds a Google Compute Engine virtual machine instance to a protection Backup Plan.
    Requires explicit user confirmation before applying policy mutation.

    Args:
        project_id: The target GCP Project ID.
        location: The target GCP region/location (e.g., us-central1).
        plan_id: Resource ID of the target Backup Plan.
        resource_uri: Full absolute GCP resource URL of the GCE instance to back up.
        user_confirmed: True only if the user explicitly confirmed this binding in chat.

    Returns:
        JSON string describing the created BackupPlanAssociation (BPA).
    """
    resource_name = resource_uri.split("/")[-1].lower()
    bpa_id = f"bpa-{resource_name}"

    if not user_confirmed:
        return json.dumps({
            "status": "MUTATION_CONFIRMATION_REQUIRED",
            "message": "Safeguard Guard: User approval is required before binding backup policies.",
            "mutation_details": {
                "action": "CREATE_BACKUP_PLAN_ASSOCIATION",
                "project_id": project_id,
                "location": location,
                "bpa_id": bpa_id,
                "target_plan": plan_id,
                "resource_uri": resource_uri
            },
            "remediation": "Prompt the user in chat to confirm this policy association before re-invoking with user_confirmed=True."
        }, indent=2)

    token, auth_err = get_auth_token()
    if auth_err:
        return json.dumps(auth_err, indent=2)

    url = f"https://backupdr.googleapis.com/v1/projects/{project_id}/locations/{location}/backupPlanAssociations?backupPlanAssociationId={bpa_id}"
    payload = {
        "resourceType": "compute.googleapis.com/Instance",
        "resource": resource_uri,
        "backupPlan": f"projects/{project_id}/locations/{location}/backupPlans/{plan_id}"
    }

    try:
        res = execute_rest_call(url, token, "POST", data=payload)
        return json.dumps({"status": "SUCCESS", "bpa": res}, indent=2)
    except Exception as e:
        return json.dumps({
            "status": "ERROR",
            "error_type": "PLAN_ASSOCIATION_FAILED",
            "component": "backupdr_mcp.create_plan_association",
            "message": str(e),
            "remediation": f"Ensure caller has 'roles/backupdr.admin' on project '{project_id}' and resource URI is valid."
        }, indent=2)


if __name__ == "__main__":
    mcp.run()
