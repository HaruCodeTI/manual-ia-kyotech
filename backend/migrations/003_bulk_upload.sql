-- Kyotech AI — Fase 3: equipment_key e doc_type tornam-se opcionais em documents
-- Executar no kyotech_db após as tabelas da Fase 1 e 2

-- Remover constraint UNIQUE antiga (doc_type, equipment_key) se existir
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_doc_type_equipment_key_key;
ALTER TABLE documents DROP CONSTRAINT IF EXISTS uq_documents_type_equipment;

-- Tornar colunas nullable
ALTER TABLE documents ALTER COLUMN equipment_key DROP NOT NULL;
ALTER TABLE documents ALTER COLUMN doc_type DROP NOT NULL;

-- Recriar a view current_versions para garantir compatibilidade
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
ORDER BY document_id, published_date DESC;
