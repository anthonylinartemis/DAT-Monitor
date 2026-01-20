#!/usr/bin/env python3
"""
DAT Treasury Monitor - Auto-Update Scraper
Fetches latest holdings data from SEC EDGAR 8-K filings and IR pages.
"""

import json
import os
import re
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# Suppress XML parsing warnings
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# Configuration
DATA_FILE = Path(__file__).parent.parent / "data.json"
SEC_BASE = "https://www.sec.gov"
USER_AGENT = os.environ.get("SEC_USER_AGENT", "DAT-Monitor/1.0 (contact@example.com)")

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Rate limiting for SEC (10 requests per second max)
LAST_SEC_REQUEST = 0
SEC_RATE_LIMIT = 0.15  # seconds between requests

# Token keywords for detection
TOKEN_KEYWORDS = {
    "BTC": ["bitcoin", "btc"],
    "ETH": ["ethereum", "ether", "eth"],
    "SOL": ["solana"],
    "HYPE": ["hyperliquid", "hype"],
    "BNB": ["bnb", "binance coin", "binance"],
}


def rate_limit_sec():
    """Ensure we don't exceed SEC rate limits."""
    global LAST_SEC_REQUEST
    elapsed = time.time() - LAST_SEC_REQUEST
    if elapsed < SEC_RATE_LIMIT:
        time.sleep(SEC_RATE_LIMIT - elapsed)
    LAST_SEC_REQUEST = time.time()


def fetch_url(url, is_sec=False):
    """Fetch a URL with proper rate limiting and error handling."""
    if is_sec:
        rate_limit_sec()

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"    Error fetching {url}: {e}")
        return None


def extract_numbers_from_text(text):
    """Extract all large numbers from text (candidates for token holdings)."""
    numbers = []

    # Pattern for numbers with commas like "709,715" or "4,203,036"
    comma_numbers = re.findall(r'\b(\d{1,3}(?:,\d{3})+)\b', text)
    for num_str in comma_numbers:
        try:
            num = int(num_str.replace(",", ""))
            if num >= 1000:  # Only consider numbers >= 1000
                numbers.append(num)
        except ValueError:
            continue

    # Pattern for decimal millions like "4.203 million" or "4.2M"
    million_patterns = [
        (r'(\d+\.?\d*)\s*million', 1_000_000),
        (r'(\d+\.?\d*)\s*M\b', 1_000_000),
        (r'(\d+\.?\d*)\s*thousand', 1_000),
        (r'(\d+\.?\d*)\s*K\b', 1_000),
    ]

    for pattern, multiplier in million_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                num = int(float(match) * multiplier)
                if num >= 1000:
                    numbers.append(num)
            except ValueError:
                continue

    return list(set(numbers))  # Remove duplicates


