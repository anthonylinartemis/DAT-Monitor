"""SEC Agent: Link transaction source URLs to specific 8-K filings.

Fetches all 8-K filings for companies with CIK numbers and matches
transaction dates to the nearest filing, updating source URLs.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from scraper.fetcher import _sec_request, SEC_SUBMISSIONS_URL, SEC_ARCHIVES_URL
from scraper.models import FilingInfo

logger = logging.getLogger(__name__)

# Default lookback period for fetching 8-K filings (2 years)
DEFAULT_LOOKBACK_DAYS = 730

# Filing types to fetch
FILING_TYPES = ("8-K", "8-K/A")


def fetch_all_8k_filings(cik: str, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> list[FilingInfo]:
    """Fetch ALL 8-K filings for a CIK within the lookback period.

    Args:
        cik: SEC CIK number (with or without leading zeros)
        lookback_days: How far back to look for filings (default 2 years)

    Returns:
        List of FilingInfo objects sorted by filing_date descending
    """
    padded_cik = cik.lstrip("0").zfill(10)
    url = SEC_SUBMISSIONS_URL.format(cik=padded_cik)

    try:
        raw_json = _sec_request(url)
    except (ValueError, Exception) as e:
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

    cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    cik_num = cik.lstrip("0")
    results: list[FilingInfo] = []

    for i in range(len(forms)):
        if forms[i] not in FILING_TYPES:
            continue
        if i >= len(dates) or dates[i] < cutoff:
            continue

        accession = accessions[i] if i < len(accessions) else ""
        primary_doc = primary_docs[i] if i < len(primary_docs) else ""

        if not accession or not primary_doc:
            continue

        # Build SEC URL
        accession_path = accession.replace("-", "")
        filing_url = SEC_ARCHIVES_URL.format(
            cik_num=cik_num,
            accession=accession_path,
            doc=primary_doc,
        )

        filing = FilingInfo(
            accession_number=accession,
            filing_date=dates[i],
            primary_document=primary_doc,
            url=filing_url,
            cik=cik,
        )
        results.append(filing)

    # Sort by date descending (most recent first)
    results.sort(key=lambda f: f.filing_date, reverse=True)
    logger.info("Found %d 8-K filings for CIK %s", len(results), cik)
    return results


def match_transaction_to_filing(
    txn: dict,
    filings: list[FilingInfo],
    tolerance_days: int = 3,
) -> Optional[FilingInfo]:
    """Match a transaction date to the nearest 8-K filing.

    Prefers filings 1-3 days AFTER the transaction date, since companies
    typically file 8-Ks 1-2 business days after the acquisition.

    Args:
        txn: Transaction dict with 'date' key (YYYY-MM-DD format)
        filings: List of FilingInfo objects
        tolerance_days: Max days difference to consider a match

    Returns:
        Best matching FilingInfo, or None if no match found
    """
    txn_date_str = txn.get("date", "")
    if not txn_date_str:
        return None

    try:
        txn_date = datetime.strptime(txn_date_str, "%Y-%m-%d")
    except ValueError:
        return None

    best_match: Optional[FilingInfo] = None
    best_score = float("inf")

    for filing in filings:
        try:
            filing_date = datetime.strptime(filing.filing_date, "%Y-%m-%d")
        except ValueError:
            continue

        delta = (filing_date - txn_date).days

        # Skip filings outside tolerance window
        if abs(delta) > tolerance_days:
            continue

        # Scoring: prefer filings 1-2 days after transaction
        # Lower score = better match
        if delta >= 1 and delta <= 2:
            # Best case: filed 1-2 days after
            score = delta
        elif delta == 0:
            # Same day: okay but less common
            score = 3
        elif delta > 2:
            # Filed 3+ days after: acceptable
            score = delta + 1
        else:
            # Filed before transaction: unusual, penalize
            score = abs(delta) + 5

        if score < best_score:
            best_score = score
            best_match = filing

    return best_match


def enrich_transactions(data: dict, dry_run: bool = False) -> dict:
    """Update all transaction source URLs with SEC filing links.

    Args:
        data: Full data.json structure
        dry_run: If True, log changes but don't modify data

    Returns:
        Modified data dict (or original if dry_run)
    """
    companies = data.get("companies", {})
    total_updated = 0

    for token_group, company_list in companies.items():
        for company in company_list:
            ticker = company.get("ticker", "")
            cik = company.get("cik", "")
            transactions = company.get("transactions", [])

            if not cik or not transactions:
                continue

            logger.info("Processing %s (CIK %s) with %d transactions",
                       ticker, cik, len(transactions))

            # Fetch all 8-K filings for this company
            filings = fetch_all_8k_filings(cik)
            if not filings:
                logger.debug("No 8-K filings found for %s", ticker)
                continue

            # Match each transaction to a filing
            for txn in transactions:
                # Skip if source is already an SEC URL
                current_source = txn.get("source", "")
                if "sec.gov" in current_source:
                    continue

                match = match_transaction_to_filing(txn, filings)
                if match:
                    if dry_run:
                        logger.info(
                            "[DRY RUN] %s %s: would update source to %s",
                            ticker, txn.get("date", ""), match.url
                        )
                    else:
                        txn["source"] = match.url
                        total_updated += 1
                        logger.debug(
                            "%s %s: updated source to %s",
                            ticker, txn.get("date", ""), match.url
                        )

    logger.info("Total transactions updated: %d", total_updated)
    return data


def run_sec_agent(ticker: Optional[str] = None, dry_run: bool = False) -> None:
    """CLI entry point - run SEC agent for specific ticker or all.

    Args:
        ticker: Specific ticker to process, or None for all
        dry_run: If True, show what would change without modifying
    """
    data_path = Path(__file__).parent.parent / "data.json"

    if not data_path.exists():
        logger.error("data.json not found at %s", data_path)
        return

    with open(data_path, "r") as f:
        data = json.load(f)

    # If specific ticker requested, filter to just that company
    if ticker:
        filtered_companies = {}
        for token_group, company_list in data.get("companies", {}).items():
            matches = [c for c in company_list if c.get("ticker") == ticker]
            if matches:
                filtered_companies[token_group] = matches
                break

        if not filtered_companies:
            logger.error("Ticker %s not found in data.json", ticker)
            return

        data["companies"] = filtered_companies

    # Run enrichment
    enriched_data = enrich_transactions(data, dry_run=dry_run)

    if dry_run:
        logger.info("Dry run complete - no changes written")
        return

    # Reload full data and merge changes
    with open(data_path, "r") as f:
        full_data = json.load(f)

    # Merge enriched transactions back
    for token_group, company_list in enriched_data.get("companies", {}).items():
        full_list = full_data.get("companies", {}).get(token_group, [])
        for company in company_list:
            for i, full_company in enumerate(full_list):
                if full_company.get("ticker") == company.get("ticker"):
                    full_list[i]["transactions"] = company.get("transactions", [])
                    break

    # Write back atomically
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", dir=data_path.parent, delete=False
    ) as tmp:
        json.dump(full_data, tmp, indent=2)
        tmp_path = tmp.name

    os.replace(tmp_path, data_path)
    logger.info("Wrote updated data.json")


def main():
    """Command-line interface for SEC agent."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="SEC Agent: Link transaction sources to 8-K filings"
    )
    parser.add_argument(
        "--ticker", "-t",
        help="Process only this ticker (default: all companies with CIK)",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would change without modifying data.json",
    )

    args = parser.parse_args()
    run_sec_agent(ticker=args.ticker, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
