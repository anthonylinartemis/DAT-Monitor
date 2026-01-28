-- DAT Monitor V2 Schema Migration
-- Adds treasury fields and audit columns to holdings_history table
--
-- Run with: psql $DATABASE_URL -f scripts/schema/holdings_history_v2.sql
-- Or execute directly in Supabase SQL editor

-- Add treasury fields to existing table
ALTER TABLE holdings_history ADD COLUMN IF NOT EXISTS convertible_debt NUMERIC;
ALTER TABLE holdings_history ADD COLUMN IF NOT EXISTS convertible_debt_shares NUMERIC;
ALTER TABLE holdings_history ADD COLUMN IF NOT EXISTS non_convertible_debt NUMERIC;
ALTER TABLE holdings_history ADD COLUMN IF NOT EXISTS warrants NUMERIC;
ALTER TABLE holdings_history ADD COLUMN IF NOT EXISTS warrant_shares NUMERIC;
ALTER TABLE holdings_history ADD COLUMN IF NOT EXISTS cash_position NUMERIC;

-- Add import audit columns
ALTER TABLE holdings_history ADD COLUMN IF NOT EXISTS import_source VARCHAR(50);
ALTER TABLE holdings_history ADD COLUMN IF NOT EXISTS imported_at TIMESTAMP DEFAULT NOW();

-- Add index for import source queries (useful for debugging imports)
CREATE INDEX IF NOT EXISTS idx_holdings_history_import_source
ON holdings_history(import_source)
WHERE import_source IS NOT NULL;

-- Add comment explaining the new columns
COMMENT ON COLUMN holdings_history.convertible_debt IS 'Convertible debt value (from 8-K filings)';
COMMENT ON COLUMN holdings_history.convertible_debt_shares IS 'Shares convertible from debt instruments';
COMMENT ON COLUMN holdings_history.non_convertible_debt IS 'Non-convertible debt value';
COMMENT ON COLUMN holdings_history.warrants IS 'Outstanding warrants value';
COMMENT ON COLUMN holdings_history.warrant_shares IS 'Shares obtainable from warrants';
COMMENT ON COLUMN holdings_history.cash_position IS 'Cash and cash equivalents (latest_cash in dbt)';
COMMENT ON COLUMN holdings_history.import_source IS 'Source of data: csv_import, excel_import, scraper, manual';
COMMENT ON COLUMN holdings_history.imported_at IS 'Timestamp when record was imported';