def find_holdings_in_text(text, token, current_holdings=0):
    """
    Find token holdings in text using multiple strategies.
    Returns the most likely holdings number or None.
    """
    text_lower = text.lower()
    keywords = TOKEN_KEYWORDS.get(token, [token.lower()])

    # Check if this document mentions our token
    token_mentioned = any(kw in text_lower for kw in keywords)
    if not token_mentioned:
        return None

    # Extract all candidate numbers
    all_numbers = extract_numbers_from_text(text)
    if not all_numbers:
        return None

    # Strategy 1: Look for "aggregate" or "total" holdings patterns
    aggregate_patterns = [
        rf'aggregate\s+{token}\s+holdings[:\s]+(\d[\d,]*)',
        rf'total\s+{token}\s+holdings[:\s]+(\d[\d,]*)',
        rf'holds?\s+(\d[\d,]*)\s+{token}',
        rf'(\d[\d,]*)\s+{token}\s+(?:tokens?|holdings?)',
        rf'holding[s]?\s+(?:of\s+)?(\d[\d,]*)\s+{token}',
        rf'{token}\s+holdings?\s+(?:of\s+)?(\d[\d,]*)',
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
                # Check if "million" follows
                context = text_lower[match.end():match.end()+20]
                if "million" in context or num_str.count('.') > 0 and num < 100:
                    num = int(num * 1_000_000)
                if num >= 1000:
                    return num
            except ValueError:
                continue

    # Strategy 2: Look for numbers near token keywords with context
    for kw in keywords:
        # Find all occurrences of keyword
        for match in re.finditer(rf'\b{kw}\b', text_lower):
            # Get context around the keyword (200 chars before and after)
            start = max(0, match.start() - 200)
            end = min(len(text_lower), match.end() + 200)
            context = text_lower[start:end]

            # Look for numbers in this context
            context_numbers = extract_numbers_from_text(context)

            # Filter to reasonable holdings numbers
            for num in sorted(context_numbers, reverse=True):
                # Sanity checks based on token type
                if token == "BTC" and 1000 <= num <= 2_000_000:
                    return num
                elif token == "ETH" and 1000 <= num <= 50_000_000:
                    return num
                elif token == "SOL" and 1000 <= num <= 100_000_000:
                    return num
                elif token == "HYPE" and 1000 <= num <= 100_000_000:
                    return num
                elif token == "BNB" and 1000 <= num <= 10_000_000:
                    return num

    # Strategy 3: If we have current holdings, look for a number close to it (within 50%)
    if current_holdings > 0:
        for num in all_numbers:
            ratio = num / current_holdings if current_holdings else 0
            if 0.5 <= ratio <= 2.0:  # Within 50% to 200% of current
                return num

    return None


def get_filing_documents(filing):
    """Get all document links from a filing index page."""
    index_url = f"{filing['url']}/{filing['accession_orig']}-index.htm"
    html = fetch_url(index_url, is_sec=True)

    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    documents = []

    for link in soup.find_all("a"):
        href = link.get("href", "")

        # Skip non-htm files
        if ".htm" not in href:
            continue

        # Handle inline XBRL viewer links: /ix?doc=/Archives/...
        if href.startswith("/ix?doc="):
            # Extract the actual document path
            actual_path = href.replace("/ix?doc=", "")
            full_url = f"{SEC_BASE}{actual_path}"
            filename = actual_path.split("/")[-1]
        elif href.endswith(".htm"):
            # Build full URL for regular links
            if href.startswith("/"):
                full_url = f"{SEC_BASE}{href}"
            else:
                full_url = f"{filing['url']}/{href}"
            filename = href.split("/")[-1]
        else:
            continue

        # Skip navigation links
        if filename in ["index.htm"] or "searchedgar" in href:
            continue

        # Categorize document type with priority
        # Priority: ex99 (press releases) > other exhibits > 8k > other
        filename_lower = filename.lower()
        if "ex99" in filename_lower or "ex-99" in filename_lower or "ex_99" in filename_lower:
            doc_type = "ex99"  # Press releases - highest priority
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


def check_8k_for_holdings(filing, token, current_holdings=0):
    """Check an 8-K filing for token holdings information."""
    documents = get_filing_documents(filing)

    if not documents:
        return None

    # Prioritize: ex99 (press releases) first, then other exhibits, then 8-K
    documents.sort(key=lambda d: (d["priority"], d["filename"]))

    best_result = None

    for doc in documents[:5]:  # Check up to 5 documents
        doc_html = fetch_url(doc["url"], is_sec=True)
        if not doc_html:
            continue

        soup = BeautifulSoup(doc_html, "lxml")
        text = soup.get_text()

        holdings = find_holdings_in_text(text, token, current_holdings)

        if holdings:
            # If ex99 (press release) finds holdings, trust it completely
            # Even if same as current - this prevents falling through to wrong docs
            if doc["type"] == "ex99":
                if holdings != current_holdings:
                    # Sanity check for suspicious drops
                    if current_holdings > 0:
                        change_ratio = holdings / current_holdings
                        if change_ratio < 0.5:
                            print(f"    Skipping {doc['filename']}: {holdings:,} {token} (suspicious -{(1-change_ratio)*100:.0f}% drop)")
                            return None  # Don't check other docs

                    print(f"    Found in {doc['filename']}: {holdings:,} {token}")
                    return {
                        "tokens": holdings,
                        "date": filing["date"],
                        "url": doc["url"],
                        "source": doc["filename"]
                    }
                else:
                    # ex99 confirms current holdings - no change needed
                    return None

            # For non-ex99 docs, only use if different from current
            if holdings != current_holdings:
                # Sanity check: reject if holdings dropped by more than 50%
                if current_holdings > 0:
                    change_ratio = holdings / current_holdings
                    if change_ratio < 0.5:
                        print(f"    Skipping {doc['filename']}: {holdings:,} {token} (suspicious -{(1-change_ratio)*100:.0f}% drop)")
                        continue

                print(f"    Found in {doc['filename']}: {holdings:,} {token}")
                result = {
                    "tokens": holdings,
                    "date": filing["date"],
                    "url": doc["url"],
                    "source": doc["filename"]
                }

                if best_result is None:
                    best_result = result

    return best_result


def get_sec_8k_filings(cik, days_back=30):
    """Fetch recent 8-K filings from SEC EDGAR."""
    if not cik:
        return []

    # Clean CIK (remove leading zeros for API, keep for display)
    cik_clean = cik.lstrip("0")

    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    html = fetch_url(url, is_sec=True)

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

        cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        for i, form in enumerate(forms[:50]):  # Check last 50 filings
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
        print(f"    Error parsing SEC data for CIK {cik}: {e}")
        return []


def check_company_dashboard(company, token):
    """Check company's treasury dashboard for holdings data."""
    ticker = company.get("ticker", "")
    data_url = company.get("dataUrl", "")
    dashboard_url = company.get("dashboardUrl", "")

    # Known dashboard data sources
    if ticker == "BNC" and data_url:
        # CEA Industries - has a data.js file with holdings
        html = fetch_url(data_url)
        if html:
            # Look for totalHoldings in the JavaScript
            match = re.search(r'totalHoldings:\s*(\d+)', html)
            if match:
                holdings = int(match.group(1))
                print(f"    Found in dashboard: {holdings:,} {token}")
                return {
                    "tokens": holdings,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "url": dashboard_url or data_url,
                    "source": "company_dashboard"
                }

    # Add more dashboard parsers here for other companies
    # Example pattern for future companies:
    # if ticker == "NEWCO" and dashboard_url:
    #     html = fetch_url(dashboard_url)
    #     # Parse holdings from HTML/JS
    #     pass

    return None


def update_company(company, token, days_back=14):
    """Update a single company's data."""
    ticker = company.get("ticker", "")
    cik = company.get("cik", "")
    current_holdings = company.get("tokens", 0)

    print(f"  Checking {ticker} ({token})...")

    updates = {}

    # First, check company dashboard if available
    dashboard_result = check_company_dashboard(company, token)
    if dashboard_result and dashboard_result["tokens"] != current_holdings:
        print(f"    ✓ Dashboard update: {current_holdings:,} → {dashboard_result['tokens']:,} {token}")
        updates["tokens"] = dashboard_result["tokens"]
        updates["lastUpdate"] = dashboard_result["date"]
        updates["alertUrl"] = dashboard_result["url"]
        updates["alertDate"] = dashboard_result["date"]
        updates["alertNote"] = "Dashboard update"
        return updates

    # Then check SEC 8-K filings
    if cik:
        filings = get_sec_8k_filings(cik, days_back=days_back)
        for filing in filings[:3]:  # Check last 3 filings
            result = check_8k_for_holdings(filing, token, current_holdings)
            if result:
                print(f"    ✓ SEC update: {current_holdings:,} → {result['tokens']:,} {token}")
                updates["tokens"] = result["tokens"]
                updates["lastUpdate"] = result["date"]
                updates["lastSecUpdate"] = result["date"]
                updates["alertUrl"] = result["url"]
                updates["alertDate"] = result["date"]
                desc = filing.get("description", "")[:40] or result.get("source", "")
                updates["alertNote"] = f"8-K: {desc}"
                break

    return updates


def load_data():
    """Load current data.json."""
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading data.json: {e}")
        return None


def save_data(data):
    """Save updated data.json."""
    # Update timestamp
    now = datetime.now()
    data["lastUpdated"] = now.isoformat()
    data["lastUpdatedDisplay"] = now.strftime("%b %d, %Y %I:%M %p EST")

    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nSaved updated data to {DATA_FILE}")


def calculate_days_back(last_updated_str):
    """Calculate days since last update, with a minimum of 1 day."""
    try:
        last_updated = datetime.fromisoformat(last_updated_str)
        days = (datetime.now() - last_updated).days + 1
        return max(1, min(days, 90))
    except (ValueError, TypeError):
        return 14


def main():
    """Main scraper entry point."""
    print("=" * 60)
    print("DAT Treasury Monitor - Auto-Update Scraper")
    print(f"Started at {datetime.now().isoformat()}")
    print("=" * 60)

    data = load_data()
    if not data:
        print("Failed to load data.json, exiting.")
        return

    # Calculate days_back from last update
    last_updated = data.get("lastUpdated", "")
    days_back = calculate_days_back(last_updated)

    last_date = last_updated[:10] if last_updated else "unknown"
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"\nChecking for changes from {last_date} to {today} ({days_back} days)")

    changes_made = False
    changes_list = []

    for token, companies in data.get("companies", {}).items():
        print(f"\n{'─' * 40}")
        print(f"Processing {token} companies...")

        for i, company in enumerate(companies):
            updates = update_company(company, token, days_back=days_back)

            if updates:
                # Calculate change if we have new token count
                if "tokens" in updates:
                    old_tokens = company.get("tokens", 0)
                    new_tokens = updates["tokens"]
                    if new_tokens != old_tokens:
                        updates["change"] = new_tokens - old_tokens
                        changes_made = True
                        changes_list.append({
                            "ticker": company["ticker"],
                            "token": token,
                            "old": old_tokens,
                            "new": new_tokens,
                            "change": new_tokens - old_tokens
                        })

                # Apply updates
                companies[i].update(updates)

    # Recalculate totals
    totals = {}
    for token, companies in data.get("companies", {}).items():
        totals[token] = sum(c.get("tokens", 0) for c in companies)
    data["totals"] = totals

    # Summary
    print(f"\n{'=' * 60}")
    if changes_made:
        print("CHANGES DETECTED:")
        for c in changes_list:
            sign = "+" if c["change"] > 0 else ""
            print(f"  {c['ticker']}: {c['old']:,} → {c['new']:,} ({sign}{c['change']:,} {c['token']})")
        save_data(data)
    else:
        print("No changes detected - data.json not modified")

    print(f"\nCompleted at {datetime.now().isoformat()}")
    print("=" * 60)


if __name__ == "__main__":
    main()
