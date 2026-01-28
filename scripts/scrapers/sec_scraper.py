"""
SEC EDGAR scraper for 8-K filings.
"""

import json
import re
import warnings
from datetime import datetime, timedelta
from typing import Optional

from bs4 import XMLParsedAsHTMLWarning

from scrapers.base import (
    BaseScraper, ScraperResult, SEC_BASE, create_soup,
    ACTION_KEYWORDS, ASSET_KEYWORDS, STRATEGY_KEYWORDS,
    FUNDING_KEYWORDS, METRIC_ANCHORS, SEC_ITEM_KEYWORDS
)
from utils.parsers import extract_numbers_from_text, extract_holdings_with_regex, is_reasonable_change

# Suppress XML parsing warnings
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


def calculate_document_relevance(text: str, token: str) -> int:
    """
    Calculate relevance score for a document based on keyword matching.

    Scoring strategy:
    - Priority 1: SEC Item indicators (Item 8.01, Item 7.01)
    - Priority 2: Action + Asset keywords within 10 words
    - Priority 3: Strategy/DAT terminology
    - Priority 4: Funding keywords

    Returns:
        Relevance score (higher = more relevant)
    """
    text_lower = text.lower()
    score = 0

    # Check for SEC Item indicators (highest priority)
    for item in SEC_ITEM_KEYWORDS:
        if item.lower() in text_lower:
            score += 50

    # Check for action keywords
    action_count = sum(1 for kw in ACTION_KEYWORDS if kw.lower() in text_lower)
    score += action_count * 10

    # Check for asset keywords (prioritize specific token)
    token_lower = token.lower()
    for kw in ASSET_KEYWORDS:
        if kw.lower() in text_lower:
            # Higher score for specific token match
            if kw.lower() == token_lower or kw.lower() in [token_lower, f"{token_lower}coin"]:
                score += 20
            else:
                score += 5

    # Check for strategy/DAT terminology
    strategy_count = sum(1 for kw in STRATEGY_KEYWORDS if kw.lower() in text_lower)
    score += strategy_count * 8

    # Check for funding keywords
    funding_count = sum(1 for kw in FUNDING_KEYWORDS if kw.lower() in text_lower)
    score += funding_count * 5

    # Check for metric anchors (very important for number extraction)
    metric_count = sum(1 for anchor in METRIC_ANCHORS if anchor.lower() in text_lower)
    score += metric_count * 15

    return score


