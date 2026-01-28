#!/usr/bin/env python3
"""
DAT Holdings History CSV Importer

Imports historical holdings data from dbt-format CSV files into Supabase.
Designed to match the exact format used in dbt-main/seeds/digital_asset_treasury/.

CSV Format:
    date,num_of_tokens,convertible_debt,convertible_debt_shares,non_convertible_debt,warrents,warrent_shares,num_of_shares,latest_cash

Usage:
    # Single file import
    python scripts/import_csv.py --file btbt_datadump.csv --ticker BTBT --dry-run

    # Bulk import from dbt-main
    python scripts/import_csv.py --bulk --source ~/code/dbt-main/seeds/digital_asset_treasury/

    # Validate only
    python scripts/import_csv.py --file btbt_datadump.csv --ticker BTBT --validate-only
"""

import argparse
import csv
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.database import get_db
from scripts.utils.validation import validate_ticker, ValidationError

# CSV column mapping: dbt CSV header -> internal name
CSV_COLUMN_MAP = {
    'date': 'date',
    'num_of_tokens': 'token_count',
    'convertible_debt': 'convertible_debt',
    'convertible_debt_shares': 'convertible_debt_shares',
    'non_convertible_debt': 'non_convertible_debt',
    'warrents': 'warrants',  # Note: typo in source CSV
    'warrent_shares': 'warrant_shares',  # Note: typo in source CSV
    'num_of_shares': 'shares_outstanding',
    'latest_cash': 'cash_position',
}

# Required columns for valid import
REQUIRED_COLUMNS = {'date', 'num_of_tokens'}

# Ticker extraction pattern from filename (e.g., btbt_datadump.csv -> BTBT)
TICKER_FROM_FILENAME = re.compile(r'^([a-z]{2,5})_datadump(?:_v\d+)?\.csv$', re.IGNORECASE)


def clean_numeric(value: str) -> Optional[Decimal]:
    """
    Clean and parse a numeric value from CSV.

    Handles:
    - Empty strings -> None
    - Trailing .00 decimals
    - Commas as thousand separators
    - Whitespace

    Args:
        value: Raw string value from CSV

    Returns:
        Decimal value or None if empty/invalid
    """
    if value is None:
        return None

    value = str(value).strip()
    if value == '' or value.lower() == 'null' or value.lower() == 'none':
        return None

    # Remove trailing .00 for cleaner integers
    cleaned = re.sub(r'\.00$', '', value)
    # Remove commas (thousand separators)
    cleaned = cleaned.replace(',', '')

    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_date(value: str) -> Optional[str]:
    """
    Parse and validate a date string.

    Args:
        value: Date string (expected YYYY-MM-DD)

    Returns:
        ISO format date string or None if invalid
    """
    if not value:
        return None

    value = str(value).strip()
    if not value:
        return None

    # Try common date formats
    for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%Y/%m/%d']:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            continue

    return None


def parse_csv_row(row: dict) -> dict:
    """
    Parse a single CSV row into database format.

    Args:
        row: Dict from csv.DictReader

    Returns:
        Dict with cleaned/mapped values
    """
    result = {}

    for csv_col, db_col in CSV_COLUMN_MAP.items():
        if csv_col not in row:
            continue

        raw_value = row[csv_col]

        if db_col == 'date':
            result[db_col] = parse_date(raw_value)
        else:
            result[db_col] = clean_numeric(raw_value)

    return result


def validate_row(row: dict, row_num: int) -> list[str]:
    """
    Validate a parsed row.

    Args:
        row: Parsed row dict
        row_num: Row number for error messages

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Check required fields
    if not row.get('date'):
        errors.append(f"Row {row_num}: Missing or invalid date")

    if row.get('token_count') is None:
        errors.append(f"Row {row_num}: Missing or invalid num_of_tokens")

    # Validate numeric ranges
    if row.get('token_count') is not None and row['token_count'] < 0:
        errors.append(f"Row {row_num}: Negative token_count ({row['token_count']})")

    if row.get('shares_outstanding') is not None and row['shares_outstanding'] < 0:
        errors.append(f"Row {row_num}: Negative shares_outstanding ({row['shares_outstanding']})")

    if row.get('cash_position') is not None and row['cash_position'] < 0:
        errors.append(f"Row {row_num}: Negative cash_position ({row['cash_position']})")

    return errors


def detect_csv_columns(file_path: Path) -> tuple[list[str], bool]:
    """
    Detect CSV columns and check if they match expected format.

    Args:
        file_path: Path to CSV file

    Returns:
        Tuple of (column_list, is_valid_format)
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        try:
            headers = next(reader)
        except StopIteration:
            return [], False

    # Clean headers (strip whitespace)
    headers = [h.strip().lower() for h in headers]

    # Check required columns
    has_required = all(col in headers for col in REQUIRED_COLUMNS)

    return headers, has_required


