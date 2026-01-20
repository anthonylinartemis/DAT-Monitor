# DAT Treasury Monitor - Scraper Documentation

This document provides comprehensive documentation for the SEC EDGAR scraper that powers the DAT Treasury Monitor.

---

## Table of Contents

1. [Overview](#overview)
2. [How It Works](#how-it-works)
3. [Running the Scraper](#running-the-scraper)
4. [Configuration](#configuration)
5. [SEC EDGAR Integration](#sec-edgar-integration)
6. [Document Parsing](#document-parsing)
7. [Adding New Companies](#adding-new-companies)
8. [Adding New Tokens](#adding-new-tokens)
9. [Troubleshooting](#troubleshooting)
10. [Technical Reference](#technical-reference)

---

## Overview

The scraper (`scripts/scraper.py`) automatically fetches cryptocurrency holdings data from SEC EDGAR 8-K filings. It:

- Monitors 21+ publicly traded companies
- Extracts holdings from press releases (ex99 exhibits)
- Tracks changes over time
- Updates `data.json` for the frontend dashboard

---

## How It Works

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        SCRAPER FLOW                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. LOAD DATA                                                   │
│     └── Read data.json                                          │
│     └── Calculate days since last update                        │
│                                                                 │
│  2. FOR EACH COMPANY                                            │
│     ├── Fetch recent 8-K filings from SEC EDGAR                │
│     ├── For each filing:                                        │
│     │   ├── Get document list (index page)                     │
│     │   ├── Prioritize ex99-*.htm (press releases)             │
│     │   ├── Extract holdings number                             │
│     │   └── Validate and update if changed                      │
│     └── Track changes                                           │
│                                                                 │
│  3. SAVE RESULTS                                                │
│     └── Update data.json (only if changes detected)            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Detailed Process

#### Step 1: Load Existing Data
```python
data = load_data()  # Reads data.json
days_back = calculate_days_back(data["lastUpdated"])
```

The scraper calculates how many days to look back based on the last update timestamp. This ensures it only checks relevant recent filings.

#### Step 2: Query SEC EDGAR
For each company with a CIK (SEC identifier):

```python
filings = get_sec_8k_filings(cik, days_back=days_back)
```

This queries: `https://data.sec.gov/submissions/CIK{cik}.json`

#### Step 3: Get Filing Documents
```python
documents = get_filing_documents(filing)
```

This fetches the filing index page and extracts all document links:
- `ex99-*.htm` - Press releases (highest priority)
- `ex*.htm` - Other exhibits
- `*8k*.htm` - Main 8-K document
- Other documents

#### Step 4: Extract Holdings
```python
holdings = find_holdings_in_text(text, token, current_holdings)
```

Uses multiple strategies:
1. **Pattern matching** - Looks for "aggregate holdings", "total BTC", etc.
2. **Keyword context** - Finds numbers near token keywords
3. **Validation** - Ensures number is reasonable for the token type

#### Step 5: Save Changes
Only updates `data.json` if actual changes were detected.

---

## Running the Scraper

### Prerequisites

```bash
pip install requests beautifulsoup4 lxml
```

### Basic Usage

```bash
# Set SEC User-Agent (required)
export SEC_USER_AGENT="YourName/1.0 (your.email@example.com)"

# Run scraper
python scripts/scraper.py
```

### Example Output

```
============================================================
DAT Treasury Monitor - Auto-Update Scraper
Started at 2026-01-20T17:11:15
============================================================

Checking for changes from 2026-01-19 to 2026-01-20 (2 days)

────────────────────────────────────────
Processing BTC companies...
  Checking MSTR (BTC)...
    Found in mstr-20260105.htm: 709,715 BTC
    ✓ Update: 687,410 → 709,715 BTC
  Checking XXI (BTC)...
  ...

============================================================
CHANGES DETECTED:
  MSTR: 687,410 → 709,715 (+22,305 BTC)
  BMNR: 4,167,768 → 4,203,036 (+35,268 ETH)

Saved updated data to data.json
============================================================
```

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SEC_USER_AGENT` | **Yes** | Your contact info for SEC API |

**SEC User-Agent Format:**
```
YourAppName/Version (your.email@example.com)
```

Example:
```bash
export SEC_USER_AGENT="DAT-Monitor/1.0 (anthony.lin@artetemisanalytics.xyz)"
```

### Internal Configuration

Located at the top of `scraper.py`:

```python
# Rate limiting
SEC_RATE_LIMIT = 0.15  # seconds between SEC requests (conservative)

# Token keywords for detection
TOKEN_KEYWORDS = {
    "BTC": ["bitcoin", "btc"],
    "ETH": ["ethereum", "ether", "eth"],
    "SOL": ["solana"],
    "HYPE": ["hyperliquid", "hype"],
    "BNB": ["bnb", "binance coin", "binance"],
}
```

---

## SEC EDGAR Integration

### API Endpoints Used

| Endpoint | Purpose | Example |
|----------|---------|---------|
| `data.sec.gov/submissions/CIK{cik}.json` | Get company filings list | [MSTR Filings](https://data.sec.gov/submissions/CIK0001050446.json) |
| `sec.gov/Archives/edgar/data/{cik}/{accession}/` | Access filing documents | Filing folder |
| `sec.gov/Archives/edgar/data/{cik}/{accession}/{accession}-index.htm` | Filing index page | Document list |

### Rate Limiting

SEC requires:
- Maximum 10 requests per second
- Valid User-Agent with contact information

The scraper uses a **0.15 second delay** between requests (conservative) to avoid rate limiting.

### Finding a Company's CIK

1. Go to [SEC EDGAR Company Search](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany)
2. Search by company name or ticker
3. The CIK is displayed (10 digits with leading zeros)

Example: MicroStrategy/Strategy → CIK: `0001050446`

---

## Document Parsing

### Priority Order

The scraper checks documents in this order:

| Priority | Document Type | Description |
|----------|---------------|-------------|
| 1 | `ex99-*.htm` | Press releases (most reliable) |
| 2 | `ex*.htm` | Other exhibits |
| 3 | `*8k*.htm` | Main 8-K document |
| 4 | Other | Additional documents |

### Holdings Extraction Strategies

#### Strategy 1: Pattern Matching
Looks for explicit holdings statements:
- "aggregate BTC holdings: 709,715"
- "holds 4,203,036 ETH"
- "total bitcoin: 500,000"

#### Strategy 2: Keyword Context
Finds numbers within 200 characters of token keywords:
- Searches for "bitcoin", "btc", "ethereum", "eth", etc.
- Extracts nearby numbers
- Validates against reasonable ranges

#### Strategy 3: Proximity to Current Holdings
If current holdings are known, looks for numbers within 50-200% of that value.

### Number Formats Supported

- `709,715` - Standard comma-separated
- `4.203 million` - Million notation
- `4.2M` - Abbreviated million
- `500K` - Abbreviated thousand

---

## Adding New Companies

### Step 1: Find the CIK

1. Go to [SEC EDGAR](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany)
2. Search for the company
3. Copy the 10-digit CIK (with leading zeros)

### Step 2: Add to data.json

Add a new entry under the appropriate token:

```json
{
  "companies": {
    "BTC": [
      // ... existing companies ...
      {
        "ticker": "NEWCO",
        "name": "New Company Name",
        "notes": "Optional description",
        "tokens": 0,
        "lastUpdate": "",
        "change": 0,
        "cik": "0001234567",
        "irUrl": "https://company-investor-relations.com"
      }
    ]
  }
}
```

### Step 3: Test

```bash
python scripts/scraper.py
```

The scraper will attempt to fetch the company's holdings from recent 8-K filings.

### Required Fields

| Field | Required | Description |
|-------|----------|-------------|
| `ticker` | Yes | Stock ticker symbol |
| `name` | Yes | Company name |
| `tokens` | Yes | Current token holdings (start with 0) |
| `cik` | Yes | SEC CIK number |
| `irUrl` | Yes | Investor relations URL |
| `notes` | No | Optional description |
| `lastUpdate` | No | Last update date (auto-filled) |
| `change` | No | Last change amount (auto-filled) |

---

## Adding New Tokens

### Step 1: Add Token Keywords

In `scraper.py`, add to `TOKEN_KEYWORDS`:

```python
TOKEN_KEYWORDS = {
    "BTC": ["bitcoin", "btc"],
    "ETH": ["ethereum", "ether", "eth"],
    "SOL": ["solana"],
    "HYPE": ["hyperliquid", "hype"],
    "BNB": ["bnb", "binance coin", "binance"],
    # Add new token:
    "NEWTOKEN": ["newtoken", "nt", "new token"],
}
```

### Step 2: Add Validation Range

In `find_holdings_in_text()`, add validation:

```python
elif token == "NEWTOKEN" and 1000 <= num <= 100_000_000:
    return num
```

### Step 3: Add to data.json

```json
{
  "companies": {
    "NEWTOKEN": []
  },
  "totals": {
    "NEWTOKEN": 0
  }
}
```

### Step 4: Update Frontend (index.html)

Add the token to the `TOKENS` array and `TOKEN_LABELS`:

```javascript
const TOKENS = ['BTC', 'ETH', 'SOL', 'HYPE', 'BNB', 'NEWTOKEN'];
const TOKEN_LABELS = {
    BTC: 'Bitcoin',
    ETH: 'Ethereum',
    // ...
    NEWTOKEN: 'New Token Name'
};
```

Add CSS color variable:

```css
:root {
    --newtoken: #ff00ff;  /* Your color */
}
```

---

## Troubleshooting

### "No changes detected"

**Cause:** No new holdings found in recent filings.

**Solutions:**
1. Check if the company filed an 8-K recently
2. Verify the filing contains holdings data
3. Manually check the SEC filing

### "Error fetching URL: 503"

**Cause:** SEC servers temporarily unavailable.

**Solutions:**
1. Wait a few minutes and retry
2. Check [SEC system status](https://www.sec.gov/status)

### "Error fetching URL: 403"

**Cause:** Missing or invalid SEC User-Agent.

**Solution:**
```bash
export SEC_USER_AGENT="YourName/1.0 (your.email@example.com)"
```

### Holdings not updating for a company

**Possible causes:**
1. **Wrong CIK** - Verify on SEC EDGAR
2. **No recent 8-K** - Company hasn't filed
3. **Different format** - Press release uses unusual format

**Debug steps:**
1. Check SEC EDGAR for recent filings
2. Look at the press release (ex99-*.htm) manually
3. Verify holdings number is present in the document

### Rate limiting errors

**Cause:** Too many requests to SEC.

**Solution:** The scraper already uses conservative rate limiting. If issues persist, increase `SEC_RATE_LIMIT`:

```python
SEC_RATE_LIMIT = 0.2  # Increase from 0.15 to 0.2 seconds
```

---

## Technical Reference

### File Structure

```
scripts/
└── scraper.py          # Main scraper script
    ├── rate_limit_sec()           # Enforce SEC rate limits
    ├── fetch_url()                # HTTP requests with error handling
    ├── extract_numbers_from_text()# Extract candidate numbers
    ├── find_holdings_in_text()    # Multi-strategy holdings detection
    ├── get_filing_documents()     # Get documents from filing
    ├── check_8k_for_holdings()    # Check filing for holdings
    ├── get_sec_8k_filings()       # Fetch recent 8-K filings
    ├── update_company()           # Update single company
    ├── load_data()                # Load data.json
    ├── save_data()                # Save data.json
    ├── calculate_days_back()      # Calculate lookback period
    └── main()                     # Entry point
```

### Dependencies

```
requests>=2.28.0      # HTTP requests
beautifulsoup4>=4.11  # HTML parsing
lxml>=4.9             # Fast XML/HTML parser
```

### Data Flow

```
SEC EDGAR API
     │
     ▼
get_sec_8k_filings() ─── Fetch filing list
     │
     ▼
get_filing_documents() ─── Get document URLs
     │
     ▼
fetch_url() ─── Download documents
     │
     ▼
find_holdings_in_text() ─── Extract holdings
     │
     ▼
update_company() ─── Update company record
     │
     ▼
save_data() ─── Write to data.json
     │
     ▼
GitHub Actions ─── Auto-commit changes
     │
     ▼
Vercel ─── Deploy updated dashboard
```

---

## Support

For issues or questions:
- Open a GitHub issue
- Contact: anthony.lin@artetemisanalytics.xyz
