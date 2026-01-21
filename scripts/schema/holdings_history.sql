-- Holdings History Table
-- Stores historical holdings data with price and market metrics
-- Run this in Supabase SQL Editor to create the table

CREATE TABLE IF NOT EXISTS holdings_history (
  id SERIAL PRIMARY KEY,
  company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
  date DATE NOT NULL,
  token_count NUMERIC NOT NULL,
  token_change NUMERIC,
  token_price NUMERIC,
  nav NUMERIC,
  share_price NUMERIC,
  shares_outstanding NUMERIC,
  market_cap NUMERIC,
  source TEXT DEFAULT 'manual',
  source_url TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(company_id, date)
);

CREATE INDEX IF NOT EXISTS idx_holdings_history_company_date ON holdings_history(company_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_holdings_history_date ON holdings_history(date DESC);

ALTER TABLE holdings_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read access" ON holdings_history FOR SELECT USING (true);
