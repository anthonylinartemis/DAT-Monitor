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

        if not url:
            raise ValueError(
                "SUPABASE_URL environment variable is not set. "
                "Add it to your .env file or set it in GitHub Actions secrets."
            )
        if not key:
            raise ValueError(
                "SUPABASE_KEY environment variable is not set. "
                "Add it to your .env file or set it in GitHub Actions secrets."
            )

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

    def get_latest_holding(self, company_id: int) -> Optional[dict]:
        """
        Get the most recent holding record for a company.
        Returns dict with token_count and filing_date, or None if no records.
        """
        result = (
            self.supabase.table("holdings")
            .select("token_count, filing_date")
            .eq("company_id", company_id)
            .order("filing_date", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def get_shares_outstanding(self, company_id: int) -> Optional[int]:
        """
        Get the most recent shares_outstanding for a company from holdings_history.
        This data comes from Excel imports.
        """
        result = (
            self.supabase.table("holdings_history")
            .select("shares_outstanding")
            .eq("company_id", company_id)
            .not_.is_("shares_outstanding", "null")
            .order("date", desc=True)
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("shares_outstanding"):
            return int(result.data[0]["shares_outstanding"])
        return None

    def update_holding_prices(
        self,
        company_id: int,
        filing_date: str,
        token_price: float = None,
        share_price: float = None,
        shares_outstanding: int = None,
        market_cap: float = None,
        nav: float = None,
    ) -> bool:
        """
        Update price fields for an existing holding record.
        Only updates fields that are provided (not None).
        """
        updates = {}
        if token_price is not None:
            updates["token_price"] = token_price
        if share_price is not None:
            updates["share_price"] = share_price
        if shares_outstanding is not None:
            updates["shares_outstanding"] = shares_outstanding
        if market_cap is not None:
            updates["market_cap"] = market_cap
        if nav is not None:
            updates["nav"] = nav

        if not updates:
            return False

        try:
            self.supabase.table("holdings").update(updates).eq(
                "company_id", company_id
            ).eq("filing_date", filing_date).execute()
            return True
        except Exception as e:
            print(f"    ⚠️ DB: Error updating prices: {e}")
            return False

    def save_holding(self, ticker: str, tokens: float, filing_date: str, source_url: str) -> bool:
        """
        Adds a new historical row to the holdings table in Supabase.
        Automatically calculates change_amount from previous filing.
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

        # Calculate change from previous holding
        previous = self.get_latest_holding(company_id)
        if previous:
            change_amount = tokens - previous["token_count"]
            prev_tokens = previous["token_count"]
        else:
            change_amount = tokens  # First entry, change equals total
            prev_tokens = 0

        data = {
            "company_id": company_id,
            "token_count": tokens,
            "token_change": change_amount,  # tokens added/bought since last filing
            "filing_date": filing_date,
            "source_url": source_url
        }

        self.supabase.table("holdings").insert(data).execute()

        # Show change info
        if change_amount > 0:
            sign = "+"
        elif change_amount < 0:
            sign = ""
        else:
            sign = ""

        print(f"    ✅ DB: {ticker} {prev_tokens:,.0f} → {tokens:,.0f} ({sign}{change_amount:,.0f}) saved to Supabase")
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