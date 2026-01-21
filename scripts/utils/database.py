import os
from dotenv import load_dotenv
from supabase import create_client, Client
from typing import Optional
from pathlib import Path

# Load .env from project root
load_dotenv(Path(__file__).parent.parent.parent / ".env")

class DATDatabase:
    def __init__(self):
        url: str = os.environ.get("SUPABASE_URL")
        key: str = os.environ.get("SUPABASE_KEY")

        if not url or not key:
            raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY in .env file")

        self.supabase: Client = create_client(url, key)

    def get_company_id(self, ticker: str) -> Optional[int]:
        """Finds the ID number for a company using its ticker."""
        result = self.supabase.table("companies").select("id").eq("ticker", ticker).execute()
        return result.data[0]["id"] if result.data else None

    def holding_exists(self, company_id: int, filing_date: str) -> bool:
        """Check if a holding record already exists for this company and date."""
        result = (
            self.supabase.table("holdings")
            .select("id")
            .eq("company_id", company_id)
            .eq("filing_date", filing_date)
            .execute()
        )
        return len(result.data) > 0

    def save_holding(self, ticker: str, tokens: float, change: float, filing_date: str, source_url: str) -> bool:
        """
        Adds a new historical row to the holdings table in Supabase.
        Returns True if saved successfully, False otherwise.
        Skips duplicate entries (same company_id + filing_date).
        """
        company_id = self.get_company_id(ticker)

        if not company_id:
            print(f"    ⚠️ DB: {ticker} not found in companies table")
            return False

        # Check for duplicate entry
        if self.holding_exists(company_id, filing_date):
            print(f"    ℹ️ DB: {ticker} record for {filing_date} already exists, skipping")
            return True  # Not an error, just already exists

        data = {
            "company_id": company_id,
            "token_count": tokens,
            "change_amount": change,
            "filing_date": filing_date,
            "source_url": source_url
        }

        self.supabase.table("holdings").insert(data).execute()
        print(f"    ✅ DB: Saved {ticker} ({tokens:,.0f} tokens) to Supabase")
        return True


# Lazy initialization to avoid errors when .env is missing
_db_instance: Optional[DATDatabase] = None

def get_db() -> Optional[DATDatabase]:
    """Get database instance, returns None if connection fails."""
    global _db_instance
    if _db_instance is None:
        try:
            _db_instance = DATDatabase()
        except ValueError as e:
            print(f"    ⚠️ DB: {e}")
            return None
    return _db_instance