def extract_ticker_from_filename(filename: str) -> Optional[str]:
    """
    Extract ticker from dbt-style filename.

    Args:
        filename: Filename like 'btbt_datadump.csv'

    Returns:
        Uppercase ticker or None
    """
    match = TICKER_FROM_FILENAME.match(filename)
    if match:
        return match.group(1).upper()
    return None


def import_csv_file(
    file_path: Path,
    ticker: str,
    db,
    dry_run: bool = False,
    validate_only: bool = False,
) -> dict:
    """
    Import a single CSV file into the database.

    Args:
        file_path: Path to CSV file
        ticker: Company ticker symbol
        db: Database connection (can be None for dry_run)
        dry_run: If True, don't write to database
        validate_only: If True, only validate (implies dry_run)

    Returns:
        Stats dict with import results
    """
    stats = {
        'ticker': ticker,
        'file': str(file_path),
        'rows_parsed': 0,
        'rows_valid': 0,
        'rows_imported': 0,
        'rows_skipped': 0,
        'validation_errors': [],
        'import_errors': [],
        'date_range': {'earliest': None, 'latest': None},
    }

    if validate_only:
        dry_run = True

    # Validate ticker
    try:
        ticker = validate_ticker(ticker, strict=True)
    except ValidationError as e:
        stats['import_errors'].append(f"Invalid ticker: {e}")
        return stats

    # Check file exists
    if not file_path.exists():
        stats['import_errors'].append(f"File not found: {file_path}")
        return stats

    # Detect columns
    headers, is_valid = detect_csv_columns(file_path)
    if not is_valid:
        stats['import_errors'].append(
            f"CSV missing required columns. Found: {headers}. "
            f"Required: {REQUIRED_COLUMNS}"
        )
        return stats

    # Get company_id
    company_id = None
    if not dry_run and db:
        company_id = db.get_company_id(ticker)
        if not company_id:
            stats['import_errors'].append(f"Company '{ticker}' not found in database")
            return stats

    # Parse all rows
    rows_data = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):  # Row 1 is header
            stats['rows_parsed'] += 1

            parsed = parse_csv_row(row)
            errors = validate_row(parsed, row_num)

            if errors:
                stats['validation_errors'].extend(errors)
                stats['rows_skipped'] += 1
                continue

            stats['rows_valid'] += 1

            if not validate_only:
                rows_data.append(parsed)

    if validate_only:
        # Just return validation results
        if rows_data or stats['rows_valid'] > 0:
            # Find date range from parsed rows
            valid_dates = []
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    d = parse_date(row.get('date'))
                    if d:
                        valid_dates.append(d)
            if valid_dates:
                stats['date_range']['earliest'] = min(valid_dates)
                stats['date_range']['latest'] = max(valid_dates)
        return stats

    # Sort by date
    rows_data.sort(key=lambda x: x['date'])

    # Update date range
    if rows_data:
        stats['date_range']['earliest'] = rows_data[0]['date']
        stats['date_range']['latest'] = rows_data[-1]['date']

    # Calculate token_change
    prev_tokens = None
    for row in rows_data:
        if prev_tokens is not None and row['token_count'] is not None:
            row['token_change'] = row['token_count'] - prev_tokens
        else:
            row['token_change'] = None
        if row['token_count'] is not None:
            prev_tokens = row['token_count']

    if dry_run:
        stats['rows_imported'] = len(rows_data)
        return stats

    # Insert into database
    batch_size = 100
    for i in range(0, len(rows_data), batch_size):
        batch = rows_data[i:i + batch_size]

        # Prepare records for upsert
        records = []
        for row in batch:
            record = {
                'company_id': company_id,
                'date': row['date'],
                'token_count': float(row['token_count']) if row['token_count'] is not None else None,
                'source': 'csv_import',
                'import_source': 'csv_import',
            }

            # Add optional fields
            if row.get('token_change') is not None:
                record['token_change'] = float(row['token_change'])
            if row.get('shares_outstanding') is not None:
                record['shares_outstanding'] = float(row['shares_outstanding'])
            if row.get('convertible_debt') is not None:
                record['convertible_debt'] = float(row['convertible_debt'])
            if row.get('convertible_debt_shares') is not None:
                record['convertible_debt_shares'] = float(row['convertible_debt_shares'])
            if row.get('non_convertible_debt') is not None:
                record['non_convertible_debt'] = float(row['non_convertible_debt'])
            if row.get('warrants') is not None:
                record['warrants'] = float(row['warrants'])
            if row.get('warrant_shares') is not None:
                record['warrant_shares'] = float(row['warrant_shares'])
            if row.get('cash_position') is not None:
                record['cash_position'] = float(row['cash_position'])

            records.append(record)

        try:
            db.supabase.table('holdings_history').upsert(
                records,
                on_conflict='company_id,date'
            ).execute()
            stats['rows_imported'] += len(records)
        except Exception as e:
            stats['import_errors'].append(f"Batch insert error: {e}")
            # Try individual inserts
            for record in records:
                try:
                    db.supabase.table('holdings_history').upsert(
                        [record],
                        on_conflict='company_id,date'
                    ).execute()
                    stats['rows_imported'] += 1
                except Exception as inner_e:
                    stats['import_errors'].append(f"Row insert error: {inner_e}")
                    stats['rows_skipped'] += 1

    return stats


