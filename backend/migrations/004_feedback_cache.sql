-- Kyotech AI — Fase 4: Feedback, quality_score e semantic cache
-- Executar após migrations 001, 002, 003

-- Tabela de feedback por mensagem
CREATE TABLE IF NOT EXISTS message_feedback (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    message_id  UUID NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
    rating      VARCHAR(10) NOT NULL CHECK (rating IN ('thumbs_up', 'thumbs_down')),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (message_id)  -- um feedback por mensagem; UNIQUE já cria índice B-tree
);

-- Coluna quality_score nos chunks (começa em 0, sobe/desce com feedback)
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS quality_score FLOAT DEFAULT 0.0;

-- Cache semântico: pergunta → resposta aprovada (👍)
CREATE TABLE IF NOT EXISTS semantic_cache (
    id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    question_embedding VECTOR(1536) NOT NULL,
    question_original  TEXT NOT NULL,
    answer             TEXT NOT NULL,
    citations          JSONB,
    query_rewritten    TEXT,
    model_used         TEXT,
    hit_count          INTEGER DEFAULT 0,
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

-- Índice HNSW para busca rápida por similaridade
CREATE INDEX IF NOT EXISTS idx_cache_embedding
    ON semantic_cache USING hnsw (question_embedding vector_cosine_ops);
