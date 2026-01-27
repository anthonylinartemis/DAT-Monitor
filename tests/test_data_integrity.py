"""Schema validation tests against the real data.json.

Ensures the dashboard contract is maintained: all required fields
present, types correct, totals accurate, tickers unique.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scraper.config import (
    OPTIONAL_COMPANY_FIELDS,
    REQUIRED_COMPANY_FIELDS,
    VALID_TOKENS,
)

# Path to the real data.json in the repo
_DATA_PATH = Path(__file__).resolve().parent.parent / "data.json"


@pytest.fixture()
def data() -> dict:
    """Load the real data.json."""
    with open(_DATA_PATH, "r") as f:
        return json.load(f)


class TestTopLevelStructure:
    def test_top_level_keys_present(self, data: dict) -> None:
        required = {"lastUpdated", "lastUpdatedDisplay", "recentChanges", "companies", "totals"}
        assert required.issubset(data.keys())

    def test_all_token_groups_present(self, data: dict) -> None:
        assert set(data["companies"].keys()) == VALID_TOKENS


class TestTotalsAccuracy:
    def test_totals_match_sum_of_tokens(self, data: dict) -> None:
        for token_group, company_list in data["companies"].items():
            expected = sum(c.get("tokens", 0) for c in company_list)
            actual = data["totals"].get(token_group, 0)
            assert actual == expected, (
                f"{token_group}: totals says {actual}, "
                f"sum of companies says {expected}"
            )


class TestCompanyFields:
    def _all_companies(self, data: dict) -> list[tuple[str, dict]]:
        """Yield (token_group, company_dict) pairs."""
        result = []
        for token_group, company_list in data["companies"].items():
            for company in company_list:
                result.append((token_group, company))
        return result

    def test_required_fields_present_with_correct_types(self, data: dict) -> None:
        for token_group, company in self._all_companies(data):
            for field_name, field_type in REQUIRED_COMPANY_FIELDS.items():
                assert field_name in company, (
                    f"{company.get('ticker', '???')} in {token_group} "
                    f"missing required field '{field_name}'"
                )
                assert isinstance(company[field_name], field_type), (
                    f"{company['ticker']}.{field_name}: expected {field_type.__name__}, "
                    f"got {type(company[field_name]).__name__}"
                )

    def test_optional_fields_correct_type_when_present(self, data: dict) -> None:
        for token_group, company in self._all_companies(data):
            for field_name, field_type in OPTIONAL_COMPANY_FIELDS.items():
                if field_name in company:
                    assert isinstance(company[field_name], field_type), (
                        f"{company['ticker']}.{field_name}: expected {field_type.__name__}, "
                        f"got {type(company[field_name]).__name__}"
                    )


class TestDataConstraints:
    def test_tickers_unique_within_each_group(self, data: dict) -> None:
        for token_group, company_list in data["companies"].items():
            tickers = [c["ticker"] for c in company_list]
            assert len(tickers) == len(set(tickers)), (
                f"Duplicate tickers in {token_group}: {tickers}"
            )

    def test_all_tokens_non_negative(self, data: dict) -> None:
        for token_group, company_list in data["companies"].items():
            for company in company_list:
                assert company["tokens"] >= 0, (
                    f"{company['ticker']} has negative tokens: {company['tokens']}"
                )

    def test_last_update_matches_date_format(self, data: dict) -> None:
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        for token_group, company_list in data["companies"].items():
            for company in company_list:
                assert date_pattern.match(company["lastUpdate"]), (
                    f"{company['ticker']}.lastUpdate '{company['lastUpdate']}' "
                    f"doesn't match YYYY-MM-DD"
                )

    def test_recent_changes_reference_valid_tickers(self, data: dict) -> None:
        all_tickers: set[str] = set()
        for company_list in data["companies"].values():
            for company in company_list:
                all_tickers.add(company["ticker"])

        for entry in data["recentChanges"]:
            assert entry["ticker"] in all_tickers, (
                f"recentChanges references unknown ticker '{entry['ticker']}'"
            )
            assert entry["token"] in VALID_TOKENS, (
                f"recentChanges references unknown token '{entry['token']}'"
            )