def bulk_import(
    source_dir: Path,
    db,
    dry_run: bool = False,
    validate_only: bool = False,
    ticker_filter: Optional[str] = None,
) -> list[dict]:
    """
    Import all CSV files from a directory.

    Args:
        source_dir: Directory containing CSV files
        db: Database connection
        dry_run: If True, don't write to database
        validate_only: If True, only validate
        ticker_filter: Only process this ticker (optional)

    Returns:
        List of stats dicts for each file
    """
    all_stats = []

    if not source_dir.exists():
        print(f"ERROR: Directory not found: {source_dir}")
        return all_stats

    # Find all datadump CSV files
    csv_files = list(source_dir.glob('*_datadump*.csv'))

    if not csv_files:
        print(f"No *_datadump*.csv files found in {source_dir}")
        return all_stats

    print(f"Found {len(csv_files)} CSV files")
    print()

    for csv_file in sorted(csv_files):
        # Extract ticker from filename
        ticker = extract_ticker_from_filename(csv_file.name)

        if not ticker:
            print(f"Skipping {csv_file.name}: Cannot extract ticker from filename")
            continue

        # Apply filter
        if ticker_filter and ticker != ticker_filter.upper():
            continue

        print(f"Processing: {csv_file.name} -> {ticker}")

        stats = import_csv_file(
            csv_file,
            ticker,
            db,
            dry_run=dry_run,
            validate_only=validate_only,
        )
        all_stats.append(stats)

        # Print results
        if validate_only:
            print(f"  Parsed: {stats['rows_parsed']} rows")
            print(f"  Valid: {stats['rows_valid']} rows")
        else:
            print(f"  Imported: {stats['rows_imported']} rows")

        if stats['rows_skipped'] > 0:
            print(f"  Skipped: {stats['rows_skipped']} rows")

        if stats['date_range']['earliest']:
            print(f"  Date range: {stats['date_range']['earliest']} to {stats['date_range']['latest']}")

        if stats['validation_errors']:
            print(f"  Validation errors: {len(stats['validation_errors'])}")
            for err in stats['validation_errors'][:5]:  # Show first 5
                print(f"    - {err}")
            if len(stats['validation_errors']) > 5:
                print(f"    ... and {len(stats['validation_errors']) - 5} more")

        if stats['import_errors']:
            for err in stats['import_errors']:
                print(f"  ERROR: {err}")

        print()

    return all_stats


