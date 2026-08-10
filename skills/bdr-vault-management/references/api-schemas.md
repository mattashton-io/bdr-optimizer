# GCP Backup & DR v1 REST API Schema Reference

This reference file lists the REST API endpoints and payload JSON schemas for managing Backup Vaults and Backup Plan Associations (BPA) in Google Cloud Backup and DR.

---

## 1. Backup Vaults API (`projects.locations.backupVaults`)

Backup Vaults are regional resources where backup data is securely stored, locked, and maintained.

### Endpoints

| HTTP Method | Request URI | Description |
| :--- | :--- | :--- |
| **POST** | `https://backupdr.googleapis.com/v1/projects/{projectId}/locations/{locationId}/backupVaults?backupVaultId={backupVaultId}` | Creates a new Backup Vault. |
| **GET** | `https://backupdr.googleapis.com/v1/projects/{projectId}/locations/{locationId}/backupVaults/{backupVaultId}` | Retrieves Backup Vault details. |
| **DELETE** | `https://backupdr.googleapis.com/v1/projects/{projectId}/locations/{locationId}/backupVaults/{backupVaultId}` | Deletes a Backup Vault. |
| **PATCH** | `https://backupdr.googleapis.com/v1/projects/{projectId}/locations/{locationId}/backupVaults/{backupVaultId}?updateMask={updateMask}` | Updates fields of a Backup Vault. |

### Schema: Create Backup Vault with Immutable Retention

To configure an immutable vault (preventing deletion of backups and modification of retention limits), specify `backupMinimumEnforcedRetentionDuration`.

#### HTTP Headers
```http
Content-Type: application/json
Authorization: Bearer <ACCESS_TOKEN>
```

#### JSON Payload
```json
{
  "description": "Immutable Production Vault for critical Tier 1 database and application workloads.",
  "labels": {
    "env": "prod",
    "data-classification": "highly-confidential",
    "compliance-lock": "true"
  },
  "backupMinimumEnforcedRetentionDuration": "2592000s"
}
```
*Note: `backupMinimumEnforcedRetentionDuration` is specified as a duration string (e.g., `"2592000s"` represents 30 days). Once configured, backups written to this vault cannot be deleted or have their retention shortened below this value.*

---

## 2. Backup Plan Associations API (`projects.locations.backupPlanAssociations`)

A Backup Plan Association (BPA) binds a specific cloud resource (such as a Compute Engine VM) to a Backup Plan, activating automated scheduled protection.

### Endpoints

| HTTP Method | Request URI | Description |
| :--- | :--- | :--- |
| **POST** | `https://backupdr.googleapis.com/v1/projects/{projectId}/locations/{locationId}/backupPlanAssociations?backupPlanAssociationId={backupPlanAssociationId}` | Creates a new BPA (associates VM to Plan). |
| **GET** | `https://backupdr.googleapis.com/v1/projects/{projectId}/locations/{locationId}/backupPlanAssociations/{backupPlanAssociationId}` | Retrieves BPA details. |
| **DELETE** | `https://backupdr.googleapis.com/v1/projects/{projectId}/locations/{locationId}/backupPlanAssociations/{backupPlanAssociationId}` | Removes a BPA (disables active protection). |

### Schema: Create Backup Plan Association (Compute Engine VM)

#### HTTP Headers
```http
Content-Type: application/json
Authorization: Bearer <ACCESS_TOKEN>
```

#### JSON Payload
```json
{
  "resourceType": "compute.googleapis.com/Instance",
  "resource": "//compute.googleapis.com/projects/my-gcp-project/zones/us-central1-a/instances/prod-db-01",
  "backupPlan": "projects/my-gcp-project/locations/us-central1/backupPlans/gold-db-policy"
}
```

#### Key Fields Explained:
- **`resourceType`**: The exact resource path identifier type. Must be `"compute.googleapis.com/Instance"` for GCE Virtual Machines.
- **`resource`**: The full path name of the resource to be backed up, starting with a double-slash `//` (standard GCP Resource URL format).
- **`backupPlan`**: Fully qualified resource path to the Backup Plan to apply.
