#!/usr/bin/env python3
"""
send_webhook.py

Sends rich cards or alert notifications to Google Chat or Slack webhooks.
Supports automatic layout formatting based on the target platform (Slack vs. Google Chat).
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error


def parse_args():
    parser = argparse.ArgumentParser(description="Send formatted status and error cards to chat webhooks.")
    parser.add_argument("--webhook-url", "-w", help="Target webhook URL. Can also be set via BDR_CHAT_WEBHOOK env var.")
    parser.add_argument("--title", "-t", required=True, help="Title of the status card.")
    parser.add_argument("--status", "-s", choices=["SUCCESS", "WARNING", "ERROR"], default="SUCCESS", help="Operational status.")
    parser.add_argument("--metrics", "-m", help="Comma-separated metrics list (e.g. 'VMs Protected=12, Storage=4.2TB, Estimated Cost=$350').")
    parser.add_argument("--deep-link", "-d", help="Console URL deep link for more details.")
    parser.add_argument("--dry-run", action="store_true", help="Format and print JSON payload locally without posting to URL.")
    return parser.parse_args()


def parse_metrics(metrics_str):
    """
    Parses a string like 'A=1, B=2' into a list of tuples.
    """
    if not metrics_str:
        return []
    items = []
    for pair in metrics_str.split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            items.append((k.strip(), v.strip()))
        else:
            items.append((pair.strip(), ""))
    return items


def build_google_chat_payload(title, status, metrics_list, deep_link):
    """
    Builds a Google Chat Card v2 JSON payload.
    """
    # Color coding based on status
    status_colors = {
        "SUCCESS": "#0F9D58",  # Google Green
        "WARNING": "#F4B400",  # Google Yellow
        "ERROR": "#DB4437"     # Google Red
    }
    header_color = status_colors.get(status, "#4285F4")
    
    # Construct widgets for metrics
    widgets = []
    for k, v in metrics_list:
        widgets.append({
            "textParagraph": {
                "text": f"<b>{k}:</b> {v}"
            }
        })
        
    if deep_link:
        widgets.append({
            "buttonList": {
                "buttons": [{
                    "text": "View in Google Cloud Console",
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
            "cardId": "bdr_status_card",
            "card": {
                "header": {
                    "title": title,
                    "subtitle": f"Status: {status}",
                    "imageUrl": "https://fonts.gstatic.com/s/i/short-term/release/googlesymbols/backup/default/48px.svg"
                },
                "sections": [{
                    "header": "Operational Metrics Summary",
                    "collapsible": False,
                    "widgets": widgets
                }]
            }
        }]
    }
    return payload


def build_slack_payload(title, status, metrics_list, deep_link):
    """
    Builds a Slack Blocks payload.
    """
    status_emoji = {
        "SUCCESS": "✅",
        "WARNING": "⚠️",
        "ERROR": "🚨"
    }
    emoji = status_emoji.get(status, "ℹ️")
    
    fields = []
    for k, v in metrics_list:
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
                "text": f"*Status:* {status}"
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
                    "text": "View in Cloud Console"
                },
                "url": deep_link,
                "style": "primary" if status == "SUCCESS" else "danger"
            }]
        })
        
    return {"blocks": blocks}


def build_fallback_payload(title, status, metrics_list, deep_link):
    """
    Simple text payload fallback.
    """
    text_lines = [f"**{title}**", f"Status: {status}", ""]
    for k, v in metrics_list:
        text_lines.append(f"- **{k}**: {v}")
    if deep_link:
        text_lines.append(f"\n[View in GCP Console]({deep_link})")
    return {"text": "\n".join(text_lines)}


def main():
    args = parse_args()
    
    # Resolve webhook URL
    webhook_url = args.webhook_url or os.environ.get("BDR_CHAT_WEBHOOK_URL")
    
    if not webhook_url and not args.dry_run:
        print("Error: Webhook URL must be specified via --webhook-url or BDR_CHAT_WEBHOOK_URL env variable.", file=sys.stderr)
        sys.exit(1)
        
    metrics_list = parse_metrics(args.metrics)
    
    # Determine the target format
    url_str = (webhook_url or "").lower()
    if "chat.googleapis.com" in url_str:
        payload = build_google_chat_payload(args.title, args.status, metrics_list, args.deep_link)
        platform_label = "Google Chat"
    elif "hooks.slack.com" in url_str:
        payload = build_slack_payload(args.title, args.status, metrics_list, args.deep_link)
        platform_label = "Slack"
    else:
        payload = build_fallback_payload(args.title, args.status, metrics_list, args.deep_link)
        platform_label = "Generic Webhook"
        
    # JSON String representation
    payload_str = json.dumps(payload, indent=2)
    
    if args.dry_run:
        print(f"\n--- Simulated Webhook Payload ({platform_label}) ---")
        print(payload_str)
        sys.exit(0)
        
    # Direct HTTP Request
    print(f"Sending card notification to {platform_label} webhook...")
    req = urllib.request.Request(
        webhook_url,
        data=payload_str.encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as resp:
            resp_body = resp.read().decode("utf-8")
            print(f"Notification sent successfully! Response: {resp_body}")
    except urllib.error.HTTPError as e:
        print(f"Error posting notification: {e.code} - {e.reason}", file=sys.stderr)
        print(e.read().decode("utf-8"), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Network error sending notification: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
