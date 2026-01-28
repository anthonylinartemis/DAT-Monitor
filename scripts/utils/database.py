import os
from decimal import Decimal
from pathlib import Path
from typing import Optional, Union

from dotenv import load_dotenv
from supabase import Client, create_client

from utils.validation import validate_ticker, ValidationError

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

    def save_holding(
        self,
        ticker: str,
        tokens: Union[int, float, Decimal],
        filing_date: str,
        source_url: str
    ) -> bool:
        """
        Adds a new historical row to the holdings table in Supabase.
        Automatically calculates change_amount from previous filing.
        Returns True if saved successfully, False otherwise.
        Skips duplicate entries (same company_id + filing_date).

        Args:
            ticker: Company ticker symbol (validated against whitelist)
            tokens: Token count (converted to Decimal for precision)
            filing_date: Date of the filing (YYYY-MM-DD)
            source_url: URL to the source document
        """
        # Validate ticker against whitelist
        try:
            ticker = validate_ticker(ticker, strict=True)
        except ValidationError as e:
            print(f"    ⚠️ DB: Validation error: {e}")
            return False

        # Convert tokens to Decimal for precision
        tokens_decimal = Decimal(str(tokens))

        company_id = self.get_company_id(ticker)

        if not company_id:
            print(f"    ⚠️ DB: {ticker} not found in companies table")
            return False

        # Check for duplicate entry (dedup by company_id + filing_date)
        if self.holding_exists(company_id, filing_date):
            print(f"    ℹ️ DB: {ticker} record for {filing_date} already exists, skipping")
            return True  # Not an error, just already exists

        # Calculate change from previous holding
        previous = self.get_latest_holding(company_id)
        if previous:
            prev_tokens = Decimal(str(previous["token_count"]))
            change_amount = tokens_decimal - prev_tokens
        else:
            change_amount = tokens_decimal  # First entry, change equals total
            prev_tokens = Decimal("0")

        data = {
            "company_id": company_id,
            "token_count": float(tokens_decimal),  # Supabase expects float/int
            "token_change": float(change_amount),  # tokens added/bought since last filing
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

        print(f"    ✅ DB: {ticker} {prev_tokens:,.0f} → {tokens_decimal:,.0f} ({sign}{change_amount:,.0f}) saved to Supabase")
        return True

    def save_treasury_holding(
        self,
        ticker: str,
        date: str,
        token_count: Union[int, float, Decimal, None] = None,
        shares_outstanding: Union[int, float, Decimal, None] = None,
        convertible_debt: Union[int, float, Decimal, None] = None,
        convertible_debt_shares: Union[int, float, Decimal, None] = None,
        non_convertible_debt: Union[int, float, Decimal, None] = None,
        warrants: Union[int, float, Decimal, None] = None,
        warrant_shares: Union[int, float, Decimal, None] = None,
        cash_position: Union[int, float, Decimal, None] = None,
        import_source: str = "manual",
    ) -> bool:
        """
        Save or update a treasury holding record in holdings_history.

        This method handles the full treasury data model including:
        - Token holdings
        - Shares outstanding
        - Debt instruments (convertible and non-convertible)
        - Warrants
        - Cash position

        Args:
            ticker: Company ticker symbol (validated against whitelist)
            date: Date of the record (YYYY-MM-DD)
            token_count: Number of tokens held
            shares_outstanding: Total shares outstanding
            convertible_debt: Value of convertible debt
            convertible_debt_shares: Shares from convertible debt
            non_convertible_debt: Value of non-convertible debt
            warrants: Value of warrants
            warrant_shares: Shares from warrants
            cash_position: Cash and cash equivalents
            import_source: Source identifier (csv_import, excel_import, manual, etc.)

        Returns:
            True if saved successfully, False otherwise
        """
        # Validate ticker
        try:
            ticker = validate_ticker(ticker, strict=True)
        except ValidationError as e:
            print(f"    ⚠️ DB: Validation error: {e}")
            return False

        company_id = self.get_company_id(ticker)
        if not company_id:
            print(f"    ⚠️ DB: {ticker} not found in companies table")
            return False

        # Build record with only non-None values
        def to_float(val):
            if val is None:
                return None
            return float(Decimal(str(val)))

        record = {
            "company_id": company_id,
            "date": date,
            "import_source": import_source,
        }

        if token_count is not None:
            record["token_count"] = to_float(token_count)
        if shares_outstanding is not None:
            record["shares_outstanding"] = to_float(shares_outstanding)
        if convertible_debt is not None:
            record["convertible_debt"] = to_float(convertible_debt)
        if convertible_debt_shares is not None:
            record["convertible_debt_shares"] = to_float(convertible_debt_shares)
        if non_convertible_debt is not None:
            record["non_convertible_debt"] = to_float(non_convertible_debt)
        if warrants is not None:
            record["warrants"] = to_float(warrants)
        if warrant_shares is not None:
            record["warrant_shares"] = to_float(warrant_shares)
        if cash_position is not None:
            record["cash_position"] = to_float(cash_position)

        try:
            self.supabase.table("holdings_history").upsert(
                [record],
                on_conflict="company_id,date"
            ).execute()
            print(f"    ✅ DB: {ticker} treasury record for {date} saved")
            return True
        except Exception as e:
            print(f"    ⚠️ DB: Error saving treasury record: {e}")
            return False

    def get_treasury_history(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get treasury history records for a company.

        Args:
            ticker: Company ticker symbol
            start_date: Filter records on or after this date (optional)
            end_date: Filter records on or before this date (optional)
            limit: Maximum records to return

        Returns:
            List of treasury records ordered by date descending
        """
        try:
            ticker = validate_ticker(ticker, strict=True)
        except ValidationError:
            return []

        company_id = self.get_company_id(ticker)
        if not company_id:
            return []

        query = (
            self.supabase.table("holdings_history")
            .select("*")
            .eq("company_id", company_id)
            .order("date", desc=True)
            .limit(limit)
        )

        if start_date:
            query = query.gte("date", start_date)
        if end_date:
            query = query.lte("date", end_date)

        result = query.execute()
        return result.data if result.data else []


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