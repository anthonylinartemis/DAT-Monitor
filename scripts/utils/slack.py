"""
Slack notification utilities with proper escaping and retry logic.
"""

import json
import os
from typing import Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Slack webhook URL from environment
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")


def escape_slack_text(text: str) -> str:
    """
    Escape special characters for Slack mrkdwn format.

    Slack uses specific characters that need escaping:
    - & -> &amp;
    - < -> &lt;
    - > -> &gt;

    Also escapes characters that could break JSON:
    - Newlines are preserved (valid in Slack)
    - Backslashes and quotes are handled by json.dumps
    """
    if not text:
        return ""

    # Escape HTML entities for Slack
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")

    return text


def escape_json_string(text: str) -> str:
    """
    Escape a string for safe JSON inclusion.

    Uses json.dumps to properly escape all special characters
    then strips the surrounding quotes.
    """
    if not text:
        return ""

    # json.dumps handles all escaping, strip the quotes it adds
    escaped = json.dumps(text)
    return escaped[1:-1]  # Remove surrounding quotes


def build_text_block(text: str, block_type: str = "mrkdwn") -> dict:
    """Build a Slack text block with proper escaping."""
    return {
        "type": "section",
        "text": {
            "type": block_type,
            "text": escape_slack_text(text)
        }
    }


def build_header_block(text: str) -> dict:
    """Build a Slack header block."""
    return {
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": escape_slack_text(text)[:150],  # Slack header limit
            "emoji": True
        }
    }


def build_divider_block() -> dict:
    """Build a Slack divider block."""
    return {"type": "divider"}


def build_context_block(text: str) -> dict:
    """Build a Slack context block."""
    return {
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": escape_slack_text(text)
            }
        ]
    }


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.RequestException, requests.Timeout))
)
def send_slack_message(
    blocks: list,
    webhook_url: Optional[str] = None,
    dry_run: bool = False
) -> bool:
    """
    Send a Slack notification using Block Kit.

    Args:
        blocks: List of Slack Block Kit blocks
        webhook_url: Optional custom webhook URL (uses env var if not provided)
        dry_run: If True, print the message instead of sending

    Returns:
        True if sent successfully, False otherwise
    """
    url = webhook_url or SLACK_WEBHOOK_URL

    if dry_run:
        print("\n[DRY RUN] Would send Slack notification:")
        print(json.dumps({"blocks": blocks}, indent=2))
        return True

    if not url:
        print("Warning: SLACK_WEBHOOK_URL not set, skipping notification")
        return False

    try:
        # Build payload with proper JSON encoding
        payload = {"blocks": blocks}

        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
        print("Slack notification sent successfully")
        return True
    except requests.RequestException as e:
        print(f"Failed to send Slack notification: {e}")
        raise  # Re-raise for retry decorator


def send_simple_message(text: str, dry_run: bool = False) -> bool:
    """Send a simple text message to Slack."""
    blocks = [build_text_block(text)]
    return send_slack_message(blocks, dry_run=dry_run)


def send_alert(
    title: str,
    message: str,
    severity: str = "warning",
    dry_run: bool = False
) -> bool:
    """
    Send an alert notification to Slack.

    Args:
        title: Alert title
        message: Alert message body
        severity: One of "info", "warning", "error"
        dry_run: If True, print instead of sending
    """
    emoji = {
        "info": "info",
        "warning": "warning",
        "error": "x"
    }.get(severity, "bell")

    blocks = [
        build_header_block(f":{emoji}: {title}"),
        build_divider_block(),
        build_text_block(message),
    ]

    return send_slack_message(blocks, dry_run=dry_run)


def send_scraper_failure_alert(
    ticker: str,
    token: str,
    error: str,
    dry_run: bool = False
) -> bool:
    """
    Send a Slack alert when scraper fails for a company.

    Args:
        ticker: Company ticker symbol
        token: Token type (BTC, ETH, etc.)
        error: Error message
        dry_run: If True, print instead of sending
    """
    # Truncate and escape error message
    safe_error = escape_slack_text(error[:200])
    safe_ticker = escape_slack_text(ticker)
    safe_token = escape_slack_text(token)

    blocks = [
        build_header_block(":warning: Scraper Failure"),
        build_divider_block(),
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Company:*\n{safe_ticker}"},
                {"type": "mrkdwn", "text": f"*Token:*\n{safe_token}"},
            ]
        },
        build_text_block(f"*Error:*\n```{safe_error}```"),
    ]

    return send_slack_message(blocks, dry_run=dry_run)


def send_holdings_change_alert(
    ticker: str,
    token: str,
    old_holdings: int,
    new_holdings: int,
    source_url: str = "",
    dry_run: bool = False
) -> bool:
    """
    Send a Slack alert when holdings change.

    Args:
        ticker: Company ticker symbol
        token: Token type (BTC, ETH, etc.)
        old_holdings: Previous holdings count
        new_holdings: New holdings count
        source_url: Optional URL to the source document
        dry_run: If True, print instead of sending
    """
    change = new_holdings - old_holdings
    change_str = f"+{change:,}" if change > 0 else f"{change:,}"
    emoji = ":chart_with_upwards_trend:" if change > 0 else ":chart_with_downwards_trend:"

    safe_ticker = escape_slack_text(ticker)
    safe_token = escape_slack_text(token)

    blocks = [
        build_header_block(f"{emoji} {safe_ticker} Holdings Update"),
        build_divider_block(),
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Token:*\n{safe_token}"},
                {"type": "mrkdwn", "text": f"*Change:*\n{change_str}"},
                {"type": "mrkdwn", "text": f"*Previous:*\n{old_holdings:,}"},
                {"type": "mrkdwn", "text": f"*New:*\n{new_holdings:,}"},
            ]
        },
    ]

    if source_url:
        safe_url = escape_slack_text(source_url)
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"<{safe_url}|View Source>"}
        })

    return send_slack_message(blocks, dry_run=dry_run)
