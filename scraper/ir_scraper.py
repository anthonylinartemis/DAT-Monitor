"""Investor Relations page scraper for all DAT companies.

Fetches company news/IR pages and extracts press release headlines and links
for manual review. This catches announcements that might not appear in SEC filings.
"""

from __future__ import annotations

import logging
import re
import ssl
import urllib.error
import urllib.request
import gzip
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

# Use a browser-like User-Agent since some IR sites block bots
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Maximum age for press releases to include (days)
MAX_PR_AGE_DAYS = 30

# Q4 Inc and similar JavaScript-rendered IR platforms that can't be scraped with simple HTTP
# These require headless browsers or have API access
JS_RENDERED_PLATFORMS = [
    "q4cdn.com",
    "q4inc.com",
    "investors.strive.com",  # Q4 platform
    "ir.upexi.com",  # Q4 platform
    "ir.hyperiondefi.com",  # Q4 platform
]

# PR wire services to search for company press releases
PR_WIRE_SEARCH_URLS = {
    "globenewswire": "https://www.globenewswire.com/search/keyword/{query}",
    "prnewswire": "https://www.prnewswire.com/search/keyword/{query}",
    "businesswire": "https://www.businesswire.com/portal/site/home/search/?searchTerm={query}",
}


@dataclass(frozen=True)
class DiscoveredPR:
    """A press release discovered from an IR page."""
    ticker: str
    token: str
    title: str
    url: str
    date: Optional[str]  # ISO format or None if unknown
    source_page: str
    discovered_at: str  # ISO timestamp

    def to_json_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "token": self.token,
            "title": self.title,
            "url": self.url,
            "date": self.date,
            "sourcePage": self.source_page,
            "discoveredAt": self.discovered_at,
        }


def _http_get(url: str, timeout: int = 30) -> str:
    """Fetch a URL with proper User-Agent. Returns decoded text."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "text/html,application/xhtml+xml,*/*")
    req.add_header("Accept-Encoding", "gzip, deflate")

    # Create SSL context that doesn't verify certificates (some IR sites have issues)
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise ValueError(f"HTTP {e.code} for {url}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise ValueError(f"URL error for {url}: {e.reason}") from e


def _extract_date_from_text(text: str) -> Optional[str]:
    """Try to extract a date from text. Returns ISO format or None."""
    # Common date patterns
    patterns = [
        # "January 21, 2026" or "Jan 21, 2026"
        r"((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+\d{1,2},?\s+\d{4})",
        # "2026-01-21" ISO format
        r"(\d{4}-\d{2}-\d{2})",
        # "01/21/2026" US format
        r"(\d{1,2}/\d{1,2}/\d{4})",
        # "21 Jan 2026"
        r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            date_str = m.group(1)
            try:
                # Try parsing with various formats
                for fmt in [
                    "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y",
                    "%Y-%m-%d",
                    "%m/%d/%Y", "%d/%m/%Y",
                    "%d %B %Y", "%d %b %Y",
                ]:
                    try:
                        dt = datetime.strptime(date_str.replace(",", ""), fmt)
                        return dt.strftime("%Y-%m-%d")
                    except ValueError:
                        continue
            except Exception:
                pass
    return None


def _is_crypto_related(text: str) -> bool:
    """Check if text mentions crypto holdings or treasury operations."""
    keywords = [
        "bitcoin", "btc", "ethereum", "eth", "ether", "solana", "sol",
        "hyperliquid", "hype", "bnb", "crypto", "treasury", "holdings",
        "acquired", "purchased", "token", "digital asset", "blockchain",
        "8-k", "filing", "acquisition", "announce", "announce"
    ]
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


def _extract_press_releases(html: str, base_url: str) -> list[dict]:
    """Extract press release links from HTML. Returns list of {title, url, date}."""
    releases = []

    # Pattern 1: Links with news/press/release in URL or text
    # Look for <a> tags with relevant content
    link_pattern = r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>'

    for match in re.finditer(link_pattern, html, re.IGNORECASE):
        href = match.group(1)
        text = match.group(2).strip()

        # Skip navigation, empty, or very short links
        if not text or len(text) < 10:
            continue

        # Skip common non-PR links
        skip_patterns = [
            r"^(home|about|contact|privacy|terms|login|sign)",
            r"^(read more|learn more|see all|view all|more info)$",
            r"\.pdf$",
            r"\.jpg$|\.png$|\.gif$",
            r"^#",
            r"^javascript:",
        ]
        if any(re.search(p, text, re.IGNORECASE) or re.search(p, href, re.IGNORECASE)
               for p in skip_patterns):
            continue

        # Check if it looks like a press release
        is_pr_url = any(x in href.lower() for x in [
            "news", "press", "release", "announce", "investor",
            "sec.gov", "globenewswire", "prnewswire", "businesswire"
        ])
        is_pr_text = _is_crypto_related(text) or any(x in text.lower() for x in [
            "announce", "report", "update", "filing", "acquisition",
            "quarter", "q1", "q2", "q3", "q4", "annual", "fiscal"
        ])

        if is_pr_url or is_pr_text:
            # Resolve relative URLs
            full_url = urljoin(base_url, href)

            # Extract date from surrounding context (look for date near link)
            # Get text around the link in HTML
            start = max(0, match.start() - 200)
            end = min(len(html), match.end() + 200)
            context = html[start:end]
            # Strip HTML tags for date extraction
            context_text = re.sub(r"<[^>]+>", " ", context)
            pr_date = _extract_date_from_text(context_text)

            releases.append({
                "title": text[:200],  # Truncate long titles
                "url": full_url,
                "date": pr_date,
            })

    return _dedupe_by_url(releases, url_getter=lambda x: x["url"])


def _is_js_rendered_platform(url: str) -> bool:
    """Check if URL is a JavaScript-rendered IR platform that can't be scraped."""
    if not url:
        return False
    url_lower = url.lower()
    return any(platform in url_lower for platform in JS_RENDERED_PLATFORMS)


