-- ============================================================================
-- Kyotech IA — Seed Data (Desenvolvimento Local)
-- ============================================================================
-- Dados de exemplo para rodar o sistema localmente.
-- NÃO executar em produção.
-- Executar APÓS 001_initial_schema.sql
-- ============================================================================

-- Equipamentos de exemplo (baseados no catálogo Fujifilm)
INSERT INTO equipments (equipment_key, display_name, aliases) VALUES
    ('JET-PRESS-750S',   'Jet Press 750S',   ARRAY['750S', 'JP750S', 'Jet Press 750']),
    ('JET-PRESS-750SHS', 'Jet Press 750S HS', ARRAY['750SHS', 'JP750SHS', 'High Speed']),
    ('REVORIA-PC1120',   'Revoria Press PC1120', ARRAY['PC1120', 'Revoria 1120']),
    ('REVORIA-SC200',    'Revoria Press SC200',  ARRAY['SC200', 'Revoria SC']),
    ('APEOS-C7070',      'Apeos C7070',       ARRAY['C7070', 'Apeos 7070']),
    ('APEOS-C5570',      'Apeos C5570',       ARRAY['C5570', 'Apeos 5570'])
ON CONFLICT (equipment_key) DO NOTHING;

-- Documentos de exemplo
INSERT INTO documents (id, doc_type, equipment_key) VALUES
    ('a1b2c3d4-0001-4000-8000-000000000001', 'manual',       'JET-PRESS-750S'),
    ('a1b2c3d4-0001-4000-8000-000000000002', 'informativo',  'JET-PRESS-750S'),
    ('a1b2c3d4-0001-4000-8000-000000000003', 'manual',       'REVORIA-PC1120'),
    ('a1b2c3d4-0001-4000-8000-000000000004', 'informativo',  'REVORIA-PC1120')
ON CONFLICT (id) DO NOTHING;

-- Versões de exemplo (simula versionamento por published_date)
-- Jet Press 750S Manual — 2 versões (v2 é a ativa por ter published_date mais recente)
INSERT INTO document_versions (id, document_id, published_date, source_hash, source_filename, storage_path, total_pages, total_chunks) VALUES
    ('b1b2c3d4-0001-4000-8000-000000000001',
     'a1b2c3d4-0001-4000-8000-000000000001',
     '2024-06-15',
     'sha256_fake_hash_v1_jetpress_manual',
     'JetPress750S_ServiceManual_v1_2024-06.pdf',
     'originals/JET-PRESS-750S/manual/2024-06-15/JetPress750S_ServiceManual_v1_2024-06.pdf',
     180, 540),

    ('b1b2c3d4-0001-4000-8000-000000000002',
     'a1b2c3d4-0001-4000-8000-000000000001',
     '2025-01-20',  -- << VERSÃO ATIVA (published_date mais recente)
     'sha256_fake_hash_v2_jetpress_manual',
     'JetPress750S_ServiceManual_v2_2025-01.pdf',
     'originals/JET-PRESS-750S/manual/2025-01-20/JetPress750S_ServiceManual_v2_2025-01.pdf',
     195, 585),

-- Jet Press 750S Informativo — 1 versão
    ('b1b2c3d4-0001-4000-8000-000000000003',
     'a1b2c3d4-0001-4000-8000-000000000002',
     '2025-02-01',
     'sha256_fake_hash_jetpress_bulletin',
     'JetPress750S_ServiceBulletin_SB-2025-003.pdf',
     'originals/JET-PRESS-750S/informativo/2025-02-01/SB-2025-003.pdf',
     8, 24),

-- Revoria PC1120 Manual — 1 versão
    ('b1b2c3d4-0001-4000-8000-000000000004',
     'a1b2c3d4-0001-4000-8000-000000000003',
     '2024-11-10',
     'sha256_fake_hash_revoria_manual',
     'RevoriaPC1120_ServiceManual_2024-11.pdf',
     'originals/REVORIA-PC1120/manual/2024-11-10/RevoriaPC1120_ServiceManual_2024-11.pdf',
     220, 660)
ON CONFLICT (id) DO NOTHING;

-- Chunks de exemplo (sem embeddings reais — usar NULL para dev local sem Azure OpenAI)
-- Em dev local, os embeddings seriam gerados via chamada à API
INSERT INTO chunks (id, document_version_id, page_number, chunk_index, content, embedding) VALUES
    -- Chunks do Jet Press 750S Manual v2 (versão ativa)
    ('c1c2c3d4-0001-4000-8000-000000000001',
     'b1b2c3d4-0001-4000-8000-000000000002',
     1, 0,
     'Jet Press 750S Service Manual - Table of Contents. This manual covers maintenance procedures, troubleshooting, and parts replacement for the Fujifilm Jet Press 750S inkjet digital press.',
     NULL),

    ('c1c2c3d4-0001-4000-8000-000000000002',
     'b1b2c3d4-0001-4000-8000-000000000002',
     15, 1,
     'Chapter 3: Print Head Maintenance. The Jet Press 750S uses SAMBA printheads. Regular maintenance intervals: Daily — nozzle check pattern. Weekly — wipe cycle. Monthly — full purge cycle. Refer to Section 3.2 for detailed procedures.',
     NULL),

    ('c1c2c3d4-0001-4000-8000-000000000003',
     'b1b2c3d4-0001-4000-8000-000000000002',
     42, 2,
     'Section 5.1: Ink Supply System Troubleshooting. Error Code E-1042: Ink pressure out of range. Check: 1) Ink tank level sensor. 2) Pressure regulator valve. 3) Air filter condition. If error persists after checks, replace pressure regulator assembly (Part No. FJ-750S-PR-001).',
     NULL),

    -- Chunk do Jet Press 750S Informativo
    ('c1c2c3d4-0001-4000-8000-000000000004',
     'b1b2c3d4-0001-4000-8000-000000000003',
     1, 0,
     'Service Bulletin SB-2025-003: Updated firmware procedure for Jet Press 750S. Applies to units with serial number JP750S-2020-XXXX through JP750S-2024-XXXX. Critical: Perform backup before firmware update. New firmware version 4.2.1 resolves intermittent E-2001 error during long print runs.',
     NULL)
ON CONFLICT (id) DO NOTHING;

-- Verificação dos dados inseridos
DO $$
DECLARE
    eq_count INT;
    doc_count INT;
    ver_count INT;
    chunk_count INT;
BEGIN
    SELECT COUNT(*) INTO eq_count FROM equipments;
    SELECT COUNT(*) INTO doc_count FROM documents;
    SELECT COUNT(*) INTO ver_count FROM document_versions;
    SELECT COUNT(*) INTO chunk_count FROM chunks;

    RAISE NOTICE '=== Seed Data Summary ===';
    RAISE NOTICE 'Equipments:        %', eq_count;
    RAISE NOTICE 'Documents:         %', doc_count;
    RAISE NOTICE 'Document Versions: %', ver_count;
    RAISE NOTICE 'Chunks:            %', chunk_count;
    RAISE NOTICE '========================';
END $$;

-- Verificação da view de versões ativas
-- Deve retornar apenas 1 versão por documento (a mais recente)
-- SELECT * FROM current_document_versions;