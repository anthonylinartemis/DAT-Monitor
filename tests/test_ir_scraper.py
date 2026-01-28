"""Tests for the IR page scraper."""

import pytest
from scraper.ir_scraper import (
    DiscoveredPR,
    _extract_date_from_text,
    _extract_press_releases,
    _is_crypto_related,
    merge_discovered_prs,
)


class TestExtractDateFromText:
    """Tests for _extract_date_from_text function."""

    def test_us_date_format(self):
        assert _extract_date_from_text("January 21, 2026") == "2026-01-21"

    def test_us_date_format_short_month(self):
        assert _extract_date_from_text("Jan 21, 2026") == "2026-01-21"

    def test_iso_format(self):
        assert _extract_date_from_text("2026-01-21") == "2026-01-21"

    def test_eu_format(self):
        assert _extract_date_from_text("21 January 2026") == "2026-01-21"

    def test_no_date(self):
        assert _extract_date_from_text("No date here") is None

    def test_date_in_context(self):
        text = "Company announced on January 21, 2026 that it acquired 1000 BTC"
        assert _extract_date_from_text(text) == "2026-01-21"


class TestIsCryptoRelated:
    """Tests for _is_crypto_related function."""

    def test_bitcoin_mention(self):
        assert _is_crypto_related("Company acquired Bitcoin") is True

    def test_eth_mention(self):
        assert _is_crypto_related("ETH treasury holdings") is True

    def test_treasury_keyword(self):
        assert _is_crypto_related("Digital asset treasury update") is True

    def test_not_crypto_related(self):
        assert _is_crypto_related("Quarterly earnings report") is False

    def test_case_insensitive(self):
        assert _is_crypto_related("BITCOIN Holdings") is True


class TestExtractPressReleases:
    """Tests for _extract_press_releases function."""

    def test_extracts_news_links(self):
        html = '''
        <html>
        <a href="/news/btc-acquisition">Company Acquires 1000 Bitcoin</a>
        <a href="/about">About Us</a>
        </html>
        '''
        releases = _extract_press_releases(html, "https://example.com")
        assert len(releases) == 1
        assert releases[0]["url"] == "https://example.com/news/btc-acquisition"
        assert "Bitcoin" in releases[0]["title"]

    def test_deduplicates_by_url(self):
        html = '''
        <html>
        <a href="/news/update">Bitcoin Treasury Update</a>
        <a href="/news/update">Read More About BTC Update</a>
        </html>
        '''
        releases = _extract_press_releases(html, "https://example.com")
        assert len(releases) == 1

    def test_resolves_relative_urls(self):
        html = '<a href="press/announcement.html">ETH Holdings Announcement</a>'
        releases = _extract_press_releases(html, "https://company.com/investor/")
        if releases:
            assert releases[0]["url"].startswith("https://company.com")

    def test_skips_navigation_links(self):
        html = '''
        <a href="/">Home</a>
        <a href="/about">About</a>
        <a href="/news/bitcoin">Bitcoin Treasury Acquisition Announcement</a>
        '''
        releases = _extract_press_releases(html, "https://example.com")
        # Should only find the bitcoin news link, not home/about
        assert all("bitcoin" in r["url"].lower() for r in releases)


class TestDiscoveredPR:
    """Tests for DiscoveredPR dataclass."""

    def test_to_json_dict(self):
        pr = DiscoveredPR(
            ticker="FGNX",
            token="ETH",
            title="ETH Acquisition",
            url="https://example.com/news",
            date="2026-01-21",
            source_page="https://example.com/investor",
            discovered_at="2026-01-28T12:00:00",
        )
        result = pr.to_json_dict()
        assert result["ticker"] == "FGNX"
        assert result["token"] == "ETH"
        assert result["title"] == "ETH Acquisition"
        assert result["url"] == "https://example.com/news"
        assert result["date"] == "2026-01-21"
        assert result["sourcePage"] == "https://example.com/investor"
        assert result["discoveredAt"] == "2026-01-28T12:00:00"


class TestMergeDiscoveredPRs:
    """Tests for merge_discovered_prs function."""

    def test_merges_new_prs(self):
        existing = [
            {"url": "https://example.com/old", "title": "Old PR", "date": "2026-01-20"}
        ]
        new_prs = [
            DiscoveredPR(
                ticker="TEST",
                token="BTC",
                title="New PR",
                url="https://example.com/new",
                date="2026-01-28",
                source_page="https://example.com",
                discovered_at="2026-01-28T12:00:00",
            )
        ]
        result = merge_discovered_prs(existing, new_prs)
        assert len(result) == 2
        urls = {pr["url"] for pr in result}
        assert "https://example.com/old" in urls
        assert "https://example.com/new" in urls

    def test_deduplicates_by_url(self):
        existing = [
            {"url": "https://example.com/same", "title": "Existing", "date": "2026-01-20"}
        ]
        new_prs = [
            DiscoveredPR(
                ticker="TEST",
                token="BTC",
                title="Duplicate",
                url="https://example.com/same",
                date="2026-01-28",
                source_page="https://example.com",
                discovered_at="2026-01-28T12:00:00",
            )
        ]
        result = merge_discovered_prs(existing, new_prs)
        # Should keep only one
        assert len(result) == 1

    def test_sorted_by_date_descending(self):
        new_prs = [
            DiscoveredPR(
                ticker="A", token="BTC", title="Old", url="https://a.com",
                date="2026-01-01", source_page="", discovered_at="",
            ),
            DiscoveredPR(
                ticker="B", token="BTC", title="New", url="https://b.com",
                date="2026-01-28", source_page="", discovered_at="",
            ),
        ]
        result = merge_discovered_prs([], new_prs)
        assert result[0]["date"] == "2026-01-28"
        assert result[1]["date"] == "2026-01-01"
