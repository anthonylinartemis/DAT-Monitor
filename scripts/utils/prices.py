"""Fetch live token prices from CoinGecko (free tier, no API key required)."""

import requests
from typing import Optional
import time

# Rate limit: CoinGecko free tier allows 10-30 calls/minute
LAST_CALL_TIME = 0
RATE_LIMIT_SECONDS = 2

COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "HYPE": "hyperliquid",
    "BNB": "binancecoin",
}


def _rate_limit():
    """Enforce rate limiting for CoinGecko free tier."""
    global LAST_CALL_TIME
    elapsed = time.time() - LAST_CALL_TIME
    if elapsed < RATE_LIMIT_SECONDS:
        time.sleep(RATE_LIMIT_SECONDS - elapsed)
    LAST_CALL_TIME = time.time()


def get_token_price(token: str) -> Optional[float]:
    """
    Fetch current USD price for a token from CoinGecko.

    Args:
        token: Token symbol (BTC, ETH, SOL, HYPE, BNB)

    Returns:
        Price in USD or None if fetch fails
    """
    coingecko_id = COINGECKO_IDS.get(token.upper())
    if not coingecko_id:
        print(f"    Unknown token for price lookup: {token}")
        return None

    _rate_limit()

    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": coingecko_id, "vs_currencies": "usd"}
        headers = {"accept": "application/json"}
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        price = data.get(coingecko_id, {}).get("usd")
        if price:
            print(f"    {token} price: ${price:,.2f}")
        return price
    except Exception as e:
        print(f"    CoinGecko error for {token}: {e}")
        return None


def get_multiple_token_prices(tokens: list[str]) -> dict[str, float]:
    """
    Fetch prices for multiple tokens in one API call (more efficient).

    Args:
        tokens: List of token symbols

    Returns:
        Dict of {token: price}
    """
    ids = [COINGECKO_IDS.get(t.upper()) for t in tokens if t.upper() in COINGECKO_IDS]
    if not ids:
        return {}

    _rate_limit()

    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": ",".join(ids), "vs_currencies": "usd"}
        headers = {"accept": "application/json"}
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        # Reverse map: coingecko_id -> token
        reverse_map = {v: k for k, v in COINGECKO_IDS.items()}
        return {reverse_map[cg_id]: info.get("usd") for cg_id, info in data.items() if cg_id in reverse_map}
    except Exception as e:
        print(f"    CoinGecko batch error: {e}")
        return {}
