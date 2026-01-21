import sys
import os

# This ensures Python can find your 'scripts' folder for the import below
sys.path.append(os.path.join(os.getcwd(), "scripts"))

from utils.database import db

# List of DAT companies to register in your new database
# These match the categories (BTC, ETH, etc.) we set up in your SQL code
companies_to_add = [
    {"ticker": "MSTR", "name": "Strategy", "primary_token": "BTC", "cik": "0001050446", "ir_url": "https://www.strategy.com/investor-relations"},
    {"ticker": "BMNR", "name": "BitMine Immersion", "primary_token": "ETH", "cik": "0001829311", "ir_url": "https://www.bitminetech.io/investor-relations"},
    {"ticker": "STSS", "name": "Sharps Technology", "primary_token": "SOL", "cik": "0001737995", "ir_url": "https://www.sharpstechnology.com/investors/news"},
    {"ticker": "HYPD", "name": "Hyperion DeFi", "primary_token": "HYPE", "cik": "0001682639", "ir_url": "https://ir.hyperiondefi.com/"},
    {"ticker": "BNC", "name": "CEA Industries", "primary_token": "BNB", "cik": "0001482541", "ir_url": "https://ceaindustries.com/investors.html"}
]

def initialize_database():
    print("🚀 Starting Database Initialization...")
    
    for co in companies_to_add:
        try:
            # 'upsert' adds the company if it's missing, or updates info if it already exists
            db.supabase.table("companies").upsert(co, on_conflict="ticker").execute()
            print(f"✅ Registered: {co['ticker']} ({co['primary_token']})")
        except Exception as e:
            print(f"❌ Error adding {co['ticker']}: {e}")

    print("\n🎉 Done! Your companies are now in the database and ready for tracking.")

if __name__ == "__main__":
    initialize_database()