class SECScraper(BaseScraper):
    """Scraper for SEC EDGAR 8-K filings."""

    def __init__(self, company: dict, token: str, days_back: int = 14, token_config: dict = None):
        super().__init__(company, token, token_config=token_config)
        self.days_back = days_back
        self.cik = company.get("cik", "")

    def scrape(self) -> Optional[ScraperResult]:
        """
        Scrape SEC EDGAR for recent 8-K filings.

        Returns:
            ScraperResult if new holdings found, None otherwise
        """
        if not self.cik:
            self.log("No CIK, skipping SEC scrape")
            return None

        filings = self._get_8k_filings()

        for filing in filings[:3]:  # Check last 3 filings
            result = self._check_filing_for_holdings(filing)
            if result:
                return result

        return None

    def _get_8k_filings(self) -> list[dict]:
        """Fetch recent 8-K filings from SEC EDGAR."""
        cik_clean = self.cik.lstrip("0")

        url = f"https://data.sec.gov/submissions/CIK{self.cik}.json"
        html = self.fetch_url(url)

        if not html:
            return []

        try:
            data = json.loads(html)
            filings = []
            recent = data.get("filings", {}).get("recent", {})

            forms = recent.get("form", [])
            dates = recent.get("filingDate", [])
            accessions = recent.get("accessionNumber", [])
            descriptions = recent.get("primaryDocDescription", [])

            cutoff = (datetime.now() - timedelta(days=self.days_back)).strftime("%Y-%m-%d")

            for i, form in enumerate(forms[:50]):
                if form in ["8-K", "8-K/A"] and dates[i] >= cutoff:
                    accession_no_dash = accessions[i].replace("-", "")
                    filings.append({
                        "form": form,
                        "date": dates[i],
                        "accession": accession_no_dash,
                        "accession_orig": accessions[i],
                        "description": descriptions[i] if i < len(descriptions) else "",
                        "url": f"{SEC_BASE}/Archives/edgar/data/{cik_clean}/{accession_no_dash}"
                    })

            return filings
        except (json.JSONDecodeError, KeyError) as e:
            self.log(f"Error parsing SEC data: {e}")
            return []

    def _get_filing_documents(self, filing: dict) -> list[dict]:
        """Get all document links from a filing index page."""
        index_url = f"{filing['url']}/{filing['accession_orig']}-index.htm"
        html = self.fetch_url(index_url)

        if not html:
            return []

        soup = create_soup(html)
        documents = []

        for link in soup.find_all("a"):
            href = link.get("href", "")

            if ".htm" not in href:
                continue

            # Handle inline XBRL viewer links
            if href.startswith("/ix?doc="):
                actual_path = href.replace("/ix?doc=", "")
                full_url = f"{SEC_BASE}{actual_path}"
                filename = actual_path.split("/")[-1]
            elif href.endswith(".htm"):
                if href.startswith("/"):
                    full_url = f"{SEC_BASE}{href}"
                else:
                    full_url = f"{filing['url']}/{href}"
                filename = href.split("/")[-1]
            else:
                continue

            if filename in ["index.htm"] or "searchedgar" in href:
                continue

            # Categorize document type with priority
            filename_lower = filename.lower()
            if "ex99" in filename_lower or "ex-99" in filename_lower or "ex_99" in filename_lower:
                doc_type = "ex99"
                priority = 0
            elif "8k" in filename_lower or "8-k" in filename_lower:
                doc_type = "8k"
                priority = 2
            elif filename_lower.startswith("ex"):
                doc_type = "exhibit"
                priority = 1
            else:
                doc_type = "other"
                priority = 3

            documents.append({
                "url": full_url,
                "type": doc_type,
                "priority": priority,
                "filename": filename
            })

        return documents

    def _check_filing_for_holdings(self, filing: dict) -> Optional[ScraperResult]:
        """Check an 8-K filing for token holdings information."""
        documents = self._get_filing_documents(filing)

        if not documents:
            return None

        documents.sort(key=lambda d: (d["priority"], d["filename"]))

        for doc in documents[:5]:
            doc_html = self.fetch_url(doc["url"])
            if not doc_html:
                continue

            soup = create_soup(doc_html)
            text = soup.get_text()

            holdings = self._find_holdings_in_text(text)

            if holdings:
                # For ex99 (press release), trust it completely
                if doc["type"] == "ex99":
                    if holdings != self.current_holdings:
                        if not is_reasonable_change(self.current_holdings, holdings):
                            self.log(f"Skipping {doc['filename']}: suspicious drop to {holdings:,}")
                            return None

                        self.log(f"Found in {doc['filename']}: {holdings:,} {self.token}")
                        return ScraperResult(
                            tokens=holdings,
                            date=filing["date"],
                            url=doc["url"],
                            source=doc["filename"]
                        )
                    else:
                        return None

                # For non-ex99 docs, only use if different
                if holdings != self.current_holdings:
                    if not is_reasonable_change(self.current_holdings, holdings):
                        self.log(f"Skipping {doc['filename']}: suspicious drop to {holdings:,}")
                        continue

                    self.log(f"Found in {doc['filename']}: {holdings:,} {self.token}")
                    return ScraperResult(
                        tokens=holdings,
                        date=filing["date"],
                        url=doc["url"],
                        source=doc["filename"]
                    )

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

    def _find_holdings_in_text(self, text: str) -> Optional[int]:
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

        # Calculate document relevance score
        relevance = calculate_document_relevance(text, self.token)
        if relevance < 10:
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
                candidates[num] = max(candidates.get(num, 0), priority)

        # Strategy 1: Metric anchors with token keywords (priority 100)
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

        # Strategy 3: Action keywords near token (priority 70)
        # Lower priority - these often capture purchase amounts, not totals
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

        # Sort by priority first, then by value (prefer higher values for ties)
        sorted_candidates = sorted(
            candidates.items(),
            key=lambda x: (x[1], x[0]),  # (priority, value)
            reverse=True
        )

        best_candidate = sorted_candidates[0][0]
        best_priority = sorted_candidates[0][1]

        # Safety check: if best candidate is LOWER than current holdings,
        # only accept if there's explicit sell language
        if self.current_holdings > 0 and best_candidate < self.current_holdings:
            if not self._has_sell_language(text):
                # No sell language - look for a higher candidate
                for num, priority in sorted_candidates:
                    if num >= self.current_holdings:
                        self.log(f"Rejecting {best_candidate:,} (no sell language), using {num:,}")
                        return num

                # All candidates are lower - reject the change
                self.log(f"Rejecting decrease to {best_candidate:,} (no sell language)")
                return None

        self.log(f"Selected {best_candidate:,} (priority {best_priority}) from {len(candidates)} candidates")
        return best_candidate
