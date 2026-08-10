# GCE Discovery Skill

## Level-1 Metadata (Intent Matching)
```json
{
  "name": "gce-discovery",
  "description": "Scans Google Compute Engine (GCE) instances to discover labels, machine specs, attached disks, and OS types.",
  "intents": [
    "scan my GCE instances",
    "find unprotected VMs",
    "discover GCP workloads",
    "get GCE specs"
  ]
}
```

---

## Overview

The `gce-discovery` skill scans a target Google Cloud Platform (GCP) project to discover all running and stopped Google Compute Engine (GCE) instances. It extracts essential metadata (such as CPU, Memory, Disks, Labels, and Network IPs) to facilitate automated scoping, BDR onboarding, and compliance analysis.

## Standard Procedures

### 1. Verification of Prerequisites
- **Google Cloud SDK:** Ensure `gcloud` CLI is installed and authenticated.
- **Application Default Credentials:** Run `gcloud auth application-default login` if running locally.
- **Service API:** Ensure the `compute.googleapis.com` API is enabled in the target project.

### 2. Execution of Discovery
Run the provided discovery script to scan the project:
```bash
python3 scripts/scan_gce_inventory.py --project-id <GCP_PROJECT_ID> --output assets/gce_inventory.json
```

### 3. Output Asset Generation
The command produces a standardized `gce_inventory.json` file in the `assets/` directory.

#### Expected Output Schema
```json
{
  "project_id": "my-gcp-project",
  "scanned_at": "2026-08-10T15:00:00Z",
  "instances": [
    {
      "instance_name": "prod-app-01",
      "zone": "us-central1-a",
      "machine_type": "n2-standard-4",
      "disk_sizes_gb": [100, 500],
      "labels": {
        "env": "prod",
        "app": "frontend"
      },
      "network_ips": ["10.128.0.5"]
    }
  ]
}
```

---

## Integration with Onboarding
Once the GCE discovery metadata is generated:
1. Load `assets/gce_inventory.json` to identify unprotected VMs (those missing BDR tags or associations).
2. Delegate the resulting VM list to the `vm-bdr-onboarding` skill for classification and policy registration.
