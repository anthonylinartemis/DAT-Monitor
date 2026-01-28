"""
Validation utilities for DAT Monitor.

Provides:
- Ticker validation (2-5 uppercase letters)
- Company whitelist to prevent arbitrary ticker injection
- Token type validation
"""

import re
from typing import Optional, Set

# Valid ticker pattern: 2-5 uppercase letters only
TICKER_PATTERN = re.compile(r'^[A-Z]{2,5}$')

# Whitelist of allowed DAT companies by token type
# This prevents arbitrary ticker injection attacks
COMPANY_WHITELIST: dict[str, Set[str]] = {
    "BTC": {"MSTR", "MTPLF", "XXI", "NAKA", "ASST", "ABTC"},
    "ETH": {"BMNR", "SBET", "ETHM", "BTBT", "BTCS", "FGNX", "ETHZ"},
    "SOL": {"FWDI", "HSDT", "DFDV", "UPXI", "STSS"},
    "HYPE": {"PURR", "HYPD"},
    "BNB": {"BNC"},
}

# All whitelisted tickers (flat set for quick lookup)
ALL_WHITELISTED_TICKERS: Set[str] = set()
for tickers in COMPANY_WHITELIST.values():
    ALL_WHITELISTED_TICKERS.update(tickers)

# Valid token types
VALID_TOKENS = {"BTC", "ETH", "SOL", "HYPE", "BNB"}


class ValidationError(Exception):
    """Raised when validation fails."""
    pass


def validate_ticker(ticker: str, strict: bool = True) -> str:
    """
    Validate a ticker symbol.

    Args:
        ticker: Ticker symbol to validate
        strict: If True, also check against whitelist

    Returns:
        Normalized (uppercase) ticker

    Raises:
        ValidationError: If ticker is invalid
    """
    if not ticker:
        raise ValidationError("Ticker cannot be empty")

    # Normalize to uppercase
    ticker = ticker.strip().upper()

    # Check format: 2-5 uppercase letters
    if not TICKER_PATTERN.match(ticker):
        raise ValidationError(
            f"Invalid ticker format: '{ticker}'. "
            "Must be 2-5 uppercase letters."
        )

    # Check whitelist if strict mode
    if strict and ticker not in ALL_WHITELISTED_TICKERS:
        raise ValidationError(
            f"Ticker '{ticker}' is not in the approved company whitelist. "
            "Contact administrator to add new companies."
        )

    return ticker


def validate_token(token: str) -> str:
    """
    Validate a token type.

    Args:
        token: Token type to validate (BTC, ETH, SOL, HYPE, BNB)

    Returns:
        Normalized (uppercase) token

    Raises:
        ValidationError: If token is invalid
    """
    if not token:
        raise ValidationError("Token type cannot be empty")

    token = token.strip().upper()

    if token not in VALID_TOKENS:
        raise ValidationError(
            f"Invalid token type: '{token}'. "
            f"Must be one of: {', '.join(sorted(VALID_TOKENS))}"
        )

    return token


def validate_company_for_token(ticker: str, token: str) -> bool:
    """
    Validate that a company/ticker is valid for the specified token type.

    Args:
        ticker: Company ticker symbol
        token: Token type (BTC, ETH, etc.)

    Returns:
        True if the company is whitelisted for this token

    Raises:
        ValidationError: If validation fails
    """
    ticker = validate_ticker(ticker, strict=False)
    token = validate_token(token)

    allowed_tickers = COMPANY_WHITELIST.get(token, set())
    if ticker not in allowed_tickers:
        raise ValidationError(
            f"Company '{ticker}' is not whitelisted for {token} token. "
            f"Allowed {token} companies: {', '.join(sorted(allowed_tickers))}"
        )

    return True


def is_valid_ticker(ticker: str, strict: bool = True) -> bool:
    """
    Check if a ticker is valid (non-raising version).

    Args:
        ticker: Ticker symbol to check
        strict: If True, also check against whitelist

    Returns:
        True if valid, False otherwise
    """
    try:
        validate_ticker(ticker, strict=strict)
        return True
    except ValidationError:
        return False


def is_valid_token(token: str) -> bool:
    """
    Check if a token type is valid (non-raising version).

    Args:
        token: Token type to check

    Returns:
        True if valid, False otherwise
    """
    try:
        validate_token(token)
        return True
    except ValidationError:
        return False


def get_token_for_ticker(ticker: str) -> Optional[str]:
    """
    Get the token type for a given ticker.

    Args:
        ticker: Company ticker symbol

    Returns:
        Token type (BTC, ETH, etc.) or None if not found
    """
    ticker = ticker.strip().upper()
    for token, tickers in COMPANY_WHITELIST.items():
        if ticker in tickers:
            return token
    return None


