#!/usr/bin/env python3
"""
DAT Data Quality Monitor

Checks data quality and sends Slack notifications:
- Days since last filing per company
- Stale data alerts (configurable threshold)
- New filing alerts
- Data integrity issues

Usage:
    python scripts/data_quality.py                    # Run quality check
    python scripts/data_quality.py --alert-new       # Alert if new filings today
    python scripts/data_quality.py --stale-days 14   # Custom staleness threshold
    python scripts/data_quality.py --dry-run         # Skip Slack notifications
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configuration
DATA_FILE = PROJECT_ROOT / "data.json"
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

# Default thresholds
DEFAULT_STALE_DAYS = 30  # Companies not updated in 30+ days are "stale"
WARNING_STALE_DAYS = 14  # Companies not updated in 14+ days get a warning

# Token colors for Slack
TOKEN_COLORS = {
    "BTC": "#f7931a",
    "ETH": "#627eea",
    "SOL": "#9945ff",
    "HYPE": "#00d395",
    "BNB": "#f0b90b",
}


def load_data() -> Optional[dict]:
    """Load current data.json."""
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading data.json: {e}")
        return None


def days_since(date_str: str) -> int:
    """Calculate days since a given date string."""
    if not date_str:
        return 999  # No date = very stale
    try:
        # Handle both ISO format and simple date format
        if "T" in date_str:
            date_str = date_str.split("T")[0]
        date = datetime.strptime(date_str, "%Y-%m-%d")
        return (datetime.now() - date).days
    except (ValueError, TypeError):
        return 999


def analyze_data_quality(data: dict, stale_threshold: int = DEFAULT_STALE_DAYS) -> dict:
    """
    Analyze data quality and return a comprehensive report.

    Returns:
        Dict with quality metrics and issues
    """
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_companies": 0,
        "by_token": {},
        "stale_companies": [],      # Not updated in 30+ days
        "warning_companies": [],    # Not updated in 14-30 days
        "recent_filings": [],       # Updated in last 7 days
        "today_filings": [],        # Updated today
        "missing_data": [],         # Companies with missing critical fields
        "errors": [],               # Companies with error status
    }

    today = datetime.now().strftime("%Y-%m-%d")

    for token, companies in data.get("companies", {}).items():
        token_stats = {
            "count": len(companies),
            "total_holdings": 0,
            "avg_days_since_update": 0,
            "oldest_update": None,
            "newest_update": None,
        }

        days_list = []

        for company in companies:
            report["total_companies"] += 1
            ticker = company.get("ticker", "UNKNOWN")
            name = company.get("name", "Unknown")
            last_update = company.get("lastUpdate", "")
            tokens = company.get("tokens", 0)
            status = company.get("status", "ok")

            token_stats["total_holdings"] += tokens

            # Calculate days since update
            days = days_since(last_update)
            days_list.append(days)

            company_info = {
                "ticker": ticker,
                "name": name,
                "token": token,
                "holdings": tokens,
                "last_update": last_update,
                "days_since_update": days,
            }

            # Categorize by staleness
            if last_update == today:
                report["today_filings"].append(company_info)
                report["recent_filings"].append(company_info)
            elif days <= 7:
                report["recent_filings"].append(company_info)
            elif days >= stale_threshold:
                report["stale_companies"].append(company_info)
            elif days >= WARNING_STALE_DAYS:
                report["warning_companies"].append(company_info)

            # Check for missing data
            missing_fields = []
            if not company.get("cik") and company.get("scrape_config", {}).get("method") == "sec_edgar":
                missing_fields.append("cik")
            if not company.get("irUrl"):
                missing_fields.append("irUrl")
            if missing_fields:
                report["missing_data"].append({
                    **company_info,
                    "missing_fields": missing_fields,
                })

            # Check for error status
            if status == "error":
                report["errors"].append({
                    **company_info,
                    "error": company.get("lastError", "Unknown error"),
                    "error_time": company.get("lastErrorTime", ""),
                })

            # Track oldest/newest
            if last_update:
                if not token_stats["oldest_update"] or last_update < token_stats["oldest_update"]:
                    token_stats["oldest_update"] = last_update
                if not token_stats["newest_update"] or last_update > token_stats["newest_update"]:
                    token_stats["newest_update"] = last_update

        # Calculate average
        if days_list:
            token_stats["avg_days_since_update"] = round(sum(days_list) / len(days_list), 1)

        report["by_token"][token] = token_stats

    # Sort lists by days since update
    report["stale_companies"].sort(key=lambda x: x["days_since_update"], reverse=True)
    report["warning_companies"].sort(key=lambda x: x["days_since_update"], reverse=True)
    report["recent_filings"].sort(key=lambda x: x["days_since_update"])

    return report


def send_slack_notification(blocks: list, dry_run: bool = False) -> bool:
    """Send a Slack notification using Block Kit."""
    if dry_run:
        print("\n[DRY RUN] Would send Slack notification:")
        print(json.dumps(blocks, indent=2))
        return True

    if not SLACK_WEBHOOK_URL:
        print("Warning: SLACK_WEBHOOK_URL not set, skipping notification")
        return False

    try:
        response = requests.post(
            SLACK_WEBHOOK_URL,
            json={"blocks": blocks},
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
        print("Slack notification sent successfully")
        return True
    except requests.RequestException as e:
        print(f"Failed to send Slack notification: {e}")
        return False


def build_daily_digest_blocks(report: dict) -> list:
    """Build Slack blocks for daily digest notification."""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "DAT Data Quality Report",
                "emoji": True,
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}"
                }
            ]
        },
        {"type": "divider"},
    ]

    # Summary section
    total = report["total_companies"]
    stale = len(report["stale_companies"])
    warning = len(report["warning_companies"])
    recent = len(report["recent_filings"])
    errors = len(report["errors"])

    health_emoji = "" if stale == 0 and errors == 0 else "" if stale <= 2 else ""

    summary_text = f"*{health_emoji} Overall Health*\n"
    summary_text += f"Total companies: *{total}*\n"
    summary_text += f"Updated (7 days): *{recent}*\n"

    if warning > 0:
        summary_text += f"Warning (14-30 days): *{warning}*\n"
    if stale > 0:
        summary_text += f"Stale (30+ days): *{stale}*\n"
    if errors > 0:
        summary_text += f"Errors: *{errors}*\n"

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": summary_text}
    })

    # Token breakdown
    token_text = "*Holdings by Token:*\n"
    for token, stats in report["by_token"].items():
        emoji = {"BTC": "", "ETH": "", "SOL": "", "HYPE": "", "BNB": ""}.get(token, "")
        token_text += f"{emoji} {token}: {stats['total_holdings']:,.0f} ({stats['count']} companies, avg {stats['avg_days_since_update']} days)\n"

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": token_text}
    })

    # Stale companies section (if any)
    if report["stale_companies"]:
        blocks.append({"type": "divider"})
        stale_text = "*Stale Companies (30+ days):*\n"
        for c in report["stale_companies"][:10]:  # Limit to 10
            stale_text += f"- {c['ticker']} ({c['token']}): {c['days_since_update']} days - last {c['last_update']}\n"
        if len(report["stale_companies"]) > 10:
            stale_text += f"_...and {len(report['stale_companies']) - 10} more_\n"

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": stale_text}
        })

    # Warning companies (if any)
    if report["warning_companies"]:
        warning_text = "*Warning (14-30 days):*\n"
        for c in report["warning_companies"][:5]:
            warning_text += f"- {c['ticker']} ({c['token']}): {c['days_since_update']} days\n"
        if len(report["warning_companies"]) > 5:
            warning_text += f"_...and {len(report['warning_companies']) - 5} more_\n"

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": warning_text}
        })

    # Errors section (if any)
    if report["errors"]:
        blocks.append({"type": "divider"})
        error_text = "*Scraper Errors:*\n"
        for e in report["errors"][:5]:
            error_text += f"- {e['ticker']}: {e['error'][:50]}...\n"

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": error_text}
        })

    return blocks


def build_new_filing_alert_blocks(filings: list) -> list:
    """Build Slack blocks for new filing alert."""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "New DAT Filing Detected!",
                "emoji": True,
            }
        },
        {"type": "divider"},
    ]

    for filing in filings:
        ticker = filing["ticker"]
        token = filing["token"]
        holdings = filing["holdings"]

        emoji = {"BTC": "", "ETH": "", "SOL": "", "HYPE": "", "BNB": ""}.get(token, "")
        color = TOKEN_COLORS.get(token, "#333333")

        filing_text = f"*{emoji} {ticker}* ({token})\n"
        filing_text += f"Holdings: *{holdings:,.0f}* {token}\n"
        filing_text += f"Filed: {filing['last_update']}"

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": filing_text}
        })

    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"Detected at {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}"
            }
        ]
    })

    return blocks


def print_console_report(report: dict):
    """Print a formatted console report."""
    print("\n" + "=" * 60)
    print("DAT DATA QUALITY REPORT")
    print("=" * 60)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("-" * 60)

    # Summary
    total = report["total_companies"]
    stale = len(report["stale_companies"])
    warning = len(report["warning_companies"])
    recent = len(report["recent_filings"])
    errors = len(report["errors"])

    print(f"\nTotal companies: {total}")
    print(f"Updated (last 7 days): {recent}")
    print(f"Warning (14-30 days): {warning}")
    print(f"Stale (30+ days): {stale}")
    print(f"Errors: {errors}")

    # Token breakdown
    print("\n" + "-" * 60)
    print("HOLDINGS BY TOKEN")
    print("-" * 60)

    for token, stats in report["by_token"].items():
        print(f"\n{token}:")
        print(f"  Companies: {stats['count']}")
        print(f"  Total holdings: {stats['total_holdings']:,.0f}")
        print(f"  Avg days since update: {stats['avg_days_since_update']}")
        if stats["newest_update"]:
            print(f"  Most recent: {stats['newest_update']}")
        if stats["oldest_update"]:
            print(f"  Oldest: {stats['oldest_update']}")

    # Today's filings
    if report["today_filings"]:
        print("\n" + "-" * 60)
        print("TODAY'S FILINGS")
        print("-" * 60)
        for c in report["today_filings"]:
            print(f"  {c['ticker']} ({c['token']}): {c['holdings']:,.0f}")

    # Stale companies
    if report["stale_companies"]:
        print("\n" + "-" * 60)
        print("STALE COMPANIES (30+ days)")
        print("-" * 60)
        for c in report["stale_companies"]:
            print(f"  {c['ticker']:8} ({c['token']:4}): {c['days_since_update']:3} days since {c['last_update']}")

    # Warning companies
    if report["warning_companies"]:
        print("\n" + "-" * 60)
        print("WARNING COMPANIES (14-30 days)")
        print("-" * 60)
        for c in report["warning_companies"]:
            print(f"  {c['ticker']:8} ({c['token']:4}): {c['days_since_update']:3} days since {c['last_update']}")

    # Errors
    if report["errors"]:
        print("\n" + "-" * 60)
        print("ERRORS")
        print("-" * 60)
        for e in report["errors"]:
            print(f"  {e['ticker']} ({e['token']}): {e['error'][:60]}")

    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="DAT Data Quality Monitor")
    parser.add_argument(
        "--alert-new",
        action="store_true",
        help="Send alert if new filings detected today"
    )
    parser.add_argument(
        "--daily-digest",
        action="store_true",
        help="Send daily digest notification"
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=DEFAULT_STALE_DAYS,
        help=f"Days threshold for stale data (default: {DEFAULT_STALE_DAYS})"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't send Slack notifications, just print"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON"
    )
    args = parser.parse_args()

    # Load data
    data = load_data()
    if not data:
        print("ERROR: Failed to load data.json")
        sys.exit(1)

    # Analyze data quality
    report = analyze_data_quality(data, stale_threshold=args.stale_days)

    # Output report
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_console_report(report)

    # Handle notifications
    notifications_sent = 0

    # New filing alert
    if args.alert_new and report["today_filings"]:
        print(f"\nNew filings detected today: {len(report['today_filings'])}")
        blocks = build_new_filing_alert_blocks(report["today_filings"])
        if send_slack_notification(blocks, dry_run=args.dry_run):
            notifications_sent += 1

    # Daily digest
    if args.daily_digest:
        print("\nSending daily digest...")
        blocks = build_daily_digest_blocks(report)
        if send_slack_notification(blocks, dry_run=args.dry_run):
            notifications_sent += 1

    # Summary
    if notifications_sent > 0:
        print(f"\nSent {notifications_sent} Slack notification(s)")

    # Exit with error code if there are stale companies or errors
    if len(report["stale_companies"]) > 0 or len(report["errors"]) > 0:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
