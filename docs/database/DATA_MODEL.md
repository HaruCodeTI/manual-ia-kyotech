# Kyotech IA — Modelo de Dados (MVP)

**Ticket:** IA-63
**Autor:** Guilherme (HaruCode — Arquiteto/DevOps)
**Última atualização:** 2026-02-27
**Ref:** Seções 4 e 5 do Documento de Consolidação Técnica

---

## 1. Visão Geral

O modelo de dados do MVP suporta o ciclo completo do sistema RAG:

1. **Cadastro de equipamentos** — catálogo de equipamentos Fujifilm
2. **Ingestão de documentos** — upload de PDFs com metadados
3. **Versionamento** — controle de versões por data de publicação
4. **Indexação vetorial** — chunks com embeddings para busca semântica
5. **Auditoria** — logs de consultas e uploads

---

## 2. Diagrama Entidade-Relacionamento (ERD)

```mermaid
erDiagram
    equipments {
        text equipment_key PK "Código único do equipamento (ex: JET-PRESS-750S)"
        text display_name "Nome de exibição (ex: Jet Press 750S)"
        text[] aliases "Nomes alternativos para match flexível"
        timestamptz created_at "Data de criação do registro"
    }

    documents {
        uuid id PK "UUID v4"
        text doc_type "enum: manual | informativo"
        text equipment_key FK "Referência ao equipamento"
        timestamptz created_at "Data de criação do registro"
    }

    document_versions {
        uuid id PK "UUID v4"
        uuid document_id FK "Referência ao documento pai"
        date published_date "Data de publicação (OBRIGATÓRIO) — chave do versionamento"
        text source_hash "SHA-256 do arquivo original para deduplicação"
        text source_filename "Nome original do arquivo PDF"
        text storage_path "Caminho no Azure Blob Storage"
        integer total_pages "Total de páginas extraídas"
        integer total_chunks "Total de chunks gerados"
        timestamptz ingested_at "Data/hora da ingestão no sistema"
    }

    chunks {
        uuid id PK "UUID v4"
        uuid document_version_id FK "Referência à versão do documento"
        integer page_number "Número da página no PDF original"
        text content "Texto extraído do chunk"
        vector embedding "vector(1536) — text-embedding-3-small"
        integer chunk_index "Posição sequencial dentro da versão"
        timestamptz created_at "Data de criação"
    }

    audit_logs {
        uuid id PK "UUID v4"
        text event_type "enum: chat_query | document_upload | pdf_view"
        text user_id "ID do usuário (Entra ID object_id)"
        text user_role "Role: tecnico | gerente"
        jsonb metadata "Dados adicionais (query, equipment_key, document_id, etc.)"
        timestamptz created_at "Timestamp do evento"
    }

    equipments ||--o{ documents : "possui"
    documents ||--o{ document_versions : "possui versões"
    document_versions ||--o{ chunks : "contém"
```

---

## 3. Regras de Negócio

### 3.1 Versionamento por `published_date` (Seção 5)

> **Decisão Arquitetural (ADR-001):** Os códigos da Fujifilm não seguem padrão. A única referência confiável é a data de publicação impressa no documento.

- `published_date` é **OBRIGATÓRIO** em toda `document_version`
- **Versão ativa** = registro com a **maior** `published_date` por `document_id`
- Versões antigas **NÃO são excluídas** — permanecem armazenadas para auditoria
- No pipeline RAG, apenas chunks da **versão ativa** são considerados na busca

**Query para versão ativa:**
```sql
-- Obtém apenas a versão mais recente de cada documento
SELECT DISTINCT ON (dv.document_id) dv.*
FROM document_versions dv
ORDER BY dv.document_id, dv.published_date DESC;
```

### 3.2 Deduplicação por `source_hash`

- Antes de processar um upload, o sistema calcula o SHA-256 do PDF
- Se o hash já existir em `document_versions` para o mesmo `document_id`, o upload é rejeitado (arquivo idêntico já foi ingerido)
- Hashes diferentes com mesmo `document_id` e `published_date` devem gerar um alerta (possível duplicata com conteúdo diferente)

### 3.3 Tipos de Documento (`doc_type`)

| Valor | Descrição | Comportamento no RAG |
|-------|-----------|---------------------|
| `manual` | Manual técnico completo do equipamento | Priorizado para perguntas sobre procedimentos e especificações |
| `informativo` | Boletim técnico, service bulletin, atualização | Priorizado para perguntas sobre correções, atualizações e alertas |

O **router RAG** classifica a pergunta do técnico e direciona a busca para o tipo adequado (ou ambos, se ambíguo).

### 3.4 Embeddings

- Modelo: `text-embedding-3-small` (Azure OpenAI)
- Dimensão: **1536**
- Métrica de similaridade: **cosine distance**
- Index: IVFFlat ou HNSW (ver DDL)

### 3.5 Auditoria (Seção 9)

Toda interação relevante é registrada em `audit_logs`:
- **chat_query**: pergunta do técnico + equipment_key filtrado
- **document_upload**: documento ingerido + user que fez upload
- **pdf_view**: visualização de PDF + página acessada

---

## 4. Índices e Performance

| Tabela | Índice | Tipo | Finalidade |
|--------|--------|------|-----------|
| `chunks` | `embedding` | HNSW (vector_cosine_ops) | Busca vetorial por similaridade |
| `chunks` | `content` | GIN (gin_trgm_ops) | Busca textual por trigramas |
| `document_versions` | `(document_id, published_date DESC)` | B-Tree | Lookup rápido da versão ativa |
| `document_versions` | `source_hash` | B-Tree | Deduplicação no upload |
| `documents` | `equipment_key` | B-Tree | Filtro por equipamento |
| `audit_logs` | `(event_type, created_at)` | B-Tree | Consultas de auditoria |

---

## 5. Considerações de Segurança

- **Nenhuma informação sensível nos embeddings** — os vetores são numéricos e não revertem para texto, mas o campo `content` contém texto original confidencial da Fujifilm
- **Acesso ao banco** exclusivamente via Private Endpoint (Seção 9)
- **SSL obrigatório** na connection string (`?sslmode=require`)
- **RBAC no app layer** — o banco não implementa row-level security no MVP; o controle de acesso é feito pelo middleware FastAPI

---