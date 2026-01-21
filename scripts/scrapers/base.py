"""
Base scraper abstract class.
"""

import os
import time
from abc import ABC, abstractmethod
from typing import Optional

import requests
from bs4 import BeautifulSoup


def create_soup(html: str, parser: str = "lxml") -> BeautifulSoup:
    """
    Create BeautifulSoup with fallback parser.

    Tries lxml first (faster), falls back to html.parser if lxml fails.
    This handles environments where lxml wheel fails to build.
    """
    try:
        return BeautifulSoup(html, parser)
    except Exception:
        # Fallback to built-in parser if lxml fails
        return BeautifulSoup(html, "html.parser")

# Configuration
SEC_BASE = "https://www.sec.gov"
USER_AGENT = os.environ.get("SEC_USER_AGENT", "")

# Track if user agent has been validated (only warn once)
_USER_AGENT_VALIDATED = False


def validate_user_agent():
    """Validate SEC_USER_AGENT is properly configured."""
    global _USER_AGENT_VALIDATED
    if _USER_AGENT_VALIDATED:
        return

    if not USER_AGENT:
        raise ValueError(
            "SEC_USER_AGENT environment variable is not set. "
            "SEC requires a valid User-Agent with contact email. "
            "Example: DAT-Monitor/1.0 (your.email@example.com)"
        )
    if "@" not in USER_AGENT:
        print("WARNING: SEC_USER_AGENT should contain a contact email address.")

    _USER_AGENT_VALIDATED = True


def get_headers():
    """Get request headers, validating user agent first."""
    validate_user_agent()
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }


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

    # Default validation ranges (used if tokenConfig not provided)
    DEFAULT_RANGES = {
        "BTC": (100, 2_000_000),
        "ETH": (100, 50_000_000),
        "SOL": (100, 100_000_000),
        "HYPE": (100, 100_000_000),
        "BNB": (100, 10_000_000),
    }

    def __init__(self, company: dict, token: str, token_config: dict = None):
        """
        Initialize scraper with company data and token type.

        Args:
            company: Company dict from data.json
            token: Token type (BTC, ETH, SOL, HYPE, BNB)
            token_config: Optional token configuration from data.json tokenConfig
        """
        # Validate SEC User-Agent is configured
        validate_user_agent()

        self.company = company
        self.token = token
        self.token_config = token_config or {}
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
        """Get keywords for this token type (from config or defaults)."""
        # Try token_config first
        if self.token_config.get("keywords"):
            return self.token_config["keywords"]
        return TOKEN_KEYWORDS.get(self.token, [self.token.lower()])

    def get_validation_range(self) -> tuple[int, int]:
        """Get min/max holdings validation range for this token."""
        # Try token_config first
        if self.token_config:
            min_val = self.token_config.get("minHoldings", 100)
            max_val = self.token_config.get("maxHoldings", 100_000_000)
            return (min_val, max_val)
        # Fall back to defaults
        return self.DEFAULT_RANGES.get(self.token, (100, 100_000_000))

    def is_valid_holdings_amount(self, num: int) -> bool:
        """Check if number is in valid range for this token type."""
        min_val, max_val = self.get_validation_range()
        return min_val <= num <= max_val

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
