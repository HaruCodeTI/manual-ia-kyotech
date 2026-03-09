# ADR-001 — Infraestrutura Azure para o Sistema RAG

| Campo        | Valor                                       |
|--------------|---------------------------------------------|
| **Data**     | 2026-02-15                                  |
| **Status**   | Aceita                                      |
| **Autor**    | HaruCode (Equipe Kyotech AI)                |
| **Jira**     | IA-65                                       |
| **Relacao**  | ADR retroativo — decisao tomada no inicio do projeto |

---

## 1. Contexto

O projeto Kyotech AI necessita de infraestrutura cloud para hospedar um sistema RAG (Retrieval-Augmented Generation) voltado para consulta inteligente de manuais tecnicos Fujifilm. Os requisitos de infraestrutura incluem:

- **Banco de dados** com suporte a busca vetorial (embeddings) e busca textual (trigramas) para o pipeline RAG
- **Armazenamento de objetos** para PDFs de manuais tecnicos (ate centenas de MBs por documento)
- **Servico de IA generativa** para geracao de embeddings e respostas (LLM)
- **Hospedagem de aplicacao** para backend FastAPI e frontend Next.js
- **Seguranca** com isolamento de rede, SSL e controle de acesso

O cliente (Kyotoec) ja possui infraestrutura Microsoft Azure e licenciamento Microsoft 365, o que influenciou a decisao.

---

## 2. Decisao

**Adotar Microsoft Azure como provedor de infraestrutura cloud**, utilizando os seguintes servicos:

| Componente | Servico Azure | Justificativa |
|------------|---------------|---------------|
| **Banco de dados** | Azure Database for PostgreSQL (Flexible Server) | Suporte nativo a `pgvector` (busca vetorial) e `pg_trgm` (busca textual). PostgreSQL 15+ com SSL obrigatorio. |
| **Armazenamento** | Azure Blob Storage | Armazenamento de PDFs dos manuais. Organizacao por `{equipment_key}/{published_date}/{filename}`. |
| **IA generativa** | Azure OpenAI Service | Modelos `text-embedding-3-small` (embeddings), `gpt-4o` (geracao de respostas) e `gpt-4o-mini` (query rewrite). Dados nao usados para treinamento. |
| **Hospedagem** | Azure Container Apps | Hospedagem do backend FastAPI e frontend Next.js em containers. Escalabilidade automatica. |

### Stack resultante

| Camada | Tecnologia | Conexao |
|--------|-----------|---------|
| Frontend | Next.js 16 + React 19 + TypeScript | HTTPS (Container Apps) |
| Backend | FastAPI + Python 3.9 | HTTPS (Container Apps) |
| Banco de dados | PostgreSQL 15+ (pgvector + pg_trgm) | asyncpg / SSL |
| Armazenamento | Azure Blob Storage | Azure SDK (HTTPS) |
| IA | Azure OpenAI (gpt-4o, gpt-4o-mini, text-embedding-3-small) | HTTPS / REST |
| Autenticacao | Clerk (SaaS externo — ver ADR-002) | HTTPS / JWKS |

---

## 3. Alternativas Consideradas

### 3a. AWS (Amazon Web Services)

| Aspecto | Avaliacao |
|---------|-----------|
| Banco de dados | Amazon RDS for PostgreSQL com pgvector. Suporte a pg_trgm nativo. |
| Armazenamento | Amazon S3 — servico maduro e amplamente utilizado. |
| IA generativa | Amazon Bedrock (Claude, Titan) ou OpenAI via API direta. Sem Azure OpenAI nativo. |
| Busca | Amazon OpenSearch como alternativa para busca hibrida. |
| Hospedagem | Amazon ECS/Fargate para containers. |
| Integracao | Sem integracao nativa com ecossistema Microsoft do cliente. |
| Custo | Competitivo. Precificacao similar ao Azure para os servicos equivalentes. |

**Motivo de rejeicao:** Cliente ja possui infraestrutura e licenciamento Azure/Microsoft 365. Migrar para AWS adicionaria complexidade operacional e custo de gestao de dois provedores cloud.

