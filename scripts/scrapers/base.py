"""
Base scraper abstract class.
"""

import os
import time
from abc import ABC, abstractmethod
from typing import Optional

import requests

# Configuration
SEC_BASE = "https://www.sec.gov"
USER_AGENT = os.environ.get("SEC_USER_AGENT", "DAT-Monitor/1.0 (contact@example.com)")

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Rate limiting for SEC (10 requests per second max)
LAST_REQUEST_TIME = 0
SEC_RATE_LIMIT = 0.15  # seconds between requests

# Token keywords for detection
TOKEN_KEYWORDS = {
    "BTC": ["bitcoin", "btc"],
    "ETH": ["ethereum", "ether", "eth"],
    "SOL": ["solana", "sol"],
    "HYPE": ["hyperliquid", "hype"],
    "BNB": ["bnb", "binance coin", "binance"],
}

# --- KEYWORD CONFIGURATION FOR 8-K / PRESS RELEASE SCRAPER ---

# 1. PRIMARY ACTION KEYWORDS (Verbs and trade events)
ACTION_KEYWORDS = [
    "purchased", "acquired", "acquisition", "accumulation", "allocation",
    "addition", "adds", "deployment", "begins purchases", "initial accumulation",
    "scaling holdings", "expanding its total holdings"
]

# 2. ASSET & TICKER KEYWORDS (Target specific tokens)
ASSET_KEYWORDS = [
    "SOL", "Solana", "HYPE", "Hyperliquid", "ETH", "Ethereum",
    "BTC", "Bitcoin", "USDH", "native asset", "digital asset",
    "token", "tokens", "cryptocurrency"
]

# 3. STRATEGY & "DAT" TERMINOLOGY (Institutional context)
STRATEGY_KEYWORDS = [
    "Digital Asset Treasury", "DAT", "treasury strategy", "treasury holdings",
    "treasury reserve asset", "treasury vehicle", "on-chain yield",
    "staking yield", "yield-bearing", "revenue-generating", "staking",
    "accretive", "maximizing SOL per share", "maximizing HYPE per share",
    "HyperCore", "HyperEVM", "Validator Network"
]

# 4. CAPITAL MARKETS & FUNDING (How the assets were bought)
FUNDING_KEYWORDS = [
    "ATM", "at-the-market", "private placement", "stapled warrants",
    "gross proceeds", "capital markets program", "equity offering",
    "Pantera Capital", "Summer Capital"
]

# 5. QUANTITATIVE ANCHORS (Regex triggers for extracting numbers)
METRIC_ANCHORS = [
    "average price of", "cost basis of", "total holdings",
    "consists of", "totaling", "in excess of", "aggregate",
    "amounted to", "worth", "valued at"
]

# 6. SEC 8-K ITEM INDICATORS (Priority sections in filings)
SEC_ITEM_KEYWORDS = [
    "Item 8.01", "Item 7.01", "Other Events", "Regulation FD Disclosure"
]


class ScraperResult:
    """Result from a scraper operation."""

    def __init__(
        self,
        tokens: int,
        date: str,
        url: str,
        source: str,
    ):
        self.tokens = tokens
        self.date = date
        self.url = url
        self.source = source

    def to_dict(self) -> dict:
        return {
            "tokens": self.tokens,
            "date": self.date,
            "url": self.url,
            "source": self.source,
        }


class BaseScraper(ABC):
    """Abstract base class for all scrapers."""

    def __init__(self, company: dict, token: str):
        """
        Initialize scraper with company data and token type.

        Args:
            company: Company dict from data.json
            token: Token type (BTC, ETH, SOL, HYPE, BNB)
        """
        self.company = company
        self.token = token
        self.config = company.get("scrape_config", {})
        self.ticker = company.get("ticker", "")
        self.current_holdings = company.get("tokens", 0)

    @abstractmethod
    def scrape(self) -> Optional[ScraperResult]:
        """
        Perform the scraping operation.

        Returns:
            ScraperResult with tokens, date, url, source if found
            None if no update found
        """
        pass

    def get_target_regex(self) -> Optional[str]:
        """Get custom regex pattern from config."""
        return self.config.get("target_regex")

    def get_source_url(self) -> Optional[str]:
        """Get source URL from config."""
        return self.config.get("source_url")

    def get_keywords(self) -> list[str]:
        """Get keywords for this token type."""
        return TOKEN_KEYWORDS.get(self.token, [self.token.lower()])

    def rate_limit(self):
        """Apply rate limiting between requests."""
        global LAST_REQUEST_TIME
        elapsed = time.time() - LAST_REQUEST_TIME
        if elapsed < SEC_RATE_LIMIT:
            time.sleep(SEC_RATE_LIMIT - elapsed)
        LAST_REQUEST_TIME = time.time()

    def fetch_url(self, url: str, apply_rate_limit: bool = True) -> Optional[str]:
        """
        Fetch a URL with proper rate limiting and error handling.

        Args:
            url: URL to fetch
            apply_rate_limit: Whether to apply rate limiting (for SEC)

        Returns:
            Response text or None on error
        """
        if apply_rate_limit:
            self.rate_limit()

        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            print(f"    Error fetching {url}: {e}")
            return None

    def log(self, message: str):
        """Log a message with ticker prefix."""
        print(f"    [{self.ticker}] {message}")
