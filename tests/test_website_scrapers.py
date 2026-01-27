"""Tests for website scrapers (Metaplanet analytics).

All HTTP calls are mocked — no network access during tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scraper.updater import apply_enrichments
from scraper.website_scrapers import (
    MetaplanetAnalytics,
    MetaplanetPurchase,
    _extract_purchase_history,
    _extract_total_btc,
    _parse_btc_amount,
    _parse_usd_amount,
    _strip_html,
    build_website_updates,
    fetch_metaplanet_updates,
    parse_metaplanet_analytics,
)


# --- Sample page text that mimics stripped Metaplanet analytics ---

SAMPLE_METAPLANET_TEXT = (
    "Metaplanet Inc. Analytics Dashboard "
    "Total BTC Holdings ₿35,102 "
    "Bitcoin Price $88,176 "
    "Bitcoin NAV $3.10B "
    "BTC per 1,000 Shares ₿0.02404860 "
    "Bitcoin Ownership Percentage 0.16715% "
    "Average BTC Purchased Daily ₿53.18 "
    "Purchase History "
    "Dec 30, 2025 ₿4,279 $105,412 $451.06M ₿35,102 "
    "Sep 30, 2025 ₿5,268 $116,870 $615.67M ₿30,823 "
    "Sep 22, 2025 ₿5,419 $116,724 $632.53M ₿25,555 "
    "Apr 23, 2024 ₿97.85 $66,018 $6.46M ₿97.85 "
)


# --- Test: amount parsers ---


class TestParseAmounts:
    def test_btc_comma_integer(self) -> None:
        assert _parse_btc_amount("35,102") == 35102.0

    def test_btc_decimal(self) -> None:
        assert _parse_btc_amount("0.02404860") == pytest.approx(0.02404860)

    def test_btc_small_decimal(self) -> None:
        assert _parse_btc_amount("97.85") == pytest.approx(97.85)

    def test_usd_millions(self) -> None:
        assert _parse_usd_amount("$451.06M") == pytest.approx(451_060_000)

    def test_usd_billions(self) -> None:
        assert _parse_usd_amount("$3.10B") == pytest.approx(3_100_000_000)

    def test_usd_plain(self) -> None:
        assert _parse_usd_amount("$105,412") == pytest.approx(105412)

    def test_usd_invalid(self) -> None:
        assert _parse_usd_amount("not a number") is None

    def test_btc_invalid(self) -> None:
        assert _parse_btc_amount("abc") is None


# --- Test: total BTC extraction ---


class TestExtractTotalBtc:
    def test_extracts_from_standard_text(self) -> None:
        assert _extract_total_btc(SAMPLE_METAPLANET_TEXT) == 35102.0

    def test_returns_none_for_missing(self) -> None:
        assert _extract_total_btc("No BTC data here") is None

    def test_alternative_label(self) -> None:
        text = "BTC Holdings ₿12,500 are growing"
        assert _extract_total_btc(text) == 12500.0


# --- Test: purchase history extraction ---


class TestExtractPurchaseHistory:
    def test_extracts_all_rows(self) -> None:
        purchases = _extract_purchase_history(SAMPLE_METAPLANET_TEXT)
        assert len(purchases) == 4

    def test_first_row_values(self) -> None:
        purchases = _extract_purchase_history(SAMPLE_METAPLANET_TEXT)
        first = purchases[0]
        assert "Dec 30, 2025" in first.date
        assert first.btc_acquired == pytest.approx(4279)
        assert first.avg_cost_usd == pytest.approx(105412)
        assert first.acquisition_cost_usd == pytest.approx(451_060_000)
        assert first.total_holdings == pytest.approx(35102)

    def test_last_row_small_amount(self) -> None:
        purchases = _extract_purchase_history(SAMPLE_METAPLANET_TEXT)
        last = purchases[-1]
        assert "Apr 23, 2024" in last.date
        assert last.btc_acquired == pytest.approx(97.85)

    def test_empty_text_returns_empty(self) -> None:
        assert _extract_purchase_history("nothing here") == []


# --- Test: full analytics parser ---


class TestParseMetaplanetAnalytics:
    def test_total_btc(self) -> None:
        result = parse_metaplanet_analytics(SAMPLE_METAPLANET_TEXT)
        assert result.total_btc == 35102

    def test_btc_per_1000_shares(self) -> None:
        result = parse_metaplanet_analytics(SAMPLE_METAPLANET_TEXT)
        assert result.btc_per_1000_shares == pytest.approx(0.02404860)

    def test_ownership_pct(self) -> None:
        result = parse_metaplanet_analytics(SAMPLE_METAPLANET_TEXT)
        assert result.ownership_pct == pytest.approx(0.16715)

    def test_avg_daily_btc(self) -> None:
        result = parse_metaplanet_analytics(SAMPLE_METAPLANET_TEXT)
        assert result.avg_daily_btc == pytest.approx(53.18)

    def test_bitcoin_nav(self) -> None:
        result = parse_metaplanet_analytics(SAMPLE_METAPLANET_TEXT)
        assert result.bitcoin_nav_usd == pytest.approx(3_100_000_000)

    def test_purchase_history_count(self) -> None:
        result = parse_metaplanet_analytics(SAMPLE_METAPLANET_TEXT)
        assert len(result.purchase_history) == 4

    def test_to_json_dict(self) -> None:
        result = parse_metaplanet_analytics(SAMPLE_METAPLANET_TEXT)
        d = result.to_json_dict()
        assert d["totalBtc"] == 35102
        assert "purchaseHistory" in d
        assert len(d["purchaseHistory"]) == 4
        assert d["purchaseHistory"][0]["btcAcquired"] == pytest.approx(4279)


# --- Test: fetch_metaplanet_updates (mocked HTTP) ---


class TestFetchMetaplanetUpdates:
    @patch("scraper.website_scrapers._http_get")
    def test_builds_update_from_page(self, mock_get: MagicMock) -> None:
        mock_get.return_value = f"<html><body>{SAMPLE_METAPLANET_TEXT}</body></html>"

        data = {"companies": {"BTC": [{"ticker": "MTPLF", "name": "Metaplanet", "cik": "", "tokens": 35102}]}}
        updates, analytics = fetch_metaplanet_updates(data)

        assert len(updates) == 1
        assert updates[0].ticker == "MTPLF"
        assert updates[0].token == "BTC"
        assert updates[0].new_value == 35102
        assert "treasury" in updates[0].context_text.lower()

    @patch("scraper.website_scrapers._http_get")
    def test_returns_analytics_dict(self, mock_get: MagicMock) -> None:
        mock_get.return_value = f"<html><body>{SAMPLE_METAPLANET_TEXT}</body></html>"

        data = {"companies": {"BTC": [{"ticker": "MTPLF", "name": "Metaplanet", "cik": "", "tokens": 35102}]}}
        _, analytics = fetch_metaplanet_updates(data)

        assert analytics is not None
        assert analytics["totalBtc"] == 35102
        assert "purchaseHistory" in analytics

    @patch("scraper.website_scrapers._http_get")
    def test_handles_network_error(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = ValueError("HTTP 503")

        data = {"companies": {"BTC": []}}
        updates, analytics = fetch_metaplanet_updates(data)

        assert updates == []
        assert analytics is None


# --- Test: build_website_updates orchestrator ---


class TestBuildWebsiteUpdates:
    @patch("scraper.website_scrapers._http_get")
    def test_returns_updates_and_enrichments(self, mock_get: MagicMock) -> None:
        mock_get.return_value = f"<html><body>{SAMPLE_METAPLANET_TEXT}</body></html>"

        data = {"companies": {"BTC": [{"ticker": "MTPLF", "name": "Metaplanet", "cik": "", "tokens": 35102}]}}
        updates, enrichments = build_website_updates(data)

        assert len(updates) == 1
        assert "MTPLF" in enrichments


# --- Test: apply_enrichments in updater ---


class TestApplyEnrichments:
    def test_adds_analytics_to_company(self) -> None:
        data = {
            "companies": {
                "BTC": [
                    {"ticker": "MTPLF", "name": "Metaplanet", "tokens": 35102},
                ]
            }
        }
        enrichments = {"MTPLF": {"totalBtc": 35102, "purchaseHistory": []}}

        result = apply_enrichments(data, enrichments)

        mtplf = result["companies"]["BTC"][0]
        assert "analytics" in mtplf
        assert mtplf["analytics"]["totalBtc"] == 35102

    def test_unknown_ticker_no_crash(self) -> None:
        data = {"companies": {"BTC": []}}
        enrichments = {"ZZZZ": {"totalBtc": 999}}

        result = apply_enrichments(data, enrichments)
        # No crash, data unchanged
        assert result == data