### 3b. GCP (Google Cloud Platform)

| Aspecto | Avaliacao |
|---------|-----------|
| Banco de dados | Cloud SQL for PostgreSQL com pgvector (suporte recente). |
| Armazenamento | Google Cloud Storage. |
| IA generativa | Vertex AI (Gemini, PaLM). Sem Azure OpenAI nativo. |
| Hospedagem | Cloud Run para containers serverless. |
| Integracao | Sem integracao com ecossistema Microsoft. |

**Motivo de rejeicao:** Mesma questao que AWS — cliente nao possui presenca no GCP. Vertex AI e competente mas nao oferece modelos OpenAI nativos.

### 3c. Self-hosted (On-premises)

| Aspecto | Avaliacao |
|---------|-----------|
| Banco de dados | PostgreSQL auto-gerenciado com pgvector e pg_trgm. |
| Armazenamento | MinIO ou storage local. |
| IA generativa | Modelos open-source (Llama, Mistral) com vLLM/Ollama. |
| Hospedagem | Docker/Kubernetes on-premises. |
| Custo | Sem custos recorrentes de cloud, mas alto custo de hardware e operacao. |

**Motivo de rejeicao:** Alto custo operacional (hardware, manutencao, backup, seguranca). Modelos open-source nao atingem a qualidade do gpt-4o para o caso de uso de geracao de respostas tecnicas com citacoes. Sem equipe dedicada de infraestrutura.

---

## 4. Consequencias

### Positivas

- **Ecossistema integrado:** Azure Database, Blob Storage, OpenAI e Container Apps sob o mesmo provedor — faturamento unificado, VNet compartilhada, identidade centralizada
- **Conformidade de dados:** Azure OpenAI garante que dados enviados para embeddings e geracao de respostas nao sao usados para treinamento de modelos
- **Qualidade dos modelos:** Acesso a gpt-4o e gpt-4o-mini, que demonstraram melhor qualidade para geracao de respostas tecnicas em portugues com citacoes
- **pgvector nativo:** Azure Database for PostgreSQL suporta pgvector e pg_trgm nativamente, eliminando necessidade de servico de busca externo
- **Infraestrutura existente:** Cliente ja possui tenant Azure e licenciamento, reduzindo custo e tempo de setup
- **SSL e isolamento:** Conexoes SSL obrigatorias, opcao de Private Endpoints e VNet integration

### Negativas

- **Vendor lock-in:** Dependencia do Azure OpenAI (API compativel com OpenAI, mas deployments e endpoints sao Azure-especificos)
- **Custo recorrente:** Azure OpenAI, PostgreSQL e Blob Storage tem custos por uso (tokens, vCores, GB armazenado)
- **Complexidade de rede:** Configuracao de VNet, NSG, Private Endpoints exige conhecimento especifico de Azure
- **Disponibilidade regional:** Nem todos os modelos Azure OpenAI estao disponiveis em todas as regioes (ex: gpt-4o pode nao estar disponivel no Brasil)

### Riscos Mitigados

| Risco | Mitigacao |
|-------|-----------|
| Vendor lock-in Azure OpenAI | API compativel com OpenAI. Migracao para OpenAI direto requer apenas trocar endpoint e API key. |
| Custo escalar com uso | MVP com <50 usuarios. Monitoramento de custos via Azure Cost Management. Limites de tokens configuraveis. |
| Indisponibilidade de regiao | Deploy em regiao com disponibilidade de todos os servicos necessarios (ex: East US). |
| Migracao futura | PostgreSQL e padrao aberto — migravel para qualquer provedor. PDFs em Blob Storage exportaveis. |

---

## 5. Referencias

- Documento tecnico: "Infraestrutura de IA — Kyotoec MVP"
- Azure OpenAI: https://learn.microsoft.com/en-us/azure/ai-services/openai/
- pgvector: https://github.com/pgvector/pgvector
- pg_trgm: https://www.postgresql.org/docs/current/pgtrgm.html
- Card Jira: IA-65
