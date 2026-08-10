#!/usr/bin/env python3
"""
chat_mcp.py

Custom FastMCP Python server to dispatch operational success cards,
reconciliation reports, and high-priority error alerts to messaging webhooks.
"""

import os
import sys
import json
import urllib.request
import urllib.error

# Try importing FastMCP from mcp.server.fastmcp
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    # Safe mock class if running in an environment without mcp installed
    print("Warning: 'mcp' SDK not found. Running in mock-server standby mode.", file=sys.stderr)
    class FastMCP:
        def __init__(self, name):
            self.name = name
        def tool(self):
            return lambda func: func


# Initialize FastMCP Server
mcp = FastMCP("chat_mcp")


def get_webhook_url():
    """
    Retrieves the webhook URL from environment variables.
    """
    return os.environ.get("WEBHOOK_URL") or os.environ.get("BDR_CHAT_WEBHOOK_URL")


def post_to_webhook(payload, url, platform_label):
    """
    Helper to dispatch HTTP POST requests to the target webhook URL.
    """
    payload_str = json.dumps(payload, indent=2)
    
    if not url:
        print(f"\n--- Simulated Webhook Delivery ({platform_label}) ---", file=sys.stderr)
        print(payload_str, file=sys.stderr)
        return {"status": "SIMULATED", "message": "Dry run or no WEBHOOK_URL environment variable set."}
        
    req = urllib.request.Request(
        url,
        data=payload_str.encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as resp:
            resp_body = resp.read().decode("utf-8")
            return {"status": "SUCCESS", "response": resp_body}
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        raise RuntimeError(f"HTTP Error {e.code} posting to webhook: {err_msg}")
    except Exception as e:
        raise RuntimeError(f"Failed to transmit webhook: {e}")


def build_payloads(title, subtitle, metrics, deep_link, severity="INFO"):
    """
    Builds both Google Chat Card v2 and Slack Blocks payloads.
    Selects layout based on URL structure.
    """
    url = get_webhook_url() or ""
    is_google_chat = "chat.googleapis.com" in url.lower() or "google" in url.lower()
    is_slack = "hooks.slack.com" in url.lower() or "slack" in url.lower()
    
    # Defaults to Google Chat if url is empty/arbitrary for broad visual appeal
    if not url:
        is_google_chat = True
        
    if is_google_chat:
        status_colors = {
            "INFO": "#4285F4",     # Blue
            "SUCCESS": "#0F9D58",  # Green
            "WARNING": "#F4B400",  # Yellow
            "ERROR": "#DB4437"     # Red
        }
        header_color = status_colors.get(severity, "#4285F4")
        
        widgets = []
        for k, v in metrics.items():
            widgets.append({
                "textParagraph": {
                    "text": f"<b>{k}:</b> {v}"
                }
            })
            
        if deep_link:
            widgets.append({
                "buttonList": {
                    "buttons": [{
                        "text": "Open in GCP Console",
                        "onClick": {
                            "openLink": {
                                "url": deep_link
                            }
                        }
                    }]
                }
            })
            
        payload = {
            "cardsV2": [{
                "cardId": "bdr_operational_card",
                "card": {
                    "header": {
                        "title": title,
                        "subtitle": subtitle,
                        "imageUrl": "https://fonts.gstatic.com/s/i/short-term/release/googlesymbols/backup/default/48px.svg"
                    },
                    "sections": [{
                        "header": "Summary Details",
                        "collapsible": False,
                        "widgets": widgets
                    }]
                }
            }]
        }
        return payload, "Google Chat"
        
    else:
        # Slack Blocks
        severity_emoji = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "WARNING": "⚠️",
            "ERROR": "🚨"
        }
        emoji = severity_emoji.get(severity, "ℹ️")
        
        fields = []
        for k, v in metrics.items():
            fields.append({
                "type": "mrkdwn",
                "text": f"*{k}:*\n{v}"
            })
            
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {title}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"_{subtitle}_"
                }
            }
        ]
        
        if fields:
            blocks.append({
                "type": "section",
                "fields": fields
            })
            
        if deep_link:
            blocks.append({
                "type": "actions",
                "elements": [{
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Open Console"
                    },
                    "url": deep_link,
                    "style": "primary" if severity in ["SUCCESS", "INFO"] else "danger"
                }]
            })
            
        return {"blocks": blocks}, "Slack"


# --- FASTMCP TOOL BINDINGS ---

@mcp.tool()
def send_bdr_summary_card(title: str, protected_vms_count: int, total_storage_gib: float, estimated_monthly_cost: float, gcp_console_link: str) -> str:
    """
    Sends a rich summary card containing sizing and cost metrics of protected resources to chat.
    
    Args:
        title: Title of the summary report card (e.g. 'BDR Sizing Optimization report').
        protected_vms_count: Number of virtual machines successfully associated.
        total_storage_gib: Total protected capacity in GiB.
        estimated_monthly_cost: Projected storage and licensing expenditure.
        gcp_console_link: Deep link back to the target Backup & DR console pages.
        
    Returns:
        JSON string describing the dispatch outcome.
    """
    url = get_webhook_url()
    metrics = {
        "Associated Workloads": f"{protected_vms_count} VMs",
        "Total Protected Storage": f"{total_storage_gib:.2f} GiB",
        "Estimated Cost": f"${estimated_monthly_cost:.2f} / month"
    }
    
    payload, platform = build_payloads(
        title=title,
        subtitle="Operational onboarding and sizing report completed successfully.",
        metrics=metrics,
        deep_link=gcp_console_link,
        severity="SUCCESS"
    )
    
    try:
        res = post_to_webhook(payload, url, platform)
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"status": "FAILURE", "error": str(e)}, indent=2)


@mcp.tool()
def post_bdr_alert(severity: str, error_message: str, impacted_resources: list[str]) -> str:
    """
    Dispatches immediate alert notifications warning of backup association or vault failures.
    
    Args:
        severity: Severity tier (WARNING, ERROR).
        error_message: Detailed explanation of the error or status code returned.
        impacted_resources: List of target VMs or Vault paths impacted by this failure.
        
    Returns:
        JSON string describing the dispatch outcome.
    """
    url = get_webhook_url()
    metrics = {
        "Error Details": error_message,
        "Impacted Resource List": ", ".join(impacted_resources)
    }
    
    payload, platform = build_payloads(
        title="Backup & DR System Alert",
        subtitle=f"Alert Level: {severity}",
        metrics=metrics,
        deep_link=None,
        severity=severity
    )
    
    try:
        res = post_to_webhook(payload, url, platform)
        return json.dumps(res, indent=2)
    except Exception as e:
        return json.dumps({"status": "FAILURE", "error": str(e)}, indent=2)


if __name__ == "__main__":
    if "FastMCP" in globals() and hasattr(mcp, "run"):
        mcp.run()
    else:
        # CLI Standby evaluation test
        print("FastMCP chat execution interface currently mocked.", file=sys.stderr)
        # Mock summary report
        print(send_bdr_summary_card(
            title="GCP BDR Execution Summary",
            protected_vms_count=8,
            total_storage_gib=4500.5,
            estimated_monthly_cost=185.50,
            gcp_console_link="https://console.cloud.google.com/backup-dr"
        ))
        # Mock alert card
        print(post_bdr_alert(
            severity="ERROR",
            error_message="Snapshot policy deadline exceeded. Target storage failed write.",
            impacted_resources=["prod-db-replica-01", "vault-prod-gold"]
        ))
