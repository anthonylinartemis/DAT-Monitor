"""Tests for keyword-scoring classifier (parser module).

Covers: FGNX buyback scenario, quantity extraction, classification
scoring, and edge cases.
"""

from __future__ import annotations

import pytest

from scraper.config import HoldingClassification
from scraper.parser import _extract_quantity, classify


# --- Test: FGNX buyback scenario ---

class TestFGNXScenario:
    def test_share_buyback_classification(self) -> None:
        """'9M share buyback' → SHARE_BUYBACK, not TOKEN_HOLDING."""
        result = classify("9M share buyback")
        assert result.classification == HoldingClassification.SHARE_BUYBACK

    def test_share_buyback_quantity(self) -> None:
        result = classify("9M share buyback")
        assert result.quantity == 9_000_000


# --- Test: classification scoring ---

class TestClassification:
    def test_normal_token_holding(self) -> None:
        text = "purchased 13,627 BTC for treasury"
        result = classify(text)
        assert result.classification == HoldingClassification.TOKEN_HOLDING

    def test_ambiguous_no_keywords_returns_unknown(self) -> None:
        text = "Company announced quarterly results"
        result = classify(text)
        assert result.classification == HoldingClassification.UNKNOWN

    def test_share_keywords_dominant(self) -> None:
        text = "Board approved stock repurchase buyback program"
        result = classify(text)
        assert result.classification == HoldingClassification.SHARE_BUYBACK

    def test_token_keywords_dominant(self) -> None:
        text = "Acquired token for wallet staking holdings"
        result = classify(text)
        assert result.classification == HoldingClassification.TOKEN_HOLDING

    def test_tie_returns_unknown(self) -> None:
        # One share keyword, one token keyword → tie → UNKNOWN
        text = "buyback of token"
        result = classify(text)
        assert result.classification == HoldingClassification.UNKNOWN

    def test_keywords_captured_in_result(self) -> None:
        result = classify("purchased 13,627 BTC for treasury")
        assert "purchased" in result.confidence_keywords
        assert "treasury" in result.confidence_keywords

    def test_raw_text_preserved(self) -> None:
        text = "something interesting happened"
        result = classify(text)
        assert result.raw_text == text


# --- Test: quantity extraction ---

class TestQuantityExtraction:
    def test_plain_integer(self) -> None:
        assert _extract_quantity("holds 13627 BTC") == 13627

    def test_comma_formatted(self) -> None:
        assert _extract_quantity("9,000,000 shares") == 9_000_000

    def test_m_suffix(self) -> None:
        assert _extract_quantity("9M tokens") == 9_000_000

    def test_k_suffix(self) -> None:
        assert _extract_quantity("500K coins") == 500_000

    def test_decimal_with_suffix(self) -> None:
        assert _extract_quantity("2.5M holdings") == 2_500_000

    def test_no_number_returns_none(self) -> None:
        assert _extract_quantity("no numbers here") is None

    def test_zero(self) -> None:
        # Single digit "0" won't match (need >= 2 digits), but "00" would
        assert _extract_quantity("holds 00 tokens") == 0
