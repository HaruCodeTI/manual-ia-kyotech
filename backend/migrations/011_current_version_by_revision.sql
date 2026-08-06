-- 011 — "Mais novo vence" pela revisão do documento, não pela data de ingestão
--
-- A 010 passou a ordenar current_versions por created_at. Isso quebra quando um
-- arquivo antigo é reingerido: ele recebe created_at novo e passa a vencer uma
-- revisão de numeração mais alta. Aconteceu de verdade ao rodar o reparo —
-- SS1511-N002 Ver.3.8, ingerido em abril, ficou escondido atrás da Ver.3.2,
-- reingerida hoje.
--
-- A revisão declarada no nome do arquivo é o sinal mais fiel de qual documento
-- é o mais novo. Casa "Ver.3.8", "ver11.4", "V2.0" e devolve numeric, então
-- 11.4 > 10.5 > 9.0 comparam corretamente. Nomes sem revisão dão NULL e caem no
-- desempate por data, que é o comportamento anterior.
--
-- Atenção: o runner em app/main.py quebra o arquivo por ponto e vírgula, sem
-- entender comentários. Não usar esse caractere em comentário.

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
ORDER BY
    document_id,
    NULLIF(substring(source_filename from '[Vv][Ee]?[Rr]?\.?\s*([0-9]+(?:\.[0-9]+)?)'), '')::numeric
        DESC NULLS LAST,
    created_at DESC NULLS LAST,
    published_date DESC NULLS LAST;