def main():
    parser = argparse.ArgumentParser(
        description="Import DAT holdings history from dbt-format CSV files"
    )

    # Input source (mutually exclusive)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        '--file', '-f',
        type=Path,
        help='Path to single CSV file'
    )
    source_group.add_argument(
        '--bulk',
        action='store_true',
        help='Import all CSV files from source directory'
    )

    # Options
    parser.add_argument(
        '--ticker', '-t',
        help='Ticker symbol (required for single file, optional filter for bulk)'
    )
    parser.add_argument(
        '--source', '-s',
        type=Path,
        default=Path.home() / 'code' / 'dbt-main' / 'seeds' / 'digital_asset_treasury',
        help='Source directory for bulk import (default: ~/code/dbt-main/seeds/digital_asset_treasury/)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Parse and preview without writing to database'
    )
    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Only validate CSV format and data (implies --dry-run)'
    )

    args = parser.parse_args()

    # Validate arguments
    if args.file and not args.ticker:
        # Try to extract ticker from filename
        args.ticker = extract_ticker_from_filename(args.file.name)
        if not args.ticker:
            parser.error("--ticker is required for single file import (cannot auto-detect from filename)")

    print("=" * 60)
    print("DAT Holdings History CSV Importer")
    print("=" * 60)

    if args.file:
        print(f"File: {args.file}")
        print(f"Ticker: {args.ticker}")
    else:
        print(f"Source: {args.source}")
        if args.ticker:
            print(f"Filter: {args.ticker} only")

    if args.validate_only:
        print("Mode: VALIDATE ONLY")
    elif args.dry_run:
        print("Mode: DRY RUN (no database writes)")

    print()

    # Connect to database
    if not args.dry_run and not args.validate_only:
        db = get_db()
        if not db:
            print("ERROR: Failed to connect to database")
            print("Make sure SUPABASE_URL and SUPABASE_KEY are set in .env")
            sys.exit(1)
    else:
        db = None

    # Run import
    if args.file:
        stats = import_csv_file(
            args.file,
            args.ticker,
            db,
            dry_run=args.dry_run,
            validate_only=args.validate_only,
        )
        all_stats = [stats]

        # Print single file results
        if args.validate_only:
            print(f"Parsed: {stats['rows_parsed']} rows")
            print(f"Valid: {stats['rows_valid']} rows")
        else:
            print(f"Imported: {stats['rows_imported']} rows")

        if stats['rows_skipped'] > 0:
            print(f"Skipped: {stats['rows_skipped']} rows")

        if stats['date_range']['earliest']:
            print(f"Date range: {stats['date_range']['earliest']} to {stats['date_range']['latest']}")

        if stats['validation_errors']:
            print()
            print("Validation Errors:")
            for err in stats['validation_errors']:
                print(f"  - {err}")

        if stats['import_errors']:
            print()
            print("Import Errors:")
            for err in stats['import_errors']:
                print(f"  - {err}")
    else:
        all_stats = bulk_import(
            args.source,
            db,
            dry_run=args.dry_run,
            validate_only=args.validate_only,
            ticker_filter=args.ticker,
        )

    # Summary
    print("=" * 60)
    print("IMPORT SUMMARY")
    print("=" * 60)

    total_parsed = sum(s['rows_parsed'] for s in all_stats)
    total_valid = sum(s['rows_valid'] for s in all_stats)
    total_imported = sum(s['rows_imported'] for s in all_stats)
    total_skipped = sum(s['rows_skipped'] for s in all_stats)
    total_errors = sum(len(s['validation_errors']) + len(s['import_errors']) for s in all_stats)

    print(f"Files processed: {len(all_stats)}")
    print(f"Rows parsed: {total_parsed}")
    print(f"Rows valid: {total_valid}")
    if not args.validate_only:
        print(f"Rows imported: {total_imported}")
    print(f"Rows skipped: {total_skipped}")

    if total_errors > 0:
        print(f"Total errors: {total_errors}")

    if args.validate_only:
        print()
        print("VALIDATE ONLY complete - no data was written")
    elif args.dry_run:
        print()
        print("DRY RUN complete - no data was written")

    print()

    # Exit with error if any failures
    if total_errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
