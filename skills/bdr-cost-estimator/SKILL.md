# BDR Cost Estimator Skill

This skill calculates estimated licensing, storage, and egress spend for Google Cloud Backup and Disaster Recovery (BDR) across both pre-migration planning inventories and live GCP environments.

---

## Level-1 Metadata (Intent Matching)
```json
{
  "name": "bdr-cost-estimator",
  "description": "Estimates Backup & DR storage, licensing, and replication costs for on-premises baselines and active live GCP infrastructures.",
  "intents": [
    "estimate BDR costs",
    "calculate backup storage price",
    "project pre-migration backup spend",
    "generate BDR cost report"
  ]
}
```

---

## 1. Input Source Flexibility

The `bdr-cost-estimator` skill is designed to ingest and parse BDR source inventories from two distinct formats representing different phases of the cloud lifecycle:

### Source Type A: Pre-Migration Baseline
- **Artifact:** `normalized_workloads.json`
- **Context:** Compiled from on-premises uploads (e.g., 100-VM RVTools sheets or Migration Center csv files).
- **Target Tag:** `"Pre-Migration Baseline"`

### Source Type B: Live GCP Infrastructure
- **Artifact:** `gce_inventory.json`
- **Context:** Compiled from active live scans of Compute Engine virtual machines.
- **Target Tag:** `"Live GCP Infrastructure"`

---

## 2. Sizing and Cost Calculations

Depending on the identified input source type, apply the corresponding calculation formulas and unit cost models:

### Calculation Path A: File-Based Pre-Migration Baseline
For on-premises datasets, compute capacity sizing using active VMware/Hyper-V sizing metrics:
- **Metrics utilized:** `total_disk_gib` or `Total disk capacity MiB` / `Provisioned MiB` / `In Use MiB`.
- **Formulas:**
  - Convert MiB to GiB (if necessary): $\text{Size (GiB)} = \text{Size (MiB)} / 1024$.
  - Calculate Base Monthly Cost:
    $$\text{Monthly Cost} = \text{Capacity (GiB)} \times \text{Regional Vault Rate (\$/GB)}$$
  - Cost Lifespans:
    * **30-Day Cost:** $\text{Monthly Cost}$
    * **90-Day Cost:** $\text{Monthly Cost} \times 3.0 \times \text{retention_accumulation_multiplier}$
    * **365-Day Cost:** $\text{Monthly Cost} \times 12.0 \times \text{retention_accumulation_multiplier}$

### Calculation Path B: Active Live GCP Infrastructure
For live running instances, use disk sizes and GCE disk-type characteristics to compute active snapshot and vault rates:
- **Disk Type Rates (Standard US Regional):**
  - `pd-standard` (HDD): Vault Storage = $\$0.026$ / GB / month.
  - `pd-balanced` (Balanced SSD): Vault Storage = $\$0.028$ / GB / month.
  - `pd-ssd` (Performance SSD): Vault Storage = $\$0.030$ / GB / month.
- **Formulas:**
  - Group total storage capacity separately by disk type.
  - Apply the corresponding disk type rate to each capacity bucket to compute the net storage fees.
  - Add the standard BDR management fee ($\$0.010$ / GB / month) for protected workloads.

---

## 3. Output Artifact Schema

No matter which source is processed, output a standardized JSON report saved to `cost_estimate_report.json`:

```json
{
  "estimate_scope": "Pre-Migration Baseline" | "Live GCP Infrastructure",
  "project_id": "my-gcp-project",
  "calculated_at": "2026-08-10T15:00:00Z",
  "summary": {
    "total_workloads_evaluated": 100,
    "total_storage_gib": 102400.0,
    "projected_monthly_storage_cost": 2662.40,
    "projected_monthly_management_cost": 1024.00,
    "projected_monthly_total_cost": 3686.40
  },
  "projections": {
    "30_day_total": 3686.40,
    "90_day_total": 11059.20,
    "365_day_total": 44236.80
  }
}
```
---

## 4. Execution Guidance

Trigger cost estimation scans via standard CLI:
```bash
# Sizing and cost calculation execution
python3 scripts/calculate_bdr_costs.py --input assets/normalized_workloads.json
```
