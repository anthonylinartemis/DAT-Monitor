"""Earnings tracker: detect earnings releases, 10-Q, and 10-K filings from SEC EDGAR.

Scans all CIK-tracked companies for:
- 8-K filings with Item 2.02 (Results of Operations = earnings release)
- 10-Q filings (quarterly reports)
- 10-K filings (annual reports)

Extracts exhibit URLs (EX-99.1 = press release / slide deck) from EDGAR
filing directories. Produces earnings event dicts for data.json.
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta

from scraper.fetcher import (
    ALL_FILING_TYPES_OF_INTEREST,
    SEC_ARCHIVES_URL,
    fetch_company_filings,
    fetch_exhibit_docs,
)

logger = logging.getLogger(__name__)

# How far back to scan for earnings events (90 days)
EARNINGS_LOOKBACK_DAYS = 90

# 8-K items that indicate earnings
EARNINGS_ITEMS = {"2.02"}

# Fiscal year detection: maps month of filing to likely quarter
# This is a rough heuristic — companies with non-calendar fiscal years
# will need manual correction, but it's better than nothing.
_MONTH_TO_QUARTER_CALENDAR: dict[int, str] = {
    1: "Q4",  # Jan: reporting Q4 of prior year
    2: "Q4",
    3: "Q1",  # Mar: reporting Q1 (Jan-Mar for calendar FY)
    4: "Q1",
    5: "Q1",
    6: "Q2",
    7: "Q2",
    8: "Q2",
    9: "Q3",
    10: "Q3",
    11: "Q3",
    12: "Q4",
}


def _infer_quarter(filing_date: str, form: str) -> str:
    """Infer fiscal quarter from filing date and form type.

    Returns a string like "Q1 FY2026" or "FY2025" for 10-K.
    This is a best-effort heuristic for calendar-year companies.
    """
    try:
        d = date.fromisoformat(filing_date)
    except (ValueError, TypeError):
        return ""

    month = d.month
    year = d.year

    if form in ("10-K", "10-K/A"):
        # Annual report — typically filed 60-90 days after fiscal year end
        # For calendar-year companies, Q4 10-K is filed in Feb-Mar
        fy_year = year if month >= 4 else year - 1
        return f"FY{fy_year}"

    quarter = _MONTH_TO_QUARTER_CALENDAR.get(month, "")
    if not quarter:
        return ""

    # For Q4 reported in Jan/Feb, the fiscal year is the previous year
    fy_year = year if month >= 3 else year - 1
    return f"{quarter} FY{fy_year}"


def _build_filing_url(cik: str, accession: str, doc: str) -> str:
    """Build a direct URL to an SEC filing document."""
    return SEC_ARCHIVES_URL.format(
        cik_num=cik.lstrip("0"),
        accession=accession.replace("-", ""),
        doc=doc,
    )


def _build_filing_index_url(cik: str, accession: str) -> str:
    """Build a URL to the SEC filing index page."""
    cik_num = cik.lstrip("0")
    accession_path = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{accession_path}/"


def build_earnings_events(data: dict) -> list[dict]:
    """Scan all CIK-tracked companies for earnings-related filings.

    Returns a list of earnings event dicts suitable for data.json["earnings"].
    Each event includes:
    - ticker, name, token
    - type: "8-K" (earnings), "10-Q", "10-K"
    - items: EDGAR items field (e.g., "2.02,9.01")
    - date: filing date
    - quarter: inferred fiscal quarter
    - filingUrl: direct URL to the filing
    - pressReleaseUrl: URL to EX-99.1 exhibit (if found)
    - accession: accession number
    - status: "reported"
    """
    events: list[dict] = []
    companies = data.get("companies", {})

    for token_group, company_list in companies.items():
        for company in company_list:
            ticker = company.get("ticker", "")
            cik = company.get("cik", "")
            name = company.get("name", "")

            if not cik:
                continue

            logger.info("Earnings scan: %s (%s) CIK %s", ticker, name, cik)

            # Fetch all filing types (8-K, 10-Q, 10-K)
            filings = fetch_company_filings(
                cik, filing_types=ALL_FILING_TYPES_OF_INTEREST
            )

            if not filings:
                logger.debug("No recent filings for %s", ticker)
                continue

            # Filter to earnings-relevant filings within lookback
            cutoff = (
                date.today() - timedelta(days=EARNINGS_LOOKBACK_DAYS)
            ).isoformat()

            for filing in filings:
                filing_date = filing.get("filingDate", "")
                if filing_date < cutoff:
                    continue

                form = filing.get("form", "")
                items = filing.get("items", "")
                accession = filing.get("accessionNumber", "")
                primary_doc = filing.get("primaryDocument", "")

                # Determine if this is an earnings-relevant filing
                is_earnings_8k = False
                if form in ("8-K", "8-K/A") and items:
                    item_set = {i.strip() for i in items.split(",")}
                    is_earnings_8k = bool(item_set & EARNINGS_ITEMS)

                is_quarterly = form in ("10-Q",)
                is_annual = form in ("10-K", "10-K/A")

                if not (is_earnings_8k or is_quarterly or is_annual):
                    continue

                # Build URLs
                filing_url = _build_filing_url(cik, accession, primary_doc)
                quarter = _infer_quarter(filing_date, form)

                # Try to find press release exhibit (EX-99.1)
                press_release_url = ""
                if is_earnings_8k:
                    try:
                        exhibits = fetch_exhibit_docs(cik, accession)
                        if exhibits:
                            # First exhibit is typically the press release
                            press_release_url = _build_filing_url(
                                cik, accession, exhibits[0]
                            )
                    except Exception as e:
                        logger.debug(
                            "Failed to fetch exhibits for %s %s: %s",
                            ticker, accession, e,
                        )

                event = {
                    "ticker": ticker,
                    "name": name,
                    "token": token_group,
                    "type": form,
                    "items": items,
                    "date": filing_date,
                    "quarter": quarter,
                    "filingUrl": filing_url,
                    "indexUrl": _build_filing_index_url(cik, accession),
                    "accession": accession,
                    "status": "reported",
                }
                if press_release_url:
                    event["pressReleaseUrl"] = press_release_url

                events.append(event)

                event_type = "earnings 8-K" if is_earnings_8k else form
                logger.info(
                    "Earnings: %s %s on %s (%s) [%s]",
                    ticker, event_type, filing_date, quarter, accession,
                )

    # Sort by date descending (most recent first)
    events.sort(key=lambda e: e.get("date", ""), reverse=True)

    logger.info("Found %d earnings event(s) across all companies", len(events))
    return events
