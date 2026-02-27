# Kyotech IA — Registro Completo de Infraestrutura & Próximos Passos

**HaruCode | Projeto Kyotech — Infraestrutura de IA**
**Data de início:** 26/02/2026
**Documento vivo — atualizar a cada fase concluída**

---

## 1. Visão Geral do Projeto

Sistema RAG (Retrieval-Augmented Generation) interno e privado para a Kyotech, permitindo que técnicos consultem manuais e informativos confidenciais da Fujifilm via chat em português, com citações rastreáveis (documento + página) e visualização direta do PDF.

**Documento de referência:** `Infraestrutura_IA_Kyotoec_MVP.md`

---

## 2. Infraestrutura Provisionada — Fase 0 ✅

### 2.1 Dados da Conta

| Campo | Valor |
|---|---|
| **Assinatura** | Azure subscription 1 |
| **Créditos disponíveis** | USD 1.000 (conta nova) |
| **Resource Group** | `rg-kyotech-ai` |
| **Região principal** | Canada Central |
| **Região secundária** | East US 2 (apenas OpenAI) |

### 2.2 Recursos Criados

#### Azure OpenAI — `aoai-kyotech`

| Campo | Valor |
|---|---|
| **Região** | East US 2 |
| **Pricing tier** | Standard S0 |
| **Acesso público** | Desabilitado (somente Private Endpoint) |
| **Private Endpoint** | `pe-openai-kyotech` (Canada Central → East US 2) |

**Deployments de modelo:**

| Nome do Deployment | Modelo | Versão | Tipo |
|---|---|---|---|
| `gpt-4o` | gpt-4o | 2024-11-20 | Global Standard |
| `gpt-4o-mini` | gpt-4o-mini | 2024-07-18 | Standard |
| `embedding-small` | text-embedding-3-small | 1 | Global Standard |

**Uso planejado:**
- `gpt-4o-mini` → Query rewriting + classificação Manual vs Informativo (barato, rápido)
- `gpt-4o` → Geração de respostas finais com citações (mais capaz)
- `embedding-small` → Gerar vetores de 1536 dimensões para chunks de texto

#### Virtual Network — `vnet-kyotech`

| Campo | Valor |
|---|---|
| **Região** | Canada Central |
| **Espaço de endereços** | 10.0.0.0/16 (65.536 endereços) |

**Subnets:**

| Nome | Intervalo | Tamanho | Delegação | Finalidade |
|---|---|---|---|---|
| `snet-app` | 10.0.1.0/24 | 256 endereços | — | Container App (backend + frontend) |
| `snet-endpoints` | 10.0.2.0/24 | 256 endereços | — | Private Endpoints |
| `snet-postgres` | 10.0.3.0/24 | 256 endereços | Microsoft.DBforPostgreSQL/flexibleServers | PostgreSQL Flexible Server |
| `AzureFirewallSubnet` | 10.0.4.0/26 | 64 endereços | — | Reservada para Firewall (Fase 2) |

#### Storage Account — `stkyotechai`

| Campo | Valor |
|---|---|
| **Região** | Canada Central |
| **Tipo** | Armazenamento de Blobs |
| **Desempenho** | Standard |
| **Redundância** | LRS (redundância local) |
| **Acesso público** | Desabilitado |
| **Transferência segura** | Habilitado (HTTPS) |
| **Acesso anônimo ao blob** | Desabilitado |
| **TLS mínimo** | 1.2 |
| **Private Endpoint** | `pe-blob-kyotech` |

**Containers:**

| Nome | Nível de acesso | Finalidade |
|---|---|---|
| `pdfs-originais` | Privado | PDFs brutos baixados do portal Fujifilm |
| `pdfs-processados` | Privado | PDFs pós-processamento (OCR futuro) |

#### PostgreSQL Flexible Server — `psql-kyotech`

| Campo | Valor |
|---|---|
| **Região** | Canada Central |
| **Versão** | PostgreSQL 17 |
| **Tier** | Burstable (Desenvolvimento/Teste) |
| **Compute** | Standard_B2s (2 vCores, 4 GiB RAM) |
| **Armazenamento** | 32 GiB (P4, 120 IOPS) |
| **Custo estimado** | USD 58.08/mês |
| **Redundância geográfica** | Desabilitada |
| **Resiliência zonal** | Desabilitada (SLA 99.9%) |
| **Autenticação** | PostgreSQL + Microsoft Entra |
| **Admin username** | *(definido na criação — armazenar em local seguro)* |
| **Rede** | VNet Integration via `snet-postgres` |
| **DNS privado** | `psql-kyotech.private.postgres.database.azure.com` |
| **Extensão pgvector** | ✅ Ativada via Server Parameters |

#### Private Endpoints

