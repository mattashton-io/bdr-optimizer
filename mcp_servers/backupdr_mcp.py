#!/usr/bin/env python3
"""
backupdr_mcp.py

Custom FastMCP Python server exposing tool bindings for the GCP Backup and DR REST API.
"""

import os
import sys
import json
import urllib.request
import urllib.error

# Try importing FastMCP from mcp.server.fastmcp
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    # Safe mock class if running in an environment without mcp installed
    print("Warning: 'mcp' SDK not found. Running in mock-server standby mode.", file=sys.stderr)
    class FastMCP:
        def __init__(self, name):
            self.name = name
        def tool(self):
            return lambda func: func

# Attempt to import GCP Authentication libraries
try:
    import google.auth
    from google.auth.transport.requests import Request
    GCP_AUTH_AVAILABLE = True
except ImportError:
    GCP_AUTH_AVAILABLE = False


# Initialize FastMCP Server
mcp = FastMCP("backupdr_mcp")


def get_auth_token():
    """
    Acquires Google OAuth2 token. Falls back to None if unavailable.
    """
    if not GCP_AUTH_AVAILABLE:
        return None
    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(Request())
        return credentials.token
    except Exception as e:
        print(f"Warning: Failed to acquire G Auth credentials: {e}", file=sys.stderr)
        return None


def execute_rest_call(url, token, method="GET", data=None):
    """
    Dispatches a direct HTTP REST request to backupdr.googleapis.com
    and handles specific error statuses (403, 409, 404, etc.)
    """
    if not token or "mock-project" in url:
        # Return mock response simulation if credentials are empty (local testing)
        return simulate_rest_call(url, method, data)
        
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    req_data = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        status_code = e.code
        err_msg = e.read().decode("utf-8")
        try:
            err_json = json.loads(err_msg)
            message = err_json.get("error", {}).get("message", err_msg)
        except ValueError:
            message = err_msg
            
        if status_code == 403:
            raise RuntimeError(f"GCP API Error 403 (IAM Permission Missing): The caller does not have authorization to perform this operation. Details: {message}")
        elif status_code == 409:
            raise RuntimeError(f"GCP API Error 409 (Conflict/Already Exists): The target resource already exists in this location. Details: {message}")
        elif status_code == 400:
            raise RuntimeError(f"GCP API Error 400 (Bad Request): Invalid parameters. Details: {message}")
        else:
            raise RuntimeError(f"GCP API Error {status_code}: {message}")
    except Exception as e:
        raise RuntimeError(f"Network error executing REST call: {e}")


def simulate_rest_call(url, method, data):
    """
    Simulated responses for testing the tool binding logic without active live tokens.
    """
    print(f"[SIMULATION] {method} request to: {url}", file=sys.stderr)
    if data:
        print(f"[SIMULATION] Request Payload: {json.dumps(data)}", file=sys.stderr)
        
    url_lower = url.lower()
    
    # 1. List Backup Vaults
    if "backupvaults" in url_lower and method == "GET":
        return {
          "backupVaults": [
            {
              "name": "projects/mock-project/locations/us-central1/backupVaults/vault-prod-gold",
              "state": "ACTIVE",
              "backupMinimumEnforcedRetentionDuration": "2592000s"
            },
            {
              "name": "projects/mock-project/locations/us-central1/backupVaults/vault-prod-silver",
              "state": "ACTIVE",
              "backupMinimumEnforcedRetentionDuration": "604800s"
            }
          ]
        }
        
    # 2. Create Backup Vault
    elif "backupvaults" in url_lower and method == "POST":
        vault_id = url.split("backupVaultId=")[-1] if "backupVaultId=" in url else "unknown-vault"
        if "conflict" in vault_id or "existing" in vault_id:
            raise RuntimeError("GCP API Error 409 (Conflict/Already Exists): Backup Vault already exists.")
        if "forbidden" in vault_id or "unauthorized" in vault_id:
            raise RuntimeError("GCP API Error 403 (IAM Permission Missing): Caller does not have backupdr.backupVaults.create permission.")
            
        return {
            "name": f"projects/mock-project/locations/us-central1/backupVaults/{vault_id}",
            "state": "CREATING",
            "backupMinimumEnforcedRetentionDuration": data.get("backupMinimumEnforcedRetentionDuration", "0s")
        }
        
    # 3. List Backup Plans
    elif "backupplans" in url_lower and method == "GET":
        return {
          "backupPlans": [
            {
              "name": "projects/mock-project/locations/us-central1/backupPlans/gold-db-policy",
              "description": "Gold backup plan (Daily backups, 30 days retention)"
            },
            {
              "name": "projects/mock-project/locations/us-central1/backupPlans/silver-app-policy",
              "description": "Silver backup plan (Daily backups, 14 days retention)"
            }
          ]
        }
        
    # 4. Create Plan Association (BPA)
    elif "backupplanassociations" in url_lower and method == "POST":
        bpa_id = url.split("backupPlanAssociationId=")[-1] if "backupPlanAssociationId=" in url else "bpa-unknown"
        if "forbidden" in bpa_id:
            raise RuntimeError("GCP API Error 403 (IAM Permission Missing): Caller does not have backupdr.backupPlanAssociations.create permission.")
            
        return {
            "name": f"projects/mock-project/locations/us-central1/backupPlanAssociations/{bpa_id}",
            "resource": data.get("resource"),
            "backupPlan": data.get("backupPlan")
        }
        
    return {"message": "Simulated request completed."}


