# chat-notifier Skill

This skill enables the automated delivery of operational status summaries, policy binding reports, and critical system alerts from GCP Backup & DR to team messaging channels (Google Chat or Slack) via inbound webhooks.

---

## Level-1 Metadata (Intent Matching)
```json
{
  "name": "chat-notifier",
  "description": "Sends automated status updates, policy association summaries, and error alerts to Google Chat or Slack webhook endpoints.",
  "intents": [
    "send chat alert",
    "notify team of backup success",
    "post Slack webhook",
    "alert failed backup job"
  ]
}
```

---

## 1. Key Capabilities

The `chat-notifier` skill supports the following communication workflows:

### A. Rich Card summaries
Generate structured, visually appealing summaries for major milestones:
- Format newly protected GCE instances, aggregated storage capacity (TB), and monthly BDR cost projections into cards.
- Support deep links directly back to the target GCP Console pages (e.g., Backup Plan Associations page).

### B. Critical Error Notifications
Dispatch immediate alert blocks to warn operations teams when:
- A backup schedule fails or encounters a timeout (`DEADLINE_EXCEEDED`).
- A Backup Vault creation fails due to precondition lock violations.
- An unauthorized user attempts to mutate a security policy.

---

## 2. Dispatching Alerts via Python Utility

Execute the `scripts/send_webhook.py` utility to deliver formatted cards to channels:

```bash
# Dispatch a simulated status card update
python3 scripts/send_webhook.py \
  --webhook-url "https://chat.googleapis.com/v1/spaces/..." \
  --title "GCP BDR Optimization Summary" \
  --status "SUCCESS" \
  --metrics "Total Protected VMs=14, Aggregated Storage=2.4TB, Monthly Cost=\$320.00" \
  --deep-link "https://console.cloud.google.com/backup-dr/..."
```
