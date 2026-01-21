"""
Web scraper for static HTML and JavaScript-rendered pages.
"""

import re
import warnings
from datetime import datetime
from typing import Optional

from bs4 import XMLParsedAsHTMLWarning

from scrapers.base import BaseScraper, ScraperResult, create_soup
from utils.parsers import (
    clean_numeric_string,
    extract_holdings_with_regex,
    extract_numbers_from_text,
    is_reasonable_change,
)

# Suppress XML parsing warnings
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


class WebScraper(BaseScraper):
    """Scraper for static HTML and JS-rendered web pages."""

    def __init__(self, company: dict, token: str, token_config: dict = None):
        super().__init__(company, token, token_config=token_config)
        self.method = self.config.get("method", "html_static")

    def scrape(self) -> Optional[ScraperResult]:
        """
        Scrape web page for holdings data.

        Uses html_static (BeautifulSoup) or playwright_js based on config.
        """
        source_url = self.get_source_url()

        if not source_url:
            self.log("No source_url configured")
            return None

        if self.method == "playwright_js":
            return self._scrape_with_playwright(source_url)
        else:
            return self._scrape_static(source_url)

    def _scrape_static(self, url: str) -> Optional[ScraperResult]:
        """Scrape static HTML page with BeautifulSoup."""
        html = self.fetch_url(url, apply_rate_limit=False)

        if not html:
            return None

        # Try parsing as JSON first (for data.js endpoints)
        holdings = self._try_parse_as_data(html)

        if holdings is None:
            # Parse as HTML
            soup = create_soup(html)
            text = soup.get_text()
            holdings = self._find_holdings_in_text(text)

        if holdings and holdings != self.current_holdings:
            if not is_reasonable_change(self.current_holdings, holdings):
                self.log(f"Suspicious drop to {holdings:,}, skipping")
                return None

            self.log(f"Found: {holdings:,} {self.token}")
            return ScraperResult(
                tokens=holdings,
                date=datetime.now().strftime("%Y-%m-%d"),
                url=url,
                source="web_static"
            )

        return None

    def _scrape_with_playwright(self, url: str) -> Optional[ScraperResult]:
        """Scrape JS-rendered page with Playwright."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.log("Playwright not installed, falling back to static scrape")
            return self._scrape_static(url)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                self.log(f"Loading {url} with Playwright...")
                page.goto(url, wait_until="networkidle", timeout=30000)

                # Wait for content to load
                page.wait_for_timeout(2000)

                # Get page content
                content = page.content()
                browser.close()

            soup = create_soup(content)
            text = soup.get_text()

            holdings = self._find_holdings_in_text(text)

            if holdings and holdings != self.current_holdings:
                if not is_reasonable_change(self.current_holdings, holdings):
                    self.log(f"Suspicious drop to {holdings:,}, skipping")
                    return None

                self.log(f"Found: {holdings:,} {self.token}")
                return ScraperResult(
                    tokens=holdings,
                    date=datetime.now().strftime("%Y-%m-%d"),
                    url=url,
                    source="web_playwright"
                )

        except Exception as e:
            self.log(f"Playwright error: {e}")

        return None

    def _try_parse_as_data(self, content: str) -> Optional[int]:
        """Try to parse content as JavaScript data file."""
        # Look for common patterns in data.js files
        patterns = [
            r'totalHoldings:\s*(\d+)',
            r'holdings:\s*(\d+)',
            r'"totalHoldings":\s*(\d+)',
            r'"holdings":\s*(\d+)',
            r'total:\s*(\d+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue

        return None

    def _find_holdings_in_text(self, text: str) -> Optional[int]:
        """Find token holdings in page text."""
        text_lower = text.lower()
        keywords = self.get_keywords()

        # Special handling for BTC - check for ₿ symbol (case-sensitive)
        if self.token == "BTC":
            btc_symbol_match = re.search(r'₿\s*([\d,]+)', text)
            if btc_symbol_match:
                num_str = btc_symbol_match.group(1)
                try:
                    num = int(num_str.replace(",", ""))
                    if self.is_valid_holdings_amount(num):
                        return num
                except (ValueError, AttributeError):
                    pass

        # Check if page mentions our token
        token_mentioned = any(kw in text_lower for kw in keywords)
        if not token_mentioned:
            return None

        # Try custom regex first (case-insensitive by default)
        custom_regex = self.get_target_regex()
        if custom_regex:
            result = extract_holdings_with_regex(text, custom_regex)
            if result:
                return result

        # Try common dashboard patterns
        dashboard_patterns = [
            rf'(\d[\d,\.]+)\s*{self.token}',
            rf'{self.token}\s*:?\s*(\d[\d,\.]+)',
            r'treasury\s*:?\s*(\d[\d,\.]+)',
            r'holdings?\s*:?\s*(\d[\d,\.]+)',
            r'balance\s*:?\s*(\d[\d,\.]+)',
            rf'total\s+{self.token}\s+count[:\s]*(\d[\d,\.]+)',
            r'total\s+sol\s+count[:\s]*(\d[\d,\.]+)',
            r'total\s+eth[:\s]*(\d[\d,\.]+)',
            r'total\s+btc[:\s]*(\d[\d,\.]+)',
        ]

        for kw in keywords:
            dashboard_patterns.extend([
                rf'(\d[\d,\.]+)\s*{kw}',
                rf'{kw}\s*:?\s*(\d[\d,\.]+)',
                rf'total\s+{kw}[:\s]*(\d[\d,\.]+)',
            ])

        for pattern in dashboard_patterns:
            match = re.search(pattern, text_lower)
            if match:
                num_str = match.group(1)
                try:
                    num = clean_numeric_string(num_str)
                    if self.is_valid_holdings_amount(num):
                        return num
                except (ValueError, AttributeError):
                    continue

        # Extract all numbers and find reasonable ones
        all_numbers = extract_numbers_from_text(text)
        for num in sorted(all_numbers, reverse=True):
            if self.is_valid_holdings_amount(num):
                # If we have current holdings, prefer numbers close to it
                if self.current_holdings > 0:
                    ratio = num / self.current_holdings
                    if 0.5 <= ratio <= 2.0:
                        return num
                else:
                    return num

        return None


class DashboardScraper(BaseScraper):
    """Scraper for known company dashboard formats."""

    def scrape(self) -> Optional[ScraperResult]:
        """Check company dashboard for holdings data."""
        data_url = self.company.get("dataUrl")
        dashboard_url = self.company.get("dashboardUrl")

        if not data_url and not dashboard_url:
            return None

        # Try data URL first (typically data.js)
        if data_url:
            html = self.fetch_url(data_url, apply_rate_limit=False)
            if html:
                holdings = self._parse_data_js(html)
                if holdings and holdings != self.current_holdings:
                    if not is_reasonable_change(self.current_holdings, holdings):
                        self.log(f"Suspicious drop to {holdings:,}, skipping")
                        return None

                    self.log(f"Found in dashboard: {holdings:,} {self.token}")
                    return ScraperResult(
                        tokens=holdings,
                        date=datetime.now().strftime("%Y-%m-%d"),
                        url=dashboard_url or data_url,
                        source="company_dashboard"
                    )

        return None

    def _parse_data_js(self, content: str) -> Optional[int]:
        """Parse data.js content for holdings."""
        patterns = [
            r'totalHoldings:\s*(\d+)',
            r'holdings:\s*(\d+)',
            r'"totalHoldings":\s*(\d+)',
            r'"holdings":\s*(\d+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue

        return None