def _dedupe_by_url(items: list, url_getter=lambda x: x.url):
    """Deduplicate a list of items by URL, preserving order."""
    seen = set()
    result = []
    for item in items:
        url = url_getter(item)
        if url not in seen:
            seen.add(url)
            result.append(item)
    return result


def _scrape_globenewswire(company_name: str, ticker: str, token: str) -> list[DiscoveredPR]:
    """Search GlobeNewswire for press releases mentioning the company."""
    results = []
    discovered_at = datetime.now().isoformat()

    # Try searching by company name
    search_url = f"https://www.globenewswire.com/search/tag/{ticker.upper()}"

    try:
        html = _http_get(search_url, timeout=15)

        # GlobeNewswire has a specific structure for search results
        # Look for news-item links
        pattern = r'<a[^>]*href="(/news-release/[^"]+)"[^>]*>([^<]+)</a>'

        for match in re.finditer(pattern, html, re.IGNORECASE):
            href = match.group(1)
            title = match.group(2).strip()

            if not title or len(title) < 15:
                continue

            full_url = urljoin("https://www.globenewswire.com", href)

            # Try to extract date from URL (format: /news-release/2026/01/28/...)
            date_match = re.search(r'/news-release/(\d{4})/(\d{2})/(\d{2})/', href)
            pr_date = None
            if date_match:
                pr_date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"

            results.append(DiscoveredPR(
                ticker=ticker,
                token=token,
                title=title[:200],
                url=full_url,
                date=pr_date,
                source_page=search_url,
                discovered_at=discovered_at,
            ))

        logger.info("GlobeNewswire: Found %d releases for %s", len(results), ticker)

    except Exception as e:
        logger.debug("GlobeNewswire search failed for %s: %s", ticker, e)

    return results


def scrape_ir_page(ticker: str, token: str, ir_url: str) -> list[DiscoveredPR]:
    """Scrape a single IR page for press releases.

    Returns list of DiscoveredPR objects.
    """
    if not ir_url:
        return []

    logger.info("Scraping IR page for %s: %s", ticker, ir_url)

    # Check if this is a JS-rendered platform we can't scrape
    if _is_js_rendered_platform(ir_url):
        logger.info("Skipping %s: JS-rendered platform (%s)", ticker, ir_url)
        # For JS platforms, try searching PR wire services instead
        return _scrape_globenewswire("", ticker, token)

    try:
        html = _http_get(ir_url)
    except (ValueError, urllib.error.URLError) as e:
        logger.warning("Failed to fetch IR page for %s: %s", ticker, e)
        # Fall back to PR wire search
        return _scrape_globenewswire("", ticker, token)

    releases = _extract_press_releases(html, ir_url)
    logger.info("Found %d potential press releases for %s", len(releases), ticker)

    discovered_at = datetime.now().isoformat()
    cutoff = date.today() - timedelta(days=MAX_PR_AGE_DAYS)

    results = []
    for pr in releases:
        # Filter by date if available
        if pr["date"]:
            try:
                pr_date = date.fromisoformat(pr["date"])
                if pr_date < cutoff:
                    continue  # Too old
            except ValueError:
                pass

        results.append(DiscoveredPR(
            ticker=ticker,
            token=token,
            title=pr["title"],
            url=pr["url"],
            date=pr["date"],
            source_page=ir_url,
            discovered_at=discovered_at,
        ))

    # Also search GlobeNewswire for additional coverage
    results.extend(_scrape_globenewswire("", ticker, token))

    return _dedupe_by_url(results)


def scrape_all_ir_pages(data: dict) -> list[DiscoveredPR]:
    """Scrape all company IR pages for press releases.

    Returns list of all discovered press releases.
    """
    all_prs: list[DiscoveredPR] = []
    companies = data.get("companies", {})

    for token_group, company_list in companies.items():
        for company in company_list:
            ticker = company.get("ticker", "")
            ir_url = company.get("irUrl", "")

            if not ir_url:
                logger.debug("Skipping %s: no irUrl", ticker)
                continue

            try:
                prs = scrape_ir_page(ticker, token_group, ir_url)
                all_prs.extend(prs)
            except Exception as e:
                logger.warning("Error scraping %s: %s", ticker, e)
                continue

    logger.info("Total discovered press releases: %d", len(all_prs))
    return all_prs


def merge_discovered_prs(
    existing: list[dict],
    new_prs: list[DiscoveredPR],
    max_age_days: int = MAX_PR_AGE_DAYS,
) -> list[dict]:
    """Merge new PRs with existing, deduplicating by URL.

    Also removes PRs older than max_age_days.
    """
    cutoff = date.today() - timedelta(days=max_age_days)

    # Index existing by URL
    by_url: dict[str, dict] = {}
    for pr in existing:
        url = pr.get("url", "")
        if url:
            # Keep if recent enough or no date
            pr_date = pr.get("date")
            if not pr_date:
                by_url[url] = pr
            else:
                try:
                    if date.fromisoformat(pr_date) >= cutoff:
                        by_url[url] = pr
                except ValueError:
                    by_url[url] = pr

    # Add new PRs
    for pr in new_prs:
        if pr.url not in by_url:
            by_url[pr.url] = pr.to_json_dict()

    # Sort by date (newest first), then by discoveredAt
    result = list(by_url.values())
    result.sort(
        key=lambda x: (x.get("date") or "0000-00-00", x.get("discoveredAt", "")),
        reverse=True,
    )

    return result
