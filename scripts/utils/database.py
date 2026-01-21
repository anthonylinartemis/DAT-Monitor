import os
from dotenv import load_dotenv
from supabase import create_client, Client
from typing import Optional

# This line loads your keys from the .env file you just made
load_dotenv()

class DATDatabase:
    def __init__(self):
        # These look for the names inside your .env file
        url: str = os.environ.get("SUPABASE_URL")
        key: str = os.environ.get("SUPABASE_KEY")
        
        if not url or not key:
            raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY in .env file")
            
        self.supabase: Client = create_client(url, key)

    def get_company_id(self, ticker: str) -> Optional[int]:
        """Finds the ID number for a company using its ticker (like MSTR)."""
        result = self.supabase.table("companies").select("id").eq("ticker", ticker).execute()
        # Returns the ID if found, otherwise returns None
        return result.data[0]["id"] if result.data else None

    def save_holding(self, ticker: str, tokens: float, change: float, filing_date: str, source_url: str):
        """Adds a new historical row to the holdings table in Supabase."""
        company_id = self.get_company_id(ticker)
        
        if not company_id:
            print(f"⚠️ Error: {ticker} not found in database 'companies' table. Please run init_db.py first.")
            return

        # This matches the 'Professional' SQL columns we set up in Supabase
        data = {
            "company_id": company_id,
            "token_count": tokens,
            "change_amount": change,
            "filing_date": filing_date,
            "source_url": source_url
        }
        
        # This actually sends the data to the web
        self.supabase.table("holdings").insert(data).execute()
        print(f"✅ Successfully saved {ticker} holdings to Supabase history.")

# This makes 'db' available to your scraper
db = DATDatabase()