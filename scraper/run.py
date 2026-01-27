"""CLI entry point for the DAT Monitor scraping engine.

Usage:
    python -m scraper.run [--dry-run] [--data-path PATH] [--history-path PATH]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from scraper import fetcher, parser
from scraper.config import DATA_JSON_PATH, HOLDINGS_HISTORY_PATH
from scraper.updater import load_data, run_batch


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

    # 2. Fetch updates from SEC EDGAR
    logger.info("Fetching recent filings from SEC EDGAR...")
    try:
        updates = fetcher.build_updates(data)
    except Exception:
        logger.exception("Failed during EDGAR fetch")
        return 1

    logger.info("Found %d potential update(s)", len(updates))

    if not updates:
        logger.info("No updates found. Done.")
        return 0

    # 3. Classify and log each update (useful for dry-run)
    for update in updates:
        result = parser.classify(update.context_text)
        logger.info(
            "  %s (%s): %d tokens, classified=%s, keywords=%s",
            update.ticker, update.token, update.new_value,
            result.classification.value, result.confidence_keywords,
        )

    if args.dry_run:
        logger.info("Dry run — no changes written.")
        return 0

    # 4. Run through the pipeline
    logger.info("Processing updates through pipeline...")
    summary = run_batch(updates, data_path, history_path)

    logger.info("=== Summary ===")
    logger.info("  Applied:             %d", summary["applied"])
    logger.info("  Skipped (override):  %d", summary["skipped_override"])
    logger.info("  Skipped (buyback):   %d", summary["skipped_buyback"])
    logger.info("  Skipped (oscillation):%d", summary["skipped_oscillation"])
    logger.info("  Skipped (unknown):   %d", summary["skipped_unknown"])
    logger.info("  Skipped (not found): %d", summary["skipped_not_found"])
    logger.info("  Errors:              %d", summary["errors"])

    if summary["errors"] > 0:
        return 1
    return 0


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
