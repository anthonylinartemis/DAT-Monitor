import requests
import json
import os

# The SEC requires a specific User-Agent header
# Format: "Name (email)"
HEADERS = {
    "User-Agent": "DAT-Monitor/1.0 (your-email@example.com)"
}

def fetch_sec_data():
    # Example URL for SEC filings
    url = "https://data.sec.gov/submissions/CIK0001067983.json"
    
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        
        # Save the result to your data.json file
        with open('data.json', 'w') as f:
            json.dump(data, f, indent=4)
        print("Successfully updated data.json")
        
    except Exception as e:
        print(f"Error fetching data: {e}")
        exit(1)

if __name__ == "__main__":
    fetch_sec_data()
