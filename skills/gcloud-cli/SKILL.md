# gcloud-cli Skill

This skill enables direct, secure execution of Google Cloud SDK (`gcloud`) command-line operations inside a managed shell context. It provides quick access to inspect, query, and modify resources for Google Compute Engine and GCP Backup & DR.

---

## Level-1 Metadata (Intent Matching)
```json
{
  "name": "gcloud-cli",
  "description": "Executes gcloud CLI commands to inspect and configure GCP resources (Compute Engine, Backup & DR, IAM).",
  "intents": [
    "list backup vaults",
    "gcloud list instances",
    "create backup plan association",
    "verify gcloud project"
  ]
}
```

---

## 1. Operational Scope

The `gcloud-cli` skill is authorized to operate on the following command scopes:

### Google Compute Engine (GCE)
- `gcloud compute instances list`
- `gcloud compute disks list`

### GCP Backup and Disaster Recovery (Backup & DR)
- `gcloud backup-dr backup-vaults list`
- `gcloud backup-dr backup-vaults create`
- `gcloud backup-dr backup-plans list`
- `gcloud backup-dr backup-plan-associations create`

---

## 2. Safety Guidelines & Guardrails

To prevent accidental resource mutation or deployment to wrong GCP tenants, the agent MUST adhere to these safety instructions:

1. **Active Project Verification (Mandatory)**:
   - Before executing any command, the agent **MUST** run:
     ```bash
     gcloud config get-value project
     ```
   - Verify that the active project matches the user's expected target project workspace.

2. **Explicit Mutation Confirmation**:
   - For any command containing `create`, `update`, `delete`, or `patch`, the agent **MUST** request explicit, clear confirmation from the user.
   - The confirmation prompt must state the exact command to be executed, its target project, and its impact.

3. **Output Standardization**:
   - Always append `--format=json` (or use the provided `run_gcloud.sh` wrapper) to obtain parseable outputs.

---

## 3. Running Commands

All commands should be dispatched via the `scripts/run_gcloud.sh` execution script.

```bash
# Example query
./scripts/run_gcloud.sh "gcloud compute instances list"
```
