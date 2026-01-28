#!/usr/bin/env python3
"""
DAT dbt Sync Validator

Validates consistency between DAT Monitor and dbt-main seed files.

Checks:
1. CSV file exists for each tracked ticker
2. Latest dates match between systems
3. Token counts match
4. dbt model exists for ticker

Usage:
    python scripts/validate_dbt_sync.py
    python scripts/validate_dbt_sync.py --ticker BTBT
    python scripts/validate_dbt_sync.py --fix  # Show fix suggestions
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

# Default dbt paths
DEFAULT_DBT_SEEDS_PATH = Path.home() / "code" / "dbt-main" / "seeds" / "digital_asset_treasury"
DEFAULT_DBT_MODELS_PATH = Path.home() / "code" / "dbt-main" / "models" / "equities" / "digital_asset_treasury"


class ValidationResult:
    """Holds validation results for a single ticker."""

    def __init__(self, ticker: str):
        self.ticker = ticker
        self.checks = []
        self.errors = []
        self.warnings = []

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def add_check(self, name: str, passed: bool, message: str = ""):
        self.checks.append({
            'name': name,
            'passed': passed,
            'message': message,
        })
        if not passed:
            self.errors.append(f"{name}: {message}")

    def add_warning(self, message: str):
        self.warnings.append(message)


def read_csv_latest_record(csv_path: Path) -> Optional[dict]:
    """
    Read the latest (last) record from a dbt CSV file.

    Args:
        csv_path: Path to CSV file

    Returns:
        Dict with last row data, or None if file doesn't exist/is empty
    """
    if not csv_path.exists():
        return None

    last_row = None
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                last_row = row
    except (IOError, csv.Error):
        return None

    return last_row


def validate_ticker(
    ticker: str,
    db,
    seeds_path: Path,
    models_path: Path,
) -> ValidationResult:
    """
    Validate a single ticker's sync status.

    Args:
        ticker: Company ticker symbol
        db: Database connection
        seeds_path: Path to dbt seeds directory
        models_path: Path to dbt models directory

    Returns:
        ValidationResult with all checks
    """
    result = ValidationResult(ticker)

    # Check 1: CSV file exists
    csv_file = seeds_path / f"{ticker.lower()}_datadump.csv"
    csv_exists = csv_file.exists()
    result.add_check(
        "csv_exists",
        csv_exists,
        f"File not found: {csv_file}" if not csv_exists else ""
    )

    if not csv_exists:
        return result

    # Check 2: Company exists in database
    company_id = db.get_company_id(ticker)
    db_exists = company_id is not None
    result.add_check(
        "db_company_exists",
        db_exists,
        f"Company '{ticker}' not found in database" if not db_exists else ""
    )

    if not db_exists:
        return result

    # Check 3: Get latest records from both sources
    csv_latest = read_csv_latest_record(csv_file)

    try:
        db_result = (
            db.supabase.table("holdings_history")
            .select("date, token_count")
            .eq("company_id", company_id)
            .order("date", desc=True)
            .limit(1)
            .execute()
        )
        db_latest = db_result.data[0] if db_result.data else None
    except Exception as e:
        result.add_check("db_query", False, f"Database query failed: {e}")
        return result

    # Check 4: Both have data
    if not csv_latest:
        result.add_check("csv_has_data", False, "CSV file is empty")
        return result

    if not db_latest:
        result.add_check("db_has_data", False, "No holdings history in database")
        return result

    result.add_check("csv_has_data", True, "")
    result.add_check("db_has_data", True, "")

    # Check 5: Latest dates match
    csv_date = csv_latest.get('date', '').strip()
    db_date = db_latest.get('date', '').strip()

    dates_match = csv_date == db_date
    if not dates_match:
        result.add_check(
            "dates_match",
            False,
            f"Date mismatch: CSV={csv_date}, DB={db_date}"
        )
    else:
        result.add_check("dates_match", True, "")

    # Check 6: Token counts match (with tolerance for rounding)
    try:
        csv_tokens = float(csv_latest.get('num_of_tokens', 0) or 0)
        db_tokens = float(db_latest.get('token_count', 0) or 0)

        # Allow 0.01% tolerance for floating point differences
        if csv_tokens > 0:
            diff_pct = abs(csv_tokens - db_tokens) / csv_tokens * 100
            tokens_match = diff_pct < 0.01
        else:
            tokens_match = db_tokens == 0

        if not tokens_match:
            result.add_check(
                "tokens_match",
                False,
                f"Token mismatch: CSV={csv_tokens:,.0f}, DB={db_tokens:,.0f}"
            )
        else:
            result.add_check("tokens_match", True, "")
    except (ValueError, TypeError) as e:
        result.add_check("tokens_match", False, f"Could not compare tokens: {e}")

    # Check 7: dbt model exists (optional warning)
    model_file = models_path / f"{ticker.lower()}_fundamental_metrics.sql"
    if not model_file.exists():
        result.add_warning(f"dbt model not found: {model_file.name}")

    return result


def get_tickers_to_validate(
    db,
    ticker_filter: Optional[str],
    seeds_path: Path,
) -> list[str]:
    """
    Get list of tickers to validate.

    Combines tickers from:
    - Whitelist
    - Existing CSV files
    - Database

    Args:
        db: Database connection
        ticker_filter: Optional specific ticker
        seeds_path: Path to dbt seeds directory

    Returns:
        Sorted list of ticker symbols
    """
    if ticker_filter:
        return [ticker_filter.upper()]

    tickers = set(ALL_WHITELISTED_TICKERS)

    # Add tickers from existing CSV files
    if seeds_path.exists():
        for csv_file in seeds_path.glob("*_datadump.csv"):
            ticker = csv_file.stem.replace("_datadump", "").upper()
            if len(ticker) >= 2 and len(ticker) <= 5:
                tickers.add(ticker)

    return sorted(tickers)


def main():
    parser = argparse.ArgumentParser(
        description="Validate DAT Monitor and dbt-main sync status"
    )

    parser.add_argument(
        '--ticker', '-t',
        help='Validate specific ticker only'
    )
    parser.add_argument(
        '--seeds-path',
        type=Path,
        default=DEFAULT_DBT_SEEDS_PATH,
        help=f'Path to dbt seeds directory (default: {DEFAULT_DBT_SEEDS_PATH})'
    )
    parser.add_argument(
        '--models-path',
        type=Path,
        default=DEFAULT_DBT_MODELS_PATH,
        help=f'Path to dbt models directory (default: {DEFAULT_DBT_MODELS_PATH})'
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help='Show suggestions to fix sync issues'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output results as JSON'
    )

    args = parser.parse_args()

    # Connect to database
    db = get_db()
    if not db:
        if args.json:
            print(json.dumps({"error": "Failed to connect to database"}))
        else:
            print("ERROR: Failed to connect to database")
            print("Make sure SUPABASE_URL and SUPABASE_KEY are set in .env")
        sys.exit(1)

    # Get tickers to validate
    tickers = get_tickers_to_validate(db, args.ticker, args.seeds_path)

    if not args.json:
        print("=" * 60)
        print("DAT Monitor <-> dbt-main Sync Validator")
        print("=" * 60)
        print(f"Seeds path: {args.seeds_path}")
        print(f"Models path: {args.models_path}")
        print(f"Tickers to validate: {len(tickers)}")
        print()

    # Validate each ticker
    all_results = []
    for ticker in tickers:
        result = validate_ticker(
            ticker,
            db,
            args.seeds_path,
            args.models_path,
        )
        all_results.append(result)

        if not args.json:
            status = "PASS" if result.passed else "FAIL"
            status_symbol = "✅" if result.passed else "❌"
            print(f"{status_symbol} {ticker}: {status}")

            if result.errors:
                for err in result.errors:
                    print(f"   - {err}")

            if result.warnings:
                for warn in result.warnings:
                    print(f"   ⚠️ {warn}")

            if args.fix and not result.passed:
                print(f"   Fix: python scripts/export_dbt_seeds.py --ticker {ticker}")

    # Summary
    passed = [r for r in all_results if r.passed]
    failed = [r for r in all_results if not r.passed]

    if args.json:
        output = {
            "summary": {
                "total": len(all_results),
                "passed": len(passed),
                "failed": len(failed),
            },
            "results": [
                {
                    "ticker": r.ticker,
                    "passed": r.passed,
                    "errors": r.errors,
                    "warnings": r.warnings,
                }
                for r in all_results
            ]
        }
        print(json.dumps(output, indent=2))
    else:
        print()
        print("=" * 60)
        print("VALIDATION SUMMARY")
        print("=" * 60)
        print(f"Total tickers: {len(all_results)}")
        print(f"Passed: {len(passed)}")
        print(f"Failed: {len(failed)}")

        if failed:
            print()
            print("Failed tickers:")
            for r in failed:
                print(f"  - {r.ticker}")

            if args.fix:
                print()
                print("To fix all failures, run:")
                print("  python scripts/export_dbt_seeds.py --all")

    # Exit with error if any failures
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