def add_company_to_whitelist(ticker: str, token: str) -> None:
    """
    Add a new company to the whitelist.

    Note: This only updates the in-memory whitelist for the current session.
    For permanent changes, update the COMPANY_WHITELIST constant.

    Args:
        ticker: Company ticker symbol
        token: Token type

    Raises:
        ValidationError: If ticker format or token is invalid
    """
    # Validate format (but not against whitelist since we're adding)
    ticker = validate_ticker(ticker, strict=False)
    token = validate_token(token)

    if token not in COMPANY_WHITELIST:
        COMPANY_WHITELIST[token] = set()

    COMPANY_WHITELIST[token].add(ticker)
    ALL_WHITELISTED_TICKERS.add(ticker)


def validate_treasury_row(
    row: dict,
    row_num: int = 0,
    strict: bool = True,
) -> list[str]:
    """
    Validate a treasury data row for import.

    Checks:
    - Required fields present (date, token_count)
    - Numeric values are non-negative where expected
    - Date format is valid
    - Values are within reasonable ranges

    Args:
        row: Dict with treasury data fields
        row_num: Row number for error messages (0 = unknown)
        strict: If True, enforce stricter validation

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    row_prefix = f"Row {row_num}: " if row_num > 0 else ""

    # Required: date
    if not row.get('date'):
        errors.append(f"{row_prefix}Missing required field: date")
    elif not _is_valid_date_format(row['date']):
        errors.append(f"{row_prefix}Invalid date format: {row['date']} (expected YYYY-MM-DD)")

    # Required: token_count (for holdings history)
    if row.get('token_count') is None and strict:
        errors.append(f"{row_prefix}Missing required field: token_count")

    # Non-negative numeric fields
    non_negative_fields = [
        'token_count',
        'shares_outstanding',
        'convertible_debt',
        'convertible_debt_shares',
        'non_convertible_debt',
        'warrants',
        'warrant_shares',
        'cash_position',
    ]

    for field in non_negative_fields:
        value = row.get(field)
        if value is not None:
            try:
                num_value = float(value)
                if num_value < 0:
                    errors.append(f"{row_prefix}Negative value not allowed for {field}: {value}")
            except (TypeError, ValueError):
                errors.append(f"{row_prefix}Invalid numeric value for {field}: {value}")

    # Range validation for token_count
    if row.get('token_count') is not None:
        try:
            tokens = float(row['token_count'])
            # Sanity check: tokens should be reasonable (< 100 trillion)
            if tokens > 100_000_000_000_000:
                errors.append(f"{row_prefix}Token count unreasonably large: {tokens}")
        except (TypeError, ValueError):
            pass  # Already caught above

    # Range validation for shares_outstanding
    if row.get('shares_outstanding') is not None:
        try:
            shares = float(row['shares_outstanding'])
            # Sanity check: shares should be reasonable (< 100 trillion)
            if shares > 100_000_000_000_000:
                errors.append(f"{row_prefix}Shares outstanding unreasonably large: {shares}")
        except (TypeError, ValueError):
            pass  # Already caught above

    return errors


def _is_valid_date_format(date_str: str) -> bool:
    """Check if string is a valid YYYY-MM-DD date."""
    if not date_str or not isinstance(date_str, str):
        return False
    try:
        from datetime import datetime
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False


def validate_csv_row(row: dict, row_num: int = 0) -> list[str]:
    """
    Validate a row from dbt-format CSV.

    This is a convenience wrapper around validate_treasury_row
    that handles the CSV column naming.

    Args:
        row: Dict from csv.DictReader with dbt column names
        row_num: Row number for error messages

    Returns:
        List of validation error messages
    """
    # Map CSV columns to internal names for validation
    mapped_row = {}

    csv_to_internal = {
        'date': 'date',
        'num_of_tokens': 'token_count',
        'convertible_debt': 'convertible_debt',
        'convertible_debt_shares': 'convertible_debt_shares',
        'non_convertible_debt': 'non_convertible_debt',
        'warrents': 'warrants',  # Note: typo in CSV
        'warrent_shares': 'warrant_shares',  # Note: typo in CSV
        'num_of_shares': 'shares_outstanding',
        'latest_cash': 'cash_position',
    }

    for csv_col, internal_col in csv_to_internal.items():
        if csv_col in row:
            mapped_row[internal_col] = row[csv_col]

    return validate_treasury_row(mapped_row, row_num, strict=True)
