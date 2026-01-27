"""Tests for the CSV sync pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scraper.csv_sync import (
    _make_fingerprint,
    merge_transactions,
    parse_csv,
    sync_csv,
)


_VALID_CSV = """\
Date,Asset,Quantity,PriceUSD,TotalCost,CumulativeTokens,AvgCostBasis,Source
2026-01-12,BTC,13627,91519,1247142213,687410,65033,https://example.com
2026-01-06,BTC,1070,94004,100584280,673783,64553,https://example.com
"""


@pytest.fixture()
def csv_file(tmp_path: Path) -> Path:
    path = tmp_path / "transactions.csv"
    path.write_text(_VALID_CSV)
    return path


@pytest.fixture()
def data_json(tmp_path: Path) -> Path:
    data = {
        "lastUpdated": "2026-01-12T21:00:00-05:00",
        "lastUpdatedDisplay": "Jan 12, 2026 9:00 PM EST",
        "recentChanges": [],
        "companies": {
            "BTC": [
                {
                    "ticker": "MSTR",
                    "name": "Strategy",
                    "tokens": 687410,
                    "lastUpdate": "2026-01-12",
                    "change": 13627,
                }
            ],
            "ETH": [],
            "SOL": [],
            "HYPE": [],
            "BNB": [],
        },
        "totals": {"BTC": 687410, "ETH": 0, "SOL": 0, "HYPE": 0, "BNB": 0},
    }
    path = tmp_path / "data.json"
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path


class TestParseCSV:
    def test_parse_csv_valid(self, csv_file: Path) -> None:
        transactions = parse_csv(csv_file)
        assert len(transactions) == 2
        assert transactions[0]["date"] == "2026-01-12"
        assert transactions[0]["asset"] == "BTC"
        assert transactions[0]["quantity"] == 13627
        assert transactions[0]["totalCost"] == 1247142213

    def test_parse_csv_generates_fingerprints(self, csv_file: Path) -> None:
        transactions = parse_csv(csv_file)
        for txn in transactions:
            assert "fingerprint" in txn
            assert txn["fingerprint"] == f"{txn['date']}:{txn['asset']}:{txn['totalCost']}"

    def test_parse_csv_missing_columns_raises(self, tmp_path: Path) -> None:
        bad_csv = tmp_path / "bad.csv"
        bad_csv.write_text("Date,Quantity\n2026-01-12,100\n")
        with pytest.raises(ValueError, match="missing required columns"):
            parse_csv(bad_csv)


class TestMergeTransactions:
    def test_merge_no_duplicates(self) -> None:
        existing = [
            {"date": "2026-01-12", "asset": "BTC", "totalCost": 100, "fingerprint": "2026-01-12:BTC:100"}
        ]
        incoming = [
            {"date": "2026-01-12", "asset": "BTC", "totalCost": 100, "fingerprint": "2026-01-12:BTC:100"}
        ]
        merged, added, skipped = merge_transactions(existing, incoming)
        assert added == 0
        assert skipped == 1
        assert len(merged) == 1

    def test_merge_adds_new(self) -> None:
        existing = [
            {"date": "2026-01-12", "asset": "BTC", "totalCost": 100, "fingerprint": "2026-01-12:BTC:100"}
        ]
        incoming = [
            {"date": "2026-01-06", "asset": "BTC", "totalCost": 200, "fingerprint": "2026-01-06:BTC:200"}
        ]
        merged, added, skipped = merge_transactions(existing, incoming)
        assert added == 1
        assert skipped == 0
        assert len(merged) == 2

    def test_merge_sorted_newest_first(self) -> None:
        existing = []
        incoming = [
            {"date": "2025-12-01", "asset": "BTC", "totalCost": 50, "fingerprint": "2025-12-01:BTC:50"},
            {"date": "2026-01-12", "asset": "BTC", "totalCost": 100, "fingerprint": "2026-01-12:BTC:100"},
        ]
        merged, _, _ = merge_transactions(existing, incoming)
        assert merged[0]["date"] == "2026-01-12"
        assert merged[1]["date"] == "2025-12-01"


class TestFingerprint:
    def test_fingerprint_deterministic(self) -> None:
        fp1 = _make_fingerprint("2026-01-12", "BTC", 1247142213)
        fp2 = _make_fingerprint("2026-01-12", "BTC", 1247142213)
        assert fp1 == fp2
        assert fp1 == "2026-01-12:BTC:1247142213"

    def test_fingerprint_different_inputs(self) -> None:
        fp1 = _make_fingerprint("2026-01-12", "BTC", 100)
        fp2 = _make_fingerprint("2026-01-12", "BTC", 200)
        assert fp1 != fp2


class TestSyncCSV:
    def test_sync_full_pipeline(self, csv_file: Path, data_json: Path) -> None:
        result = sync_csv(csv_file, "MSTR", "BTC", data_json)
        assert result["added"] == 2
        assert result["skipped"] == 0

        with open(data_json) as f:
            data = json.load(f)
        mstr = data["companies"]["BTC"][0]
        assert "transactions" in mstr
        assert len(mstr["transactions"]) == 2

    def test_sync_idempotent(self, csv_file: Path, data_json: Path) -> None:
        sync_csv(csv_file, "MSTR", "BTC", data_json)
        result2 = sync_csv(csv_file, "MSTR", "BTC", data_json)
        assert result2["added"] == 0
        assert result2["skipped"] == 2

        with open(data_json) as f:
            data = json.load(f)
        assert len(data["companies"]["BTC"][0]["transactions"]) == 2

    def test_sync_invalid_ticker_raises(self, csv_file: Path, data_json: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            sync_csv(csv_file, "FAKE", "BTC", data_json)

    def test_sync_invalid_token_raises(self, csv_file: Path, data_json: Path) -> None:
        with pytest.raises(ValueError, match="Invalid token"):
            sync_csv(csv_file, "MSTR", "DOGE", data_json)