| Nome | Recurso alvo | Sub-resource | Subnet | Região |
|---|---|---|---|---|
| `pe-blob-kyotech` | `stkyotechai` | blob | `snet-endpoints` | Canada Central |
| `pe-openai-kyotech` | `aoai-kyotech` | account | `snet-endpoints` | Canada Central |

#### Private DNS Zones

| Zona | Tipo |
|---|---|
| `privatelink.blob.core.windows.net` | Global |
| `privatelink.openai.azure.com` | Global |
| `psql-kyotech.private.postgres.database.azure.com` | Global |

### 2.3 Segurança Configurada

| Item | Status |
|---|---|
| Todos os serviços sem acesso público | ✅ |
| Private Endpoints para Blob e OpenAI | ✅ |
| PostgreSQL isolado via VNet Integration | ✅ |
| Storage com acesso anônimo desabilitado | ✅ |
| TLS 1.2 mínimo em todos os serviços | ✅ |
| Azure Firewall | ⏳ Fase 2 (subnet reservada) |
| NSG com regras customizadas | ⏳ Fase 1 |
| Clerk (autenticação app) | ✅ |

### 2.4 Custos Atuais

| Recurso | Custo/mês (USD) |
|---|---|
| PostgreSQL B2s | ~$58 |
| Private Endpoints (x2) | ~$15 |
| Private DNS Zones (x3) | ~$1.50 |
| Storage (< 1 GB) | ~$0.10 |
| OpenAI (testes leves) | ~$5–15 |
| **Total estimado Mês 1** | **~$80–90** |
| **Créditos restantes após Mês 1** | **~$910** |

**Budget Alerts configurados:**
- `budget-kyotech-1000`: Mensal, USD 150, alertas em 50%, 80% e 100% (forecasted)
- `budget-creditos-total`: Anual, USD 900, alertas em 25%, 50% e 75%

---

## 3. Próximo Passo Imediato — Conectar ao PostgreSQL via VS Code

### 3.1 Instalar a Extensão

A extensão oficial da Microsoft para PostgreSQL no VS Code é a **"PostgreSQL"** (publisher: Microsoft).

**Passos:**

1. Abra o VS Code.
2. Vá em **Extensions** (Ctrl+Shift+X).
3. Busque por **"PostgreSQL"** — procure a extensão publicada por **Microsoft**.
   - Nome completo: `ms-ossdata.vscode-postgresql` ou a mais recente `microsoft.vscode-postgresql`
4. Clique em **Install**.

> 📖 Doc oficial: https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/quickstart-create-connect-server-vscode

### 3.2 Obter a String de Conexão

1. No portal Azure, vá em `psql-kyotech`.
2. No menu lateral, clique em **"Conectar"** (ou "Connect").
3. Anote os seguintes dados:

| Campo | Valor |
|---|---|
| **Host** | `psql-kyotech.postgres.database.azure.com` |
| **Porta** | `5432` |
| **Database** | `postgres` (padrão; depois criaremos `kyotech_db`) |
| **Username** | *(o admin definido na criação)* |
| **SSL** | Obrigatório (require) |

### 3.3 Configurar Acesso de Rede Temporário

**Problema:** O PostgreSQL está isolado na VNet, então seu computador local não consegue acessá-lo diretamente. Para o desenvolvimento inicial, precisamos liberar acesso temporário.

**Solução no portal:**

1. No `psql-kyotech`, vá em **"Rede"** (ou "Networking") no menu lateral.
2. Procure a opção **"Permitir acesso público a este recurso através da Internet usando um endereço IP público"** e habilite.
3. Em **"Regras de firewall"**, clique em **"+ Adicionar endereço IP do cliente atual"**.
4. Clique em **"Salvar"**.

> ⚠️ **IMPORTANTE:** Isso é temporário, apenas para desenvolvimento. Na Fase 2 (hardening), vamos remover esse acesso e usar apenas a VNet. Anote no checklist para não esquecer de revogar depois.

### 3.4 Conectar pelo VS Code

1. Abra o VS Code com a extensão PostgreSQL instalada.
2. Na barra lateral, clique no ícone de banco de dados (ou Ctrl+Shift+P → "PostgreSQL: New Connection").
3. Preencha:
   - **Host:** `psql-kyotech.postgres.database.azure.com`
   - **Port:** `5432`
   - **Database:** `postgres`
   - **Username:** *(seu admin)*
   - **Password:** *(sua senha)*
   - **SSL:** Require
4. Teste a conexão. Se conectar, você verá o banco no explorer lateral.

### 3.5 Criar o Database do Projeto

Após conectar, abra um **New Query** e execute:

```sql
-- Criar o database do projeto
CREATE DATABASE kyotech_db;
```

Depois, **reconecte** apontando para `kyotech_db` em vez de `postgres`.

