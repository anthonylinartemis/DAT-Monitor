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
