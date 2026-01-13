# DAT Treasury Monitor

Real-time tracking of Digital Asset Treasury (DAT) companies and their crypto holdings.

**Live Dashboard:** [dat-monitor.vercel.app](https://dat-monitor.vercel.app)

## Features

- 📊 Track 21 DAT companies across BTC, ETH, SOL, HYPE, BNB
- 🔔 NEW alert badges for recent press releases
- 🔄 Auto-updates 3x daily via GitHub Actions
- 📈 SEC 8-K and IR page links

## Setup Auto-Updates

### 1. Add GitHub Secret

1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `SEC_USER_AGENT`
4. Value: `DAT-Monitor/1.0 (your-email@example.com)`

### 2. Enable GitHub Actions

1. Go to your repo → **Actions** tab
2. If prompted, click **"I understand my workflows, go ahead and enable them"**
3. The workflow will now run automatically at 10am, 2pm, 6pm ET on weekdays

### 3. Manual Trigger

You can also manually trigger an update:
1. Go to **Actions** → **Update DAT Data**
2. Click **Run workflow** → **Run workflow**

## File Structure

```
├── index.html           # Dashboard frontend
├── data.json            # Holdings data (auto-updated)
├── scripts/
│   └── scraper.py       # SEC EDGAR scraper
├── requirements.txt     # Python dependencies
└── .github/
    └── workflows/
        └── update-data.yml  # Auto-update cron job
```

## Powered by Artemis

[artemisanalytics.com](https://www.artemisanalytics.com)
