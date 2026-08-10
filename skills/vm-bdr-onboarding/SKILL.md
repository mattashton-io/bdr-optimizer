# VM BDR Onboarding Skill

This skill provides a structured framework for discovering, evaluating, classifying, and onboarding VMware (vSphere), Hyper-V, and other Non-VMware Virtual Machines (VMs) into GCP Backup and Disaster Recovery (BDR). It enables comparing target physical/on-premises baselines with actual GCP cloud configurations to identify optimization and gaps.

---

## 1. Data Ingestion Paths

Onboarding supports two distinct on-premises hypervisor source ingestion paths. Column names and syntax must **match these schemas exactly** to prevent parsing failures in automated ingestion workflows.

### Path 1: VMware (vSphere) Sources (RVTools)
The primary ingestion format for VMware environments is the RVTools export (either an `.xlsx` workbook containing these sheets, or separate `.csv` exports representing each tab).

#### `vInfo` Schema
```
VM, Powerstate, Template, Config status, DNS Name, Connection state, Guest state, CPUs, Memory, Active Memory, NICs, Disks, Total disk capacity MiB, Provisioned MiB, In Use MiB, Primary IP Address, Network #1, Datacenter, Cluster, Host, Folder, OS according to the configuration file, OS according to the VMware Tools, VM ID, VM UUID, VI SDK Server, VI SDK API Version
```

#### `vCPU` Schema
```
VM, Powerstate, CPUs, Sockets, Cores p/s, Cluster, Host, OS according to the configuration file, OS according to the VMware Tools, VM ID, VM UUID, VI SDK Server
```

#### `vMemory` Schema
```
VM, Powerstate, Size MiB, Consumed, Cluster, Host, OS according to the configuration file, VM ID, VM UUID, VI SDK Server
```

#### `vDisk` Schema
```
VM, Powerstate, Disk, Disk Key, Capacity MiB, Disk Mode, Thin, Controller, Disk Path, Raw Comp. Mode, Datacenter, Cluster, Host, OS according to the configuration file, OS according to the VMware Tools, VM ID, VM UUID, VI SDK Server
```

---

### Path 2: Hyper-V or Non-VMware (e.g., Nutanix) Sources
For Non-VMware hypervisors, manual data upload templates compliant with the GCP Migration Center schema are required. Files must be uploaded to the `assets/migration-center-manual-upload/` directory.

#### `vmInfo.csv` Schema
```
MachineId, MachineName, PrimaryIPAddress(optional), PrimaryMACAddress(optional), PublicIPAddress(optional), IpAddressListSemiColonDelimited(optional), TotalDiskAllocatedGiB, TotalDiskUsedGiB, MachineTypeLabel(optional), AllocatedProcessorCoreCount, MemoryGiB, HostingLocation(optional), OsType(optional), OsPublisher(optional), OsName, OsVersion(optional), MachineStatus(optional), ProvisioningState(optional), CreateDate(optional), IsPhysical
```

#### `diskInfo.csv` Schema
```
MachineId, DiskLabel, SizeInGib, UsedInGib, StorageTypeLabel
```

#### `perfInfo.csv` Schema
```
MachineId, TimeStamp, CpuUtilizationPercentage, MemoryUtilizationPercentage(optional), AvailableMemoryBytes, DiskReadOperationsPerSec, DiskWriteOperationsPerSec, NetworkBytesPerSecSent, NetworkBytesPerSecReceived
```

---

## 2. Configuration Evaluation

Before classifying VMs, analyze core resources from either path:
1. **Labels & Metadata:** Inspect existing guest labels, folders, or machine-type tags to identify business groupings (e.g., `env=prod`, `role=db`).
2. **Sizing Evaluation:**
   - Compute: vCPUs, sockets, cores per socket, and CPU utilization (from `perfInfo.csv` or active memory).
   - Memory: Total size (MiB/GiB) and utilization metrics.
