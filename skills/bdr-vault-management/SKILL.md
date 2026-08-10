# BDR Vault Management Skill

This skill governs the configuration, health, and cost-efficiency of GCP Backup and Disaster Recovery (BDR) Backup Vaults.

## Overview

The BDR Vault Management skill focuses on storage optimization, retention auditing, replication oversight, and cost forecasting for GCP BDR vaults. It includes tools and workflows to monitor capacity utilization, ensure vault security (e.g., locking policies/immutable storage), and automate replication verification.

## Directory Structure

- `references/`: Architecture blueprints, compliance mandates, and storage optimization guidelines.
- `assets/`: Terraform templates, JSON IAM policy templates, and cost-modeling spreadsheets.
- `scripts/`: Monitoring scripts to analyze vault size growth, retention violations, and replication health.

## Standard Procedures

### 1. Vault Storage & Cost Auditing
- Track storage consumption across all Backup Vaults.
- Identify expired recovery points that are still consuming storage.
- Project monthly BDR cost based on vault data growth trends.

### 2. Immutability & Compliance Verification
- Verify that vault-locking/immutable policies are active for highly regulated environments.
- Ensure proper separation of duties via IAM roles assigned to vault administrators.

### 3. Replication & Cross-Region Recovery Health
- Validate replication status between source and destination regions.
- Trigger non-disruptive disaster recovery drills and test mounts to verify data integrity.
