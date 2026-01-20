# DAT Treasury Monitor - Project Context

This document preserves important context about the project for future development sessions.

---

## Project Overview

**Purpose:** Track cryptocurrency holdings of publicly traded companies (Digital Asset Treasury companies) by scraping SEC EDGAR 8-K filings automatically.

**Live URL:** https://dat-monitor.vercel.app

**Owner:** Anthony Lin (anthony.lin@artetemisanalytics.xyz)

**GitHub:** https://github.com/anthonylinartemis/dat-monitor

---

## Current State (as of Jan 20, 2026)

### Holdings Data

| Token | Total Holdings | Top Company |
|-------|---------------|-------------|
| BTC | 807,150 | MSTR (709,715) |
| ETH | 5,837,531 | BMNR (4,203,036) |
| SOL | 15,617,254 | FWDI (6,921,342) |
| HYPE | 14,027,178 | PURR (12,600,000) |
| BNB | 515,054 | BNC (515,054) |

### Recent Updates (Jan 20, 2026)
- **MSTR:** 687,410 → 709,715 BTC (+22,305)
- **BMNR:** 4,167,768 → 4,203,036 ETH (+35,268)

---

## Key Technical Decisions

### 1. SEC EDGAR URL Format Fix

**Problem:** SEC filing index pages return 503 errors with old URL format.

**Solution:** Changed from:
```
/Archives/edgar/data/{cik}/{accession}-index.htm  # WRONG
```
To:
```
/Archives/edgar/data/{cik}/{accession}/{accession-with-dashes}-index.htm  # CORRECT
```

### 2. Inline XBRL Document Handling

**Problem:** SEC uses `/ix?doc=/Archives/...` wrapper URLs for XBRL documents.

**Solution:** Extract actual document path:
```python
if href.startswith("/ix?doc="):
    actual_path = href.replace("/ix?doc=", "")
```

### 3. Document Priority System

**Problem:** Main 8-K documents often don't contain holdings numbers; press releases (ex99) do.

**Solution:** Priority order:
1. `ex99-*.htm` (press releases) - Priority 0
2. Other exhibits - Priority 1
3. `*8k*.htm` (main document) - Priority 2
4. Other documents - Priority 3

### 4. Holdings Extraction Strategies

The scraper uses multiple strategies to find holdings:

1. **Pattern matching** - "aggregate BTC holdings: X"
2. **Keyword context** - Numbers within 200 chars of token keywords
3. **Validation ranges** - BTC: 1K-2M, ETH: 1K-50M, etc.

---

## File Purposes

| File | Purpose |
|------|---------|
| `index.html` | Single-page dashboard frontend (vanilla JS, no build) |
| `data.json` | Holdings data source (auto-updated by scraper) |
| `scripts/scraper.py` | SEC EDGAR scraper (runs via GitHub Actions) |
| `.github/workflows/update-data.yml` | Automation (3x daily on weekdays) |
| `README.md` | User-facing documentation |
| `SCRAPER.md` | Technical scraper documentation |
| `CONTEXT.md` | This file - project context for future sessions |

---

## Companies Tracked

### BTC Companies
| Ticker | Name | CIK | Notes |
|--------|------|-----|-------|
| MSTR | Strategy | 0001050446 | Largest BTC holder, weekly purchases |
| XXI | Twenty One Capital | 0002070457 | Backed by Tether, SoftBank |
| MTPLF | Metaplanet | (none) | Japan TSE - No SEC filings |
| ASST | Strive | 0001855631 | |
| NAKA | Nakamoto Holdings | 0001946573 | Nasdaq warning |
| ABTC | American Bitcoin | 0001755953 | fka Gryphon Digital |

### ETH Companies
| Ticker | Name | CIK | Notes |
|--------|------|-----|-------|
| BMNR | BitMine Immersion | 0001829311 | Largest ETH treasury (3.48% supply) |
| SBET | SharpLink Gaming | 0001811115 | Has live ETH dashboard |
| ETHM | Ether Machine | 0002028699 | |
| BTBT | Bit Digital | 0001710350 | |
| BTCS | BTCS | 0001521184 | |
| FGNX | FG Nexus | 0001591890 | |
| ETHZ | Ethzilla | 0001690080 | fka 180 Life Sciences |

### SOL Companies
| Ticker | Name | CIK | Notes |
|--------|------|-----|-------|
| FWDI | Forward Industries | 0000038264 | Largest SOL holder |
| HSDT | Solana Company | 0001610853 | fka Helius Medical |
| DFDV | DeFi Development | 0001805526 | dfdvSOL liquid staking |
| UPXI | Upexi | 0001839175 | High-yield strategy |
| STSS | Sharps Technology | 0001737995 | Coinbase validator partner |

### HYPE Companies
| Ticker | Name | CIK | Notes |
|--------|------|-----|-------|
| PURR | Hyperliquid Strategies | 0001106838 | fka Sonnet Bio |
| HYPD | Hyperion DeFi | 0001682639 | fka Eyenovia |

### BNB Companies
| Ticker | Name | CIK | Notes |
|--------|------|-----|-------|
| BNC | CEA Industries | 0001482541 | |

---

## Automation Schedule

GitHub Actions runs at:
- 10:00 AM ET (15:00 UTC)
- 2:00 PM ET (19:00 UTC)
- 6:00 PM ET (23:00 UTC)

Only on weekdays (Mon-Fri) since SEC filings are rare on weekends.

---

## Environment Setup

### Required Secret
```
SEC_USER_AGENT=DAT-Monitor/1.0 (anthony.lin@artetemisanalytics.xyz)
```

### Local Development
```bash
export SEC_USER_AGENT="DAT-Monitor/1.0 (anthony.lin@artetemisanalytics.xyz)"
pip install requests beautifulsoup4 lxml
python scripts/scraper.py
```

---

## Common Issues & Fixes

### Issue: "No changes detected" but there should be
1. Check SEC EDGAR for recent 8-K filings
2. Verify the filing contains a press release (ex99-*.htm)
3. Check if holdings number format matches extraction patterns

### Issue: Wrong holdings number extracted
1. The scraper prioritizes ex99 files - verify they exist
2. Check if another number in the document matches the pattern
3. May need to add company-specific handling

### Issue: 503 errors from SEC
1. SEC servers may be busy - retry later
2. Check SEC_USER_AGENT is set correctly
3. Rate limiting is already conservative (0.15s delay)

---

## Future Improvements

Potential enhancements:
1. Add email/Slack notifications on changes
2. Track historical data over time
3. Add more token types (XRP, ADA, etc.)
4. Improve regex patterns for edge cases
5. Add company-specific parsers for unusual formats

---

## Contact

- **Owner:** Anthony Lin
- **Email:** anthony.lin@artetemisanalytics.xyz
- **Company:** Artemis Analytics (artemisanalytics.com)
