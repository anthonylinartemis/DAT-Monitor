"""Keyword-scoring classifier for scraped financial text.

Determines whether text describes a SHARE_BUYBACK or TOKEN_HOLDING,
fixing the FGNX labeling bug where share buybacks were misclassified
as token holdings.
"""

from __future__ import annotations

import re
from typing import Optional

from scraper.config import (
    SHARE_KEYWORDS,
    TOKEN_KEYWORDS,
    HoldingClassification,
)
from scraper.models import ParseResult


def _extract_quantity(text: str) -> Optional[int]:
    """Extract a numeric quantity from financial text.

    Supports formats: 9M, 9,000,000, 2.5M, 500K, plain integers.
    Returns None if no number is found.
    """
    # Try suffix notation first: 2.5M, 9M, 500K
    suffix_match = re.search(
        r"([\d,]+(?:\.\d+)?)\s*([MmKk])\b", text
    )
    if suffix_match:
        raw_number = suffix_match.group(1).replace(",", "")
        multiplier = {"m": 1_000_000, "k": 1_000}[suffix_match.group(2).lower()]
        return int(float(raw_number) * multiplier)

    # Try comma-formatted or plain integers: 9,000,000 or 13627
    int_match = re.search(r"\b(\d{1,3}(?:,\d{3})+)\b", text)
    if int_match:
        return int(int_match.group(1).replace(",", ""))

    # Plain integer (at least 2 digits to avoid matching stray single digits)
    plain_match = re.search(r"\b(\d{2,})\b", text)
    if plain_match:
        return int(plain_match.group(1))

    return None


def _score_keywords(
    text: str, keywords: tuple[str, ...]
) -> tuple[int, tuple[str, ...]]:
    """Count case-insensitive keyword matches in text.

    Returns (match_count, tuple_of_matched_keywords).
    """
    text_lower = text.lower()
    matched: list[str] = []
    for keyword in keywords:
        if keyword.lower() in text_lower:
            matched.append(keyword)
    return len(matched), tuple(matched)


def classify(text: str) -> ParseResult:
    """Classify scraped text as SHARE_BUYBACK, TOKEN_HOLDING, or UNKNOWN.

    Uses keyword scoring: the category with more keyword matches wins.
    Ties (including 0-0) return UNKNOWN — we fail loudly rather than guess.

    FGNX scenario: "9M share buyback" → share_score=2 (share, buyback)
    > token_score=0 → SHARE_BUYBACK.
    """
    share_count, share_matched = _score_keywords(text, SHARE_KEYWORDS)
    token_count, token_matched = _score_keywords(text, TOKEN_KEYWORDS)

    quantity = _extract_quantity(text)
    all_matched = share_matched + token_matched

    if share_count > token_count:
        classification = HoldingClassification.SHARE_BUYBACK
    elif token_count > share_count:
        classification = HoldingClassification.TOKEN_HOLDING
    else:
        # Tie (including 0-0): fail loudly per bible.md
        classification = HoldingClassification.UNKNOWN

    return ParseResult(
        classification=classification,
        quantity=quantity,
        raw_text=text,
        confidence_keywords=all_matched,
    )
