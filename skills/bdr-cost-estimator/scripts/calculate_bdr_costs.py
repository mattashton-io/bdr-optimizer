#!/usr/bin/env python3
"""
calculate_bdr_costs.py

Processes BDR sizing and cost calculations for either:
- On-premises normalized workload baselines (pre-migration)
- Active live GCP instance inventories
Outputs a standardized 'cost_estimate_report.json' artifact.
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone


def parse_args():
    parser = argparse.ArgumentParser(description="Calculate GCP Backup & DR costs from baseline or live files.")
    parser.add_argument("--input", "-i", required=True, help="Path to input JSON (normalized_workloads.json or gce_inventory.json).")
    parser.add_argument("--project-id", "-p", default="my-gcp-project", help="GCP Project ID.")
    parser.add_argument("--output", "-o", default="cost_estimate_report.json", help="Path to output cost report.")
    return parser.parse_args()


def calculate_pre_migration(data, project_id):
    """
    Computes pricing based on normalized workloads file.
    """
    workloads = data.get("workloads", [])
    total_vms = len(workloads)
    total_disk_gib = 0.0
    
    for wl in workloads:
        total_disk_gib += float(wl.get("total_disk_gib", 0))
        
    # Sizing unit rates
    vault_storage_rate = 0.026  # Standard vault rate
    management_rate = 0.010     # License rate
    
    monthly_storage = total_disk_gib * vault_storage_rate
    monthly_management = total_disk_gib * management_rate
    monthly_total = monthly_storage + monthly_management
    
    # Cost accumulation projection (assuming 5% data growth multiplier for 90 days and 20% for 365 days)
    projections = {
        "30_day_total": round(monthly_total, 2),
        "90_day_total": round(monthly_total * 3.0 * 1.05, 2),
        "365_day_total": round(monthly_total * 12.0 * 1.20, 2)
    }
    
    return {
        "estimate_scope": "Pre-Migration Baseline",
        "project_id": project_id,
        "calculated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "summary": {
            "total_workloads_evaluated": total_vms,
            "total_storage_gib": round(total_disk_gib, 2),
            "projected_monthly_storage_cost": round(monthly_storage, 2),
            "projected_monthly_management_cost": round(monthly_management, 2),
            "projected_monthly_total_cost": round(monthly_total, 2)
        },
        "projections": projections
    }


def calculate_live_infrastructure(data, project_id):
    """
    Computes pricing based on GCE live scanned inventories (grouping by disk types).
    """
    instances = data.get("instances", [])
    total_vms = len(instances)
    
    total_storage_gib = 0.0
    monthly_storage = 0.0
    
    # Rates per disk category
    rates = {
        "pd-standard": 0.026,
        "pd-balanced": 0.028,
        "pd-ssd": 0.030
    }
    
    for inst in instances:
        disks = inst.get("disk_sizes_gb", [])
        # Simple heuristic: map GCE instance profiles or machine types to default disk categories
        # For mock validation, if machine type contains 'n2' or 'ssd' we assume pd-ssd, else pd-balanced.
        mtype = str(inst.get("machine_type", "")).lower()
        if "n2" in mtype or "db" in mtype:
            disk_type = "pd-ssd"
        elif "e2" in mtype or "f1" in mtype:
            disk_type = "pd-standard"
        else:
            disk_type = "pd-balanced"
            
        disk_rate = rates[disk_type]
        
        for d_size in disks:
            size_gb = float(d_size)
            total_storage_gib += size_gb
            monthly_storage += size_gb * disk_rate
            
    # Licence fees apply for active protection
    management_rate = 0.010
    monthly_management = total_storage_gib * management_rate
    monthly_total = monthly_storage + monthly_management
    
    projections = {
        "30_day_total": round(monthly_total, 2),
        "90_day_total": round(monthly_total * 3.0 * 1.05, 2),
        "365_day_total": round(monthly_total * 12.0 * 1.20, 2)
    }
    
    return {
        "estimate_scope": "Live GCP Infrastructure",
        "project_id": project_id,
        "calculated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "summary": {
            "total_workloads_evaluated": total_vms,
            "total_storage_gib": round(total_storage_gib, 2),
            "projected_monthly_storage_cost": round(monthly_storage, 2),
            "projected_monthly_management_cost": round(monthly_management, 2),
            "projected_monthly_total_cost": round(monthly_total, 2)
        },
        "projections": projections
    }


def main():
    args = parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
        
    with open(args.input, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception as e:
            print(f"Error: Failed to parse input JSON: {e}", file=sys.stderr)
            sys.exit(1)
            
    # Determine source schema
    if "workloads" in data:
        report = calculate_pre_migration(data, args.project_id)
    elif "instances" in data:
        report = calculate_live_infrastructure(data, args.project_id)
    else:
        print("Error: Unrecognized input schema. Must contain 'workloads' or 'instances'.", file=sys.stderr)
        sys.exit(1)
        
    # Ensure target output directory exists
    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    print(f"Cost estimation successfully completed for scope: {report['estimate_scope']}.")
    print(f"Evaluated workloads: {report['summary']['total_workloads_evaluated']}")
    print(f"Projected Monthly Total: ${report['summary']['projected_monthly_total_cost']:.2f}")
    print(f"Report written to: {args.output}")


if __name__ == "__main__":
    main()
