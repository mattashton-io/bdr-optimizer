#!/usr/bin/env python3
"""
query_audit_logs.py

Queries Google Cloud Logging for Backup and Disaster Recovery (BDR) service logs,
focusing on errors, warnings, and administrative audit trails over the past 24-72 hours.
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta, timezone

# Attempt to import Google Cloud Logging library
try:
    from google.cloud import logging as gcp_logging
    GCP_LOGGING_AVAILABLE = True
except ImportError:
    GCP_LOGGING_AVAILABLE = False


def parse_args():
    parser = argparse.ArgumentParser(description="Query GCP BDR audit and error logs.")
    parser.add_argument("--project-id", "-p", required=True, help="GCP Project ID to query.")
    parser.add_argument("--hours", "-t", type=int, default=24, help="Query window in hours (24-72).")
    parser.add_argument("--output", "-o", default="bdr_audit_logs.json", help="Path to save the logs JSON output.")
    parser.add_argument("--dry-run", action="store_true", help="Perform a simulated query execution.")
    return parser.parse_args()


def query_live_logs(project_id, hours):
    """
    Queries live Google Cloud Logging using the official client library.
    """
    if not GCP_LOGGING_AVAILABLE:
        raise RuntimeError("google-cloud-logging package is not installed. Use --dry-run or install it.")
        
    client = gcp_logging.Client(project=project_id)
    
    # Calculate timestamp filter
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    timestamp_filter = cutoff_time.isoformat()
    
    # Construct robust log filter for Backup & DR and related cloud audit logs
    log_filter = (
        f'timestamp >= "{timestamp_filter}" AND '
        f'(resource.type:"backupdr" OR '
        f'logName:"cloudaudit.googleapis.com" OR '
        f'protoPayload.serviceName="backupdr.googleapis.com") AND '
        f'severity >= WARNING'
    )
    
    print(f"Connecting to Cloud Logging for project {project_id}...")
    print(f"Filter payload: {log_filter}")
    
    entries = client.list_entries(filter_=log_filter, page_size=100)
    
    results = []
    for entry in entries:
        # Standardize audit/log properties
        payload = entry.payload
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
            
        results.append({
            "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
            "insert_id": entry.insert_id,
            "severity": entry.severity,
            "log_name": entry.log_name,
            "resource_type": entry.resource.type if entry.resource else "unknown",
            "payload": payload,
            "principal_email": entry.http_request.get("principalEmail") if entry.http_request else None
        })
        
    return results


def query_simulated_logs(project_id, hours):
    """
    Generates realistic GCP BDR audit trail scenarios for testing/dry-runs.
    """
    print("\n--- Running Simulated BDR Log Audit Query ---")
    
    now = datetime.now(timezone.utc)
    
    return [
        {
            "timestamp": (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            "insert_id": "ins-92849184",
            "severity": "ERROR",
            "log_name": f"projects/{project_id}/logs/backupdr.googleapis.com%2Foperational_logs",
            "resource_type": "backupdr.googleapis.com/BackupPlanAssociation",
            "payload": {
                "message": "Backup job failed for target VM: prod-sql-replica. Execution timed out after 120 minutes during snapshot transfer.",
                "job_id": "job-88392-18",
                "error_details": {
                    "code": "DEADLINE_EXCEEDED",
                    "source": "GCS_UPLOADER"
                }
            },
            "principal_email": "bdr-agent-sa@my-gcp-project.iam.gserviceaccount.com"
        },
        {
            "timestamp": (now - timedelta(hours=5)).isoformat().replace("+00:00", "Z"),
            "insert_id": "ins-91028394",
            "severity": "WARNING",
            "log_name": f"projects/{project_id}/logs/cloudaudit.googleapis.com%2Factivity",
            "resource_type": "backupdr.googleapis.com/BackupVault",
            "payload": {
                "methodName": "google.cloud.backupdr.v1.BackupDR.DeleteBackupVault",
                "status": {
                    "code": 9,
                    "message": "FAILED_PRECONDITION: Cannot delete backup vault with active immutable locks."
                },
                "resourceName": f"projects/{project_id}/locations/us-central1/backupVaults/immutable-vault-prod"
            },
            "principal_email": "admin-auditor@my-company.com"
        },
        {
            "timestamp": (now - timedelta(hours=12)).isoformat().replace("+00:00", "Z"),
            "insert_id": "ins-83749102",
            "severity": "WARNING",
            "log_name": f"projects/{project_id}/logs/backupdr.googleapis.com%2Foperational_logs",
            "resource_type": "backupdr.googleapis.com/BackupPlanAssociation",
            "payload": {
                "message": "Backup plan association bpa-dev-app-worker modified. Protection policy retention was decreased from 14 days to 7 days.",
                "bpa_id": "bpa-dev-app-worker"
            },
            "principal_email": "dev-ops-engineer@my-company.com"
        }
    ]


def main():
    args = parse_args()
    
    # Enforce hours constraints
    if args.hours < 24 or args.hours > 72:
        print("Error: Query window --hours must be between 24 and 72.", file=sys.stderr)
        sys.exit(1)
        
    try:
        if args.dry_run or not GCP_LOGGING_AVAILABLE:
            if not args.dry_run:
                print("Notice: 'google-cloud-logging' client library not found. Falling back to simulation mode...", file=sys.stderr)
            entries = query_simulated_logs(args.project_id, args.hours)
        else:
            entries = query_live_logs(args.project_id, args.hours)
            
        payload = {
            "project_id": args.project_id,
            "query_window_hours": args.hours,
            "extracted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "total_entries": len(entries),
            "log_entries": entries
        }
        
        # Ensure output directory exists
        out_dir = os.path.dirname(args.output)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            
        print(f"Successfully retrieved and parsed {len(entries)} operational logs.")
        print(f"Audit log output exported to: {args.output}")
        
    except Exception as e:
        print(f"Error querying GCP logs: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
