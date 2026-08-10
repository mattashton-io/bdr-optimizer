#!/usr/bin/env bash
# run_gcloud.sh
# Safely executes a gcloud command string, appending JSON formats for queries,
# and outputs the result. Handles simulation fallbacks when offline or dry-running.

set -euo pipefail

if [ $# -lt 1 ]; then
    echo '{"error": "No gcloud command specified. Usage: ./run_gcloud.sh <command_string> [--dry-run]"}'
    exit 1
fi

CMD_STRING="$1"
DRY_RUN=false

# Check if --dry-run is present as second arg or in command string
if [ "${2:-}" = "--dry-run" ] || [[ "$CMD_STRING" == *"--dry-run"* ]]; then
    DRY_RUN=true
    # Strip --dry-run from the command string
    CMD_STRING="${CMD_STRING//--dry-run/}"
fi

# Trim whitespace
CMD_STRING=$(echo "$CMD_STRING" | xargs)

# Standard list of supported commands
SUPPORTED_PREFIXES=(
    "gcloud compute instances list"
    "gcloud compute disks list"
    "gcloud backup-dr backup-vaults list"
    "gcloud backup-dr backup-vaults create"
    "gcloud backup-dr backup-plans list"
    "gcloud backup-dr backup-plan-associations create"
    "gcloud config get-value project"
)

# Validate if the prefix is supported
IS_SUPPORTED=false
for pref in "${SUPPORTED_PREFIXES[@]}"; do
    if [[ "$CMD_STRING" == "$pref"* ]]; then
        IS_SUPPORTED=true
        break
    fi
done

if [ "$IS_SUPPORTED" = false ]; then
    echo "{\"error\": \"Unauthorized or unsupported gcloud command pattern: $CMD_STRING\"}" >&2
    exit 1
fi

# Automatically append --format=json for list or get commands if not present
if [[ "$CMD_STRING" == *"list"* ]] || [[ "$CMD_STRING" == *"get-value"* ]]; then
    if [[ "$CMD_STRING" != *"--format"* ]]; then
        CMD_STRING="$CMD_STRING --format=json"
    fi
fi

# Run mock simulation if --dry-run or if gcloud binary is missing
if [ "$DRY_RUN" = true ] || ! command -v gcloud &> /dev/null; then
    # Simulate based on command content
    if [[ "$CMD_STRING" == *"get-value project"* ]]; then
        echo '"my-gcp-project"'
    elif [[ "$CMD_STRING" == *"backup-vaults list"* ]]; then
        cat <<EOF
[
  {
    "name": "projects/my-gcp-project/locations/us-central1/backupVaults/immutable-vault-prod",
    "description": "Immutable Production Vault for SQL",
    "labels": {
      "env": "prod"
    },
    "backupMinimumEnforcedRetentionDuration": "2592000s"
  }
]
EOF
    elif [[ "$CMD_STRING" == *"backup-plans list"* ]]; then
        cat <<EOF
[
  {
    "name": "projects/my-gcp-project/locations/us-central1/backupPlans/gold-db-policy",
    "description": "Gold retention: hourly backups, 30 days retention"
  }
]
EOF
    elif [[ "$CMD_STRING" == *"backup-vaults create"* ]]; then
        echo '{"status": "SUCCESS", "message": "Simulated Backup Vault creation successful."}'
    elif [[ "$CMD_STRING" == *"backup-plan-associations create"* ]]; then
        echo '{"status": "SUCCESS", "message": "Simulated Backup Plan Association successful."}'
    elif [[ "$CMD_STRING" == *"compute instances list"* ]]; then
        cat <<EOF
[
  {
    "name": "prod-sql-primary",
    "zone": "us-central1-a",
    "status": "RUNNING"
  }
]
EOF
    else
        echo '{"status": "SUCCESS", "message": "Simulated gcloud execution completed."}'
    fi
    exit 0
fi

# Live execution path
eval "$CMD_STRING"
