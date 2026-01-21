# DAT Treasury Extraction Examples

These JSON files demonstrate the clean structured data output from the DAT Treasury Monitor extraction pipeline.

## Pipeline Overview

```
SEC EDGAR API → 8-K Filing → Parse HTML → Extract Holdings → Structured JSON
```

## Example Extractions

### MSTR (Bitcoin)
- **File:** `mstr_extraction.json`
- **Company:** Strategy (formerly MicroStrategy)
- **Asset:** BTC (Bitcoin)
- **Holdings:** 709,715 BTC
- **Source:** SEC 8-K filing (2026-01-20)

### BMNR (Ethereum)
- **File:** `bmnr_eth_extraction.json`
- **Company:** BitMine Immersion Technologies
- **Asset:** ETH (Ethereum)
- **Holdings:** 4,203,036 ETH
- **Source:** SEC 8-K filing (2026-01-20)

## JSON Schema

```json
{
  "extraction_info": {
    "timestamp": "ISO 8601 timestamp",
    "scraper": "FinstatSecScraper",
    "method": "finstat_sec"
  },
  "source": {
    "type": "SEC EDGAR 8-K",
    "filing_date": "YYYY-MM-DD",
    "url": "SEC filing URL",
    "accession_number": "SEC accession number",
    "form_type": "8-K"
  },
  "company": {
    "ticker": "Stock ticker",
    "name": "Company name",
    "legal_name": "Legal entity name",
    "cik": "SEC CIK number"
  },
  "holdings": {
    "asset": "BTC|ETH|SOL|HYPE|BNB",
    "asset_name": "Full asset name",
    "amount": 123456,
    "formatted": "123,456"
  },
  "change_analysis": {
    "previous_amount": 123456,
    "current_amount": 123456,
    "difference": 0,
    "change_detected": false
  },
  "document_metadata": {
    "size_bytes": 374910,
    "sha256": "document hash",
    "text_characters": 94903
  }
}
```

## How to Generate

```bash
# Run extraction for a specific company
python3 scripts/scraper.py --ticker MSTR --dry-run

# Run extraction for all companies
python3 scripts/scraper.py --dry-run
```
