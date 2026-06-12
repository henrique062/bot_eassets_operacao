-- Adiciona rastreamento do score no momento de abertura da posição
-- Permite correlacionar entry_score com total_pnl para validação empírica do algoritmo

-- Posições abertas (paper)
ALTER TABLE paper_positions
    ADD COLUMN IF NOT EXISTS entry_score INTEGER DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS entry_score_breakdown JSONB DEFAULT NULL;

-- Posições abertas (real)
ALTER TABLE real_positions
    ADD COLUMN IF NOT EXISTS entry_score INTEGER DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS entry_score_breakdown JSONB DEFAULT NULL;

-- Histórico de trades fechados (paper)
ALTER TABLE paper_trades
    ADD COLUMN IF NOT EXISTS entry_score INTEGER DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS entry_score_breakdown JSONB DEFAULT NULL;

-- Histórico de trades fechados (real)
ALTER TABLE real_trades
    ADD COLUMN IF NOT EXISTS entry_score INTEGER DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS entry_score_breakdown JSONB DEFAULT NULL;

-- Índices para análise futura (correlação score vs resultado)
CREATE INDEX IF NOT EXISTS idx_paper_trades_entry_score ON paper_trades(entry_score);
CREATE INDEX IF NOT EXISTS idx_real_trades_entry_score ON real_trades(entry_score);
