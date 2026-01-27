"""CLI tool for merging CSV transaction data into data.json.

Usage:
    python -m scraper.csv_sync <csv_path> <ticker> <token> [--data-path PATH]

Fingerprint-based dedup ensures idempotent imports:
running the same CSV twice produces identical output.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from scraper.config import DATA_JSON_PATH, VALID_TOKENS

logger = logging.getLogger(__name__)


def _make_fingerprint(date: str, asset: str, total_cost: int) -> str:
    """Deterministic dedup key matching the JS implementation."""
    return f"{date}:{asset}:{total_cost}"


def parse_csv(csv_path: Path) -> list[dict]:
    """Parse a CSV file into a list of transaction dicts.

    Expected columns: Date, Asset, Quantity, PriceUSD, TotalCost,
    CumulativeTokens, AvgCostBasis, Source.

    Raises ValueError on missing required columns or empty file.
    """
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"CSV file is empty or has no header: {csv_path}")

        required = {"Date", "Asset", "Quantity", "TotalCost"}
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")

        transactions: list[dict] = []
        for i, row in enumerate(reader, start=2):
            date_val = row.get("Date", "").strip()
            asset_val = row.get("Asset", "").strip()
            if not date_val or not asset_val:
                logger.warning("Skipping CSV row %d: missing Date or Asset", i)
                continue

            def _int(val: str) -> int:
                return int(val.replace(",", "").strip()) if val.strip() else 0

            txn = {
                "date": date_val,
                "asset": asset_val,
                "quantity": _int(row.get("Quantity", "0")),
                "priceUsd": _int(row.get("PriceUSD", "0")),
                "totalCost": _int(row.get("TotalCost", "0")),
                "cumulativeTokens": _int(row.get("CumulativeTokens", "0")),
                "avgCostBasis": _int(row.get("AvgCostBasis", "0")),
                "source": row.get("Source", "").strip(),
            }
            txn["fingerprint"] = _make_fingerprint(
                txn["date"], txn["asset"], txn["totalCost"]
            )
            transactions.append(txn)

    return transactions


def merge_transactions(
    existing: list[dict], incoming: list[dict]
) -> tuple[list[dict], int, int]:
    """Merge incoming transactions into existing, deduping by fingerprint.

    Returns (merged_list, added_count, skipped_count).
    """
    fingerprints = {t["fingerprint"] for t in existing}
    merged = list(existing)
    added = 0
    skipped = 0

    for txn in incoming:
        fp = txn.get("fingerprint") or _make_fingerprint(
            txn["date"], txn["asset"], txn["totalCost"]
        )
        if fp in fingerprints:
            skipped += 1
        else:
            merged.append({**txn, "fingerprint": fp})
            fingerprints.add(fp)
            added += 1

    merged.sort(key=lambda t: t["date"], reverse=True)
    return merged, added, skipped


def sync_csv(
    csv_path: Path | str,
    ticker: str,
    token: str,
    data_path: Optional[Path | str] = None,
) -> dict[str, int]:
    """Full pipeline: parse CSV -> find company -> merge -> save.

    Returns dict with 'added' and 'skipped' counts.
    Raises ValueError on invalid ticker or token.
    """
    csv_path = Path(csv_path)
    data_path = Path(data_path) if data_path else DATA_JSON_PATH
    token = token.upper()

    if token not in VALID_TOKENS:
        raise ValueError(f"Invalid token '{token}'. Must be one of: {sorted(VALID_TOKENS)}")

    with open(data_path, "r") as f:
        data = json.load(f)

    companies = data.get("companies", {})
    company_list = companies.get(token, [])
    company_idx = None
    for i, c in enumerate(company_list):
        if c["ticker"] == ticker:
            company_idx = i
            break

    if company_idx is None:
        raise ValueError(
            f"Ticker '{ticker}' not found in {token} companies. "
            f"Available: {[c['ticker'] for c in company_list]}"
        )

    incoming = parse_csv(csv_path)
    existing = company_list[company_idx].get("transactions", [])
    merged, added, skipped = merge_transactions(existing, incoming)

    company_list[company_idx]["transactions"] = merged
    data["companies"][token] = company_list

    # Atomic write
    fd, tmp_path = tempfile.mkstemp(
        dir=data_path.parent, suffix=".tmp", prefix="data_"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, data_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    logger.info(
        "CSV sync for %s/%s: %d added, %d skipped (duplicates)",
        ticker, token, added, skipped,
    )
    return {"added": added, "skipped": skipped}


def main() -> int:
    """CLI entry point."""
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Merge CSV transaction data into data.json"
    )
    parser.add_argument("csv_path", type=Path, help="Path to CSV file")
    parser.add_argument("ticker", help="Company ticker (e.g., MSTR)")
    parser.add_argument("token", help="Token group (e.g., BTC)")
    parser.add_argument(
        "--data-path", type=Path, default=None,
        help="Path to data.json (defaults to project root)",
    )

    args = parser.parse_args()

    try:
        result = sync_csv(args.csv_path, args.ticker, args.token, args.data_path)
        logger.info("Result: %s", result)
        return 0
    except (ValueError, FileNotFoundError) as e:
        logger.error("%s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
