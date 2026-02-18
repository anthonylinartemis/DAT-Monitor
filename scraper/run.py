"""CLI entry point for the DAT Monitor scraping engine.

Usage:
    python -m scraper.run [--dry-run] [--data-path PATH] [--history-path PATH]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from scraper import fetcher, ir_scraper, parser, website_scrapers
from scraper.config import DATA_JSON_PATH, HOLDINGS_HISTORY_PATH
from scraper.updater import (
    apply_enrichments,
    load_data,
    run_batch,
    save_data,
    stamp_last_updated,
)


def main(argv: list[str] | None = None) -> int:
    """Run the scraping engine. Returns 0 on success, 1 on errors."""
    args = _parse_args(argv)
    _configure_logging(verbose=args.dry_run)

    logger = logging.getLogger(__name__)
    data_path = Path(args.data_path)
    history_path = Path(args.history_path)

    logger.info("=== DAT Monitor Refresh ===")
    logger.info("Data path: %s", data_path)
    logger.info("Dry run: %s", args.dry_run)

    # 1. Load current data
    try:
        data = load_data(data_path)
    except (FileNotFoundError, ValueError) as e:
        logger.error("Failed to load data.json: %s", e)
        return 1

    company_count = sum(len(v) for v in data.get("companies", {}).values())
    logger.info("Loaded %d companies across %d token groups",
                company_count, len(data.get("companies", {})))

    # 2. Fetch updates from all sources
    updates = []
    enrichments: dict[str, dict] = {}

    # 2a. SEC EDGAR
    logger.info("Fetching recent filings from SEC EDGAR...")
    try:
        edgar_updates = fetcher.build_updates(data)
        updates.extend(edgar_updates)
        logger.info("EDGAR: %d potential update(s)", len(edgar_updates))
    except Exception:
        logger.exception("Failed during EDGAR fetch")

    # 2b. Website scrapers (Metaplanet, etc.)
    logger.info("Running website scrapers...")
    try:
        web_updates, web_enrichments = website_scrapers.build_website_updates(data)
        # Source priority: EDGAR updates take precedence over website updates.
        # If EDGAR already produced an update for a ticker, skip the website
        # update for that same ticker to prevent stale website data from
        # overwriting fresh SEC filing data.
        edgar_tickers = {u.ticker for u in edgar_updates}
        filtered_web = [u for u in web_updates if u.ticker not in edgar_tickers]
        if len(filtered_web) < len(web_updates):
            skipped = len(web_updates) - len(filtered_web)
            logger.info("Source priority: skipped %d web update(s) for EDGAR-covered tickers: %s",
                         skipped, edgar_tickers & {u.ticker for u in web_updates})
        updates.extend(filtered_web)
        enrichments.update(web_enrichments)
        logger.info("Websites: %d update(s) (%d after EDGAR filter), %d enrichment(s)",
                     len(web_updates), len(filtered_web), len(web_enrichments))
    except Exception:
        logger.exception("Failed during website scraping")

    # 2c. IR page scraper (discovers press releases from company news pages)
    discovered_prs: list[dict] = []
    logger.info("Scraping IR pages for press releases...")
    try:
        new_prs = ir_scraper.scrape_all_ir_pages(data)
        existing_prs = data.get("discoveredPressReleases", [])
        discovered_prs = ir_scraper.merge_discovered_prs(existing_prs, new_prs)
        logger.info("IR Scraper: %d new PRs, %d total after merge",
                    len(new_prs), len(discovered_prs))
    except Exception:
        logger.exception("Failed during IR page scraping")

    logger.info("Total: %d potential update(s)", len(updates))

    if not updates and not enrichments and not discovered_prs:
        logger.info("No updates, enrichments, or press releases found. Done.")
        return 0

    # 3. Classify and log each update (useful for dry-run)
    for update in updates:
        result = parser.classify(update.context_text)
        logger.info(
            "  %s (%s): %d tokens, classified=%s, keywords=%s",
            update.ticker, update.token, update.new_value,
            result.classification.value, result.confidence_keywords,
        )

    if enrichments:
        logger.info("Enrichments queued for: %s", ", ".join(enrichments.keys()))

    if args.dry_run:
        logger.info("Dry run — no changes written.")
        return 0

    # 4. Run pipeline for token updates
    summary = {"applied": 0, "skipped_override": 0, "skipped_buyback": 0,
               "skipped_oscillation": 0, "skipped_unknown": 0,
               "skipped_not_found": 0, "errors": 0}

    if updates:
        logger.info("Processing updates through pipeline...")
        summary = run_batch(updates, data_path, history_path)

    # 5. Apply enrichments (analytics data from website scrapers)
    if enrichments or discovered_prs:
        logger.info("Applying enrichments to data.json...")
        data = load_data(data_path)
        if enrichments:
            data = apply_enrichments(data, enrichments)
        if discovered_prs:
            data["discoveredPressReleases"] = discovered_prs
            logger.info("Saved %d discovered press releases", len(discovered_prs))
        stamp_last_updated(data)
        save_data(data, data_path)
        if enrichments:
            logger.info("Enrichments applied for: %s", ", ".join(enrichments.keys()))

    logger.info("=== Summary ===")
    logger.info("  Applied:             %d", summary["applied"])
    logger.info("  Skipped (override):  %d", summary["skipped_override"])
    logger.info("  Skipped (buyback):   %d", summary["skipped_buyback"])
    logger.info("  Skipped (oscillation):%d", summary["skipped_oscillation"])
    logger.info("  Skipped (unknown):   %d", summary["skipped_unknown"])
    logger.info("  Skipped (not found): %d", summary["skipped_not_found"])
    logger.info("  Enrichments:         %d", len(enrichments))
    logger.info("  Discovered PRs:      %d", len(discovered_prs))
    logger.info("  Errors:              %d", summary["errors"])

    # 6. Staleness check — warn about companies that haven't updated in >14 days
    _check_stale_companies(data_path)

    if summary["errors"] > 0:
        return 1
    return 0


STALENESS_THRESHOLD_DAYS = 14


def _check_stale_companies(data_path: Path) -> None:
    """Log warnings for any company with lastUpdate older than threshold."""
    logger = logging.getLogger(__name__)
    try:
        data = load_data(data_path)
    except Exception:
        return

    cutoff = (date.today() - timedelta(days=STALENESS_THRESHOLD_DAYS)).isoformat()
    stale: list[tuple[str, str, str]] = []  # (ticker, token, lastUpdate)

    for token_group, company_list in data.get("companies", {}).items():
        for company in company_list:
            ticker = company.get("ticker", "")
            last_update = company.get("lastUpdate", "")
            if last_update and last_update < cutoff:
                stale.append((ticker, token_group, last_update))

    if stale:
        logger.warning("=== STALE DATA ALERT (%d companies) ===", len(stale))
        for ticker, token, last_update in sorted(stale, key=lambda x: x[2]):
            days_old = (date.today() - date.fromisoformat(last_update)).days
            logger.warning(
                "  %s (%s): last updated %s (%d days ago)",
                ticker, token, last_update, days_old,
            )
    else:
        logger.info("No stale companies (all updated within %d days)", STALENESS_THRESHOLD_DAYS)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="DAT Monitor — fetch SEC EDGAR filings and update data.json"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and classify but don't write changes",
    )
    p.add_argument(
        "--data-path",
        default=str(DATA_JSON_PATH),
        help=f"Path to data.json (default: {DATA_JSON_PATH})",
    )
    p.add_argument(
        "--history-path",
        default=str(HOLDINGS_HISTORY_PATH),
        help=f"Path to holdings history (default: {HOLDINGS_HISTORY_PATH})",
    )
    return p.parse_args(argv)


def _configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


if __name__ == "__main__":
    sys.exit(main())
