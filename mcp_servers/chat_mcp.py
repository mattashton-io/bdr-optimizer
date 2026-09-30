#!/usr/bin/env python3
"""
chat_mcp.py

FastMCP Python server exposing webhook dispatch tools for operational success cards,
reconciliation reports, and high-priority alerts to Google Chat or Slack.
Adheres strictly to spec.md (No silent mock degradation, structured error payloads).
"""

import os
import sys
import json
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional

# Strict Dependency Check: FastMCP / MCPServer (MCP 1.x & 2.x compatible)
try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise ImportError(
            "\n================================================================================\n"
            "[BDR-OPTIMIZER ERROR] MISSING_DEPENDENCY_ERROR: 'mcp' package is not installed.\n"
            "================================================================================\n"
            "Component:   chat_mcp (FastMCP Server)\n"
            "Cause:       ModuleNotFoundError: No module named 'mcp'\n"
            "Impact:      Cannot initialize FastMCP messaging tool server.\n\n"
            "Remediation:\n"
            "  1. Install the mcp package: pip install \"mcp>=1.0.0\"\n"
            "  2. Ensure the active virtual environment (.venv-bdr) is activated.\n"
            "================================================================================\n"
        ) from exc


# Initialize FastMCP Server
mcp = FastMCP("chat_mcp")


def get_webhook_url() -> Optional[str]:
    """Retrieves the webhook URL from environment variables."""
    return os.environ.get("WEBHOOK_URL") or os.environ.get("BDR_CHAT_WEBHOOK_URL")


def post_to_webhook(payload: Dict[str, Any], url: str, timeout: int = 30) -> Dict[str, Any]:
    """
    Dispatches HTTP POST request to webhook endpoint with explicit timeout.
    Returns response dict or raises RuntimeError with actionable details.
    """
    payload_str = json.dumps(payload, indent=2)
    req = urllib.request.Request(
        url,
        data=payload_str.encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_body = resp.read().decode("utf-8")
            return {"status": "SUCCESS", "response": resp_body}
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        raise RuntimeError(f"HTTP Error {e.code} posting to webhook: {err_msg}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error posting to webhook: {e.reason}")
    except TimeoutError:
        raise RuntimeError(f"Webhook request timed out after {timeout} seconds.")


def build_payloads(title: str, subtitle: str, metrics: Dict[str, str], deep_link: Optional[str], severity: str = "INFO") -> tuple[Dict[str, Any], str]:
    """
    Builds Google Chat Card v2 or Slack Blocks payload based on target URL.
    """
    url = get_webhook_url() or ""
    is_google_chat = "chat.googleapis.com" in url.lower() or "google" in url.lower() or not url

    if is_google_chat:
        status_colors = {
            "INFO": "#4285F4",     # Blue
            "SUCCESS": "#0F9D58",  # Green
            "WARNING": "#F4B400",  # Yellow
            "ERROR": "#DB4437"     # Red
        }
        header_color = status_colors.get(severity, "#4285F4")

        widgets: List[Dict[str, Any]] = []
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

        blocks: List[Dict[str, Any]] = [
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
def send_bdr_summary_card(title: str, protected_vms_count: int, total_storage_gib: float, estimated_monthly_cost: float, gcp_console_link: Optional[str] = None) -> str:
    """
    Sends a rich summary card containing sizing and cost metrics of protected resources to chat.

    Args:
        title: Title of the summary report card (e.g. 'BDR Sizing Optimization report').
        protected_vms_count: Number of virtual machines successfully associated.
        total_storage_gib: Total protected capacity in GiB.
        estimated_monthly_cost: Projected storage and licensing expenditure in USD.
        gcp_console_link: Optional deep link back to the target Backup & DR console pages.

    Returns:
        JSON string describing the dispatch outcome.
    """
    url = get_webhook_url()
    if not url:
        return json.dumps({
            "status": "ERROR",
            "error_type": "CONFIG_ERROR",
            "component": "chat_mcp.send_bdr_summary_card",
            "message": "Environment variable 'WEBHOOK_URL' or 'BDR_CHAT_WEBHOOK_URL' is missing.",
            "remediation": "Set WEBHOOK_URL (e.g. export WEBHOOK_URL='https://chat.googleapis.com/...') before dispatching chat notifications."
        }, indent=2)

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
        res = post_to_webhook(payload, url)
        return json.dumps({"status": "SUCCESS", "platform": platform, "result": res}, indent=2)
    except Exception as e:
        return json.dumps({
            "status": "ERROR",
            "error_type": "WEBHOOK_DELIVERY_FAILED",
            "component": "chat_mcp.send_bdr_summary_card",
            "message": str(e),
            "remediation": "Verify the webhook URL endpoint is valid and reachable."
        }, indent=2)


@mcp.tool()
def post_bdr_alert(severity: str, error_message: str, impacted_resources: List[str]) -> str:
    """
    Dispatches immediate alert notifications warning of backup association or vault failures.

    Args:
        severity: Severity tier ('WARNING', 'ERROR').
        error_message: Detailed explanation of the error or status code returned.
        impacted_resources: List of target VMs or Vault paths impacted by this failure.

    Returns:
        JSON string describing the dispatch outcome.
    """
    url = get_webhook_url()
    if not url:
        return json.dumps({
            "status": "ERROR",
            "error_type": "CONFIG_ERROR",
            "component": "chat_mcp.post_bdr_alert",
            "message": "Environment variable 'WEBHOOK_URL' or 'BDR_CHAT_WEBHOOK_URL' is missing.",
            "remediation": "Set WEBHOOK_URL (e.g. export WEBHOOK_URL='https://chat.googleapis.com/...') before dispatching alerts."
        }, indent=2)

    metrics = {
        "Error Details": error_message,
        "Impacted Resource List": ", ".join(impacted_resources) if impacted_resources else "None"
    }

    payload, platform = build_payloads(
        title="Backup & DR System Alert",
        subtitle=f"Alert Level: {severity}",
        metrics=metrics,
        deep_link=None,
        severity=severity
    )

    try:
        res = post_to_webhook(payload, url)
        return json.dumps({"status": "SUCCESS", "platform": platform, "result": res}, indent=2)
    except Exception as e:
        return json.dumps({
            "status": "ERROR",
            "error_type": "WEBHOOK_DELIVERY_FAILED",
            "component": "chat_mcp.post_bdr_alert",
            "message": str(e),
            "remediation": "Verify the webhook URL endpoint is valid and reachable."
        }, indent=2)


if __name__ == "__main__":
    mcp.run()
