CREATE TABLE IF NOT EXISTS ai_reports (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(50) NOT NULL,
    general_stats JSONB NOT NULL,
    market_overview TEXT,
    recommended_coins JSONB NOT NULL,
    is_accurate BOOLEAN,
    accuracy_details TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_reports_created_at ON ai_reports(created_at DESC);
