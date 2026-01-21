#!/usr/bin/env python3
"""
Update token prices, stock prices, and NAV for all companies.

Fetches:
- Token prices from CoinGecko (BTC, ETH, SOL, HYPE, BNB)
- Share prices from Yahoo Finance

Uses from database (Excel imports):
- Shares outstanding

Calculates:
- NAV = token_count * token_price
- Market Cap = shares_outstanding * share_price

Updates the holdings table in Supabase with current prices.
"""

import json
import argparse
from pathlib import Path
from datetime import datetime

from utils.prices import get_multiple_token_prices
from utils.stocks import get_stock_price
from utils.database import get_db


def load_data() -> dict:
    """Load companies from data.json."""
    data_path = Path(__file__).parent.parent / "data.json"
    with open(data_path) as f:
        return json.load(f)


def update_prices(dry_run: bool = False):
    """
    Fetch current prices and update all companies.

    Args:
        dry_run: If True, print what would be updated without saving to DB
    """
    print("=" * 60)
    print(f"Price Update - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Load data
    data = load_data()
    companies_by_token = data.get("companies", {})

    # Get all unique tokens
    tokens = list(companies_by_token.keys())
    print(f"\nFetching prices for: {', '.join(tokens)}")

    # Fetch all token prices in one batch call
    token_prices = get_multiple_token_prices(tokens)
    print(f"\nToken prices fetched:")
    for token, price in token_prices.items():
        print(f"  {token}: ${price:,.2f}")

    if not token_prices:
        print("\nNo token prices available. Exiting.")
        return

    # Get database connection
    db = get_db()
    if not db and not dry_run:
        print("\nDatabase connection failed. Use --dry-run to see prices without saving.")
        return

    # Process each company
    print("\n" + "-" * 60)
    print("Updating companies...")
    print("-" * 60)

    updated = 0
    skipped = 0
    errors = 0

    for token, companies in companies_by_token.items():
        token_price = token_prices.get(token)
        if not token_price:
            print(f"\n[{token}] No price available, skipping token")
            skipped += len(companies)
            continue

        print(f"\n[{token}] ${token_price:,.2f}")

        for company in companies:
            ticker = company.get("ticker")
            token_count = company.get("tokens", 0)
            last_update = company.get("lastUpdate")

            if not ticker or not last_update:
                print(f"  {ticker or 'Unknown'}: Missing data, skipping")
                skipped += 1
                continue

            # Calculate NAV
            nav = token_count * token_price

            # Fetch share price from Yahoo Finance
            share_price = get_stock_price(ticker)

            # Get company_id for database lookups
            company_id = db.get_company_id(ticker) if db else None

            # Get shares_outstanding from database (from Excel imports)
            shares_outstanding = None
            if company_id and db:
                shares_outstanding = db.get_shares_outstanding(company_id)

            # Calculate market cap from shares_outstanding * share_price
            market_cap = None
            if shares_outstanding and share_price:
                market_cap = shares_outstanding * share_price

            # Print summary
            print(f"  {ticker}:")
            print(f"    Tokens: {token_count:,.0f} {token}")
            print(f"    NAV: ${nav:,.2f}")
            if share_price:
                print(f"    Share Price: ${share_price:,.2f}")
            else:
                print(f"    Share Price: N/A")
            if shares_outstanding:
                print(f"    Shares Outstanding: {shares_outstanding:,.0f} (from Excel)")
            else:
                print(f"    Shares Outstanding: N/A (not in Excel data)")
            if market_cap:
                print(f"    Market Cap: ${market_cap:,.2f} (calculated)")

            # Update database
            if dry_run:
                print(f"    [DRY RUN] Would update {ticker} for {last_update}")
                updated += 1
            else:
                if not company_id:
                    print(f"    Company not found in DB")
                    errors += 1
                    continue

                success = db.update_holding_prices(
                    company_id=company_id,
                    filing_date=last_update,
                    token_price=token_price,
                    share_price=share_price,
                    shares_outstanding=None,  # Don't overwrite Excel data
                    market_cap=market_cap,
                    nav=nav,
                )
                if success:
                    print(f"    Updated in DB")
                    updated += 1
                else:
                    print(f"    DB update failed")
                    errors += 1

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Updated: {updated}")
    print(f"Skipped: {skipped}")
    print(f"Errors: {errors}")


def main():
    parser = argparse.ArgumentParser(
        description="Update token prices, stock prices, and NAV for all companies"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print prices without updating database",
    )
    args = parser.parse_args()

    update_prices(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