---

## 4. Próximo Passo — Criar o Schema do Banco (Fase 1)

Após conectar ao `kyotech_db`, executar o seguinte SQL para criar a estrutura conforme Seção 4 do documento de arquitetura:

```sql
-- Ativar extensões necessárias
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm; -- para busca textual fuzzy

-- Tabela: equipments
-- Mapeia equipamentos Fujifilm com aliases para query rewriting
CREATE TABLE equipments (
    equipment_key VARCHAR(100) PRIMARY KEY,
    display_name  VARCHAR(255) NOT NULL,
    aliases       TEXT[] DEFAULT '{}'
);

-- Tabela: documents
-- Registro lógico de cada documento (manual ou informativo)
CREATE TABLE documents (
    id             UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    doc_type       VARCHAR(20) NOT NULL CHECK (doc_type IN ('manual', 'informativo')),
    equipment_key  VARCHAR(100) NOT NULL REFERENCES equipments(equipment_key),
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_documents_equipment ON documents(equipment_key);
CREATE INDEX idx_documents_doc_type ON documents(doc_type);

-- Tabela: document_versions
-- Cada versão de um documento, versionada por published_date
CREATE TABLE document_versions (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    published_date  DATE NOT NULL,
    source_hash     VARCHAR(64) NOT NULL,
    source_filename VARCHAR(500) NOT NULL,
    ingested_at     TIMESTAMPTZ DEFAULT NOW(),
    storage_path    VARCHAR(1000) NOT NULL,

    -- Previne duas versões com mesma data para o mesmo documento
    CONSTRAINT uq_document_version UNIQUE (document_id, published_date)
);

CREATE INDEX idx_versions_document ON document_versions(document_id);
CREATE INDEX idx_versions_published ON document_versions(published_date DESC);

-- Tabela: chunks
-- Pedaços de texto extraídos de cada versão, com embedding vetorial
CREATE TABLE chunks (
    id                   UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    document_version_id  UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    page_number          INTEGER NOT NULL,
    chunk_index          INTEGER NOT NULL DEFAULT 0,
    content              TEXT NOT NULL,
    embedding            vector(1536), -- text-embedding-3-small gera 1536 dimensões

    CONSTRAINT uq_chunk UNIQUE (document_version_id, page_number, chunk_index)
);

-- Índice vetorial para busca por similaridade (IVFFlat)
-- Criar APÓS ter pelo menos ~1000 chunks para calibragem adequada
-- CREATE INDEX idx_chunks_embedding ON chunks
--     USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Índice para busca textual (full-text search em inglês)
CREATE INDEX idx_chunks_content_trgm ON chunks USING gin (content gin_trgm_ops);

-- Índice para filtragem rápida por versão
CREATE INDEX idx_chunks_version ON chunks(document_version_id);

-- View: versões atuais (mais recente de cada documento)
CREATE VIEW current_versions AS
SELECT DISTINCT ON (document_id)
    id,
    document_id,
    published_date,
    source_filename,
    storage_path
FROM document_versions
ORDER BY document_id, published_date DESC;

-- Função: busca vetorial apenas nas versões atuais
CREATE OR REPLACE FUNCTION search_current_chunks(
    query_embedding vector(1536),
    match_count INTEGER DEFAULT 10,
    filter_doc_type VARCHAR DEFAULT NULL,
    filter_equipment VARCHAR DEFAULT NULL
)
RETURNS TABLE (
    chunk_id          UUID,
    content           TEXT,
    page_number       INTEGER,
    similarity        FLOAT,
    document_id       UUID,
    doc_type          VARCHAR,
    equipment_key     VARCHAR,
    published_date    DATE,
    source_filename   VARCHAR,
    storage_path      VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id AS chunk_id,
        c.content,
        c.page_number,
        1 - (c.embedding <=> query_embedding) AS similarity,
        d.id AS document_id,
        d.doc_type,
        d.equipment_key,
        cv.published_date,
        cv.source_filename,
        cv.storage_path
    FROM chunks c
    JOIN current_versions cv ON c.document_version_id = cv.id
    JOIN documents d ON cv.document_id = d.id
    WHERE
        (filter_doc_type IS NULL OR d.doc_type = filter_doc_type)
        AND (filter_equipment IS NULL OR d.equipment_key = filter_equipment)
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;
```

**Nota sobre o índice vetorial (IVFFlat):** Está comentado propositalmente. Deve ser criado apenas após inserir pelo menos ~1.000 chunks, para que a calibragem do índice seja adequada. Até lá, a busca vetorial funciona com scan sequencial (mais lento, mas correto).

---

## 5. Roadmap — Fases Seguintes

### Fase 1 — MVP Funcional (Semanas 1–4)

