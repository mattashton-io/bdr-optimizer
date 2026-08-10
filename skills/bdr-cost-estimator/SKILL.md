# BDR Cost Estimator Skill

This skill calculates estimated licensing, storage, and cross-region egress spend for Google Cloud Backup and Disaster Recovery (BDR) across both simulated pre-migration environments and live GCP instances. It integrates custom pricing tools and standard platform discovery to deliver comparative financial analysis reports.

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

## 1. Input Ingestion Flexibility

The cost estimator skill processes workload capacity profiles from either active or pre-migration phases of the workload lifecycle:

### A. Pre-Migration Baseline (File Ingestion)
- **Artifact:** `normalized_workloads.json`
- **Source Tool:** Generated via `google/skills/code-interpreter` (which parses uploaded on-premises spreadsheets like a 100-VM RVTools xlsx/csv workbook).
- **Target Tag:** `"Pre-Migration Simulation (File Upload)"`

### B. Live GCP Infrastructure (Active Cloud Ingestion)
- **Artifact:** Direct query stream of GCE metadata.
- **Source Tool:** Scanned using `google/skills/gcp-compute` (which lists specifications of running GCE virtual machines and custom labels).
- **Target Tag:** `"Live GCP Infrastructure"`

---

## 2. Cost Sizing Mathematics & Pricing MCP Integration

When computing storage and licensing projections, the agent must leverage custom billing engines:

1. **Calculate Base Capacities:** Sum up total allocated/consumed disk capacity in Gigabytes (GB) across the identified workloads.
2. **Pricing MCP Invocation:** Call `mcp_servers/pricing_mcp.py` tool `estimate_vault_storage_cost(size_gib, retention_days, region)` to calculate baseline monthly fees:
   - **Vault Storage Rates:** Charged at regional unit rates (e.g., standard base of $\$0.026$ / GB / month for Backup Vault storage).
   - **BDR Management Licenses:** Add standard BDR management licensing fee ($\$0.010$ / GB / month) for protected workloads.
3. **Cross-Region Replication Egress (Optional):**
   - If the target Backup Vault resides in a secondary region for disaster recovery (cross-region replication):
     * Sum up the estimated daily egress bandwidth requirements (front-end data changes).
     * Multiply the egress volume by the regional egress unit fee (e.g., $\$0.12$ / GB for replication egress) to determine the net egress cost.

---

## 3. Structured Cost Reporting

### A. JSON Artifact
Write all compiled costs, metadata, and 30/90/365-day lifespans to the output JSON file: `cost_estimate_report.json` (complying with the standardized schema and correct estimate scope tag).

### B. Markdown Summary Table
In addition to generating the JSON artifact, the agent **MUST** present the user with a comparative markdown summary table. Use the following structured format:

#### Cost Sizing Estimate Scope: `<Scope_Tag>`

| Retention Window | Total Storage (GB) | Est. Storage Cost | Est. License Cost | Net Monthly Spend | Projected Annual Spend |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **30-Day Retention** | 10,240 GB | $266.24 | $102.40 | $368.64 | $4,423.68 |
| **90-Day Retention** | 16,384 GB (Accumulated) | $425.98 | $102.40 | $528.38 | $6,340.56 |
| **365-Day Retention** | 24,576 GB (Accumulated) | $638.98 | $102.40 | $741.38 | $8,896.56 |

---

## 4. Execution Guidance

Execute sizing calculator:
```bash
# Run calculation pipeline
python3 scripts/calculate_bdr_costs.py --input assets/normalized_workloads.json
```
