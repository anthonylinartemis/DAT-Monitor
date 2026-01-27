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

# SEC requires a descriptive User-Agent with contact info
USER_AGENT = "DAT-Monitor-Bot/1.0 (dat-monitor-github-action)"

# Filing types that announce crypto acquisitions
FILING_TYPES_OF_INTEREST: tuple[str, ...] = ("8-K", "8-K/A")

# Only check filings from the last week
LOOKBACK_DAYS = 7

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


def _sec_request(url: str) -> str:
    """Fetch a URL from SEC EDGAR with proper User-Agent and rate limiting.

    Raises urllib.error.URLError on network failures.
    Raises ValueError on non-200 responses.
    """
    global _last_request_time

    # Rate limit: wait if needed
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _REQUEST_DELAY_SECONDS:
        time.sleep(_REQUEST_DELAY_SECONDS - elapsed)

    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
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
        raise ValueError(
            f"SEC EDGAR HTTP {e.code} for {url}: {e.reason}"
        ) from e


# --- Text Processing ---


def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_token_quantity(text: str, token_symbol: str) -> Optional[int]:
    """Search filing text for a token quantity near a token name mention.

    Looks for patterns like "acquired 13,627 BTC", "holds 687,410 Bitcoin",
    "treasury of 4,167,768 ETH".

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

        # Extract a window of text around the match (200 chars each side)
        start = max(0, match.start() - 200)
        end = min(len(text), match.end() + 200)
        window = text[start:end]

        quantity = _extract_quantity(window)
        if quantity is not None and quantity > 0:
            return quantity

    return None


# --- EDGAR API ---


def fetch_company_filings(cik: str) -> list[dict]:
    """Fetch recent 8-K filings from SEC EDGAR for a given CIK.

    Returns list of dicts with keys:
    {accessionNumber, filingDate, primaryDocument, form}
    """
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

    cutoff = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    results: list[dict] = []

    for i in range(len(forms)):
        if forms[i] not in FILING_TYPES_OF_INTEREST:
            continue
        if i >= len(dates) or dates[i] < cutoff:
            continue

        filing = {
            "accessionNumber": accessions[i] if i < len(accessions) else "",
            "filingDate": dates[i],
            "primaryDocument": primary_docs[i] if i < len(primary_docs) else "",
            "form": forms[i],
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


# --- Main Entry Point ---


def build_updates(data: dict) -> list[ScrapedUpdate]:
    """Check all companies for recent EDGAR filings and build ScrapedUpdates.

    Reads companies from the data dict (same structure as data.json).
    Skips companies without CIK numbers.
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
                text = fetch_filing_text(
                    cik,
                    filing["accessionNumber"],
                    filing["primaryDocument"],
                )
                if not text:
                    continue

                quantity = _extract_token_quantity(text, token_group)
                if quantity is None:
                    logger.debug(
                        "No %s quantity found in %s filing %s",
                        token_group, ticker, filing["accessionNumber"],
                    )
                    continue

                # Use a context snippet (first 500 chars of filing text)
                context = text[:500]
                source_url = SEC_ARCHIVES_URL.format(
                    cik_num=cik.lstrip("0"),
                    accession=filing["accessionNumber"].replace("-", ""),
                    doc=filing["primaryDocument"],
                )

                update = ScrapedUpdate(
                    ticker=ticker,
                    token=token_group,
                    new_value=quantity,
                    context_text=context,
                    source_url=source_url,
                )
                updates.append(update)
                logger.info(
                    "Extracted %s update: %s = %d %s from filing %s",
                    ticker, ticker, quantity, token_group,
                    filing["accessionNumber"],
                )

    logger.info("Built %d update(s) from EDGAR filings", len(updates))
    return updates
