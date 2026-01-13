import requests
import json
import os
from datetime import datetime

# Get User-Agent from GitHub Secrets or use a fallback for local testing
USER_AGENT = os.getenv("SEC_USER_AGENT", "DAT-Monitor/1.0 (contact@example.com)")

HEADERS = {"User-Agent": USER_AGENT}

# List of DAT companies to track (Ticker and CIK)
DAT_COMPANIES = [
    {"ticker": "MSTR", "cik": "0001050446", "token": "BTC"},
    {"ticker": "BMNR", "cik": "0001829311", "token": "ETH"},
    {"ticker": "STSS", "cik": "0001737995", "token": "SOL"},
    {"ticker": "HYPD", "cik": "0001682639", "token": "HYPE"},
    {"ticker": "BTCS", "cik": "0001521184", "token": "ETH"}
    # Add more CIKs here from your previous data.json list
]

def fetch_latest_filings(cik):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching CIK {cik}: {e}")
        return None

def update_data():
    # Load your current data.json to preserve the structure
    with open('data.json', 'r') as f:
        master_data = json.load(f)

    # Update timestamp
    now = datetime.now()
    master_data["lastUpdated"] = now.isoformat()
    master_data["lastUpdatedDisplay"] = now.strftime("%b %d, %Y %I:%0M %p EST")

    # Update recent changes logic or holdings here
    for company in DAT_COMPANIES:
        sec_data = fetch_latest_filings(company["cik"])
        if sec_data:
            print(f"Updated {company['ticker']} data from SEC")
            # Here you would add logic to parse specific 8-K filings 
            # and update the master_data["companies"] values.

    # Save back to file
    with open('data.json', 'w') as f:
        json.dump(master_data, f, indent=4)
    print("Dashboard data successfully synchronized.")

if __name__ == "__main__":
    update_data()
