"""SEC EDGAR client for fetching recent filings and extracting token holdings.

Checks 8-K filings for all CIK-tracked companies, extracts token
quantities from filing text, and produces ScrapedUpdate objects for
the pipeline.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from typing import Optional

from scraper.models import ScrapedUpdate
from scraper.parser import _extract_quantity

logger = logging.getLogger(__name__)

# --- Constants ---

SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVES_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik_num}/{accession}/{doc}"
)
SEC_FILING_DIR_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik_num}/{accession}/"
)

# SEC requires a descriptive User-Agent with contact email
# Format: "Company/App Name (contact@email.com)"
USER_AGENT = "DAT-Monitor/1.0 (anthony.lin@artemisanalytics.xyz)"

# Filing types that announce crypto acquisitions
FILING_TYPES_OF_INTEREST: tuple[str, ...] = ("8-K", "8-K/A")

# Broader set of filing types for comprehensive tracking (earnings, quarterlies)
ALL_FILING_TYPES_OF_INTEREST: tuple[str, ...] = ("8-K", "8-K/A", "10-Q", "10-K", "10-K/A")

# Check filings from the last 30 days (covers gaps if scraper misses a run)
LOOKBACK_DAYS = 30

# Minimum delay between SEC requests (SEC allows 10 req/sec)
_REQUEST_DELAY_SECONDS = 0.11

# Token name aliases for text extraction
TOKEN_ALIASES: dict[str, tuple[str, ...]] = {
    "BTC": ("BTC", "Bitcoin", "bitcoin", "btc"),
    "ETH": ("ETH", "Ether", "ether", "Ethereum", "ethereum", "eth"),
    "SOL": ("SOL", "Solana", "solana", "sol"),
    "HYPE": ("HYPE", "Hyperliquid", "hyperliquid", "hype"),
    "BNB": ("BNB", "bnb"),
}

# Tracks the last request time to enforce rate limiting
_last_request_time: float = 0.0


# --- HTTP Layer ---


def _sec_request(url: str, retries: int = 3) -> str:
    """Fetch a URL from SEC EDGAR with proper User-Agent and rate limiting.

    Includes retry logic for transient failures (429, 503, connection errors).
    Raises urllib.error.URLError on network failures.
    Raises ValueError on non-200 responses after all retries.
    """
    global _last_request_time

    last_error = None
    for attempt in range(retries):
        # Rate limit: wait if needed (increase delay on retries)
        delay = _REQUEST_DELAY_SECONDS * (attempt + 1)
        elapsed = time.monotonic() - _last_request_time
        if elapsed < delay:
            time.sleep(delay - elapsed)

        req = urllib.request.Request(url)
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/json, text/html, */*")
        req.add_header("Accept-Encoding", "gzip, deflate")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                _last_request_time = time.monotonic()
                if resp.status != 200:
                    raise ValueError(
                        f"SEC EDGAR returned status {resp.status} for {url}"
                    )
                raw = resp.read()
                # Handle gzip encoding
                if resp.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    raw = gzip.decompress(raw)
                return raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            last_error = e
            # Retry on rate limit or server errors
            if e.code in (429, 500, 502, 503, 504):
                logger.warning(
                    "SEC EDGAR HTTP %d for %s, retrying (%d/%d)",
                    e.code, url, attempt + 1, retries
                )
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            # 403 Forbidden - log but don't retry (likely auth/bot detection)
            if e.code == 403:
                logger.error(
                    "SEC EDGAR 403 Forbidden for %s - check User-Agent compliance",
                    url
                )
            raise ValueError(
                f"SEC EDGAR HTTP {e.code} for {url}: {e.reason}"
            ) from e
        except (urllib.error.URLError, TimeoutError) as e:
            last_error = e
            logger.warning(
                "Network error for %s: %s, retrying (%d/%d)",
                url, e, attempt + 1, retries
            )
            time.sleep(2 ** attempt)
            continue

    raise ValueError(f"SEC EDGAR failed after {retries} retries: {last_error}")


# --- Text Processing ---


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# Patterns to strip from extraction windows before quantity parsing
_WINDOW_NOISE_RE = re.compile(
    r"EX-?\s*99\.\d+"       # EX-99.1, EX 99.2, EX99.1
    r"|Item\s+9\.01"        # Item 9.01
    r"|Exhibit\s+99\.\d+",  # Exhibit 99.1
    re.IGNORECASE,
)


def _clean_extraction_window(window: str) -> str:
    """Strip exhibit headers and item references that pollute number extraction."""
    return _WINDOW_NOISE_RE.sub("", window)


def _extract_token_quantity(text: str, token_symbol: str) -> Optional[int]:
    """Search filing text for a token quantity near a token name mention.

    Looks for patterns like "acquired 13,627 BTC", "holds 687,410 Bitcoin",
    "treasury of 4,167,768 ETH".

    Uses close-proximity search (50 chars) first, then falls back to a wider
    window (200 chars). Strips exhibit/item headers before parsing.

    Returns the extracted integer quantity, or None if not found.
    """
    aliases = TOKEN_ALIASES.get(token_symbol, (token_symbol,))

    for alias in aliases:
        # Search for the alias in text (case-sensitive for abbreviations,
        # case-insensitive for full names)
        if len(alias) <= 4:
            # Short alias (BTC, ETH) — match exact case, word boundary
            pattern = rf"\b{re.escape(alias)}\b"
        else:
            # Long alias (Bitcoin, Ethereum) — case-insensitive
            pattern = rf"(?i)\b{re.escape(alias)}\b"

        match = re.search(pattern, text)
        if not match:
            continue

        # Try close-proximity window first (50 chars each side)
        for window_size in (50, 200):
            start = max(0, match.start() - window_size)
            end = min(len(text), match.end() + window_size)
            window = _clean_extraction_window(text[start:end])

            quantity = _extract_quantity(window)
            if quantity is not None and quantity > 0:
                return quantity

    return None


# --- EDGAR API ---


def fetch_company_filings(
    cik: str, filing_types: tuple[str, ...] | None = None
) -> list[dict]:
    """Fetch recent filings from SEC EDGAR for a given CIK.

    Returns list of dicts with keys:
    {accessionNumber, filingDate, primaryDocument, form, items}
    """
    if filing_types is None:
        filing_types = FILING_TYPES_OF_INTEREST

    padded_cik = cik.lstrip("0").zfill(10)
    url = SEC_SUBMISSIONS_URL.format(cik=padded_cik)

    try:
        raw_json = _sec_request(url)
    except (ValueError, urllib.error.URLError) as e:
        logger.warning("Failed to fetch filings for CIK %s: %s", cik, e)
        return []

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        logger.warning("Invalid JSON from EDGAR for CIK %s: %s", cik, e)
        return []

    recent = data.get("filings", {}).get("recent", {})
    if not recent:
        return []

    # Parallel arrays in the EDGAR response
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    items_list = recent.get("items", [])

    cutoff = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    results: list[dict] = []

    for i in range(len(forms)):
        if forms[i] not in filing_types:
            continue
        if i >= len(dates) or dates[i] < cutoff:
            continue

        filing = {
            "accessionNumber": accessions[i] if i < len(accessions) else "",
            "filingDate": dates[i],
            "primaryDocument": primary_docs[i] if i < len(primary_docs) else "",
            "form": forms[i],
            "items": items_list[i] if i < len(items_list) else "",
        }
        results.append(filing)

    return results


def fetch_filing_text(cik: str, accession_number: str, primary_doc: str) -> str:
    """Fetch the text content of an SEC filing document.

    Returns stripped plain text. Returns empty string on failure.
    """
    cik_num = cik.lstrip("0")
    # EDGAR URL uses accession number without dashes in the path
    accession_path = accession_number.replace("-", "")
    url = SEC_ARCHIVES_URL.format(
        cik_num=cik_num, accession=accession_path, doc=primary_doc
    )

    try:
        html = _sec_request(url)
    except (ValueError, urllib.error.URLError) as e:
        logger.warning(
            "Failed to fetch filing %s for CIK %s: %s",
            accession_number, cik, e,
        )
        return ""

    return _strip_html(html)


# --- Exhibit Fetching ---


# Regex to find exhibit filenames in EDGAR filing directory pages
# Matches: ex99-1.htm, ex-99-1.htm, exhibit99.htm, ex99_1.htm,
# pressrelease.htm, item9_01.htm, and similar patterns
_EXHIBIT_FILENAME_RE = re.compile(
    r'href="([^"]*(?:'
    r'ex\s*-?\s*99'          # ex99, ex-99, ex 99
    r'|exhibit\s*99'         # exhibit99
    r'|pressrelease'         # pressrelease.htm
    r'|press[\-_]?release'   # press-release.htm, press_release.htm
    r'|item9'                # item9_01.htm (Item 9.01 exhibits)
    r')[^"]*\.htm[l]?)"',
    re.IGNORECASE,
)


def fetch_exhibit_docs(cik: str, accession_number: str) -> list[str]:
    """Fetch the EDGAR filing directory and return EX-99.* exhibit filenames.

    Returns a list of exhibit document filenames (e.g., ["ex99-1.htm"]).
    Returns empty list on failure or if no exhibits found.
    """
    cik_num = cik.lstrip("0")
    accession_path = accession_number.replace("-", "")
    url = SEC_FILING_DIR_URL.format(cik_num=cik_num, accession=accession_path)

    try:
        html = _sec_request(url)
    except (ValueError, urllib.error.URLError) as e:
        logger.warning(
            "Failed to fetch filing directory for CIK %s accession %s: %s",
            cik, accession_number, e,
        )
        return []

    # Parse exhibit filenames from the directory listing
    raw_exhibits = _EXHIBIT_FILENAME_RE.findall(html)
    # Strip path prefixes — EDGAR hrefs can be absolute paths like
    # "/Archives/edgar/data/123/000.../ex99-1.htm" but we only need
    # the filename since fetch_filing_text builds the full URL.
    exhibits = []
    for ex in raw_exhibits:
        # Extract just the filename from any path
        if "/" in ex:
            ex = ex.rsplit("/", 1)[-1]
        exhibits.append(ex)
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for ex in exhibits:
        if ex not in seen:
            seen.add(ex)
            unique.append(ex)

    if unique:
        logger.debug(
            "Found %d exhibit(s) for %s: %s",
            len(unique), accession_number, unique,
        )
    return unique


def _get_filing_text_with_exhibits(
    cik: str,
    accession_number: str,
    primary_doc: str,
    token_symbol: str,
) -> tuple[str, str]:
    """Try primaryDocument first; if no token data found, scan EX-99 exhibits.

    Returns (text, source_doc_filename) tuple.
    Returns ("", "") if no document contains token data.
    """
    # Try primary document first
    text = fetch_filing_text(cik, accession_number, primary_doc)
    if text:
        quantity = _extract_token_quantity(text, token_symbol)
        if quantity is not None:
            return text, primary_doc

    # Primary doc didn't have token data — try exhibits
    logger.debug(
        "No %s data in primary doc %s, scanning exhibits for %s",
        token_symbol, primary_doc, accession_number,
    )
    exhibits = fetch_exhibit_docs(cik, accession_number)

    for exhibit_doc in exhibits:
        exhibit_text = fetch_filing_text(cik, accession_number, exhibit_doc)
        if not exhibit_text:
            continue

        quantity = _extract_token_quantity(exhibit_text, token_symbol)
        if quantity is not None:
            logger.info(
                "Found %s data in exhibit %s (not primary doc %s)",
                token_symbol, exhibit_doc, primary_doc,
            )
            return exhibit_text, exhibit_doc

    # Nothing found in primary or exhibits
    return text or "", primary_doc


# --- Main Entry Point ---


def _describe_filing_items(items: str, form: str) -> str:
    """Generate a human-readable note for a filing based on its items field."""
    item_descriptions = {
        "1.01": "Entry into Material Agreement",
        "2.02": "Results of Operations (Earnings)",
        "2.05": "Costs Associated with Exit",
        "5.02": "Departure/Election of Officers",
        "5.07": "Submission of Matters to Shareholder Vote",
        "7.01": "Regulation FD Disclosure",
        "8.01": "Other Events",
        "9.01": "Financial Statements and Exhibits",
    }
    if not items:
        return f"{form} filing"

    parts = []
    for item in items.split(","):
        item = item.strip()
        if item in item_descriptions:
            parts.append(f"Item {item} - {item_descriptions[item]}")
        elif item:
            parts.append(f"Item {item}")
    return f"{form}: {'; '.join(parts)}" if parts else f"{form} filing"


def build_updates(data: dict) -> list[ScrapedUpdate]:
    """Check all companies for recent EDGAR filings and build ScrapedUpdates.

    Reads companies from the data dict (same structure as data.json).
    Skips companies without CIK numbers.

    Now tracks ALL 8-K filings (not just those with token quantities),
    so that regulatory activity is visible even when no holdings data
    can be extracted.
    """
    updates: list[ScrapedUpdate] = []
    companies = data.get("companies", {})

    for token_group, company_list in companies.items():
        for company in company_list:
            ticker = company.get("ticker", "")
            cik = company.get("cik", "")
            name = company.get("name", "")

            if not cik:
                logger.debug("Skipping %s: no CIK", ticker)
                continue

            logger.info("Checking EDGAR for %s (%s) CIK %s", ticker, name, cik)

            filings = fetch_company_filings(cik)
            if not filings:
                logger.debug("No recent 8-K filings for %s", ticker)
                continue

            logger.info("Found %d recent 8-K filing(s) for %s", len(filings), ticker)

            for filing in filings:
                text, source_doc = _get_filing_text_with_exhibits(
                    cik,
                    filing["accessionNumber"],
                    filing["primaryDocument"],
                    token_group,
                )

                source_url = SEC_ARCHIVES_URL.format(
                    cik_num=cik.lstrip("0"),
                    accession=filing["accessionNumber"].replace("-", ""),
                    doc=source_doc,
                )

                quantity = None
                if text:
                    quantity = _extract_token_quantity(text, token_group)

                if quantity is not None:
                    context = text[:500]
                    update = ScrapedUpdate(
                        ticker=ticker,
                        token=token_group,
                        new_value=quantity,
                        context_text=context,
                        source_url=source_url,
                        source_type="sec_edgar",
                        items=filing.get("items", ""),
                        filing_form=filing.get("form", ""),
                    )
                    updates.append(update)
                    logger.info(
                        "Extracted %s update: %s = %d %s from filing %s",
                        ticker, ticker, quantity, token_group,
                        filing["accessionNumber"],
                    )
                else:
                    # No token quantity found, but still record the filing
                    # so it appears in the filing feed
                    note = _describe_filing_items(
                        filing.get("items", ""), filing.get("form", "8-K")
                    )
                    update = ScrapedUpdate(
                        ticker=ticker,
                        token=token_group,
                        new_value=company.get("tokens", 0),  # Keep current value
                        context_text=note,
                        source_url=source_url,
                        source_type="sec_edgar",
                        items=filing.get("items", ""),
                        filing_form=filing.get("form", ""),
                    )
                    updates.append(update)
                    logger.info(
                        "Recorded %s filing without token data: %s (%s)",
                        ticker, filing["accessionNumber"], note,
                    )

    logger.info("Built %d update(s) from EDGAR filings", len(updates))
    return updates
