#!/usr/bin/env python3
"""
DAT Treasury Monitor - Auto-Update Scraper

Fetches latest holdings data from SEC EDGAR 8-K filings, IR pages, and
company dashboards using a modular, class-based scraping system.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytz
import requests

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from scrapers import get_scraper
from utils import calculate_change
from utils.database import get_db
from utils.slack import send_scraper_failure_alert, send_holdings_change_alert
from utils.validation import is_valid_ticker

# Configuration
DATA_FILE = Path(__file__).parent.parent / "data.json"
USER_AGENT = os.environ.get("SEC_USER_AGENT", "")


def validate_sec_user_agent() -> bool:
    """
    Validate that SEC_USER_AGENT environment variable is properly configured.
    SEC requires a valid User-Agent with contact info to avoid rate limiting/blocking.
    """
    if not USER_AGENT:
        print("=" * 60)
        print("ERROR: SEC_USER_AGENT environment variable is not set!")
        print("=" * 60)
        print()
        print("The SEC requires a valid User-Agent header for EDGAR API access.")
        print("Without it, requests may be blocked or rate-limited.")
        print()
        print("To fix this:")
        print("  1. Set the SEC_USER_AGENT environment variable")
        print("  2. Format: 'YourApp/1.0 (your-email@example.com)'")
        print()
        print("Examples:")
        print("  export SEC_USER_AGENT='DAT-Monitor/1.0 (yourname@company.com)'")
        print()
        print("For GitHub Actions:")
        print("  Add SEC_USER_AGENT as a repository secret in")
        print("  Settings > Secrets and variables > Actions")
        print("=" * 60)
        return False

    if "@" not in USER_AGENT:
        print("=" * 60)
        print("WARNING: SEC_USER_AGENT may be invalid")
        print("=" * 60)
        print(f"Current value: {USER_AGENT}")
        print()
        print("SEC recommends including contact email in User-Agent.")
        print("Format: 'YourApp/1.0 (your-email@example.com)'")
        print("=" * 60)

    return True


def load_data() -> Optional[dict]:
    """Load current data.json."""
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading data.json: {e}")
        return None


def save_data(data: dict):
    """Save updated data.json with proper Eastern timezone handling."""
    # Use proper US/Eastern timezone (handles EST/EDT automatically)
    eastern = pytz.timezone("US/Eastern")
    now = datetime.now(eastern)

    data["lastUpdated"] = now.isoformat()
    # Display format: "Jan 20, 2026 10:25 PM ET"
    data["lastUpdatedDisplay"] = now.strftime("%b %d, %Y %I:%M %p ET")

    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nSaved updated data to {DATA_FILE}")


def calculate_days_back(last_updated_str: str) -> int:
    """Calculate days since last update, with a minimum of 1 day."""
    try:
        last_updated = datetime.fromisoformat(last_updated_str)
        days = (datetime.now() - last_updated).days + 1
        return max(1, min(days, 90))
    except (ValueError, TypeError):
        return 14


def update_company(
    company: dict,
    token: str,
    days_back: int = 14,
    dry_run: bool = False,
    token_config: dict = None
) -> dict:
    """
    Update a single company's data using the appropriate scraper.

    Args:
        company: Company dict from data.json
        token: Token type (BTC, ETH, SOL, HYPE, BNB)
        days_back: Days to look back for SEC filings
        dry_run: If True, don't return updates
        token_config: Token configuration (validation ranges, keywords) from data.json

    Returns:
        Dict with updates including a 'status' field:
        - 'ok': Successfully checked (whether or not holdings changed)
        - 'error': Failed to check due to network/parsing error
    """
    ticker = company.get("ticker", "")
    current_holdings = company.get("tokens", 0)

    # Validate ticker format (2-5 uppercase letters)
    if not is_valid_ticker(ticker, strict=False):
        print(f"  Skipping invalid ticker: {ticker}")
        return {"status": "error", "lastError": f"Invalid ticker format: {ticker}"}

    print(f"  Checking {ticker} ({token})...")

    updates = {}

    try:
        # Get the appropriate scraper based on config (factory handles all types)
        scraper = get_scraper(company, token, days_back=days_back, token_config=token_config)
        result = scraper.scrape()

        if result and result.tokens != current_holdings:
            print(f"    Update: {current_holdings:,} -> {result.tokens:,} {token}")

            if dry_run:
                return {"status": "ok"}

            updates["tokens"] = result.tokens
            updates["lastUpdate"] = result.date
            updates["alertUrl"] = result.url
            updates["alertDate"] = result.date

            # Determine note based on scraper type
            if result.source == "company_dashboard":
                updates["alertNote"] = "Dashboard update"
            elif result.source.startswith("ex") or "8k" in result.source.lower():
                updates["alertNote"] = f"8-K: {result.source}"
                updates["lastSecUpdate"] = result.date
            else:
                updates["alertNote"] = f"Web: {result.source}"

        # Mark as successfully checked
        updates["status"] = "ok"
        updates["lastChecked"] = datetime.now().isoformat()

    except requests.RequestException as e:
        print(f"    Error checking {ticker}: {e}")
        updates["status"] = "error"
        updates["lastError"] = str(e)
        updates["lastErrorTime"] = datetime.now(pytz.timezone("US/Eastern")).isoformat()

        # Send Slack alert for scraper failure
        try:
            send_scraper_failure_alert(
                ticker=ticker,
                token=token,
                error=str(e),
                dry_run=dry_run
            )
        except Exception:
            pass  # Don't fail scraper if Slack alert fails

    except Exception as e:
        print(f"    Unexpected error checking {ticker}: {e}")
        updates["status"] = "error"
        updates["lastError"] = str(e)
        updates["lastErrorTime"] = datetime.now(pytz.timezone("US/Eastern")).isoformat()

        # Send Slack alert for scraper failure
        try:
            send_scraper_failure_alert(
                ticker=ticker,
                token=token,
                error=str(e),
                dry_run=dry_run
            )
        except Exception:
            pass  # Don't fail scraper if Slack alert fails

    return updates


def run_scraper(
    data: dict,
    ticker_filter: Optional[str] = None,
    dry_run: bool = False
) -> tuple[bool, list[dict], list[dict], int]:
    """
    Run the scraper on all companies or a specific ticker.

    Args:
        data: Full data.json dict
        ticker_filter: Optional ticker to filter to single company
        dry_run: If True, don't save changes

    Returns:
        Tuple of (changes_made, changes_list, error_list, success_count)
    """
    last_updated = data.get("lastUpdated", "")
    days_back = calculate_days_back(last_updated)

    # Get token configuration for validation ranges
    token_configs = data.get("tokenConfig", {})

    last_date = last_updated[:10] if last_updated else "unknown"
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"\nChecking for changes from {last_date} to {today} ({days_back} days)")

    if dry_run:
        print("DRY RUN - no changes will be saved")

    changes_made = False
    changes_list = []
    error_list = []
    success_count = 0

    for token, companies in data.get("companies", {}).items():
        print(f"\n{'─' * 40}")
        print(f"Processing {token} companies...")

        for i, company in enumerate(companies):
            # Skip if filtering by ticker
            if ticker_filter and company.get("ticker") != ticker_filter:
                continue

            # Get token-specific config for validation ranges
            token_config = token_configs.get(token, {})
            updates = update_company(
                company, token,
                days_back=days_back,
                dry_run=dry_run,
                token_config=token_config
            )

            if updates:
                # Track success/error status
                if updates.get("status") == "error":
                    error_list.append({
                        "ticker": company["ticker"],
                        "token": token,
                        "error": updates.get("lastError", "Unknown error")
                    })
                else:
                    success_count += 1

                # Calculate change if we have new token count
                if "tokens" in updates:
                    old_tokens = company.get("tokens", 0)
                    new_tokens = updates["tokens"]
                    if new_tokens != old_tokens:
                        updates["change"] = calculate_change(old_tokens, new_tokens)
                        changes_made = True
                        change_amount = new_tokens - old_tokens
                        changes_list.append({
                            "ticker": company["ticker"],
                            "token": token,
                            "old": old_tokens,
                            "new": new_tokens,
                            "change": change_amount
                        })

                        # Send Slack alert for holdings change
                        try:
                            send_holdings_change_alert(
                                ticker=company["ticker"],
                                token=token,
                                old_holdings=old_tokens,
                                new_holdings=new_tokens,
                                source_url=updates.get("alertUrl", ""),
                                dry_run=dry_run
                            )
                        except Exception:
                            pass  # Don't fail scraper if Slack alert fails

                        # Save to Supabase database (change is auto-calculated from previous filing)
                        if not dry_run:
                            try:
                                db = get_db()
                                if db:
                                    db.save_holding(
                                        ticker=company["ticker"],
                                        tokens=new_tokens,
                                        filing_date=updates.get("lastUpdate", datetime.now().strftime("%Y-%m-%d")),
                                        source_url=updates.get("alertUrl", "")
                                    )
                            except Exception as e:
                                print(f"    ⚠️ DB Error: {e} (data.json backup saved)")

                # Apply updates
                if not dry_run:
                    companies[i].update(updates)

    return changes_made, changes_list, error_list, success_count


def main():
    """Main scraper entry point."""
    parser = argparse.ArgumentParser(description="DAT Treasury Monitor Scraper")
    parser.add_argument(
        "--ticker",
        help="Only check specific ticker (e.g., MSTR)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't save changes, just show what would happen"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("DAT Treasury Monitor - Auto-Update Scraper")
    print(f"Started at {datetime.now().isoformat()}")
    print("=" * 60)

    # Validate SEC User-Agent before proceeding
    if not validate_sec_user_agent():
        print("\nExiting due to missing SEC_USER_AGENT configuration.")
        return

    data = load_data()
    if not data:
        print("Failed to load data.json, exiting.")
        return

    changes_made, changes_list, error_list, success_count = run_scraper(
        data,
        ticker_filter=args.ticker,
        dry_run=args.dry_run
    )

    # Recalculate totals
    if not args.dry_run:
        totals = {}
        for token, companies in data.get("companies", {}).items():
            totals[token] = sum(c.get("tokens", 0) for c in companies)
        data["totals"] = totals

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'─' * 40}")

    # Health status
    total_companies = success_count + len(error_list)
    print(f"Health: {success_count}/{total_companies} companies checked successfully")

    if error_list:
        print(f"\nERRORS ({len(error_list)}):")
        for e in error_list:
            print(f"  {e['ticker']} ({e['token']}): {e['error'][:60]}")

    # Holdings changes
    if changes_made:
        print("\nCHANGES DETECTED:")
        for c in changes_list:
            sign = "+" if c["change"] > 0 else ""
            print(f"  {c['ticker']}: {c['old']:,} -> {c['new']:,} ({sign}{c['change']:,} {c['token']})")

        if not args.dry_run:
            save_data(data)
        else:
            print("\nDRY RUN - changes not saved")
    else:
        print("\nNo holdings changes detected")
        if not args.dry_run:
            save_data(data)

    print(f"\nCompleted at {datetime.now().isoformat()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
