#!/usr/bin/env python3
"""
associate_policy.py

Handles Backup and Disaster Recovery (BDR) policy execution:
1. Consumes the normalized workloads JSON artifact.
2. Locates target GCE VMs in GCP.
3. Checks current Backup Plan Association (BPA) status.
4. Associates unprotected instances with target Backup Plans.
5. Generates an execution report JSON.
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error

# Attempt to import GCP Authentication libraries
try:
    import google.auth
    from google.auth.transport.requests import Request
    GCP_AUTH_AVAILABLE = True
except ImportError:
    GCP_AUTH_AVAILABLE = False


def parse_args():
    parser = argparse.ArgumentParser(description="Associate GCP Backup & DR policies to GCE instances.")
    parser.add_argument("--input-file", "-i", default="normalized_workloads.json", help="Path to normalized workloads JSON.")
    parser.add_argument("--project-id", "-p", required=True, help="GCP Project ID.")
    parser.add_argument("--location", "-l", default="us-central1", help="GCP region/location.")
    parser.add_argument("--backup-plan-id", "-b", required=True, help="Backup Plan resource ID to bind.")
    parser.add_argument("--dry-run", action="store_true", help="Perform a simulation dry-run without making API calls.")
    parser.add_argument("--output-report", "-o", default="bdr_association_report.json", help="Path to write execution report.")
    return parser.parse_args()


def get_gcp_access_token():
    """
    Retrieves OAuth2 access token using google-auth library if available.
    """
    if not GCP_AUTH_AVAILABLE:
        return None
    try:
        credentials, project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(Request())
        return credentials.token
    except Exception as e:
        print(f"Warning: Could not get Google credentials: {e}", file=sys.stderr)
        return None


def gcp_request(url, token, method="GET", data=None):
    """
    Helper to send authenticated REST HTTP requests to GCP.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    req_data = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        try:
            return None, json.loads(err_msg)
        except ValueError:
            return None, {"error": {"message": err_msg, "code": e.code}}
    except Exception as e:
        return None, {"error": {"message": str(e), "code": 500}}


def fetch_live_gce_instances(project_id, token):
    """
    Fetches GCE instances across all zones using GCE aggregatedList REST API.
    """
    url = f"https://compute.googleapis.com/compute/v1/projects/{project_id}/aggregated/instances"
    res, err = gcp_request(url, token)
    if err:
        print(f"Error listing GCE instances: {err}", file=sys.stderr)
        return {}
        
    instances = {}
    for zone, zone_data in res.get("items", {}).items():
        for inst in zone_data.get("instances", []):
            name = inst.get("name")
            zone_name = zone.split("/")[-1]
            instances[name] = {
                "selfLink": inst.get("selfLink"),
                "zone": zone_name,
                "status": inst.get("status")
            }
    return instances


def fetch_current_bpa_associations(project_id, location, token):
    """
    Fetches existing BackupPlanAssociations for Backup & DR.
    """
    url = f"https://backupdr.googleapis.com/v1/projects/{project_id}/locations/{location}/backupPlanAssociations"
    res, err = gcp_request(url, token)
    if err:
        # If API is not enabled, list returns error. Handle gracefully.
        print(f"Warning: Could not list BPAs: {err}", file=sys.stderr)
        return []
    return res.get("backupPlanAssociations", [])


def create_backup_plan_association(project_id, location, bpa_id, instance_self_link, backup_plan_path, token):
    """
    POST request to bind the instance to the specified Backup Plan.
    """
    url = f"https://backupdr.googleapis.com/v1/projects/{project_id}/locations/{location}/backupPlanAssociations?backupPlanAssociationId={bpa_id}"
    payload = {
        "resourceType": "compute.googleapis.com/Instance",
        "resource": f"/{instance_self_link.replace('https://www.googleapis.com/', '')}",
        "backupPlan": backup_plan_path
    }
    return gcp_request(url, token, method="POST", data=payload)


def simulate_orchestration(workloads, backup_plan_id, location):
    """
    Simulates binding when dry-run or when credentials are not active.
    """
    print("\n--- Running BDR Orchestration Simulation (Dry Run) ---")
    
    successful = []
    skipped = []
    missing = []
    errors = []
    
    # Mocking live cloud discovery
    # We pretend that vms containing 'prod' are present in GCE, and others are missing.
    for wl in workloads:
        name = wl.get("name")
        source_id = wl.get("source_id")
        
        # Scenario rules for mock test
        if "dev" in name.lower() or "sandbox" in name.lower():
            # Pretend Dev machines were not migrated to GCP yet
            missing.append({
                "workload_name": name,
                "source_id": source_id,
                "reason": "Target instance not found in Google Compute Engine. Ensure VM is migrated before onboarding to BDR."
            })
        elif "replica" in name.lower():
            # Pretend it failed with a BDR permission/policy error
            errors.append({
                "workload_name": name,
                "source_id": source_id,
                "error_code": 403,
                "error_message": "Permission backupdr.backupPlanAssociations.create denied on backupPlan resource."
            })
        elif "existing" in name.lower():
            # Pretend it is already protected
            skipped.append({
                "workload_name": name,
                "source_id": source_id,
                "bpa_id": f"bpa-{name}-existing",
                "reason": "Already associated with Backup Plan."
            })
        else:
            # Successfully bind
            bpa_id = f"bpa-{name}"
            successful.append({
                "workload_name": name,
                "source_id": source_id,
                "bpa_id": bpa_id,
                "backup_plan": f"projects/mock-project/locations/{location}/backupPlans/{backup_plan_id}",
                "bpa_resource_path": f"projects/mock-project/locations/{location}/backupPlanAssociations/{bpa_id}"
            })
            
    return successful, skipped, missing, errors


