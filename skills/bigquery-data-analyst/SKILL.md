# bigquery-data-analyst Skill

This skill provides pre-built SQL scripts, procedures, and guidance to query and analyze Google Cloud Billing BigQuery export tables. It specializes in isolating, aggregating, and projecting storage and egress costs associated with GCP Backup and Disaster Recovery (BDR).

---

## Level-1 Metadata (Intent Matching)
```json
{
  "name": "bigquery-data-analyst",
  "description": "Queries Google Cloud Billing BigQuery export tables to analyze historical, current, and projected backup storage spend and network egress costs.",
  "intents": [
    "query backup billing costs",
    "analyze BDR storage spend",
    "project monthly egress costs",
    "get backup billing sql"
  ]
}
```

---

## 1. Key Capabilities

The `bigquery-data-analyst` skill enables the following analytics workflows:

### A. SKU and Service Filtering
Identify exact billing rows matching Backup & DR and related snapshots:
- Filter service descriptions or IDs matching: `"Backup and DR"`, `"Backup Vault"`, or `"Cloud Storage Snapshot"`.

### B. Grouping & Granularity Analysis
Group historical billing records by:
- **GCP Project ID**: To identify which applications/workloads are driving the highest backup storage spend.
- **Region**: To optimize regional storage pricing differences.
- **Storage Tier**: Distinguish between Standard, Nearline, and Coldline tiers to recommend tiering optimizations.

### C. Cost Projections and Forecasting
- Analyze daily ingestion rates and storage accumulation trends to project future monthly spend.
- Calculate historical data growth curves to forecast year-over-year backup storage requirements.

---

## 2. Using Billing Query SQL Templates

Query templates are located in `references/billing-queries.sql`. These are standard Google SQL templates targeting the `gcp_billing_export_v1_*` tables.

### Quick Commands

```bash
# Example query dispatch using bq command line tool
bq query --use_legacy_sql=false < references/billing-queries.sql
```
