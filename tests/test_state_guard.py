"""Tests for oscillation prevention (state_guard module).

Covers: first observation, no-change, genuinely new, oscillation
suppression, confirmation keywords, immutability of record_update.
"""

from __future__ import annotations

import pytest

from scraper.models import HoldingRecord, ScrapedUpdate
from scraper.state_guard import (
    _contains_confirmation,
    load_history,
    record_update,
    save_history,
    should_update,
)


# --- Fixtures ---

def _make_update(
    ticker: str = "MSTR",
    token: str = "BTC",
    new_value: int = 700000,
    context_text: str = "",
) -> ScrapedUpdate:
    return ScrapedUpdate(
        ticker=ticker,
        token=token,
        new_value=new_value,
        context_text=context_text,
    )


def _mstr_history() -> dict[str, HoldingRecord]:
    """MSTR with seen_values={700000, 709000, 712000}, confirmed=709000."""
    return {
        "MSTR:BTC": HoldingRecord(
            last_confirmed_value=709000,
            seen_values=frozenset({700000, 709000, 712000}),
            last_update_date="2026-01-10",
        )
    }


# --- Test: should_update decisions ---

class TestShouldUpdate:
    def test_first_observation_accepted(self) -> None:
        """Ticker not in history → YES."""
        update = _make_update(new_value=500000)
        result, reason = should_update(update, {})
        assert result is True
        assert "first" in reason.lower()

    def test_same_value_as_confirmed_rejected(self) -> None:
        """Value == last_confirmed → NO (no change)."""
        update = _make_update(new_value=709000)
        result, reason = should_update(update, _mstr_history())
        assert result is False
        assert "no change" in reason.lower()

    def test_genuinely_new_value_accepted(self) -> None:
        """Value not in seen_values → YES."""
        update = _make_update(new_value=720000)
        result, reason = should_update(update, _mstr_history())
        assert result is True
        assert "genuinely new" in reason.lower()

    def test_oscillation_without_keyword_suppressed(self) -> None:
        """Value in seen_values + no confirmation keyword → NO."""
        update = _make_update(
            new_value=712000,
            context_text="MSTR holds BTC worth billions",
        )
        result, reason = should_update(update, _mstr_history())
        assert result is False
        assert "oscillation" in reason.lower()

    def test_oscillation_with_confirmation_keyword_accepted(self) -> None:
        """Value in seen_values + confirmation keyword → YES."""
        update = _make_update(
            new_value=712000,
            context_text="New filing confirms 712K BTC acquired",
        )
        result, reason = should_update(update, _mstr_history())
        assert result is True
        assert "confirmed" in reason.lower()


# --- Test: confirmation keyword detection ---

class TestContainsConfirmation:
    @pytest.mark.parametrize(
        "keyword",
        ["new filing", "confirmed", "acquired", "purchased", "8-K", "press release"],
    )
    def test_each_confirmation_keyword(self, keyword: str) -> None:
        assert _contains_confirmation(f"Company {keyword} today") is True

    def test_case_insensitive(self) -> None:
        assert _contains_confirmation("NEW FILING issued") is True
        assert _contains_confirmation("Press Release today") is True

    def test_no_keyword(self) -> None:
        assert _contains_confirmation("Just a normal update") is False


# --- Test: record_update immutability ---

class TestRecordUpdate:
    def test_adds_to_seen_values_and_updates_confirmed(self) -> None:
        history = _mstr_history()
        update = _make_update(new_value=720000)

        new_history = record_update(update, history, "2026-01-15")

        record = new_history["MSTR:BTC"]
        assert record.last_confirmed_value == 720000
        assert 720000 in record.seen_values
        # All old values still present
        assert 700000 in record.seen_values
        assert 709000 in record.seen_values
        assert 712000 in record.seen_values
        assert record.last_update_date == "2026-01-15"

    def test_returns_new_dict_original_unmodified(self) -> None:
        history = _mstr_history()
        original_record = history["MSTR:BTC"]
        update = _make_update(new_value=720000)

        new_history = record_update(update, history, "2026-01-15")

        # Original dict unchanged
        assert history["MSTR:BTC"] is original_record
        assert original_record.last_confirmed_value == 709000
        assert 720000 not in original_record.seen_values

        # New dict is different object
        assert new_history is not history


# --- Test: load/save round-trip ---

class TestHistoryIO:
    def test_load_missing_file_returns_empty(self, empty_history) -> None:
        result = load_history(empty_history)
        assert result == {}

    def test_save_and_load_round_trip(self, tmp_path) -> None:
        path = tmp_path / "history.json"
        history = _mstr_history()

        save_history(history, path)
        loaded = load_history(path)

        assert loaded.keys() == history.keys()
        original = history["MSTR:BTC"]
        loaded_record = loaded["MSTR:BTC"]
        assert loaded_record.last_confirmed_value == original.last_confirmed_value
        assert loaded_record.seen_values == original.seen_values
        assert loaded_record.last_update_date == original.last_update_date