def main():
    args = parse_args()
    
    if not os.path.exists(args.input_file):
        print(f"Error: Input file not found: {args.input_file}", file=sys.stderr)
        sys.exit(1)
        
    with open(args.input_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        workloads = data.get("workloads", [])
        
    print(f"Loaded {len(workloads)} normalized workloads from {args.input_file}.")
    
    token = get_gcp_access_token() if not args.dry_run else None
    
    # Run simulation if requested, or if no GCP credentials found
    if args.dry_run or not token:
        if not args.dry_run:
            print("No GCP credentials or authentication found. Defaulting to Simulation Mode...", file=sys.stderr)
        successful, skipped, missing, errors = simulate_orchestration(workloads, args.backup_plan_id, args.location)
    else:
        # LIVE EXECUTION MODE
        print(f"\n--- Running Live BDR Orchestration on Project {args.project_id} ---")
        successful, skipped, missing, errors = [], [], [], []
        
        # 1. Fetch live GCE targets
        gce_instances = fetch_live_gce_instances(args.project_id, token)
        print(f"Discovered {len(gce_instances)} live GCE instances.")
        
        # 2. Fetch current BDR Associations
        current_bpas = fetch_current_bpa_associations(args.project_id, args.location, token)
        # Create map of protected resource URLs to BPA resource ID
        protected_resources = {}
        for bpa in current_bpas:
            res_url = bpa.get("resource", "")
            protected_resources[res_url] = bpa.get("name")
            
        backup_plan_path = f"projects/{args.project_id}/locations/{args.location}/backupPlans/{args.backup_plan_id}"
        
        # 3. Match and Bind
        for wl in workloads:
            name = wl.get("name")
            source_id = wl.get("source_id")
            
            # Match by name
            if name not in gce_instances:
                missing.append({
                    "workload_name": name,
                    "source_id": source_id,
                    "reason": "GCE instance with this name was not found in the project inventory."
                })
                continue
                
            inst_data = gce_instances[name]
            self_link = inst_data["selfLink"]
            resource_url = f"//compute.googleapis.com/{self_link.replace('https://www.googleapis.com/', '')}"
            
            # Check if already protected
            if resource_url in protected_resources:
                skipped.append({
                    "workload_name": name,
                    "source_id": source_id,
                    "bpa_id": protected_resources[resource_url].split("/")[-1],
                    "reason": "Instance is already associated with a Backup Plan."
                })
                continue
                
            # Perform association binding
            bpa_id = f"bpa-{name.lower()}"
            print(f"Associating unprotected instance {name} with plan {args.backup_plan_id}...")
            res, err = create_backup_plan_association(
                args.project_id, args.location, bpa_id, self_link, backup_plan_path, token
            )
            
            if err:
                errors.append({
                    "workload_name": name,
                    "source_id": source_id,
                    "error_code": err.get("error", {}).get("code", 500),
                    "error_message": err.get("error", {}).get("message", "Unknown error")
                })
            else:
                successful.append({
                    "workload_name": name,
                    "source_id": source_id,
                    "bpa_id": bpa_id,
                    "backup_plan": backup_plan_path,
                    "bpa_resource_path": res.get("name")
                })
                
    # 4. Write Execution Report
    report = {
        "project_id": args.project_id,
        "location": args.location,
        "backup_plan_id": args.backup_plan_id,
        "summary": {
            "total_workloads_processed": len(workloads),
            "successful_bindings": len(successful),
            "skipped_already_protected": len(skipped),
            "missing_gce_targets": len(missing),
            "binding_failures": len(errors)
        },
        "successful_bindings": successful,
        "skipped_bindings": skipped,
        "missing_gce_targets": missing,
        "binding_failures": errors
    }
    
    with open(args.output_report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    print(f"\n--- BDR Execution Policy Association Summary ---")
    print(f"Successfully bound: {len(successful)}")
    print(f"Skipped (already protected): {len(skipped)}")
    print(f"Missing GCE targets: {len(missing)}")
    print(f"Binding API errors: {len(errors)}")
    print(f"Detailed execution report saved to: {args.output_report}")


if __name__ == "__main__":
    main()
