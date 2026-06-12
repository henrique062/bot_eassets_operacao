INSERT INTO system_settings (key, value, description)
VALUES
    ('api_keys_binance', '{"apiKey": "", "apiSecret": ""}', 'Chaves de API para operações na Binance Futures'),
    ('api_keys_bybit', '{"apiKey": "", "apiSecret": ""}', 'Chaves de API para operações na Bybit Futures')
ON CONFLICT (key) DO NOTHING;
