"""Tests for the orchestrator (updater module).

Covers: valid update, manual_override, SHARE_BUYBACK skip, unknown
ticker, totals recalculation, recentChanges, empty batch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scraper.models import ScrapedUpdate
from scraper.state_guard import load_history
from scraper.updater import load_data, process_update, run_batch, save_data


def _make_update(
    ticker: str = "MSTR",
    token: str = "BTC",
    new_value: int = 700000,
    context_text: str = "purchased 700000 BTC for treasury",
) -> ScrapedUpdate:
    return ScrapedUpdate(
        ticker=ticker,
        token=token,
        new_value=new_value,
        context_text=context_text,
    )


class TestProcessUpdate:
    def test_valid_update_applied(self, sample_data_json: Path) -> None:
        data = load_data(sample_data_json)
        history: dict = {}
        update = _make_update(new_value=700000)

        data, history, applied = process_update(update, data, history)

        assert applied is True
        mstr = data["companies"]["BTC"][0]
        assert mstr["tokens"] == 700000
        assert mstr["change"] == 700000 - 687410

    def test_manual_override_skips(self, sample_data_json: Path) -> None:
        data = load_data(sample_data_json)
        history: dict = {}
        update = _make_update(
            ticker="OVER",
            new_value=200,
            context_text="purchased 200 BTC for treasury",
        )

        data, history, applied = process_update(update, data, history)

        assert applied is False
        # Value unchanged
        over = data["companies"]["BTC"][1]
        assert over["tokens"] == 100

    def test_share_buyback_skips(self, sample_data_json: Path) -> None:
        data = load_data(sample_data_json)
        history: dict = {}
        update = _make_update(
            ticker="FGNX",
            token="ETH",
            new_value=50000,
            context_text="9M share buyback program announced",
        )

        data, history, applied = process_update(update, data, history)

        assert applied is False
        fgnx = data["companies"]["ETH"][0]
        assert fgnx["tokens"] == 40088

    def test_unknown_ticker_no_crash(self, sample_data_json: Path) -> None:
        data = load_data(sample_data_json)
        history: dict = {}
        update = _make_update(
            ticker="ZZZZ",
            token="BTC",
            new_value=999,
            context_text="purchased tokens for treasury",
        )

        data, history, applied = process_update(update, data, history)

        assert applied is False

    def test_totals_recalculated(self, sample_data_json: Path) -> None:
        data = load_data(sample_data_json)
        history: dict = {}
        update = _make_update(new_value=700000)

        data, history, applied = process_update(update, data, history)

        assert applied is True
        # MSTR=700000 + OVER=100
        assert data["totals"]["BTC"] == 700100

    def test_recent_changes_prepended(self, sample_data_json: Path) -> None:
        data = load_data(sample_data_json)
        history: dict = {}
        update = _make_update(new_value=700000)

        data, history, applied = process_update(update, data, history)

        assert applied is True
        recent = data["recentChanges"]
        assert recent[0]["ticker"] == "MSTR"
        assert recent[0]["tokens"] == 700000
        # Original entry pushed to position 1
        assert len(recent) == 2


class TestRunBatch:
    def test_empty_batch_no_write(
        self, sample_data_json: Path, empty_history: Path
    ) -> None:
        original_content = sample_data_json.read_text()

        summary = run_batch([], sample_data_json, empty_history)

        assert summary["applied"] == 0
        # File content unchanged (no write occurred)
        assert sample_data_json.read_text() == original_content

    def test_batch_applies_and_saves(
        self, sample_data_json: Path, empty_history: Path
    ) -> None:
        updates = [
            _make_update(new_value=700000),
        ]

        summary = run_batch(updates, sample_data_json, empty_history)

        assert summary["applied"] == 1
        # Verify file was written
        data = json.loads(sample_data_json.read_text())
        assert data["companies"]["BTC"][0]["tokens"] == 700000
        # History file created
        assert empty_history.exists()
