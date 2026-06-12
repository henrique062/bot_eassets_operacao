CREATE TABLE IF NOT EXISTS exchange_symbols (
    exchange VARCHAR(20) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    status VARCHAR(20),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (exchange, symbol)
);
