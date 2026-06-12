-- Migration: adiciona coluna paused nas tabelas de bots
-- Data: 2026-02-24
-- Permite pausar um bot sem parar definitivamente:
-- bot fica suspenso (não abre novas posições), mas monitora posições abertas normalmente.

ALTER TABLE paper_config ADD COLUMN IF NOT EXISTS paused BOOLEAN DEFAULT FALSE;
ALTER TABLE real_config  ADD COLUMN IF NOT EXISTS paused BOOLEAN DEFAULT FALSE;
