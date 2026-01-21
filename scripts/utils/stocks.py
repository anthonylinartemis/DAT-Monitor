"""Fetch stock data from Yahoo Finance using yfinance (free, no API key)."""

from decimal import Decimal
from typing import Optional

import yfinance as yf
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _fetch_stock_info(ticker: str) -> dict:
    """Fetch stock info from Yahoo Finance with retry logic."""
    stock = yf.Ticker(ticker)
    return stock.info


def get_stock_data(ticker: str) -> Optional[dict]:
    """
    Fetch current stock price and shares outstanding from Yahoo Finance.

    Args:
        ticker: Stock ticker symbol (e.g., MSTR, BMNR)

    Returns:
        Dict with 'price', 'shares_outstanding', 'market_cap' (as Decimal) or None if error
    """
    try:
        info = _fetch_stock_info(ticker)

        price = info.get("currentPrice") or info.get("regularMarketPrice")
        shares = info.get("sharesOutstanding")
        market_cap = info.get("marketCap")

        if price:
            price_decimal = Decimal(str(price))
            if shares:
                print(f"    {ticker} stock: ${price_decimal:,.2f}, {shares:,.0f} shares")
            else:
                print(f"    {ticker} stock: ${price_decimal:,.2f}")
            return {
                "price": price_decimal,
                "shares_outstanding": int(shares) if shares else None,
                "market_cap": Decimal(str(market_cap)) if market_cap else None,
            }
        return None
    except Exception as e:
        print(f"    Yahoo Finance error for {ticker}: {e}")
        return None


def get_stock_price(ticker: str) -> Optional[Decimal]:
    """
    Fetch only the current stock price from Yahoo Finance.
    Does not print debug info (for cleaner output when only price is needed).

    Returns:
        Stock price as Decimal or None if error
    """
    try:
        info = _fetch_stock_info(ticker)
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        return Decimal(str(price)) if price else None
    except Exception as e:
        print(f"    Yahoo Finance error for {ticker}: {e}")
        return None
