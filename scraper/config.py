"""Single source of truth for all constants, keyword lists, and enums."""

from enum import Enum
from pathlib import Path


class HoldingClassification(Enum):
    """Classification result for scraped financial text."""
    TOKEN_HOLDING = "TOKEN_HOLDING"
    SHARE_BUYBACK = "SHARE_BUYBACK"
    UNKNOWN = "UNKNOWN"


# --- Keyword lists for classifier scoring ---

SHARE_KEYWORDS: tuple[str, ...] = (
    "buyback",
    "repurchase",
    "share",
    "stock",
    "equity",
    "common stock",
)

TOKEN_KEYWORDS: tuple[str, ...] = (
    "holdings",
    "treasury",
    "purchased",
    "acquired",
    "token",
    "coin",
    "wallet",
    "staking",
)

CONFIRMATION_KEYWORDS: tuple[str, ...] = (
    "new filing",
    "confirmed",
    "acquired",
    "purchased",
    "8-k",
    "press release",
)

# --- Valid token symbols tracked by the dashboard ---

VALID_TOKENS: frozenset[str] = frozenset({"BTC", "ETH", "SOL", "HYPE", "BNB"})

# --- data.json schema field definitions ---

REQUIRED_COMPANY_FIELDS: dict[str, type] = {
    "ticker": str,
    "name": str,
    "tokens": int,
    "lastUpdate": str,
    "change": int,
}

OPTIONAL_COMPANY_FIELDS: dict[str, type] = {
    "notes": str,
    "cik": str,
    "irUrl": str,
    "alertUrl": str,
    "alertDate": str,
    "alertNote": str,
    "manual_override": bool,
}

# --- File paths (relative to project root) ---

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_JSON_PATH: Path = _PROJECT_ROOT / "data.json"
HOLDINGS_HISTORY_PATH: Path = _PROJECT_ROOT / "scraper" / "holdings_history.json"
