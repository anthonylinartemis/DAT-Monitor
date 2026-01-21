# DAT Monitor - Changelog & Technical Documentation

## Session: January 20, 2026

### Overview
Integrated Supabase database for persistent storage of treasury holdings data, with automatic change tracking and Slack notifications.

---

## Changes Made

### 1. Supabase Database Integration
**Files:** `scripts/utils/database.py`, `init_db.py`

- Added `DATDatabase` class for Supabase connection
- `get_company_id(ticker)` - Look up company by ticker symbol
- `get_latest_holding(company_id)` - Fetch most recent holding for change calculation
- `holding_exists(company_id, filing_date)` - Duplicate prevention
- `save_holding(ticker, tokens, filing_date, source_url)` - Save with auto-calculated change
- `get_db()` - Lazy initialization with error handling

**Schema (Supabase tables):**
```
companies: id, ticker, name, primary_token, cik, ir_url
holdings: id, company_id, token_count, token_change, filing_date, source_url, captured_at
```

### 2. Scraper Integration
**File:** `scripts/scraper.py`

- Imports `get_db` from database module
- On holdings change detection:
  1. Saves to `data.json` (local backup)
  2. Saves to Supabase (primary storage)
  3. Auto-calculates `token_change` from previous filing in Supabase
- Wrapped in try/except - DB failures don't crash scraper

### 3. GitHub Actions Workflow
**File:** `.github/workflows/update-data.yml`

**Schedule:** 10am, 2pm, 6pm ET on weekdays (cron: `0 15,19,23 * * 1-5`)

**Environment secrets required:**
- `SEC_USER_AGENT` - Required for SEC EDGAR API
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_KEY` - Supabase anon/public key
- `SLACK_WEBHOOK_URL` - For change notifications

**Features:**
- Auto-commits `data.json` changes
- Sends Slack notification when holdings change
- Manual trigger via `workflow_dispatch`

### 4. Slack Notifications
**Trigger:** Only when `CHANGES DETECTED` in scraper output

**Message includes:**
- Header: "DAT Holdings Update Detected"
- Change details (ticker, old → new, delta)
- Timestamp
- Link to GitHub Actions run

---

## How It Works

### Data Flow
```
SEC EDGAR / Company Dashboards
         ↓
    scraper.py (detects changes)
         ↓
    ┌────┴────┐
    ↓         ↓
data.json   Supabase
(backup)    (primary)
         ↓
  Slack notification
  (if changes detected)
```

### Change Calculation
When a new holding is saved:
1. Query Supabase for latest holding of that company
2. Calculate: `token_change = new_tokens - previous_tokens`
3. First entry: `token_change = token_count` (baseline)

---

## Running Locally

```bash
# Set environment variables
export SEC_USER_AGENT='DAT-Monitor/1.0 (your-email@example.com)'

# Run full scraper
python3 scripts/scraper.py

# Run for single ticker
python3 scripts/scraper.py --ticker MSTR

# Dry run (no saves)
python3 scripts/scraper.py --dry-run
```

---

## Companies Tracked (21)

| Token | Tickers |
|-------|---------|
| BTC | MSTR, XXI, MTPLF, ASST, NAKA, ABTC |
| ETH | BMNR, SBET, ETHM, BTBT, BTCS, FGNX, ETHZ |
| SOL | FWDI, HSDT, DFDV, UPXI, STSS |
| HYPE | PURR, HYPD |
| BNB | BNC |

---

## Commits (this session)

1. `ec5fa10` - Add Supabase database integration for holdings tracking
2. `b5f6a38` - Integrate Supabase database into scraper
3. `4f87cb8` - Fix token_change column and auto-calculate from previous filing
4. `bd4f65a` - Add Supabase secrets to GitHub Actions workflow
5. `7409fa4` - Add Slack notifications for holdings changes
6. `3db7284` - Fix Slack notification secret reference

---

## Notes

- `.env` file must be in project root (not `.claude/`)
- Supabase column is `token_change` (not `change_amount`)
- GitHub Actions runs on GitHub servers - your computer can be off
- Duplicate entries are skipped (same company + filing_date)
