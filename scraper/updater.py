"""Orchestrator: load data.json → pipeline → save data.json.

Wires parser + state_guard together. Handles all I/O for the scraping
engine while keeping the dashboard contract intact.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

from scraper import parser, state_guard
from scraper.config import DATA_JSON_PATH, HoldingClassification, VALID_TOKENS
from scraper.models import ScrapedUpdate

logger = logging.getLogger(__name__)


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
    if source_url:
        company["alertUrl"] = source_url
        company["alertDate"] = today
        company["alertNote"] = scraped.context_text[:100] if scraped.context_text else ""
        company["lastSecUpdate"] = today

    # Append to filings[] for grouped filing history
    if scraped.context_text:
        filing_entry = {
            "url": source_url,
            "date": today,
            "note": scraped.context_text[:100],
        }
        filings = company.get("filings", [])
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
        "errors": 0,
    }

    data = load_data(data_path)
    history = state_guard.load_history(history_path)
    dirty = False

    for update in updates:
        try:
            data, history, was_applied = process_update(update, data, history)

            if was_applied:
                summary["applied"] += 1
                dirty = True
            # Determine skip reason from process_update's logging behavior
            # by re-checking conditions (lightweight since no I/O)
            elif not was_applied:
                _classify_skip(update, data, history, summary)

        except Exception:
            logger.exception("Error processing update for %s", update.ticker)
            summary["errors"] += 1

    if dirty:
        save_data(data, data_path)
        state_guard.save_history(history, history_path)

    return summary


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
