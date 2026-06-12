-- Migração para alterar o nome da coluna annualized_rate para monthly_rate

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'funding_rate_snapshots'
          AND column_name = 'annualized_rate'
    ) THEN
        ALTER TABLE funding_rate_snapshots RENAME COLUMN annualized_rate TO monthly_rate;
    END IF;
END $$;