| Tarefa | Descrição | Status |
|---|---|---|
| Schema do banco | Criar tabelas, índices, views e funções | ⏳ Próximo |
| Pipeline de ingestion | Upload PDF → extração de texto → chunking → embedding → armazenamento | ⬜ |
| API Backend | FastAPI/Node.js com orquestração RAG | ⬜ |
| Query rewriting | Prompt PT→EN com glossário Fujifilm | ⬜ |
| Classificação | Router automático Manual vs Informativo | ⬜ |
| Busca híbrida | Vetorial (pgvector) + textual (pg_trgm) | ⬜ |
| Geração de resposta | GPT-4o com citações (documento + página) | ⬜ |
| Frontend chat | Interface básica de chat em React/Next.js | ⬜ |
| Viewer de PDF | Abertura na página citada via URL assinada (#page=) | ⬜ |
| Autenticação | Clerk (login corporativo) | ✅ |

### Fase 2 — Robustez Operacional (Semanas 5–8)

| Tarefa | Descrição |
|---|---|
| Azure Firewall Basic | Ativar na `AzureFirewallSubnet` para bloqueio de egress |
| Revogar acesso público do PostgreSQL | Remover regra de firewall temporária |
| NSG refinado | Regras deny-all + allow explícito entre subnets |
| Dashboard de uso | Métricas de consultas, tokens, latência |
| Versionamento refinado | Tiebreaker por `ingested_at`, validação de data por OCR |
| Melhorias de ranking | Reranking, feedback loop, ajuste de prompts |

### Fase 3 — Evolução Contínua (Semana 9+)

| Tarefa | Descrição |
|---|---|
| OCR avançado | Azure Document Intelligence para PDFs escaneados |
| Tradução batch JP→EN | Pipeline de tradução na ingestion para docs em japonês |
| Métricas e alertas | Application Insights, dashboards de custo |
| Scale out | PostgreSQL General Purpose, múltiplas instâncias do app |
| Feedback loop | Técnicos avaliam respostas, dados alimentam melhorias |

---

## 6. Links de Referência

| Tópico | URL |
|---|---|
| Resource Groups | https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/manage-resource-groups-portal |
| Budget Alerts | https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets |
| Virtual Networks | https://learn.microsoft.com/en-us/azure/virtual-network/quick-create-portal |
| Storage Account | https://learn.microsoft.com/en-us/azure/storage/common/storage-account-create |
| PostgreSQL Flexible Server | https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/quickstart-create-server-portal |
| pgvector no PostgreSQL | https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-use-pgvector |
| Azure OpenAI — Criar recurso | https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/create-resource |
| Private Endpoints | https://learn.microsoft.com/en-us/azure/private-link/create-private-endpoint-portal |
| VS Code + PostgreSQL | https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/quickstart-create-connect-server-vscode |
| Acesso limitado ao OpenAI | https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/openai/limited-access |
| Limites de assinatura Azure | https://learn.microsoft.com/pt-br/azure/azure-resource-manager/management/azure-subscription-service-limits |

---

## 7. Decisões Técnicas Registradas

| # | Decisão | Justificativa |
|---|---|---|
| 1 | Canada Central como região principal | East US 2 bloqueada para PostgreSQL na assinatura. Canada Central aceita todos os recursos necessários. |
| 2 | OpenAI em East US 2 | Criado antes da descoberta do bloqueio. Funciona via Private Endpoint cross-region sem impacto relevante de latência. |
| 3 | Sem Azure Firewall no MVP | Custo de ~$335/mês representa 65% do fixo. NSG + Private Endpoints garantem isolamento adequado para Fase 1. Firewall entra na Fase 2. |
| 4 | PostgreSQL B2s (Burstable) | Suficiente para desenvolvimento e carga inicial (~$58/mês). Upgrade para General Purpose na Fase 3 se necessário. |
| 5 | LRS para Storage | Redundância local suficiente para MVP. PDFs podem ser re-obtidos do portal Fujifilm se necessário. |
| 6 | Índice IVFFlat adiado | Deve ser criado somente após ~1.000+ chunks para calibragem adequada. Busca sequencial é aceitável durante ingestion inicial. |
| 7 | Acesso público temporário no PostgreSQL | Necessário para desenvolvimento via VS Code. Será revogado na Fase 2 (hardening). |

---

## 8. Checklist de Segurança Pendente (Revogar na Fase 2)

- [ ] Remover regra de firewall pública do PostgreSQL
- [ ] Implementar Azure Firewall Basic na `AzureFirewallSubnet`
- [ ] Configurar NSG com deny-all outbound + allow explícito
- [ ] Auditar logs de acesso ao Blob Storage
- [ ] Configurar RBAC granular para usuários do sistema

---

*HaruCode © 2026 — Documento de uso interno*
*Última atualização: 26/02/2026*