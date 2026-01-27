"""Tests for the SEC EDGAR fetcher (fetcher module).

All HTTP calls are mocked — no network access during tests.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from scraper.fetcher import (
    _extract_token_quantity,
    _strip_html,
    build_updates,
    fetch_company_filings,
    fetch_filing_text,
)


# --- Test: HTML stripping ---


class TestStripHtml:
    def test_removes_tags(self) -> None:
        html = "<p>Hello <b>world</b></p>"
        assert _strip_html(html) == "Hello world"

    def test_collapses_whitespace(self) -> None:
        html = "<div>  lots   of   spaces  </div>"
        result = _strip_html(html)
        assert "  " not in result
        assert "lots of spaces" in result

    def test_handles_empty_string(self) -> None:
        assert _strip_html("") == ""

    def test_plain_text_unchanged(self) -> None:
        assert _strip_html("no tags here") == "no tags here"


# --- Test: token quantity extraction ---


class TestExtractTokenQuantity:
    def test_btc_with_comma_format(self) -> None:
        text = "The company acquired 13,627 BTC for approximately $1.25 billion"
        assert _extract_token_quantity(text, "BTC") == 13627

    def test_eth_with_large_number(self) -> None:
        text = "BitMine holds 4,167,768 Ether in its treasury"
        assert _extract_token_quantity(text, "ETH") == 4167768

    def test_sol_with_m_suffix(self) -> None:
        text = "Forward Industries holds 6.9M SOL tokens"
        assert _extract_token_quantity(text, "SOL") == 6900000

    def test_bitcoin_full_name(self) -> None:
        text = "Strategy purchased 687,410 Bitcoin for treasury holdings"
        assert _extract_token_quantity(text, "BTC") == 687410

    def test_no_token_mentioned_returns_none(self) -> None:
        text = "The company announced quarterly earnings results"
        assert _extract_token_quantity(text, "BTC") is None

    def test_no_quantity_near_token_returns_none(self) -> None:
        text = "The board discussed BTC strategy going forward"
        assert _extract_token_quantity(text, "BTC") is None


# --- Test: fetch_company_filings response parsing ---


class TestFetchCompanyFilings:
    def _mock_submissions_response(self, filings: list[dict]) -> str:
        """Build a mock SEC submissions JSON response."""
        forms = [f["form"] for f in filings]
        dates = [f["date"] for f in filings]
        accessions = [f.get("accession", "0000000000-00-000001") for f in filings]
        docs = [f.get("doc", "filing.htm") for f in filings]

        return json.dumps({
            "cik": "1050446",
            "name": "Strategy",
            "filings": {
                "recent": {
                    "form": forms,
                    "filingDate": dates,
                    "accessionNumber": accessions,
                    "primaryDocument": docs,
                }
            },
        })

    @patch("scraper.fetcher._sec_request")
    def test_returns_recent_8k_filings(self, mock_request: MagicMock) -> None:
        today = date.today().isoformat()
        mock_request.return_value = self._mock_submissions_response([
            {"form": "8-K", "date": today, "accession": "0001050446-26-000001", "doc": "filing.htm"},
            {"form": "10-Q", "date": today},  # Should be filtered out
            {"form": "8-K/A", "date": today, "accession": "0001050446-26-000002", "doc": "amend.htm"},
        ])

        results = fetch_company_filings("0001050446")

        assert len(results) == 2
        assert results[0]["form"] == "8-K"
        assert results[1]["form"] == "8-K/A"

    @patch("scraper.fetcher._sec_request")
    def test_filters_old_filings(self, mock_request: MagicMock) -> None:
        old_date = (date.today() - timedelta(days=30)).isoformat()
        mock_request.return_value = self._mock_submissions_response([
            {"form": "8-K", "date": old_date},
        ])

        results = fetch_company_filings("0001050446")

        assert len(results) == 0

    @patch("scraper.fetcher._sec_request")
    def test_handles_network_error(self, mock_request: MagicMock) -> None:
        mock_request.side_effect = ValueError("HTTP 503")

        results = fetch_company_filings("0001050446")

        assert results == []


# --- Test: fetch_filing_text ---


class TestFetchFilingText:
    @patch("scraper.fetcher._sec_request")
    def test_returns_stripped_text(self, mock_request: MagicMock) -> None:
        mock_request.return_value = "<html><body><p>Acquired 13,627 BTC</p></body></html>"

        text = fetch_filing_text("0001050446", "0001050446-26-000001", "filing.htm")

        assert "Acquired 13,627 BTC" in text
        assert "<" not in text

    @patch("scraper.fetcher._sec_request")
    def test_returns_empty_on_error(self, mock_request: MagicMock) -> None:
        mock_request.side_effect = ValueError("HTTP 404")

        text = fetch_filing_text("0001050446", "0001050446-26-000001", "filing.htm")

        assert text == ""


# --- Test: build_updates ---


class TestBuildUpdates:
    @patch("scraper.fetcher.fetch_filing_text")
    @patch("scraper.fetcher.fetch_company_filings")
    def test_skips_empty_cik(
        self,
        mock_filings: MagicMock,
        mock_text: MagicMock,
    ) -> None:
        data = {
            "companies": {
                "BTC": [
                    {"ticker": "MTPLF", "name": "Metaplanet", "cik": "", "tokens": 35102},
                ]
            }
        }

        updates = build_updates(data)

        assert len(updates) == 0
        mock_filings.assert_not_called()

    @patch("scraper.fetcher.fetch_filing_text")
    @patch("scraper.fetcher.fetch_company_filings")
    def test_builds_update_from_filing(
        self,
        mock_filings: MagicMock,
        mock_text: MagicMock,
    ) -> None:
        mock_filings.return_value = [
            {
                "accessionNumber": "0001050446-26-000001",
                "filingDate": date.today().isoformat(),
                "primaryDocument": "filing.htm",
                "form": "8-K",
            }
        ]
        mock_text.return_value = (
            "Strategy acquired 700,000 BTC for approximately $64 billion "
            "in treasury holdings as of January 2026."
        )

        data = {
            "companies": {
                "BTC": [
                    {"ticker": "MSTR", "name": "Strategy", "cik": "0001050446", "tokens": 687410},
                ]
            }
        }

        updates = build_updates(data)

        assert len(updates) == 1
        assert updates[0].ticker == "MSTR"
        assert updates[0].token == "BTC"
        assert updates[0].new_value == 700000

    @patch("scraper.fetcher.fetch_filing_text")
    @patch("scraper.fetcher.fetch_company_filings")
    def test_no_quantity_no_update(
        self,
        mock_filings: MagicMock,
        mock_text: MagicMock,
    ) -> None:
        mock_filings.return_value = [
            {
                "accessionNumber": "0001050446-26-000001",
                "filingDate": date.today().isoformat(),
                "primaryDocument": "filing.htm",
                "form": "8-K",
            }
        ]
        mock_text.return_value = "Board approved new compensation plan for executives."

        data = {
            "companies": {
                "BTC": [
                    {"ticker": "MSTR", "name": "Strategy", "cik": "0001050446", "tokens": 687410},
                ]
            }
        }

        updates = build_updates(data)

        assert len(updates) == 0
