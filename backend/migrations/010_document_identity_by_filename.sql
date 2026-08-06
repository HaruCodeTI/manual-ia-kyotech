-- 010 — Identidade do documento pelo nome de arquivo normalizado
--
-- Problema corrigido: documents era identificado por (doc_type, equipment_key),
-- e document_versions tinha chave única (document_id, published_date). Como
-- published_date cai em date.today() quando não vem no upload, todo arquivo
-- enviado no mesmo dia sob o mesmo doc_type colidia via ON CONFLICT e
-- sobrescrevia a linha anterior. Em prod uma única versão acumulou 373 chunks
-- de cinco documentos distintos, servidos sob o nome do último a gravar.
--
-- Ordem de aplicação: esta migration → deploy do código novo → scripts/repair_document_identity.py
-- (o backfill de doc_key roda em Python para usar exatamente a mesma
--  normalização de repository.normalize_doc_key)

-- ── 1. Identidade do documento ──
ALTER TABLE documents ADD COLUMN IF NOT EXISTS doc_key TEXT;

-- NULLs são permitidos e não colidem entre si: as linhas existentes ficam sem
-- doc_key até o backfill do script de reparo.
CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_doc_key
    ON documents (doc_key);

-- ── 2. Chave da versão: conteúdo, não data ──
-- Reenviar o mesmo arquivo deve ser no-op. Arquivos diferentes no mesmo dia
-- devem gerar versões diferentes.
-- Atenção: o runner em app/main.py quebra o arquivo por ponto e vírgula, sem
-- entender comentários. Um desses caracteres dentro de um comentário parte o
-- statement seguinte ao meio e derruba o startup da aplicação.
ALTER TABLE document_versions DROP CONSTRAINT IF EXISTS uq_document_version;
DROP INDEX IF EXISTS uq_document_version;

CREATE UNIQUE INDEX IF NOT EXISTS uq_document_version_hash
    ON document_versions (document_id, source_hash);

-- ── 3. "Mais novo vence" por data de ingestão, não de publicação ──
-- published_date é a data do upload na prática (date.today()), e em DESC o
-- Postgres coloca NULLS FIRST, então uma versão sem data ganhava de uma com
-- data real. created_at reflete a ordem real de ingestão.
DROP VIEW IF EXISTS current_versions;
CREATE VIEW current_versions AS
SELECT DISTINCT ON (document_id)
    id,
    document_id,
    published_date,
    source_hash,
    source_filename,
    storage_path
FROM document_versions
ORDER BY document_id, created_at DESC NULLS LAST, published_date DESC NULLS LAST;
