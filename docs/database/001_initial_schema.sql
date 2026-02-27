-- ============================================================================
-- Kyotech IA — DDL Migration Script (MVP)
-- ============================================================================
-- Ticket:  IA-63
-- Autor:   HaruCode
-- Data:    2026-02-27
-- DB:      PostgreSQL 15+ com extensões pgvector e pg_trgm
-- Ref:     Seção 4 (Modelo de Dados) + Seção 5 (Versionamento)
-- ============================================================================

-- ============================================================================
-- 0. Extensões obrigatórias
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";     -- Geração de UUID v4
CREATE EXTENSION IF NOT EXISTS vector;           -- pgvector — busca vetorial
CREATE EXTENSION IF NOT EXISTS pg_trgm;          -- pg_trgm — busca textual por trigramas

-- ============================================================================
-- 1. Tipos ENUM
-- ============================================================================

DO $$ BEGIN
    CREATE TYPE doc_type_enum AS ENUM ('manual', 'informativo');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE audit_event_enum AS ENUM ('chat_query', 'document_upload', 'pdf_view');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================================
-- 2. Tabela: equipments
-- ============================================================================
-- Catálogo de equipamentos Fujifilm.
-- equipment_key é o identificador primário (não UUID) porque os técnicos
-- referenciam equipamentos por código (ex: JET-PRESS-750S).
-- aliases permite match flexível durante a detecção automática no upload.
-- ============================================================================

