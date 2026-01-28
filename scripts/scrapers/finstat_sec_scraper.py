"""
Finstat SEC EDGAR Scraper Adapter.

This adapter class integrates the finstat SecEdgarConnector into the
existing DAT Treasury Monitor scraper system, allowing it to be used
through the standard scraper factory while maintaining all existing
infrastructure (Supabase, Slack alerts, validation, etc.).

Usage:
    Set scrape_method: "finstat_sec" in dat_companies.yaml to use this scraper.
"""

import re
import sys
import warnings
from pathlib import Path

from bs4 import XMLParsedAsHTMLWarning

# Add src to path for finstat imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from finstat.connectors.sec_edgar import SecEdgarConnector
from finstat.core.config import (
    DiscoveryConfig,
    FilterConfig,
    RateLimitConfig,
    SourceConfig,
    TypePattern,
)

from scrapers.base import (
    ACTION_KEYWORDS,
    METRIC_ANCHORS,
    BaseScraper,
    ScraperResult,
    create_soup,
)
from utils.parsers import (
    extract_holdings_with_regex,
    extract_numbers_from_text,
    is_reasonable_change,
)

# Suppress XML parsing warnings
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


class FinstatSecScraper(BaseScraper):
    """
    SEC EDGAR scraper using the finstat SecEdgarConnector.

    This adapter provides:
    - Better rate limiting (built into finstat connector)
    - Cleaner SEC EDGAR API integration
    - Full compatibility with existing DAT scraper infrastructure
    - Access to all finstat connector features (retries, error handling)

    The holdings extraction logic is preserved from the original SECScraper
    to maintain accuracy and proven patterns.
    """

    def __init__(self, company: dict, token: str, days_back: int = 14, token_config: dict = None):
        super().__init__(company, token, token_config=token_config)
        self.days_back = days_back
        self.cik = company.get("cik", "")

        # Create finstat connector for this single company
        self._connector = self._create_connector()

    def _create_connector(self) -> SecEdgarConnector:
        """Create a finstat SecEdgarConnector configured for this company."""
        # Build a minimal SourceConfig for this single company
        cik_key = f"cik_{self.cik.zfill(10)}"
        cik_value = f"{self.ticker}|{self.company.get('name', '')}|{self.token}"

        config = SourceConfig(
            name=f"dat_single_{self.ticker}",
            connector="sec_edgar",
            base_url="https://www.sec.gov",
            discovery=DiscoveryConfig(
                selectors={
                    "user_agent": f"FinstatDAT/1.0 (dat-monitor@finstat.io)",
                    cik_key: cik_value,
                },
                date_format="%Y-%m-%d",
                type_patterns=[
                    TypePattern(pattern="8-K", doc_type="SEC_8K"),
                ],
            ),
            rate_limit=RateLimitConfig(
                requests_per_second=6.0,
                max_retries=3,
            ),
            filters=FilterConfig(
                lookback_days=self.days_back,
                include_doc_types=["SEC_8K"],
            ),
        )

        return SecEdgarConnector(config)

    def scrape(self) -> ScraperResult | None:
        """
        Scrape SEC EDGAR using the finstat connector.

        Returns:
            ScraperResult if new holdings found, None otherwise
        """
        if not self.cik:
            self.log("No CIK, skipping SEC scrape")
            return None

        # Use finstat connector for discovery
        self.log("Using finstat SecEdgarConnector")
        candidates = self._connector.discover()

        if not candidates:
            self.log("No recent 8-K filings found")
            return None

        self.log(f"Found {len(candidates)} 8-K filings")

        # Check each filing for holdings data
        for candidate in candidates[:5]:  # Check up to 5 recent filings
            result = self._check_filing_for_holdings(candidate)
            if result:
                return result

        return None

    def _check_filing_for_holdings(self, candidate) -> ScraperResult | None:
        """
        Check a filing candidate for token holdings information.

        Uses finstat connector for fetching, then applies existing
        holdings extraction logic for accuracy.
        """
        try:
            # Fetch document using finstat connector
            raw_doc = self._connector.fetch(candidate)

            # Decode content
            try:
                text = raw_doc.content.decode('utf-8')
            except UnicodeDecodeError:
                text = raw_doc.content.decode('latin-1')

            # Parse and extract text
            soup = create_soup(text)
            doc_text = soup.get_text(separator=' ', strip=True)

            # Find holdings using proven extraction logic
            holdings = self._find_holdings_in_text(doc_text)

            if holdings and holdings != self.current_holdings:
                # Validate the change is reasonable
                if not is_reasonable_change(self.current_holdings, holdings):
                    self.log(f"Skipping suspicious value: {holdings:,}")
                    return None

                self.log(f"Found holdings: {holdings:,} {self.token}")

                filing_date = candidate.filing_date.isoformat() if candidate.filing_date else ""

                return ScraperResult(
                    tokens=holdings,
                    date=filing_date,
                    url=candidate.url,
                    source=f"finstat:{candidate.doc_type}"
                )

        except Exception as e:
            self.log(f"Error processing filing: {e}")

        return None

    def _has_sell_language(self, text: str) -> bool:
        """
        Check if document contains explicit sell/disposal language.

        Returns True only if there's clear indication of selling tokens.
        This prevents false decreases from misinterpreting "previous holdings" numbers.
        """
        text_lower = text.lower()
        keywords = self.get_keywords()

        # Sell/disposal keywords that must appear near our token
        sell_keywords = [
            "sold", "selling", "sale of", "disposed", "disposing",
            "liquidated", "liquidating", "divested", "reduced holdings",
            "decreased holdings", "sold off"
        ]

        for sell_word in sell_keywords:
            if sell_word in text_lower:
                # Check if sell word is near our token keyword
                for kw in keywords:
                    # Look for sell word within 100 chars of token keyword
                    pattern = rf'{sell_word}.{{0,100}}{kw}|{kw}.{{0,100}}{sell_word}'
                    if re.search(pattern, text_lower):
                        return True

        return False

    def _extract_from_to_pattern(self, text: str) -> tuple[int, int] | None:
        """
        Look for "from X to Y" patterns that indicate previous and new holdings.

        Returns (previous, new) tuple if found, None otherwise.
        Examples:
          - "from 687,410 to 709,715 bitcoin"
          - "increased from 687,410 bitcoin to 709,715"
        """
        text_lower = text.lower()
        keywords = self.get_keywords()

        for kw in keywords:
            # Pattern: "from X to Y <keyword>" or "from X <keyword> to Y"
            patterns = [
                rf'from\s+(\d[\d,]*)\s+to\s+(\d[\d,]*)\s+{kw}',
                rf'from\s+(\d[\d,]*)\s+{kw}\s+to\s+(\d[\d,]*)',
                rf'{kw}\s+from\s+(\d[\d,]*)\s+to\s+(\d[\d,]*)',
                rf'(\d[\d,]*)\s+{kw}\s+to\s+(\d[\d,]*)\s+{kw}',
            ]

            for pattern in patterns:
                match = re.search(pattern, text_lower)
                if match:
                    try:
                        prev_val = int(match.group(1).replace(",", ""))
                        new_val = int(match.group(2).replace(",", ""))
                        if self.is_valid_holdings_amount(prev_val) and self.is_valid_holdings_amount(new_val):
                            return (prev_val, new_val)
                    except (ValueError, IndexError):
                        continue

        return None

    def _find_holdings_in_text(self, text: str) -> int | None:
        """
        Find token holdings in text using multiple strategies.

        Key improvements:
        - Collects ALL candidate numbers instead of returning on first match
        - Detects "from X to Y" patterns to identify previous vs current holdings
        - Requires explicit sell language before allowing holdings to decrease
        - Returns the highest valid candidate (since DAT companies rarely sell)
        """
        text_lower = text.lower()
        keywords = self.get_keywords()

        # Check if document mentions our token
        token_mentioned = any(kw in text_lower for kw in keywords)
        if not token_mentioned:
            return None

        # Try custom regex first (highest priority)
        custom_regex = self.get_target_regex()
        if custom_regex:
            result = extract_holdings_with_regex(text, custom_regex)
            if result:
                return result

        # Check for "from X to Y" pattern first - this gives us definitive answer
        from_to = self._extract_from_to_pattern(text)
        if from_to:
            prev_val, new_val = from_to
            self.log(f"Found from/to pattern: {prev_val:,} -> {new_val:,}")
            # Return the new (higher) value, which is the current total
            return max(prev_val, new_val)

        # Extract all candidate numbers from the document
        all_numbers = extract_numbers_from_text(text)
        if not all_numbers:
            return None

        # Collect candidates with their priority scores
        # Higher score = higher confidence this is the actual total
        candidates: dict[int, int] = {}  # number -> priority score

        def add_candidate(num: int, priority: int):
            """Add a candidate number with priority (higher = better)."""
            if self.is_valid_holdings_amount(num):
                # Keep the highest priority for each number
                candidates[num] = max(candidates.get(num, 0), priority)

        # Strategy 1: Metric anchors with token keywords (priority 100)
        # These explicitly say "total", "aggregate", etc.
        for anchor in METRIC_ANCHORS:
            anchor_lower = anchor.lower()
            for kw in keywords:
                patterns = [
                    rf'{anchor_lower}\s+(\d[\d,]*)\s+{kw}',
                    rf'{anchor_lower}\s+{kw}[:\s]+(\d[\d,]*)',
                    rf'{kw}\s+{anchor_lower}[:\s]+(\d[\d,]*)',
                ]
                for pattern in patterns:
                    match = re.search(pattern, text_lower)
                    if match:
                        num_str = match.group(1).replace(",", "")
                        try:
                            num = int(float(num_str))
                            context = text_lower[match.end():match.end() + 20]
                            if "million" in context or (num_str.count('.') > 0 and num < 100):
                                num = int(num * 1_000_000)
                            add_candidate(num, 100)
                        except ValueError:
                            continue

        # Strategy 2: "aggregate" or "total" holdings patterns (priority 90)
        aggregate_patterns = [
            rf'aggregate\s+{self.token}\s+holdings[:\s]+(\d[\d,]*)',
            rf'total\s+{self.token}\s+holdings[:\s]+(\d[\d,]*)',
            rf'holds?\s+(\d[\d,]*)\s+{self.token}',
            rf'(\d[\d,]*)\s+{self.token}\s+(?:tokens?|holdings?)',
            rf'holding[s]?\s+(?:of\s+)?(\d[\d,]*)\s+{self.token}',
            rf'{self.token}\s+holdings?\s+(?:of\s+)?(\d[\d,]*)',
        ]

        for kw in keywords:
            aggregate_patterns.extend([
                rf'aggregate\s+{kw}\s+holdings[:\s]*(\d[\d,]*)',
                rf'total\s+{kw}[:\s]*(\d[\d,]*)',
                rf'holds?\s+(\d[\d,]*)\s+{kw}',
                rf'(\d[\d,]*)\s+{kw}\s+(?:tokens?|holdings?)',
                rf'holding[s]?\s+(?:are\s+)?(?:comprised\s+of\s+)?(\d[\d,]*)\s+{kw}',
                rf'{kw}\s+holdings?\s+(?:reach|total|of)\s+(\d[\d,\.]*)\s*(?:million|M)?',
            ])

        for pattern in aggregate_patterns:
            match = re.search(pattern, text_lower)
            if match:
                num_str = match.group(1).replace(",", "")
                try:
                    num = int(float(num_str))
                    context = text_lower[match.end():match.end() + 20]
                    if "million" in context or (num_str.count('.') > 0 and num < 100):
                        num = int(num * 1_000_000)
                    if num >= 1000:
                        add_candidate(num, 90)
                except ValueError:
                    continue

        # Strategy 3: Action keywords near token and numbers (priority 70)
        # These are purchase announcements - the number is what was ADDED, not total
        # Lower priority since we want totals, not incremental purchases
        for action in ACTION_KEYWORDS:
            action_lower = action.lower()
            for kw in keywords:
                patterns = [
                    rf'{action_lower}\s+(\d[\d,]*)\s+{kw}',
                    rf'{action_lower}\s+(?:an?\s+)?(?:additional\s+)?(\d[\d,]*)\s+{kw}',
                ]
                for pattern in patterns:
                    match = re.search(pattern, text_lower)
                    if match:
                        num_str = match.group(1).replace(",", "")
                        try:
                            num = int(float(num_str))
                            context = text_lower[match.end():match.end() + 20]
                            if "million" in context or (num_str.count('.') > 0 and num < 100):
                                num = int(num * 1_000_000)
                            add_candidate(num, 70)
                        except ValueError:
                            continue

        # Strategy 4: Numbers near token keywords (priority 50)
        for kw in keywords:
            for match in re.finditer(rf'\b{kw}\b', text_lower):
                start = max(0, match.start() - 200)
                end = min(len(text_lower), match.end() + 200)
                context = text_lower[start:end]

                context_numbers = extract_numbers_from_text(context)
                for num in context_numbers:
                    add_candidate(num, 50)

        # Strategy 5: Numbers similar to current holdings (priority 30)
        if self.current_holdings > 0:
            for num in all_numbers:
                ratio = num / self.current_holdings
                if 0.5 <= ratio <= 2.0:
                    add_candidate(num, 30)

        if not candidates:
            return None

        # Now select the best candidate
        # Sort by priority first, then by value (prefer higher values for ties)
        sorted_candidates = sorted(
            candidates.items(),
            key=lambda x: (x[1], x[0]),  # (priority, value)
            reverse=True
        )

        best_candidate = sorted_candidates[0][0]
        best_priority = sorted_candidates[0][1]

        # Safety check: if the best candidate is LOWER than current holdings,
        # only accept it if there's explicit sell language
        if self.current_holdings > 0 and best_candidate < self.current_holdings:
            if not self._has_sell_language(text):
                # No sell language - this is likely a "previous holdings" number
                # Look for a higher candidate that could be the actual total
                for num, priority in sorted_candidates:
                    if num >= self.current_holdings:
                        self.log(f"Rejecting lower value {best_candidate:,} (no sell language), using {num:,}")
                        return num

                # All candidates are lower - reject the change entirely
                self.log(f"Rejecting decrease to {best_candidate:,} (no sell language found)")
                return None

        self.log(f"Selected {best_candidate:,} (priority {best_priority}) from {len(candidates)} candidates")
        return best_candidate
