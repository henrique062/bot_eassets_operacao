ALTER TABLE real_config ADD COLUMN maker_timeout_seconds SMALLINT DEFAULT 8;
ALTER TABLE paper_config ADD COLUMN maker_timeout_seconds SMALLINT DEFAULT 8;
