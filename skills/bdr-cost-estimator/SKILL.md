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

The cost estimator skill accepts capacity profiles from either active infrastructure or pre-migration phases of the workload lifecycle:

### A. Pre-Migration Baseline (File Ingestion)
- **Artifact:** `normalized_workloads.json` (e.g., generated from the 100-VM RVTools mock file or Migration Center templates).
- **Source Tool:** Generated via `google/skills/code-interpreter` (which parses uploaded on-premises spreadsheets).
- **Target Tag:** `"Pre-Migration Simulation (File Upload)"`

### B. Live GCP Infrastructure (Active Cloud Ingestion)
- **Artifact:** Direct query stream of GCE metadata.
- **Source Tool:** Scanned using `google/skills/gcp-compute` (which lists specifications of running GCE virtual machines and custom labels).
- **Target Tag:** `"Live GCP Infrastructure"`

---

## 2. Cost Sizing Mathematics & Pricing MCP Integration

When computing storage and licensing projections, the agent must leverage the custom billing engine:

1. **Calculate Base Capacities:** Sum up total allocated/consumed disk capacity in Gigabytes (GB) across the identified workloads (from either `normalized_workloads.json` or live GCE instances retrieved via `google/skills/gcp-compute`).
2. **Pricing MCP Invocation:** Call the `'pricing_mcp'` tool `estimate_vault_storage_cost(size_gib, retention_days, region)` to calculate baseline monthly fees for three specific retention windows:
   - **30-Day Retention**
   - **90-Day Retention**
   - **365-Day Retention**
3. **Regional Rates & Licensing:** Include BDR management licensing fees alongside Backup Vault storage rates returned by the `'pricing_mcp'` tool.

---

## 3. Structured Cost Reporting Comparison Table

The agent **MUST** present the user with a comparative markdown summary table directly in the chat interface using values retrieved from the `'pricing_mcp'` tool.

### Comparative Cost Sizing Estimate Scope: `<Scope_Tag>`

| Retention Window | Total Storage (GB) | Est. Storage Cost | Est. License Cost | Net Monthly Spend | Projected Annual Spend |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **30-Day Retention** | 10,240 GB | $266.24 | $102.40 | $368.64 | $4,423.68 |
| **90-Day Retention** | 16,384 GB (Accumulated) | $425.98 | $102.40 | $528.38 | $6,340.56 |
| **365-Day Retention** | 24,576 GB (Accumulated) | $638.98 | $102.40 | $741.38 | $8,896.56 |

*Note: Write the complete compiled costs and lifecycle reports to the output JSON file: `cost_estimate_report.json` as well.*

---

## 4. Execution Guidance

Execute sizing calculator:
```bash
# Run calculation pipeline
python3 scripts/calculate_bdr_costs.py --input assets/normalized_workloads.json
```
