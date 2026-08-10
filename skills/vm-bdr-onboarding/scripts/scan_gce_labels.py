#!/usr/bin/env python3
"""
scan_gce_labels.py

Discovers Google Compute Engine (GCE) instances in a specified project,
evaluates their configuration, labels, size, zone, and attached disks,
classifies them into BDR Protection Tiers (Tier 1/2/3), and saves the
inventory metadata.

Supports fallback static ingestion from CSV if live API is unavailable.
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone

# Attempt to import google-cloud-compute, but fallback gracefully if not installed
try:
    from google.cloud import compute_v1
    GCP_SDK_AVAILABLE = True
except ImportError:
    GCP_SDK_AVAILABLE = False


def parse_args():
    parser = argparse.ArgumentParser(description="Scan GCE instances and classify into BDR tiers.")
    parser.add_argument("--project-id", "-p", required=True, help="GCP Project ID to scan.")
    parser.add_argument("--output", "-o", default="assets/inventory.json", help="Path to write the classified inventory JSON.")
    parser.add_argument("--csv-fallback", "-c", help="Path to fallback CSV inventory file if GCP APIs are not used.")
    return parser.parse_args()


def classify_instance(labels, vcpus, ssd_size_gb):
    """
    Apply rule-based classification into Protection Tiers.
    """
    labels_lower = {k.lower(): v.lower() for k, v in labels.items()}
    
    # Tier 1 (Database/Critical)
    if (labels_lower.get("role") == "db" or 
        labels_lower.get("tier") == "critical" or 
        (vcpus >= 16 and ssd_size_gb >= 1024)):
        return "Tier 1", "Gold"
        
    # Tier 2 (Application/Production)
    if (labels_lower.get("env") in ["prod", "production", "staging"] or
        labels_lower.get("role") == "app"):
        return "Tier 2", "Silver"
        
    # Tier 3 (Dev/Test/Other)
    return "Tier 3", "Bronze"


def scan_live_gce(project_id):
    """
    Scans live Google Compute Engine instances using the official Python client.
    """
    if not GCP_SDK_AVAILABLE:
        raise RuntimeError("google-cloud-compute package is not installed. Please install it or use CSV fallback.")
        
    print(f"Connecting to Google Cloud APIs for project: {project_id}...")
    instance_client = compute_v1.InstancesClient()
    zone_client = compute_v1.ZonesClient()
    
    # Get all active zones in project
    try:
        zones = [z.name for z in zone_client.list(project=project_id)]
    except Exception as e:
        raise RuntimeError(f"Failed to authenticate or list zones: {e}")
        
    classified_instances = []
    
    for zone in zones:
        request = compute_v1.ListInstancesRequest(project=project_id, zone=zone)
        try:
            for instance in instance_client.list(request=request):
                # Extract disk configurations
                disks = []
                ssd_size_gb = 0
                for d in instance.disks:
                    # Parse size (approximate for client library)
                    disk_size = getattr(d, 'disk_size_gb', 50)  # default fallback
                    disk_type_url = getattr(d, 'source', '')
                    disk_type = "pd-standard"
                    if "pd-ssd" in disk_type_url or "ssd" in disk_type_url:
                        disk_type = "pd-ssd"
                        ssd_size_gb += disk_size
                    elif "pd-balanced" in disk_type_url:
                        disk_type = "pd-balanced"
                        
                    disks.append({
                        "name": d.device_name or "unknown",
                        "type": disk_type,
                        "size_gb": disk_size
                    })
                
                # Parse machine type to get approximate vCPUs (e.g., n2-standard-16)
                mtype = instance.machine_type.split('/')[-1] if instance.machine_type else "unknown"
                vcpus = 2  # standard default fallback
                try:
                    if "-" in mtype:
                        vcpus = int(mtype.split("-")[-1])
                except ValueError:
                    pass
                
                # Extract labels
                labels = dict(instance.labels) if instance.labels else {}
                
                # Classify
                classification, recommendation = classify_instance(labels, vcpus, ssd_size_gb)
                
                classified_instances.append({
                    "name": instance.name,
                    "zone": zone,
                    "machine_type": mtype,
                    "disks": disks,
                    "labels": labels,
                    "classification": classification,
                    "bdr_profile_recommendation": recommendation
                })
        except Exception as e:
            # Handle potential zone access permission issues gracefully
            print(f"Warning: Could not list instances in zone {zone}: {e}", file=sys.stderr)
            
    return classified_instances


def scan_csv_fallback(csv_path):
    """
    Parses a CSV file and mock-classifies the rows to simulate scanning.
    """
    print(f"Parsing static CSV inventory from: {csv_path}...")
    import csv
    classified_instances = []
    
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            vm_name = row.get("vm_name") or row.get("name", "unknown-vm")
            zone = row.get("zone", "us-central1-a")
            mtype = row.get("machine_type", "n1-standard-2")
            
            # Simple label parser from string e.g. "env=prod;role=db"
            labels = {}
            raw_labels = row.get("labels", "")
            if raw_labels:
                for pair in raw_labels.split(";"):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        labels[k.strip()] = v.strip()
                        
            # Disk mapping
            disk_size = int(row.get("disk_size_gb", "100"))
            disk_type = row.get("disk_type", "pd-standard")
            ssd_size = disk_size if disk_type == "pd-ssd" else 0
            
            vcpus = 2
            try:
                if "-" in mtype:
                    vcpus = int(mtype.split("-")[-1])
            except ValueError:
                pass
                
            classification, recommendation = classify_instance(labels, vcpus, ssd_size)
            
            classified_instances.append({
                "name": vm_name,
                "zone": zone,
                "machine_type": mtype,
                "disks": [{
                    "name": "data-disk",
                    "type": disk_type,
                    "size_gb": disk_size
                }],
                "labels": labels,
                "classification": classification,
                "bdr_profile_recommendation": recommendation
            })
            
    return classified_instances


def main():
    args = parse_args()
    
    try:
        if args.csv_fallback:
            instances = scan_csv_fallback(args.csv_fallback)
        else:
            if not GCP_SDK_AVAILABLE:
                print("Error: Google Cloud SDK client library not found.", file=sys.stderr)
                print("Please install 'google-cloud-compute' or use --csv-fallback.", file=sys.stderr)
                sys.exit(1)
            instances = scan_live_gce(args.project_id)
            
        payload = {
            "project_id": args.project_id,
            "scanned_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "instances": instances
        }
        
        # Ensure output directory exists
        out_dir = os.path.dirname(args.output)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            
        print(f"Successfully processed {len(instances)} instances.")
        print(f"Classified metadata written to: {args.output}")
        
    except Exception as e:
        print(f"Error executing scan: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
