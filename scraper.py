#!/usr/bin/env python3
"""
DAT Treasury Monitor - Auto-Update Scraper
Fetches latest holdings data from SEC EDGAR 8-K filings and IR pages.
"""

import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

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
        print(f"  Error fetching {url}: {e}")
        return None


def parse_token_amount(text):
    """Extract token amount from text like '687,410 BTC' or '4.17 million ETH'."""
    text = text.lower().replace(",", "").replace(" ", "")
    
    # Match patterns like "687410btc" or "4.17millioneth"
    patterns = [
        (r"(\d+\.?\d*)\s*million", 1_000_000),
        (r"(\d+\.?\d*)\s*m(?:illion)?", 1_000_000),
        (r"(\d+\.?\d*)\s*thousand", 1_000),
        (r"(\d+\.?\d*)\s*k", 1_000),
        (r"(\d+\.?\d*)", 1),
    ]
    
    for pattern, multiplier in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                value = float(match.group(1)) * multiplier
                return int(value)
            except ValueError:
                continue
    return None


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
                filings.append({
                    "form": form,
                    "date": dates[i],
                    "accession": accessions[i].replace("-", ""),
                    "description": descriptions[i] if i < len(descriptions) else "",
                    "url": f"{SEC_BASE}/Archives/edgar/data/{cik_clean}/{accessions[i].replace('-', '')}"
                })
        
        return filings
    except (json.JSONDecodeError, KeyError) as e:
        print(f"  Error parsing SEC data for CIK {cik}: {e}")
        return []


def check_8k_for_holdings(filing, token):
    """Check an 8-K filing for token holdings information."""
    # Fetch the filing index page
    index_url = f"{filing['url']}-index.htm"
    html = fetch_url(index_url, is_sec=True)
    
    if not html:
        return None
    
    soup = BeautifulSoup(html, "lxml")
    
    # Find the main 8-K document (usually .htm file)
    doc_link = None
    for link in soup.find_all("a"):
        href = link.get("href", "")
        if href.endswith(".htm") and "8k" in href.lower():
            doc_link = f"{SEC_BASE}{href}" if href.startswith("/") else f"{filing['url']}/{href}"
            break
    
    if not doc_link:
        return None
    
    # Fetch and parse the document
    doc_html = fetch_url(doc_link, is_sec=True)
    if not doc_html:
        return None
    
    doc_soup = BeautifulSoup(doc_html, "lxml")
    text = doc_soup.get_text().lower()
    
    # Look for token holdings mentions
    token_patterns = {
        "BTC": [r"bitcoin", r"btc"],
        "ETH": [r"ethereum", r"ether(?!eum)", r"eth\b"],
        "SOL": [r"solana", r"sol\b"],
        "HYPE": [r"hyperliquid", r"hype\b"],
        "BNB": [r"bnb", r"binance\s*coin"],
    }
    
    patterns = token_patterns.get(token, [])
    for pattern in patterns:
        if re.search(pattern, text):
            # Found mention of the token, try to extract amount
            # Look for patterns like "holds X BTC" or "X bitcoin"
            amount_patterns = [
                rf"(\d[\d,]*\.?\d*)\s*(?:million\s*)?{pattern}",
                rf"hold[s]?\s*(\d[\d,]*\.?\d*)\s*(?:million\s*)?",
                rf"total[^\d]*(\d[\d,]*\.?\d*)\s*(?:million\s*)?{pattern}",
            ]
            
            for amt_pattern in amount_patterns:
                match = re.search(amt_pattern, text)
                if match:
                    amount = parse_token_amount(match.group(1))
                    if amount and amount > 100:  # Sanity check
                        return {
                            "tokens": amount,
                            "date": filing["date"],
                            "url": doc_link,
                        }
    
    return None


def check_ir_page(ir_url, token):
    """Check IR/news page for recent press releases about holdings."""
    html = fetch_url(ir_url)
    if not html:
        return None
    
    soup = BeautifulSoup(html, "lxml")
    
    # Look for press release links
    pr_links = []
    for link in soup.find_all("a"):
        href = link.get("href", "")
        text = link.get_text().lower()
        
        # Look for links mentioning holdings, treasury, or the token
        keywords = ["holding", "treasury", "acqui", token.lower(), "purchase"]
        if any(kw in text for kw in keywords):
            full_url = href if href.startswith("http") else f"{ir_url.rstrip('/')}/{href.lstrip('/')}"
            pr_links.append({"url": full_url, "text": text[:100]})
    
    return pr_links[:5]  # Return top 5 potential links


def update_company(company, token):
    """Update a single company's data."""
    ticker = company.get("ticker", "")
    cik = company.get("cik", "")
    
    print(f"  Checking {ticker} ({token})...")
    
    updates = {}
    
    # Check SEC 8-K filings
    if cik:
        filings = get_sec_8k_filings(cik, days_back=14)
        for filing in filings[:3]:  # Check last 3 filings
            result = check_8k_for_holdings(filing, token)
            if result:
                print(f"    Found 8-K update: {result['tokens']} {token}")
                updates["tokens"] = result["tokens"]
                updates["lastUpdate"] = result["date"]
                updates["lastSecUpdate"] = result["date"]
                updates["alertUrl"] = result["url"]
                updates["alertDate"] = result["date"]
                updates["alertNote"] = f"8-K filing: {filing['description'][:50]}"
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
    
    print(f"Saved updated data to {DATA_FILE}")


def main():
    """Main scraper entry point."""
    print("=" * 50)
    print("DAT Treasury Monitor - Auto-Update Scraper")
    print(f"Started at {datetime.now().isoformat()}")
    print("=" * 50)
    
    data = load_data()
    if not data:
        print("Failed to load data.json, exiting.")
        return
    
    changes_made = False
    
    for token, companies in data.get("companies", {}).items():
        print(f"\nProcessing {token} companies...")
        
        for i, company in enumerate(companies):
            updates = update_company(company, token)
            
            if updates:
                # Calculate change if we have new token count
                if "tokens" in updates:
                    old_tokens = company.get("tokens", 0)
                    new_tokens = updates["tokens"]
                    if new_tokens != old_tokens:
                        updates["change"] = new_tokens - old_tokens
                        changes_made = True
                
                # Apply updates
                companies[i].update(updates)
    
    # Recalculate totals
    totals = {}
    for token, companies in data.get("companies", {}).items():
        totals[token] = sum(c.get("tokens", 0) for c in companies)
    data["totals"] = totals
    
    # Save if changes were made (or always save to update timestamp)
    save_data(data)
    
    print("\n" + "=" * 50)
    print(f"Completed at {datetime.now().isoformat()}")
    print(f"Changes detected: {changes_made}")
    print("=" * 50)


if __name__ == "__main__":
    main()
