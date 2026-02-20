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
        # "00" is now rejected by artifact filter (value < 10)
        assert _extract_quantity("holds 00 tokens") is None


# --- Test: artifact filtering ---

class TestArtifactFiltering:
    def test_exhibit_number_99_rejected(self) -> None:
        """'EX-99.1 Filing Document' should not extract 99."""
        assert _extract_quantity("EX-99.1 Filing Document") is None

    def test_year_rejected(self) -> None:
        """Text with only a year should not extract it."""
        assert _extract_quantity("filed in 2026 fiscal year") is None

    def test_real_number_still_works(self) -> None:
        """'holds 5427 tokens' should extract 5427."""
        assert _extract_quantity("holds 5427 tokens") == 5427

    def test_small_artifact_rejected(self) -> None:
        """Single-digit-like small numbers are rejected."""
        # Value < 10 is rejected as artifact
        assert _extract_quantity("only 5 remaining") is None

    def test_suffix_notation_unaffected(self) -> None:
        """Suffix notation (9M, 500K) should bypass artifact filtering."""
        assert _extract_quantity("9M tokens") == 9_000_000

    def test_comma_formatted_unaffected(self) -> None:
        """Comma-formatted numbers should bypass artifact filtering."""
        assert _extract_quantity("holds 9,000,000 BTC") == 9_000_000

    def test_991_exhibit_number_rejected(self) -> None:
        """Exhibit number 991 should be rejected."""
        assert _extract_quantity("see exhibit 991 for details") is None

    def test_year_2025_rejected(self) -> None:
        assert _extract_quantity("In 2025 the company") is None

    def test_legitimate_value_near_year(self) -> None:
        """A real number coexisting with a year should still extract."""
        # 5427 comes first and is not an artifact
        assert _extract_quantity("In 2026 holds 5427 tokens") == 5427