3. **Storage Configuration:** Total allocated vs. active usage (e.g., `In Use MiB`, `TotalDiskUsedGiB`, thin/thick provisioning status, storage disk mode).
4. **Placement Context:** Host, Datacenter, Cluster, or Hosting Location to plan recovery zone/region affinity.

---

## 3. Protection Tier Classification

Workloads are classified into standardized BDR Protection Tiers:

| Protection Tier | Workload Example | RPO / RTO | Default BDR Profile |
| :--- | :--- | :--- | :--- |
| **Tier 1 (Database)** | SQL Server, SAP HANA, Oracle, PostgreSQL | RPO: 15 min / RTO: 1 hr | **Gold (Immutable, Cross-Region)** |
| **Tier 2 (Application)**| Production API servers, Middleware | RPO: 4 hrs / RTO: 4 hrs | **Silver (Daily, Cross-Zone)** |
| **Tier 3 (Dev/Test)** | Dev sandboxes, non-critical systems | RPO: 24 hrs / RTO: 24 hrs | **Bronze (Daily, Local-only)** |

### Classification Rules:
- **Rule 1 (Tier 1):** VM contains `db`, `oracle`, `sap`, or `sql` in name or labels, OR has Allocated CPUs $\ge 16$ and Disk capacity $\ge 1024$ GB.
- **Rule 2 (Tier 2):** VM name or folder path contains `prod`, `prd`, `staging`, or `stg`.
- **Rule 3 (Tier 3):** VM name/folder contains `dev`, `tst`, `sandbox`, or has label `bdr-opt-out=true`.

---

## 4. Live GCE API Comparison and Cloud Validation

To reconcile the baseline on-premises sizing with what is actually running in Google Cloud, utilize the `scripts/scan_gce_labels.py` utility.

### Process:
1. **Live Discovery:** Run the discovery script to collect real-time configuration of migrated instances:
   ```bash
   python3 scripts/scan_gce_labels.py --project-id <gcp-project-id> --output assets/live_cloud_inventory.json
   ```
2. **Baseline Reconciliation:** Compare `live_cloud_inventory.json` with the uploaded RVTools or Migration Center baselines (`vmInfo.csv`/`vInfo`).
3. **Sizing Delta Report:** Highlight instances where actual cloud sizing deviates from the recommended on-premises baseline (e.g., over-provisioned vCPUs or unattached disks).

---

## 5. Expected Output Metadata Schema

After merging and classifying baseline configurations, the aggregated inventory metadata should adhere to this JSON format:

```json
{
  "project_id": "my-gcp-project",
  "scanned_at": "2026-08-10T14:30:00Z",
  "source_platform": "VMware-vSphere",
  "instances": [
    {
      "name": "prod-sql-01",
      "source_id": "vm-92841",
      "allocated_cpus": 16,
      "memory_gib": 64.0,
      "total_disk_allocated_gib": 2048.0,
      "classification": "Tier 1",
      "bdr_profile_recommendation": "Gold",
      "reconciliation_status": "Migrated",
      "gcp_instance_name": "gce-prod-sql-01"
    }
  ]
}
```

---

## 6. Sizing & Cost Estimator Delegation

Once workloads are classified and grouped, cost modeling must be delegated to the `bdr-cost-estimator` skill.

### Delegation Protocol:
1. **Aggregate Grouping:** Compute total Front-End Capacity (TB) and CPU/Memory totals for each protection tier.
2. **Invoke Estimator:** Pass the classified baseline data payload to the estimator:
   ```bash
   agy run bdr-cost-estimator --inventory-file assets/live_cloud_inventory.json
   ```
3. **Execution Formula:** The `bdr-cost-estimator` calculates the final BDR licensing and vault storage fees:
   $$\text{BDR Fee} = (\text{Front-End Capacity (TB)} \times \text{License Rate}) + (\text{Back-End Storage (TB)} \times \text{Vault Storage Rate})$$
