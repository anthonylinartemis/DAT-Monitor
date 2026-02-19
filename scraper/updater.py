"""Orchestrator: load data.json → pipeline → save data.json.

Wires parser + state_guard together. Handles all I/O for the scraping
engine while keeping the dashboard contract intact.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from scraper import parser, state_guard
from scraper.config import DATA_JSON_PATH, HoldingClassification, VALID_TOKENS
from scraper.models import ScrapedUpdate

logger = logging.getLogger(__name__)


def stamp_last_updated(data: dict) -> dict:
    """Set lastUpdated and lastUpdatedDisplay to the current time in ET."""
    et = ZoneInfo("America/New_York")
    now = datetime.now(et)
    data["lastUpdated"] = now.isoformat()
    data["lastUpdatedDisplay"] = now.strftime("%b %d, %Y %I:%M %p ET")
    return data


def load_data(path: Optional[Path] = None) -> dict:
    """Load data.json and return the parsed dict."""
    path = path or DATA_JSON_PATH
    with open(path, "r") as f:
        return json.load(f)


def save_data(data: dict, path: Optional[Path] = None) -> None:
    """Atomic write of data.json: temp file → os.replace()."""
    path = path or DATA_JSON_PATH
    serialized = json.dumps(data, indent=2) + "\n"

    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", prefix=".data_"
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(serialized)
        os.replace(tmp_path, str(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _recalculate_totals(companies: dict[str, list[dict]]) -> dict[str, int]:
    """Sum token counts per group. Returns {token_symbol: total}."""
    totals: dict[str, int] = {}
    for token_group, company_list in companies.items():
        totals[token_group] = sum(c.get("tokens", 0) for c in company_list)
    return totals


def _find_company(
    companies: dict[str, list[dict]], ticker: str, token: str
) -> Optional[tuple[dict, int, str]]:
    """Find a company by ticker within the specified token group.

    Returns (company_dict, index_in_list, token_group) or None.
    """
    if token not in companies:
        return None

    for idx, company in enumerate(companies[token]):
        if company.get("ticker") == ticker:
            return company, idx, token

    return None


def process_update(
    scraped: ScrapedUpdate,
    data: dict,
    history: dict,
) -> tuple[dict, dict, bool]:
    """Full pipeline for a single scraped update.

    Returns (updated_data, updated_history, was_applied).

    Steps:
    1. Find company → skip if not found
    2. Check manual_override → skip if True
    3. Classify context_text → skip if SHARE_BUYBACK or UNKNOWN
    4. Check oscillation → skip if suppressed
    5. Apply: update tokens, compute delta, set lastUpdate, recalc totals,
       prepend to recentChanges (capped at 10)
    6. Record in history
    """
    companies = data.get("companies", {})

    # 1. Find the company
    result = _find_company(companies, scraped.ticker, scraped.token)
    if result is None:
        logger.warning(
            "Ticker %s not found in %s group", scraped.ticker, scraped.token
        )
        return data, history, False

    company, idx, token_group = result

    # 2. Check manual_override
    if company.get("manual_override", False):
        logger.info(
            "Skipping %s: manual_override is set", scraped.ticker
        )
        return data, history, False

    # 3. Classify
    parse_result = parser.classify(scraped.context_text)

    if parse_result.classification == HoldingClassification.SHARE_BUYBACK:
        logger.info(
            "Skipping %s: classified as SHARE_BUYBACK (keywords: %s)",
            scraped.ticker,
            parse_result.confidence_keywords,
        )
        return data, history, False

    if parse_result.classification == HoldingClassification.UNKNOWN:
        logger.warning(
            "Skipping %s: classification UNKNOWN for text: %.100s",
            scraped.ticker,
            scraped.context_text,
        )
        return data, history, False

    # 4. Oscillation check
    should_apply, reason = state_guard.should_update(scraped, history)
    if not should_apply:
        logger.info(
            "Skipping %s: %s", scraped.ticker, reason
        )
        return data, history, False

    # 5. Apply update
    today = date.today().isoformat()
    old_value = company.get("tokens", 0)
    delta = scraped.new_value - old_value

    company["tokens"] = scraped.new_value
    company["change"] = delta
    company["lastUpdate"] = today

    # Update alert fields for the dashboard
    source_url = getattr(scraped, "source_url", "") or ""
    source_type = getattr(scraped, "source_type", "") or ""
    if source_url:
        company["alertUrl"] = source_url
        company["alertDate"] = today
        company["alertNote"] = scraped.context_text[:100] if scraped.context_text else ""
        if source_type:
            company["alertSource"] = source_type
        if source_type == "sec_edgar":
            company["lastSecUpdate"] = today

    # Append to filings[] for grouped filing history
    if scraped.context_text:
        filing_entry = {
            "url": source_url,
            "date": today,
            "note": scraped.context_text[:100],
            "type": "sec_filing" if source_type == "sec_edgar" else "dashboard_update",
        }
        items = getattr(scraped, "items", "") or ""
        if items:
            filing_entry["items"] = items
        filing_form = getattr(scraped, "filing_form", "") or ""
        if filing_form:
            filing_entry["form"] = filing_form
        filings = company.get("filings", [])
        # Deduplicate: don't add if same URL already exists
        existing_urls = {f.get("url") for f in filings}
        if source_url not in existing_urls:
            filings.insert(0, filing_entry)
            company["filings"] = filings[:20]  # Cap at 20 entries

    # Recalculate totals
    data["totals"] = _recalculate_totals(companies)

    # Prepend to recentChanges (capped at 10)
    recent_entry = {
        "ticker": scraped.ticker,
        "token": scraped.token,
        "date": today,
        "tokens": scraped.new_value,
        "change": delta,
        "summary": scraped.context_text[:200],
    }
    recent_changes = data.get("recentChanges", [])
    data["recentChanges"] = [recent_entry] + recent_changes[:9]

    # 6. Record in history
    history = state_guard.record_update(scraped, history, today)

    logger.info(
        "Applied %s: %d → %d (delta %+d)",
        scraped.ticker,
        old_value,
        scraped.new_value,
        delta,
    )

    return data, history, True


def record_filing_only(
    scraped: ScrapedUpdate,
    data: dict,
) -> tuple[dict, bool]:
    """Record a filing in a company's filings[] without updating token counts.

    Used for SEC filings where no token quantity was extracted, but we still
    want to surface the filing in the Filing Feed. Bypasses classification
    and oscillation checks since there's no token change.

    Returns (updated_data, was_recorded).
    """
    companies = data.get("companies", {})
    result = _find_company(companies, scraped.ticker, scraped.token)
    if result is None:
        return data, False

    company, idx, token_group = result
    today = date.today().isoformat()
    source_url = getattr(scraped, "source_url", "") or ""
    source_type = getattr(scraped, "source_type", "") or ""
    items = getattr(scraped, "items", "") or ""
    filing_form = getattr(scraped, "filing_form", "") or ""

    # Build filing entry
    filing_entry = {
        "url": source_url,
        "date": today,
        "note": scraped.context_text[:100] if scraped.context_text else "",
        "type": "sec_filing",
    }
    if items:
        filing_entry["items"] = items
    if filing_form:
        filing_entry["form"] = filing_form

    # Deduplicate
    filings = company.get("filings", [])
    existing_urls = {f.get("url") for f in filings}
    if source_url and source_url in existing_urls:
        return data, False

    filings.insert(0, filing_entry)
    company["filings"] = filings[:20]

    # Update alert fields so it shows in the filing feed
    if source_url:
        company["alertUrl"] = source_url
        company["alertDate"] = today
        company["alertNote"] = scraped.context_text[:100] if scraped.context_text else ""
        if source_type:
            company["alertSource"] = source_type
        if source_type == "sec_edgar":
            company["lastSecUpdate"] = today

    logger.info(
        "Recorded filing-only for %s: %s (%s)",
        scraped.ticker, filing_form or "8-K", items,
    )

    return data, True


def run_batch(
    updates: list[ScrapedUpdate],
    data_path: Optional[Path] = None,
    history_path: Optional[Path] = None,
) -> dict[str, int]:
    """Load files, iterate updates, save if dirty.

    Returns summary counts:
    {applied, skipped_override, skipped_buyback, skipped_oscillation,
     skipped_unknown, errors}
    """
    data_path = data_path or DATA_JSON_PATH

    summary = {
        "applied": 0,
        "skipped_override": 0,
        "skipped_buyback": 0,
        "skipped_oscillation": 0,
        "skipped_unknown": 0,
        "skipped_not_found": 0,
        "filings_recorded": 0,
        "errors": 0,
    }

    data = load_data(data_path)
    history = state_guard.load_history(history_path)
    dirty = False

    for update in updates:
        try:
            # Check if this is a filing-only update (SEC filing without token data).
            # These have filing_form set and new_value == current company tokens.
            is_filing_only = _is_filing_only_update(update, data)

            if is_filing_only:
                data, was_recorded = record_filing_only(update, data)
                if was_recorded:
                    summary["filings_recorded"] += 1
                    dirty = True
                continue

            data, history, was_applied = process_update(update, data, history)

            if was_applied:
                summary["applied"] += 1
                dirty = True
            elif not was_applied:
                _classify_skip(update, data, history, summary)

        except Exception:
            logger.exception("Error processing update for %s", update.ticker)
            summary["errors"] += 1

    if dirty:
        stamp_last_updated(data)
        save_data(data, data_path)
        state_guard.save_history(history, history_path)

    return summary


def _is_filing_only_update(update: ScrapedUpdate, data: dict) -> bool:
    """Detect if a ScrapedUpdate is a filing-only entry (no token change).

    Filing-only entries are created by the EDGAR fetcher when an 8-K filing
    is found but no token quantity could be extracted from the text.
    """
    filing_form = getattr(update, "filing_form", "") or ""
    source_type = getattr(update, "source_type", "") or ""
    if not filing_form or source_type != "sec_edgar":
        return False

    # Check if new_value matches the company's current token count
    companies = data.get("companies", {})
    result = _find_company(companies, update.ticker, update.token)
    if result is None:
        return False

    company, _, _ = result
    return update.new_value == company.get("tokens", 0)


def _classify_skip(
    update: ScrapedUpdate,
    data: dict,
    history: dict,
    summary: dict[str, int],
) -> None:
    """Classify why an update was skipped and increment the right counter."""
    companies = data.get("companies", {})
    result = _find_company(companies, update.ticker, update.token)

    if result is None:
        summary["skipped_not_found"] += 1
        return

    company, _, _ = result

    if company.get("manual_override", False):
        summary["skipped_override"] += 1
        return

    parse_result = parser.classify(update.context_text)

    if parse_result.classification == HoldingClassification.SHARE_BUYBACK:
        summary["skipped_buyback"] += 1
        return

    if parse_result.classification == HoldingClassification.UNKNOWN:
        summary["skipped_unknown"] += 1
        return

    # Must be oscillation
    summary["skipped_oscillation"] += 1


def apply_enrichments(data: dict, enrichments: dict[str, dict]) -> dict:
    """Merge analytics enrichment data into company entries.

    enrichments: {ticker: analytics_dict} from website scrapers.
    Adds/updates the 'analytics' field on matching company entries.
    Dashboard ignores unknown keys, so this is backward compatible.
    """
    companies = data.get("companies", {})

    for ticker, analytics_dict in enrichments.items():
        found = False
        for token_group, company_list in companies.items():
            for company in company_list:
                if company.get("ticker") == ticker:
                    company["analytics"] = analytics_dict
                    found = True
                    break
            if found:
                break

        if not found:
            logger.warning(
                "Enrichment target %s not found in data.json", ticker
            )

    return data
