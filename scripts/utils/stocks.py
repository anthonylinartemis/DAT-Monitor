"""Fetch stock data from Yahoo Finance using yfinance (free, no API key)."""

from typing import Optional

import yfinance as yf


def get_stock_data(ticker: str) -> Optional[dict]:
    """
    Fetch current stock price and shares outstanding from Yahoo Finance.

    Args:
        ticker: Stock ticker symbol (e.g., MSTR, BMNR)

    Returns:
        Dict with 'price', 'shares_outstanding', 'market_cap' or None if error
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        price = info.get("currentPrice") or info.get("regularMarketPrice")
        shares = info.get("sharesOutstanding")
        market_cap = info.get("marketCap")

        if price:
            if shares:
                print(f"    {ticker} stock: ${price:,.2f}, {shares:,.0f} shares")
            else:
                print(f"    {ticker} stock: ${price:,.2f}")
            return {
                "price": price,
                "shares_outstanding": shares,
                "market_cap": market_cap,
            }
        return None
    except Exception as e:
        print(f"    Yahoo Finance error for {ticker}: {e}")
        return None


def get_stock_price(ticker: str) -> Optional[float]:
    """Simple helper to just get the stock price."""
    data = get_stock_data(ticker)
    return data.get("price") if data else None
