"""Post-scrape auditor for DAT Monitor data quality.

Runs sanity checks against data.json and holdings_history.json,
flagging implausible values, stale data, and suspicious changes.

Usage:
    python -m scraper.auditor --data-path data.json [--history-path path] [--json]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from scraper.config import DATA_JSON_PATH, HOLDINGS_HISTORY_PATH, SMALL_VALUE_FLOOR

logger = logging.getLogger(__name__)

# --- Data structures ---


@dataclass(frozen=True)
class AuditFlag:
    """One flagged issue found by the auditor."""

    severity: str  # "CRITICAL" or "WARNING"
    ticker: str
    token: str
    check_name: str
    message: str


@dataclass
class AuditReport:
    """Aggregated audit results."""

    timestamp: str
    flags: list[AuditFlag] = field(default_factory=list)
    companies_checked: int = 0

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.flags if f.severity == "CRITICAL")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.flags if f.severity == "WARNING")

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "companies_checked": self.companies_checked,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "flags": [
                {
                    "severity": f.severity,
                    "ticker": f.ticker,
                    "token": f.token,
                    "check_name": f.check_name,
                    "message": f.message,
                }
                for f in self.flags
            ],
        }


# --- Individual checks ---


def _check_artifact_value(company: dict, token: str) -> Optional[AuditFlag]:
    """Flag token counts that are suspiciously small (likely extraction artifacts)."""
    tokens = company.get("tokens", 0)
    ticker = company.get("ticker", "")
    if 0 < tokens < SMALL_VALUE_FLOOR:
        return AuditFlag(
            severity="CRITICAL",
            ticker=ticker,
            token=token,
            check_name="artifact_value",
            message=f"Token count {tokens} is below artifact floor ({SMALL_VALUE_FLOOR})",
        )
    return None


def _check_magnitude_drop(company: dict, token: str) -> Optional[AuditFlag]:
    """Flag companies where the `change` field represents a >50% decrease."""
    tokens = company.get("tokens", 0)
    change = company.get("change", 0)
    ticker = company.get("ticker", "")
    if change < 0 and tokens > 0:
        previous = tokens - change  # change is negative, so previous = tokens + |change|
        drop_pct = abs(change) / previous
        if drop_pct > 0.50:
            return AuditFlag(
                severity="CRITICAL",
                ticker=ticker,
                token=token,
                check_name="magnitude_drop",
                message=f"Change of {change} represents {drop_pct:.0%} drop (from {previous} to {tokens})",
            )
    return None


def _check_stale_data(company: dict, token: str) -> Optional[AuditFlag]:
    """Flag companies with lastUpdate > 30 days old."""
    ticker = company.get("ticker", "")
    last_update = company.get("lastUpdate", "")
    if not last_update:
        return None
    try:
        update_date = date.fromisoformat(last_update)
    except ValueError:
        return None
    days_old = (date.today() - update_date).days
    if days_old > 30:
        return AuditFlag(
            severity="WARNING",
            ticker=ticker,
            token=token,
            check_name="stale_data",
            message=f"Last updated {last_update} ({days_old} days ago)",
        )
    return None


def _check_history_consistency(
    company: dict, token: str, history: dict
) -> Optional[AuditFlag]:
    """Flag when current tokens != last_confirmed in history."""
    ticker = company.get("ticker", "")
    key = f"{ticker}:{token}"
    if key not in history:
        return None
    record = history[key]
    last_confirmed = record.get("last_confirmed_value", record.get("last_confirmed_value"))
    if last_confirmed is None:
        return None
    tokens = company.get("tokens", 0)
    if tokens != last_confirmed:
        return AuditFlag(
            severity="WARNING",
            ticker=ticker,
            token=token,
            check_name="history_consistency",
            message=f"Current tokens ({tokens}) != history last_confirmed ({last_confirmed})",
        )
    return None


def _check_suspicious_recent_changes(
    recent_changes: list[dict],
) -> list[AuditFlag]:
    """Flag recentChanges entries with implausible deltas."""
    flags: list[AuditFlag] = []
    for entry in recent_changes:
        ticker = entry.get("ticker", "")
        token = entry.get("token", "")
        tokens = entry.get("tokens", 0)
        change = entry.get("change", 0)
        if change < 0 and tokens > 0:
            previous = tokens - change
            drop_pct = abs(change) / previous
            if drop_pct > 0.50:
                flags.append(AuditFlag(
                    severity="CRITICAL",
                    ticker=ticker,
                    token=token,
                    check_name="suspicious_recent_change",
                    message=f"Recent change of {change} is a {drop_pct:.0%} drop (from {previous} to {tokens})",
                ))
    return flags


# --- Main audit runner ---


def run_audit(
    data_path: Path,
    history_path: Optional[Path] = None,
) -> AuditReport:
    """Run all audit checks and return an AuditReport."""
    report = AuditReport(timestamp=date.today().isoformat())

    with open(data_path, "r") as f:
        data = json.load(f)

    history: dict = {}
    if history_path and history_path.exists():
        with open(history_path, "r") as f:
            history = json.load(f)

    companies = data.get("companies", {})
    count = 0

    for token_group, company_list in companies.items():
        for company in company_list:
            count += 1
            for check_fn in (_check_artifact_value, _check_magnitude_drop, _check_stale_data):
                flag = check_fn(company, token_group)
                if flag:
                    report.flags.append(flag)
            flag = _check_history_consistency(company, token_group, history)
            if flag:
                report.flags.append(flag)

    # Check recent changes
    recent_changes = data.get("recentChanges", [])
    report.flags.extend(_check_suspicious_recent_changes(recent_changes))

    report.companies_checked = count
    return report


# --- CLI ---


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 1 if any CRITICAL flags, 0 otherwise."""
    parser = argparse.ArgumentParser(
        description="DAT Monitor — post-scrape data auditor"
    )
    parser.add_argument(
        "--data-path",
        default=str(DATA_JSON_PATH),
        help=f"Path to data.json (default: {DATA_JSON_PATH})",
    )
    parser.add_argument(
        "--history-path",
        default=str(HOLDINGS_HISTORY_PATH),
        help=f"Path to holdings history (default: {HOLDINGS_HISTORY_PATH})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON instead of human-readable",
    )
    args = parser.parse_args(argv)

    data_path = Path(args.data_path)
    history_path = Path(args.history_path)

    if not data_path.exists():
        print(f"Error: {data_path} not found", file=sys.stderr)
        return 1

    report = run_audit(data_path, history_path)

    if args.json_output:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"Audit Report — {report.timestamp}")
        print(f"Companies checked: {report.companies_checked}")
        print(f"Critical: {report.critical_count}, Warnings: {report.warning_count}")
        if report.flags:
            print()
            for flag in report.flags:
                print(f"  [{flag.severity}] {flag.ticker} ({flag.token}) — {flag.check_name}: {flag.message}")
        else:
            print("\nNo issues found.")

    return 1 if report.critical_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
