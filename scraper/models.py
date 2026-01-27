"""Frozen dataclasses for the scraping engine. No I/O — pure data containers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from scraper.config import HoldingClassification


# --- Mapping helpers for camelCase <-> snake_case ---

_COMPANY_CAMEL_TO_SNAKE: dict[str, str] = {
    "ticker": "ticker",
    "name": "name",
    "notes": "notes",
    "tokens": "tokens",
    "lastUpdate": "last_update",
    "change": "change",
    "cik": "cik",
    "irUrl": "ir_url",
    "alertUrl": "alert_url",
    "alertDate": "alert_date",
    "alertNote": "alert_note",
    "manual_override": "manual_override",
}

_COMPANY_SNAKE_TO_CAMEL: dict[str, str] = {v: k for k, v in _COMPANY_CAMEL_TO_SNAKE.items()}


@dataclass(frozen=True)
class Company:
    """Mirrors one entry in data.json's companies array."""

    ticker: str
    name: str
    tokens: int
    last_update: str
    change: int
    notes: str = ""
    cik: str = ""
    ir_url: str = ""
    alert_url: str = ""
    alert_date: str = ""
    alert_note: str = ""
    manual_override: bool = False

    def to_json_dict(self) -> dict:
        """Convert to camelCase dict matching data.json format.

        Omits optional fields that are empty/falsy to keep JSON clean.
        Always includes required fields.
        """
        result: dict = {}
        for snake, camel in _COMPANY_SNAKE_TO_CAMEL.items():
            value = getattr(self, snake)
            # Always include required fields; skip empty optional fields
            if snake in ("ticker", "name", "tokens", "last_update", "change"):
                result[camel] = value
            elif snake == "manual_override":
                if value:
                    result[camel] = value
            elif value:
                result[camel] = value
        return result

    @classmethod
    def from_json_dict(cls, data: dict) -> Company:
        """Create from a camelCase dict (one company entry in data.json)."""
        kwargs: dict = {}
        for camel, snake in _COMPANY_CAMEL_TO_SNAKE.items():
            if camel in data:
                kwargs[snake] = data[camel]
        return cls(**kwargs)


@dataclass(frozen=True)
class RecentChange:
    """One entry in the recentChanges array."""

    ticker: str
    token: str
    date: str
    tokens: int
    change: int
    summary: str

    def to_json_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "token": self.token,
            "date": self.date,
            "tokens": self.tokens,
            "change": self.change,
            "summary": self.summary,
        }

    @classmethod
    def from_json_dict(cls, data: dict) -> RecentChange:
        return cls(
            ticker=data["ticker"],
            token=data["token"],
            date=data["date"],
            tokens=data["tokens"],
            change=data["change"],
            summary=data["summary"],
        )


@dataclass(frozen=True)
class ParseResult:
    """Output of the keyword-scoring classifier."""

    classification: HoldingClassification
    quantity: Optional[int]
    raw_text: str
    confidence_keywords: tuple[str, ...]


@dataclass(frozen=True)
class HoldingRecord:
    """Per-ticker state guard record for oscillation prevention."""

    last_confirmed_value: int
    seen_values: frozenset[int]
    last_update_date: str

    def to_json_dict(self) -> dict:
        return {
            "last_confirmed_value": self.last_confirmed_value,
            "seen_values": sorted(self.seen_values),
            "last_update_date": self.last_update_date,
        }

    @classmethod
    def from_json_dict(cls, data: dict) -> HoldingRecord:
        return cls(
            last_confirmed_value=data["last_confirmed_value"],
            seen_values=frozenset(data["seen_values"]),
            last_update_date=data["last_update_date"],
        )


@dataclass(frozen=True)
class ScrapedUpdate:
    """Raw scraped input before classification or filtering."""

    ticker: str
    token: str
    new_value: int
    context_text: str
    source_url: str = ""
