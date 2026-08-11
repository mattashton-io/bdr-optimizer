# BDR Vault Orchestration Skill

This skill governs the configuration, health, cost-efficiency, and active policy binding of GCP Backup and Disaster Recovery (BDR) Backup Vaults and BackupPlanAssociations (BPA). It leverages standard Google ecosystem skills and custom FastMCP servers to discover running workloads and enforce backup compliance.

---

## Level-1 Metadata (Intent Matching)
```json
{
  "name": "vault-orchestration",
  "description": "Orchestrates Backup Vault creation, fetches active backup policies, and associates live Compute Engine VMs with Backup Plans.",
  "intents": [
    "create backup plan association",
    "list active backup plans",
    "bind GCE vm to gold backup policy",
    "audit live GCP protection"
  ]
}
```

---

## 1. Live Infrastructure Discovery

For real-time cloud audits and compliance scoping, the agent must perform GCE instance discovery:
- **Execution Tool:** Delegate to the standard ecosystem skill `google/skills/gcp-compute` to retrieve real-time configurations by scanning live GCE instances.
- **Data Captured:** Discover running GCE instances, their machine types, deployment zones, attached disk footprints, and custom metadata labels.
- **Caching:** Output the running cloud footprint to `assets/live_cloud_inventory.json` (to enable comparative cost modeling).

---

## 2. Backup Policy Evaluation & Protection Gaps

Before binding new backup rules, evaluate the active security baseline of the target project location using standard BDR tools:
1. **Fetch Configured Plans:** Call the `'backupdr_mcp'` tool `list_backup_plans(project_id, location)` to compile a list of available Gold, Silver, and Bronze backup schedules.
2. **Fetch Active Vaults:** Call the `'backupdr_mcp'` tool `list_backup_vaults(project_id, location)` to locate active secure repositories and verify minimum enforced retention locks.
3. **Cross-Reference Protection Gaps:**
   - Query the GCP Backup & DR REST API or the `'backupdr_mcp'` tools to fetch existing `BackupPlanAssociations` (BPA).
   - Cross-reference the discovered GCE instances scanned by `google/skills/gcp-compute` against the retrieved active BPAs.
   - Automatically flag any running GCE virtual machine lacking a corresponding BPA as **Unprotected**.

---

## 3. Action Execution & Safeguard Protocol

### A. Mutation Confirmation Guard (Mandatory Safety Check)
Before calling the `'backupdr_mcp'` tools `create_plan_association` or `create_backup_vault` to modify GCP project states, the agent **MUST** request explicit, clear confirmation from the user in the chat interface. 

The confirmation request must specify:
- **Action Type:** (e.g., Create Backup Vault or Bind GCE VM to Backup Plan)
- **Target VM Name & Zone**
- **Selected Backup Plan & Vault Name**
- **Enforced Immutable Retention Period** (e.g., `"2592000s"` / 30 days)

*CRITICAL SAFEGUARD:* Do not execute any mutation or API call (`create_plan_association`, `create_backup_vault`) unless the user has provided explicit approval in chat.

### B. Execution Logging
Upon successful registration of any new BackupPlanAssociation (BPA) or Vault, append an audit entry to `execution_summary.json`:

```json
{
  "action": "CREATE_BACKUP_PLAN_ASSOCIATION",
  "timestamp": "2026-08-10T16:00:00Z",
  "caller": "gcp-bdr-orchestrator",
  "details": {
    "vm_name": "prod-sql-primary",
    "zone": "us-central1-a",
    "backup_plan": "projects/my-gcp-project/locations/us-central1/backupPlans/gold-db-policy",
    "association_id": "bpa-prod-sql-primary",
    "status": "BOUND"
  }
}
```
