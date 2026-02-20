"""Tests for the post-scrape auditor module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scraper.auditor import (
    AuditReport,
    _check_artifact_value,
    _check_history_consistency,
    _check_magnitude_drop,
    _check_stale_data,
    _check_suspicious_recent_changes,
    main,
    run_audit,
)


# --- Test: individual checks ---


class TestCheckArtifactValue:
    def test_flags_small_token_count(self) -> None:
        company = {"ticker": "NAKA", "tokens": 15}
        flag = _check_artifact_value(company, "BTC")
        assert flag is not None
        assert flag.severity == "CRITICAL"
        assert flag.check_name == "artifact_value"

    def test_zero_tokens_not_flagged(self) -> None:
        company = {"ticker": "NAKA", "tokens": 0}
        flag = _check_artifact_value(company, "BTC")
        assert flag is None

    def test_normal_tokens_not_flagged(self) -> None:
        company = {"ticker": "MSTR", "tokens": 687410}
        flag = _check_artifact_value(company, "BTC")
        assert flag is None

    def test_boundary_value_49_flagged(self) -> None:
        company = {"ticker": "TEST", "tokens": 49}
        flag = _check_artifact_value(company, "BTC")
        assert flag is not None

    def test_boundary_value_50_not_flagged(self) -> None:
        company = {"ticker": "TEST", "tokens": 50}
        flag = _check_artifact_value(company, "BTC")
        assert flag is None


class TestCheckMagnitudeDrop:
    def test_flags_large_drop(self) -> None:
        company = {"ticker": "NAKA", "tokens": 100, "change": -5665}
        flag = _check_magnitude_drop(company, "BTC")
        assert flag is not None
        assert flag.severity == "CRITICAL"
        assert flag.check_name == "magnitude_drop"

    def test_normal_decrease_not_flagged(self) -> None:
        company = {"ticker": "MSTR", "tokens": 687410, "change": -1000}
        flag = _check_magnitude_drop(company, "BTC")
        assert flag is None

    def test_increase_not_flagged(self) -> None:
        company = {"ticker": "MSTR", "tokens": 700000, "change": 13627}
        flag = _check_magnitude_drop(company, "BTC")
        assert flag is None

    def test_zero_change_not_flagged(self) -> None:
        company = {"ticker": "MSTR", "tokens": 687410, "change": 0}
        flag = _check_magnitude_drop(company, "BTC")
        assert flag is None


class TestCheckStaleData:
    def test_flags_old_data(self) -> None:
        company = {"ticker": "OLD", "lastUpdate": "2025-01-01"}
        flag = _check_stale_data(company, "BTC")
        assert flag is not None
        assert flag.severity == "WARNING"
        assert flag.check_name == "stale_data"

    def test_recent_data_not_flagged(self) -> None:
        from datetime import date

        company = {"ticker": "MSTR", "lastUpdate": date.today().isoformat()}
        flag = _check_stale_data(company, "BTC")
        assert flag is None

    def test_missing_date_not_flagged(self) -> None:
        company = {"ticker": "TEST", "lastUpdate": ""}
        flag = _check_stale_data(company, "BTC")
        assert flag is None


class TestCheckHistoryConsistency:
    def test_flags_mismatch(self) -> None:
        company = {"ticker": "MSTR", "tokens": 687410}
        history = {"MSTR:BTC": {"last_confirmed_value": 700000}}
        flag = _check_history_consistency(company, "BTC", history)
        assert flag is not None
        assert flag.severity == "WARNING"

    def test_match_not_flagged(self) -> None:
        company = {"ticker": "MSTR", "tokens": 700000}
        history = {"MSTR:BTC": {"last_confirmed_value": 700000}}
        flag = _check_history_consistency(company, "BTC", history)
        assert flag is None

    def test_no_history_not_flagged(self) -> None:
        company = {"ticker": "NEW", "tokens": 100}
        flag = _check_history_consistency(company, "BTC", {})
        assert flag is None


class TestCheckSuspiciousRecentChanges:
    def test_flags_large_drop(self) -> None:
        changes = [{"ticker": "NAKA", "token": "BTC", "tokens": 99, "change": -5666}]
        flags = _check_suspicious_recent_changes(changes)
        assert len(flags) == 1
        assert flags[0].severity == "CRITICAL"

    def test_normal_change_not_flagged(self) -> None:
        changes = [{"ticker": "MSTR", "token": "BTC", "tokens": 700000, "change": 13627}]
        flags = _check_suspicious_recent_changes(changes)
        assert len(flags) == 0


# --- Test: full audit run ---


class TestRunAudit:
    def test_clean_data_no_flags(self, tmp_path: Path) -> None:
        from datetime import date

        data = {
            "companies": {
                "BTC": [
                    {"ticker": "MSTR", "tokens": 687410, "change": 13627,
                     "lastUpdate": date.today().isoformat()}
                ]
            },
            "recentChanges": [],
        }
        data_path = tmp_path / "data.json"
        data_path.write_text(json.dumps(data))

        report = run_audit(data_path)
        assert report.critical_count == 0
        assert report.warning_count == 0
        assert report.companies_checked == 1

    def test_artifact_value_flagged(self, tmp_path: Path) -> None:
        from datetime import date

        data = {
            "companies": {
                "BTC": [
                    {"ticker": "NAKA", "tokens": 15, "change": 0,
                     "lastUpdate": date.today().isoformat()}
                ]
            },
            "recentChanges": [],
        }
        data_path = tmp_path / "data.json"
        data_path.write_text(json.dumps(data))

        report = run_audit(data_path)
        assert report.critical_count == 1
        assert report.flags[0].check_name == "artifact_value"


# --- Test: CLI exit codes ---


class TestCLI:
    def test_clean_exits_zero(self, tmp_path: Path) -> None:
        from datetime import date

        data = {
            "companies": {
                "BTC": [
                    {"ticker": "MSTR", "tokens": 687410, "change": 0,
                     "lastUpdate": date.today().isoformat()}
                ]
            },
            "recentChanges": [],
        }
        data_path = tmp_path / "data.json"
        data_path.write_text(json.dumps(data))

        exit_code = main(["--data-path", str(data_path)])
        assert exit_code == 0

    def test_critical_exits_one(self, tmp_path: Path) -> None:
        from datetime import date

        data = {
            "companies": {
                "BTC": [
                    {"ticker": "NAKA", "tokens": 15, "change": 0,
                     "lastUpdate": date.today().isoformat()}
                ]
            },
            "recentChanges": [],
        }
        data_path = tmp_path / "data.json"
        data_path.write_text(json.dumps(data))

        exit_code = main(["--data-path", str(data_path)])
        assert exit_code == 1

    def test_json_output(self, tmp_path: Path, capsys) -> None:
        from datetime import date

        data = {
            "companies": {
                "BTC": [
                    {"ticker": "MSTR", "tokens": 687410, "change": 0,
                     "lastUpdate": date.today().isoformat()}
                ]
            },
            "recentChanges": [],
        }
        data_path = tmp_path / "data.json"
        data_path.write_text(json.dumps(data))

        exit_code = main(["--data-path", str(data_path), "--json"])
        assert exit_code == 0
        output = capsys.readouterr().out
        parsed = json.loads(output)
        assert parsed["critical_count"] == 0

    def test_missing_file_exits_one(self, tmp_path: Path) -> None:
        exit_code = main(["--data-path", str(tmp_path / "nonexistent.json")])
        assert exit_code == 1
