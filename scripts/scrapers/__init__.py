"""
Scrapers package for DAT Treasury Monitor.
"""

from scrapers.base import BaseScraper, ScraperResult
from scrapers.sec_scraper import SECScraper
from scrapers.web_scraper import WebScraper, DashboardScraper

__all__ = [
    "BaseScraper",
    "ScraperResult",
    "SECScraper",
    "WebScraper",
    "DashboardScraper",
]


def get_scraper(company: dict, token: str, days_back: int = 14) -> BaseScraper:
    """
    Factory function to get the appropriate scraper for a company.

    Args:
        company: Company dict from data.json
        token: Token type (BTC, ETH, SOL, HYPE, BNB)
        days_back: Days to look back for SEC filings

    Returns:
        Appropriate scraper instance based on scrape_config.method
    """
    config = company.get("scrape_config", {})
    method = config.get("method", "sec_edgar")

    if method == "sec_edgar":
        return SECScraper(company, token, days_back=days_back)
    elif method == "html_static":
        return WebScraper(company, token)
    elif method == "playwright_js":
        return WebScraper(company, token)
    else:
        # Default to SEC for US companies with CIK
        if company.get("cik"):
            return SECScraper(company, token, days_back=days_back)
        return WebScraper(company, token)
