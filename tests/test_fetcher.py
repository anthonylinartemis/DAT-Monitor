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
    _get_filing_text_with_exhibits,
    _strip_html,
    build_updates,
    fetch_company_filings,
    fetch_exhibit_docs,
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
        old_date = (date.today() - timedelta(days=60)).isoformat()
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


# --- Test: exhibit fetching ---


class TestFetchExhibitDocs:
    @patch("scraper.fetcher._sec_request")
    def test_finds_exhibit_filenames(self, mock_request: MagicMock) -> None:
        # Simulated EDGAR filing directory page
        mock_request.return_value = """
        <html><body><table>
        <tr><td><a href="form8-k.htm">form8-k.htm</a></td></tr>
        <tr><td><a href="ex99-1.htm">ex99-1.htm</a></td></tr>
        <tr><td><a href="ex99-2.htm">ex99-2.htm</a></td></tr>
        </table></body></html>
        """

        exhibits = fetch_exhibit_docs("1234567", "0001234567-26-000001")

        assert exhibits == ["ex99-1.htm", "ex99-2.htm"]

    @patch("scraper.fetcher._sec_request")
    def test_no_exhibits_returns_empty(self, mock_request: MagicMock) -> None:
        mock_request.return_value = """
        <html><body><table>
        <tr><td><a href="form8-k.htm">form8-k.htm</a></td></tr>
        <tr><td><a href="R1.htm">R1.htm</a></td></tr>
        </table></body></html>
        """

        exhibits = fetch_exhibit_docs("1234567", "0001234567-26-000001")

        assert exhibits == []

    @patch("scraper.fetcher._sec_request")
    def test_deduplicates_exhibits(self, mock_request: MagicMock) -> None:
        mock_request.return_value = """
        <html><body>
        <a href="ex99-1.htm">ex99-1.htm</a>
        <a href="ex99-1.htm">ex99-1.htm</a>
        </body></html>
        """

        exhibits = fetch_exhibit_docs("1234567", "0001234567-26-000001")

        assert exhibits == ["ex99-1.htm"]

    @patch("scraper.fetcher._sec_request")
    def test_handles_network_error(self, mock_request: MagicMock) -> None:
        mock_request.side_effect = ValueError("HTTP 503")

        exhibits = fetch_exhibit_docs("1234567", "0001234567-26-000001")

        assert exhibits == []


class TestGetFilingTextWithExhibits:
    @patch("scraper.fetcher.fetch_exhibit_docs")
    @patch("scraper.fetcher.fetch_filing_text")
    def test_uses_primary_doc_when_it_has_data(
        self, mock_text: MagicMock, mock_exhibits: MagicMock
    ) -> None:
        mock_text.return_value = "Company holds 4,371,497 ETH in treasury"

        text, doc = _get_filing_text_with_exhibits(
            "1234567", "0001234567-26-000001", "form8-k.htm", "ETH"
        )

        assert "4,371,497 ETH" in text
        assert doc == "form8-k.htm"
        mock_exhibits.assert_not_called()

    @patch("scraper.fetcher.fetch_exhibit_docs")
    @patch("scraper.fetcher.fetch_filing_text")
    def test_falls_back_to_exhibit(
        self, mock_text: MagicMock, mock_exhibits: MagicMock
    ) -> None:
        # Primary doc has no token data, exhibit does
        mock_text.side_effect = [
            "Form 8-K cover page with no token info",  # primary doc
            "Company acquired 4,371,497 Ether in treasury",  # exhibit
        ]
        mock_exhibits.return_value = ["ex99-1.htm"]

        text, doc = _get_filing_text_with_exhibits(
            "1234567", "0001234567-26-000001", "form8-k.htm", "ETH"
        )

        assert "4,371,497 Ether" in text
        assert doc == "ex99-1.htm"

    @patch("scraper.fetcher.fetch_exhibit_docs")
    @patch("scraper.fetcher.fetch_filing_text")
    def test_returns_empty_when_nothing_found(
        self, mock_text: MagicMock, mock_exhibits: MagicMock
    ) -> None:
        mock_text.return_value = "Board approved new compensation plan"
        mock_exhibits.return_value = []

        text, doc = _get_filing_text_with_exhibits(
            "1234567", "0001234567-26-000001", "form8-k.htm", "ETH"
        )

        # Returns the primary text (even though no token data)
        assert doc == "form8-k.htm"

    @patch("scraper.fetcher.fetch_exhibit_docs")
    @patch("scraper.fetcher.fetch_filing_text")
    def test_tries_multiple_exhibits(
        self, mock_text: MagicMock, mock_exhibits: MagicMock
    ) -> None:
        mock_text.side_effect = [
            "Cover page boilerplate",  # primary
            "Financial summary no tokens",  # ex99-1
            "Treasury holds 5,427 BTC as of filing date",  # ex99-2
        ]
        mock_exhibits.return_value = ["ex99-1.htm", "ex99-2.htm"]

        text, doc = _get_filing_text_with_exhibits(
            "1234567", "0001234567-26-000001", "form8-k.htm", "BTC"
        )

        assert "5,427 BTC" in text
        assert doc == "ex99-2.htm"


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
    def test_no_quantity_creates_filing_only_update(
        self,
        mock_filings: MagicMock,
        mock_text: MagicMock,
    ) -> None:
        """When no token quantity is found, a filing-only update is still created
        so the filing appears in the Filing Feed."""
        mock_filings.return_value = [
            {
                "accessionNumber": "0001050446-26-000001",
                "filingDate": date.today().isoformat(),
                "primaryDocument": "filing.htm",
                "form": "8-K",
                "items": "",
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

        # Filing-only update preserves current token count
        assert len(updates) == 1
        assert updates[0].ticker == "MSTR"
        assert updates[0].new_value == 687410  # unchanged
        assert updates[0].source_type == "sec_edgar"
        assert updates[0].filing_form == "8-K"
