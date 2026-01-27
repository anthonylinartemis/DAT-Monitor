"""Shared fixtures for the scraping engine test suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def sample_data_json(tmp_path: Path) -> Path:
    """Minimal valid data.json with MSTR (BTC) and FGNX (ETH)."""
    data = {
        "lastUpdated": "2026-01-12T21:00:00-05:00",
        "lastUpdatedDisplay": "Jan 12, 2026 9:00 PM EST",
        "recentChanges": [
            {
                "ticker": "MSTR",
                "token": "BTC",
                "date": "2026-01-12",
                "tokens": 687410,
                "change": 13627,
                "summary": "Acquired 13,627 BTC for ~$1.25B",
            }
        ],
        "companies": {
            "BTC": [
                {
                    "ticker": "MSTR",
                    "name": "Strategy",
                    "tokens": 687410,
                    "lastUpdate": "2026-01-12",
                    "change": 13627,
                    "cik": "0001050446",
                    "transactions": [
                        {
                            "date": "2026-01-12",
                            "asset": "BTC",
                            "quantity": 13627,
                            "priceUsd": 91519,
                            "totalCost": 1247142213,
                            "cumulativeTokens": 687410,
                            "avgCostBasis": 65033,
                            "source": "https://www.strategy.com/news",
                            "fingerprint": "2026-01-12:BTC:1247142213",
                        },
                        {
                            "date": "2026-01-06",
                            "asset": "BTC",
                            "quantity": 1070,
                            "priceUsd": 94004,
                            "totalCost": 100584280,
                            "cumulativeTokens": 673783,
                            "avgCostBasis": 64553,
                            "source": "https://www.strategy.com/news",
                            "fingerprint": "2026-01-06:BTC:100584280",
                        },
                    ],
                },
                {
                    "ticker": "OVER",
                    "name": "Override Co",
                    "tokens": 100,
                    "lastUpdate": "2026-01-01",
                    "change": 0,
                    "manual_override": True,
                },
            ],
            "ETH": [
                {
                    "ticker": "FGNX",
                    "name": "FG Nexus",
                    "tokens": 40088,
                    "lastUpdate": "2025-12-17",
                    "change": 0,
                    "cik": "0001591890",
                }
            ],
            "SOL": [],
            "HYPE": [],
            "BNB": [],
        },
        "totals": {"BTC": 687510, "ETH": 40088, "SOL": 0, "HYPE": 0, "BNB": 0},
    }
    path = tmp_path / "data.json"
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path


@pytest.fixture()
def empty_history(tmp_path: Path) -> Path:
    """Empty history file path (does not exist on disk — simulates first run)."""
    return tmp_path / "holdings_history.json"


@pytest.fixture()
def mstr_oscillation_history(tmp_path: Path) -> Path:
    """MSTR with seen_values={700000, 709000, 712000}, confirmed=709000."""
    history = {
        "MSTR:BTC": {
            "last_confirmed_value": 709000,
            "seen_values": [700000, 709000, 712000],
            "last_update_date": "2026-01-10",
        }
    }
    path = tmp_path / "holdings_history.json"
    path.write_text(json.dumps(history, indent=2) + "\n")
    return path
