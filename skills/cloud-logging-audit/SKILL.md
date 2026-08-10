# cloud-logging-audit Skill

This skill provides a structured framework for searching, parsing, and auditing Cloud Audit Logs and operational logs from GCP Backup and Disaster Recovery (BDR). It enables engineers to monitor backup execution, diagnose pipeline errors, and track administration operations.

---

## Level-1 Metadata (Intent Matching)
```json
{
  "name": "cloud-logging-audit",
  "description": "Searches Cloud Audit Logs and BDR operational logs to track backup job execution status, detect snapshot failures, and audit IAM activity.",
  "intents": [
    "query backup audit logs",
    "find failed backup jobs",
    "audit who deleted backup vault",
    "check BDR error logs"
  ]
}
```

---

## 1. Key Capabilities

The `cloud-logging-audit` skill empowers the following logging workflows:

### A. Operational Logging Queries
Apply specific log query filters to retrieve active resource activities:
- **Filter pattern:** `resource.type="backupdr.googleapis.com/BackupVault"` or `resource.type="backupdr.googleapis.com/BackupPlanAssociation"`

### B. Error and Failure Detection
Scan logs to isolate operational failures:
- Identify aborted backup schedules, API timeout errors, and Google Cloud Storage (GCS) transfer failures.
- Detect authentication and `PERMISSION_DENIED` errors on IAM backup service accounts.

### C. Admin & Security Audit Trail
Audit management plane operations:
- Identify which user or service account initiated actions such as `CreateBackupVault`, `DeleteBackupVault`, `UpdateBackupPlan`, or `DeleteBackupPlanAssociation`.
- Verify caller identities and source IP addresses in security reports.

---

## 2. Executing Queries via Python Utility

Use the `scripts/query_audit_logs.py` script to fetch, filter, and output structured logs:

```bash
# Query logs for the past 48 hours for a given project
python3 scripts/query_audit_logs.py --project-id <GCP_PROJECT_ID> --hours 48
```