# --- FASTMCP TOOL BINDINGS ---

@mcp.tool()
def list_backup_vaults(project_id: str, location: str) -> str:
    """
    Lists all active Backup Vaults in a project and location.
    
    Args:
        project_id: The target GCP Project ID.
        location: The target GCP region/location (e.g., us-central1).
        
    Returns:
        JSON string containing the list of backup vaults with names, states, and retention profiles.
    """
    token = get_auth_token()
    url = f"https://backupdr.googleapis.com/v1/projects/{project_id}/locations/{location}/backupVaults"
    
    try:
        res = execute_rest_call(url, token, "GET")
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


@mcp.tool()
def create_backup_vault(project_id: str, location: str, vault_id: str, retention_days: int) -> str:
    """
    Creates a new Backup Vault with a minimum enforced retention in days.
    
    Args:
        project_id: The target GCP Project ID.
        location: The target GCP region/location (e.g., us-central1).
        vault_id: Name of the Backup Vault to create.
        retention_days: Number of days for the minimum enforced immutable retention lock.
        
    Returns:
        JSON string with creation progress, name, and configuration details.
    """
    token = get_auth_token()
    url = f"https://backupdr.googleapis.com/v1/projects/{project_id}/locations/{location}/backupVaults?backupVaultId={vault_id}"
    
    # Convert retention days to seconds string required by GAPI (e.g., "86400s")
    seconds_duration = f"{retention_days * 86400}s"
    payload = {
        "description": "Created via Backup & DR Custom FastMCP Server",
        "backupMinimumEnforcedRetentionDuration": seconds_duration
    }
    
    try:
        res = execute_rest_call(url, token, "POST", data=payload)
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


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
    token = get_auth_token()
    url = f"https://backupdr.googleapis.com/v1/projects/{project_id}/locations/{location}/backupPlans"
    
    try:
        res = execute_rest_call(url, token, "GET")
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


@mcp.tool()
def create_plan_association(project_id: str, location: str, plan_id: str, resource_uri: str) -> str:
    """
    Binds a Google Compute Engine virtual machine instance to a protection Backup Plan.
    
    Args:
        project_id: The target GCP Project ID.
        location: The target GCP region/location (e.g., us-central1).
        plan_id: Resource ID of the target Backup Plan.
        resource_uri: Full absolute GCP resource URL of the GCE instance to back up.
        
    Returns:
        JSON string describing the created BackupPlanAssociation (BPA).
    """
    token = get_auth_token()
    
    # Derive a clean association ID (e.g., bpa-prod-db-01)
    resource_name = resource_uri.split("/")[-1].lower()
    bpa_id = f"bpa-{resource_name}"
    
    url = f"https://backupdr.googleapis.com/v1/projects/{project_id}/locations/{location}/backupPlanAssociations?backupPlanAssociationId={bpa_id}"
    
    payload = {
        "resourceType": "compute.googleapis.com/Instance",
        "resource": resource_uri,
        "backupPlan": f"projects/{project_id}/locations/{location}/backupPlans/{plan_id}"
    }
    
    try:
        res = execute_rest_call(url, token, "POST", data=payload)
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


if __name__ == "__main__":
    # If run directly, run the FastMCP server
    if "FastMCP" in globals() and hasattr(mcp, "run"):
        mcp.run()
    else:
        # CLI tool test
        print("FastMCP execution interface is currently mocked.", file=sys.stderr)
        # Test individual functions in standby mode
        print(list_backup_vaults("mock-project", "us-central1"))
