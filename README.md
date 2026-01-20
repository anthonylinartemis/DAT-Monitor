# DAT Treasury Monitor

A real-time dashboard tracking cryptocurrency holdings of publicly traded Digital Asset Treasury (DAT) companies. Automatically scrapes SEC EDGAR 8-K filings to monitor Bitcoin, Ethereum, Solana, Hyperliquid, and BNB holdings.

**Live Dashboard:** [dat-monitor.vercel.app](https://dat-monitor.vercel.app)

---

## Features

- **Real-time Holdings Data** - Tracks 21+ publicly traded companies holding crypto
- **Automated SEC Scraping** - Fetches data from SEC EDGAR 8-K filings 3x daily
- **Multi-Token Support** - BTC, ETH, SOL, HYPE, BNB
- **Change Tracking** - Shows +/- changes from previous updates
- **Alert Badges** - Highlights recent press releases and filings
- **Direct Links** - Quick access to SEC filings and IR pages

---

## Companies Tracked

| Token | Companies | Description |
|-------|-----------|-------------|
| **BTC** | MSTR, XXI, MTPLF, ASST, NAKA, ABTC | Bitcoin treasury companies |
| **ETH** | BMNR, SBET, ETHM, BTBT, BTCS, FGNX, ETHZ | Ethereum treasury companies |
| **SOL** | FWDI, HSDT, DFDV, UPXI, STSS | Solana treasury companies |
| **HYPE** | PURR, HYPD | Hyperliquid treasury companies |
| **BNB** | BNC | Binance Coin treasury companies |

---

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/dat-monitor.git
cd dat-monitor
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the Scraper

```bash
# Set your SEC User-Agent (required by SEC)
export SEC_USER_AGENT="YourName/1.0 (your.email@example.com)"

# Run the scraper
python scripts/scraper.py
```

### 4. View the Dashboard

Open `index.html` in your browser, or deploy to Vercel/Netlify.

---

## Project Structure

```
dat-monitor/
├── index.html              # Frontend dashboard (single-page app)
├── data.json               # Holdings data (auto-updated by scraper)
├── scripts/
│   └── scraper.py          # SEC EDGAR scraper
├── .github/
│   └── workflows/
│       └── update-data.yml # GitHub Actions automation
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── SCRAPER.md              # Detailed scraper documentation
└── .env.example            # Environment variables template
```

---

## Automation with GitHub Actions

The scraper runs automatically via GitHub Actions on weekdays at **10am, 2pm, and 6pm ET**.

### Setup (One-Time):

1. **Add GitHub Secret:**
   - Go to repo **Settings** → **Secrets and variables** → **Actions**
   - Click **New repository secret**
   - Name: `SEC_USER_AGENT`
   - Value: `DAT-Monitor/1.0 (your.email@example.com)`

2. **Enable Actions:**
   - Go to **Actions** tab
   - Enable workflows if prompted

3. **Manual Trigger:**
   - Go to **Actions** → **Update DAT Data**
   - Click **Run workflow**

---

## Deployment

### Vercel (Recommended)

1. Push your repo to GitHub
2. Go to [vercel.com](https://vercel.com)
3. Import your GitHub repository
4. Deploy (no configuration needed)

The dashboard auto-updates when `data.json` changes.

---

## Documentation

- **[SCRAPER.md](./SCRAPER.md)** - Detailed scraper documentation, how it works, and how to modify it
- **[data.json](./data.json)** - Current holdings data

---

## Data Format

```json
{
  "lastUpdated": "2026-01-20T17:11:20",
  "companies": {
    "BTC": [
      {
        "ticker": "MSTR",
        "name": "Strategy",
        "tokens": 709715,
        "lastUpdate": "2026-01-20",
        "change": 22305,
        "cik": "0001050446"
      }
    ]
  },
  "totals": {
    "BTC": 807150,
    "ETH": 5837531
  }
}
```

---

## Adding a New Company

1. Find the company's CIK on [SEC EDGAR](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany)
2. Add entry to `data.json` under the appropriate token
3. Run the scraper to fetch initial data

See **[SCRAPER.md](./SCRAPER.md)** for detailed instructions.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "No changes detected" | Normal if no new filings; check SEC for recent 8-Ks |
| "Error 503" | SEC servers busy; retry in a few minutes |
| "Module not found" | Run `pip install -r requirements.txt` |
| Holdings not updating | Verify CIK is correct; check filing has press release |

---

## License

MIT License

---

## Credits

- **Data Source:** [SEC EDGAR](https://www.sec.gov/edgar)
- **Powered by:** [Artemis Analytics](https://www.artemisanalytics.com)
- **Contact:** anthony.lin@artetemisanalytics.xyz
