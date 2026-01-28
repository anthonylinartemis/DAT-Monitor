#!/usr/bin/env python3
"""
DAT Holdings dbt Seeds Exporter

Exports holdings data from Supabase to dbt-format CSV files.
Output format matches dbt-main/seeds/digital_asset_treasury/*.csv

Usage:
    # Export all tickers
    python scripts/export_dbt_seeds.py --all

    # Export specific ticker
    python scripts/export_dbt_seeds.py --ticker BTBT

    # Dry run (preview without writing)
    python scripts/export_dbt_seeds.py --all --dry-run

    # Custom output directory
    python scripts/export_dbt_seeds.py --all --output ~/code/dbt-main/seeds/digital_asset_treasury/
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Optional

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.database import get_db
from scripts.utils.validation import ALL_WHITELISTED_TICKERS

# Default output path (dbt-main seeds directory)
DEFAULT_DBT_SEEDS_PATH = Path.home() / "code" / "dbt-main" / "seeds" / "digital_asset_treasury"

# CSV columns in exact dbt order
DBT_CSV_COLUMNS = [
    'date',
    'num_of_tokens',
    'convertible_debt',
    'convertible_debt_shares',
    'non_convertible_debt',
    'warrents',  # Note: typo preserved to match dbt-main format
    'warrent_shares',  # Note: typo preserved to match dbt-main format
    'num_of_shares',
    'latest_cash',
]

# Internal to CSV column mapping
INTERNAL_TO_CSV = {
    'date': 'date',
    'token_count': 'num_of_tokens',
    'convertible_debt': 'convertible_debt',
    'convertible_debt_shares': 'convertible_debt_shares',
    'non_convertible_debt': 'non_convertible_debt',
    'warrants': 'warrents',
    'warrant_shares': 'warrent_shares',
    'shares_outstanding': 'num_of_shares',
    'cash_position': 'latest_cash',
}


def format_number(value) -> str:
    """
    Format a number for CSV output.

    - None -> empty string
    - Integers -> no decimal places
    - Floats with .00 -> integer format
    - Other floats -> preserve decimal places (max 2)
    """
    if value is None:
        return ''

    try:
        num = float(value)
    except (TypeError, ValueError):
        return ''

    # Check if it's effectively an integer
    if num == int(num):
        return str(int(num))

    # Otherwise, format with up to 2 decimal places
    formatted = f"{num:.2f}"
    # Remove trailing zeros after decimal
    if '.' in formatted:
        formatted = formatted.rstrip('0').rstrip('.')
    return formatted


def export_ticker(
    ticker: str,
    db,
    output_dir: Path,
    dry_run: bool = False,
) -> dict:
    """
    Export a single ticker's holdings to CSV.

    Args:
        ticker: Company ticker symbol
        db: Database connection
        output_dir: Directory to write CSV
        dry_run: If True, don't write file

    Returns:
        Stats dict with export results
    """
    stats = {
        'ticker': ticker,
        'rows_exported': 0,
        'output_file': None,
        'date_range': {'earliest': None, 'latest': None},
        'errors': [],
    }

    # Get company ID
    company_id = db.get_company_id(ticker)
    if not company_id:
        stats['errors'].append(f"Company '{ticker}' not found in database")
        return stats

    # Fetch holdings history
    try:
        result = (
            db.supabase.table("holdings_history")
            .select("*")
            .eq("company_id", company_id)
            .order("date", desc=False)
            .execute()
        )
        records = result.data if result.data else []
    except Exception as e:
        stats['errors'].append(f"Database query error: {e}")
        return stats

    if not records:
        stats['errors'].append("No holdings history found")
        return stats

    # Update date range
    if records:
        stats['date_range']['earliest'] = records[0].get('date')
        stats['date_range']['latest'] = records[-1].get('date')

    # Convert to CSV format
    csv_rows = []
    for record in records:
        csv_row = {}
        for internal_col, csv_col in INTERNAL_TO_CSV.items():
            value = record.get(internal_col)
            csv_row[csv_col] = format_number(value)
        csv_rows.append(csv_row)

    stats['rows_exported'] = len(csv_rows)

    # Determine output filename
    output_file = output_dir / f"{ticker.lower()}_datadump.csv"
    stats['output_file'] = str(output_file)

    if dry_run:
        return stats

    # Write CSV file
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=DBT_CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(csv_rows)
    except Exception as e:
        stats['errors'].append(f"File write error: {e}")
        stats['rows_exported'] = 0

    return stats


def get_enabled_tickers(config_path: Optional[Path] = None) -> list[str]:
    """
    Get list of tickers enabled for dbt export.

    Reads from config/dbt_tickers.json if it exists,
    otherwise returns all whitelisted tickers.

    Args:
        config_path: Optional path to config file

    Returns:
        List of ticker symbols
    """
    if config_path is None:
        config_path = PROJECT_ROOT / "config" / "dbt_tickers.json"

    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            # Return only enabled tickers
            return [
                ticker for ticker, settings in config.get('tickers', {}).items()
                if settings.get('enabled', True)
            ]
        except (json.JSONDecodeError, IOError):
            pass

    # Default: all whitelisted tickers
    return sorted(ALL_WHITELISTED_TICKERS)


def main():
    parser = argparse.ArgumentParser(
        description="Export DAT holdings to dbt-format CSV files"
    )

    # Target selection
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument(
        '--all',
        action='store_true',
        help='Export all enabled tickers'
    )
    target_group.add_argument(
        '--ticker', '-t',
        help='Export specific ticker'
    )

    # Options
    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=DEFAULT_DBT_SEEDS_PATH,
        help=f'Output directory (default: {DEFAULT_DBT_SEEDS_PATH})'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview export without writing files'
    )
    parser.add_argument(
        '--config', '-c',
        type=Path,
        help='Path to dbt_tickers.json config file'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("DAT Holdings dbt Seeds Exporter")
    print("=" * 60)
    print(f"Output: {args.output}")
    if args.dry_run:
        print("Mode: DRY RUN (no files written)")
    print()

    # Connect to database
    db = get_db()
    if not db:
        print("ERROR: Failed to connect to database")
        print("Make sure SUPABASE_URL and SUPABASE_KEY are set in .env")
        sys.exit(1)

    # Determine tickers to export
    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        tickers = get_enabled_tickers(args.config)

    print(f"Tickers to export: {len(tickers)}")
    print()

    # Export each ticker
    all_stats = []
    for ticker in tickers:
        print(f"Exporting: {ticker}")

        stats = export_ticker(
            ticker,
            db,
            args.output,
            dry_run=args.dry_run,
        )
        all_stats.append(stats)

        if stats['rows_exported'] > 0:
            print(f"  Rows: {stats['rows_exported']}")
            if stats['date_range']['earliest']:
                print(f"  Date range: {stats['date_range']['earliest']} to {stats['date_range']['latest']}")
            if not args.dry_run:
                print(f"  Output: {stats['output_file']}")
        else:
            print(f"  Skipped: {stats['errors'][0] if stats['errors'] else 'No data'}")

        if stats['errors']:
            for err in stats['errors']:
                print(f"  ERROR: {err}")

        print()

    # Summary
    print("=" * 60)
    print("EXPORT SUMMARY")
    print("=" * 60)

    successful = [s for s in all_stats if s['rows_exported'] > 0]
    failed = [s for s in all_stats if s['errors']]

    print(f"Tickers processed: {len(all_stats)}")
    print(f"Successful exports: {len(successful)}")
    print(f"Total rows exported: {sum(s['rows_exported'] for s in all_stats)}")

    if failed:
        print(f"Failed exports: {len(failed)}")
        for stats in failed:
            print(f"  - {stats['ticker']}: {stats['errors'][0] if stats['errors'] else 'Unknown error'}")

    if args.dry_run:
        print()
        print("DRY RUN complete - no files were written")

    print()

    # Exit with error if any failures
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