CREATE TABLE IF NOT EXISTS equipments (
    equipment_key   TEXT        PRIMARY KEY,
    display_name    TEXT        NOT NULL,
    aliases         TEXT[]      DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE  equipments IS 'Catálogo de equipamentos Fujifilm';
COMMENT ON COLUMN equipments.equipment_key IS 'Código único do equipamento (ex: JET-PRESS-750S)';
COMMENT ON COLUMN equipments.aliases IS 'Nomes alternativos para match flexível no upload e chat';

-- ============================================================================
-- 3. Tabela: documents
-- ============================================================================
-- Representa um documento lógico (manual ou informativo) de um equipamento.
-- Um document pode ter múltiplas versions (versionamento por published_date).
-- ============================================================================

CREATE TABLE IF NOT EXISTS documents (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_type        doc_type_enum NOT NULL,
    equipment_key   TEXT        NOT NULL REFERENCES equipments(equipment_key) ON DELETE RESTRICT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_equipment_key
    ON documents(equipment_key);

COMMENT ON TABLE  documents IS 'Documento lógico (manual ou informativo) vinculado a um equipamento';
COMMENT ON COLUMN documents.doc_type IS 'Tipo: manual (procedimentos/specs) ou informativo (bulletins/atualizações)';

-- ============================================================================
-- 4. Tabela: document_versions
-- ============================================================================
-- Cada upload de PDF gera uma nova versão.
-- REGRA CRÍTICA: Versão ativa = maior published_date por document_id.
-- Versões antigas NÃO são excluídas (mantidas para auditoria).
-- source_hash (SHA-256) previne ingestão duplicada do mesmo arquivo.
-- ============================================================================

CREATE TABLE IF NOT EXISTS document_versions (
    id                  UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id         UUID        NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    published_date      DATE        NOT NULL,       -- OBRIGATÓRIO (Seção 5)
    source_hash         TEXT        NOT NULL,        -- SHA-256 do PDF original
    source_filename     TEXT        NOT NULL,        -- Nome original do arquivo
    storage_path        TEXT        NOT NULL,        -- Caminho no Azure Blob Storage
    total_pages         INTEGER     DEFAULT 0,
    total_chunks        INTEGER     DEFAULT 0,
    ingested_at         TIMESTAMPTZ DEFAULT NOW(),

    -- Impede upload de arquivo idêntico para o mesmo documento
    CONSTRAINT uq_document_version_hash UNIQUE (document_id, source_hash)
);

-- Index composto para lookup rápido da versão ativa
CREATE INDEX IF NOT EXISTS idx_document_versions_active
    ON document_versions(document_id, published_date DESC);

-- Index para deduplicação no upload
CREATE INDEX IF NOT EXISTS idx_document_versions_hash
    ON document_versions(source_hash);

COMMENT ON TABLE  document_versions IS 'Versões de um documento — versionamento estrito por published_date';
COMMENT ON COLUMN document_versions.published_date IS 'Data de publicação do documento Fujifilm (OBRIGATÓRIO). Versão ativa = maior published_date por document_id.';
COMMENT ON COLUMN document_versions.source_hash IS 'SHA-256 do PDF original para deduplicação';
COMMENT ON COLUMN document_versions.storage_path IS 'Path no Azure Blob Storage (container: originals)';

-- ============================================================================
-- 5. Tabela: chunks
-- ============================================================================
-- Fragmentos de texto extraídos de cada versão de documento.
-- Cada chunk contém o texto + embedding para busca vetorial.
-- page_number permite citação rastreável (Documento + Página).
-- ============================================================================

CREATE TABLE IF NOT EXISTS chunks (
    id                      UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_version_id     UUID        NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    page_number             INTEGER     NOT NULL,
    chunk_index             INTEGER     NOT NULL DEFAULT 0,
    content                 TEXT        NOT NULL,
    embedding               vector(1536),  -- text-embedding-3-small
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- Index HNSW para busca vetorial por cosine similarity
-- HNSW escolhido sobre IVFFlat por melhor recall em datasets < 1M vectors
-- m=16, ef_construction=64 são defaults razoáveis para MVP
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Index GIN para busca textual por trigramas (pg_trgm)
CREATE INDEX IF NOT EXISTS idx_chunks_content_trgm
    ON chunks USING gin (content gin_trgm_ops);

-- Index para filtro por versão (usado no JOIN com versão ativa)
CREATE INDEX IF NOT EXISTS idx_chunks_version_id
    ON chunks(document_version_id);

COMMENT ON TABLE  chunks IS 'Fragmentos de texto com embeddings para busca vetorial e textual';
COMMENT ON COLUMN chunks.page_number IS 'Página do PDF original — usado nas citações [Documento + Página]';
COMMENT ON COLUMN chunks.embedding IS 'vector(1536) gerado por text-embedding-3-small (Azure OpenAI)';
COMMENT ON COLUMN chunks.chunk_index IS 'Posição sequencial do chunk dentro da versão (para ordenação)';

-- ============================================================================
-- 6. Tabela: audit_logs
-- ============================================================================
-- Registro de todas as interações relevantes para auditoria (Seção 9).
-- Não possui FK para evitar acoplamento — usa IDs como referência em metadata.
-- ============================================================================

CREATE TABLE IF NOT EXISTS audit_logs (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type      audit_event_enum NOT NULL,
    user_id         TEXT            NOT NULL,    -- Entra ID object_id
    user_role       TEXT            NOT NULL,    -- 'tecnico' | 'gerente'
    metadata        JSONB           DEFAULT '{}',
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_event_time
    ON audit_logs(event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user
    ON audit_logs(user_id, created_at DESC);

COMMENT ON TABLE  audit_logs IS 'Log de auditoria de todas as interações do sistema';
COMMENT ON COLUMN audit_logs.metadata IS 'JSON livre: {query, equipment_key, document_id, page_number, etc.}';

-- ============================================================================
-- 7. View: current_document_versions
-- ============================================================================
-- View de conveniência que retorna apenas a versão ativa de cada documento.
-- Usada pelo pipeline RAG para filtrar chunks apenas de versões atuais.
-- ============================================================================

CREATE OR REPLACE VIEW current_document_versions AS
SELECT DISTINCT ON (dv.document_id)
    dv.id AS version_id,
    dv.document_id,
    d.doc_type,
    d.equipment_key,
    e.display_name AS equipment_name,
    dv.published_date,
    dv.source_filename,
    dv.storage_path,
    dv.total_pages,
    dv.total_chunks,
    dv.ingested_at
FROM document_versions dv
JOIN documents d ON d.id = dv.document_id
JOIN equipments e ON e.equipment_key = d.equipment_key
ORDER BY dv.document_id, dv.published_date DESC;

COMMENT ON VIEW current_document_versions IS 'Versão ativa (mais recente por published_date) de cada documento — usada pelo pipeline RAG';

-- ============================================================================
-- 8. Funções utilitárias
-- ============================================================================

-- Busca vetorial: retorna chunks mais similares da versão ativa
-- Uso: SELECT * FROM search_chunks_by_embedding(query_embedding, 'JET-PRESS-750S', 10);
CREATE OR REPLACE FUNCTION search_chunks_by_embedding(
    query_embedding vector(1536),
    filter_equipment_key TEXT DEFAULT NULL,
    result_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    chunk_id            UUID,
    document_id         UUID,
    equipment_key       TEXT,
    equipment_name      TEXT,
    doc_type            doc_type_enum,
    published_date      DATE,
    source_filename     TEXT,
    storage_path        TEXT,
    page_number         INTEGER,
    chunk_index         INTEGER,
    content             TEXT,
    similarity_score    FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id AS chunk_id,
        cdv.document_id,
        cdv.equipment_key,
        cdv.equipment_name,
        cdv.doc_type,
        cdv.published_date,
        cdv.source_filename,
        cdv.storage_path,
        c.page_number,
        c.chunk_index,
        c.content,
        1 - (c.embedding <=> query_embedding) AS similarity_score
    FROM chunks c
    JOIN current_document_versions cdv ON cdv.version_id = c.document_version_id
    WHERE (filter_equipment_key IS NULL OR cdv.equipment_key = filter_equipment_key)
    ORDER BY c.embedding <=> query_embedding
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION search_chunks_by_embedding IS 'Busca vetorial por cosine similarity — retorna apenas chunks de versões ativas';

-- ============================================================================
-- FIM DO MIGRATION SCRIPT
-- ============================================================================