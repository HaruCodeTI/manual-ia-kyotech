-- Kyotech AI — Fase 6: Memória de Conversa
-- Executar após migrations 001–005
-- Adiciona suporte a histórico persistido e sumarização incremental

ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS history_summary TEXT;
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS last_summarized_at TIMESTAMPTZ;
