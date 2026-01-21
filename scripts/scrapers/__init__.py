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


def get_scraper(
    company: dict,
    token: str,
    days_back: int = 14,
    token_config: dict = None
) -> BaseScraper:
    """
    Factory function to get the appropriate scraper for a company.

    Args:
        company: Company dict from data.json
        token: Token type (BTC, ETH, SOL, HYPE, BNB)
        days_back: Days to look back for SEC filings
        token_config: Optional token configuration (validation ranges, keywords)

    Returns:
        Appropriate scraper instance based on scrape_config.method

    Scraper selection priority:
    1. Explicit scrape_config.method if set
    2. DashboardScraper if dataUrl is configured (for data.js endpoints)
    3. SECScraper if company has a CIK
    4. WebScraper as fallback
    """
    config = company.get("scrape_config", {})
    method = config.get("method")

    # Explicit method takes priority
    if method == "sec_edgar":
        return SECScraper(company, token, days_back=days_back, token_config=token_config)
    elif method == "html_static":
        return WebScraper(company, token, token_config=token_config)
    elif method == "playwright_js":
        return WebScraper(company, token, token_config=token_config)
    elif method == "dashboard":
        return DashboardScraper(company, token, token_config=token_config)

    # Auto-select based on company configuration
    # Check for dashboard data URL (e.g., data.js endpoints)
    if company.get("dataUrl"):
        return DashboardScraper(company, token, token_config=token_config)

    # Default to SEC for US companies with CIK
    if company.get("cik"):
        return SECScraper(company, token, days_back=days_back, token_config=token_config)

    # Fallback to WebScraper
    return WebScraper(company, token, token_config=token_config)
