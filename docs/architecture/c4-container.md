# C4 — Diagrama de Container: Kyotech AI

| Campo        | Valor                                       |
|--------------|---------------------------------------------|
| **Data**     | 2026-03-09                                  |
| **Autor**    | HaruCode (Equipe Kyotech AI)                |
| **Jira**     | IA-61                                       |

---

## Visao Geral

O diagrama de container detalha os componentes internos do sistema Kyotech AI e suas interacoes com sistemas externos, incluindo protocolos de comunicacao.

---

## Diagrama

```mermaid
C4Container
    title Diagrama de Container — Kyotech AI

    Person(tecnico, "Tecnico de Campo", "Consulta manuais via chat")
    Person(admin, "Gerente / Admin", "Gerencia documentos e metricas")

    System_Boundary(kyotech, "Kyotech AI") {
        Container(frontend, "Frontend", "Next.js 16, React 19, TypeScript", "SPA com chat RAG, upload de documentos, viewer de PDFs e dashboard de metricas. Autenticacao via @clerk/nextjs.")
        Container(backend, "Backend API", "FastAPI, Python 3.9", "API REST com pipeline RAG, ingestion de PDFs, busca hibrida e viewer seguro. Validacao JWT via PyJWKClient.")
    }

    System_Ext(clerk, "Clerk", "Autenticacao SaaS (JWT + JWKS)")
    System_Ext(azure_openai, "Azure OpenAI", "Embeddings + LLM (gpt-4o, gpt-4o-mini)")
    System_Ext(azure_blob, "Azure Blob Storage", "Armazenamento de PDFs")
    System_Ext(azure_pg, "Azure PostgreSQL", "PostgreSQL 15+ com pgvector e pg_trgm")

    Rel(tecnico, frontend, "Acessa via navegador", "HTTPS")
    Rel(admin, frontend, "Acessa via navegador", "HTTPS")

    Rel(frontend, clerk, "Login, sessao, getToken()", "HTTPS")
    Rel(frontend, backend, "Chamadas API com Bearer JWT", "HTTPS / REST")

    Rel(backend, clerk, "Valida JWT via JWKS", "HTTPS / RS256")
    Rel(backend, azure_openai, "Embeddings, query rewrite, geracao de resposta", "HTTPS / REST")
    Rel(backend, azure_blob, "Upload e download de PDFs", "HTTPS / Azure SDK")
    Rel(backend, azure_pg, "CRUD de documentos, chunks, sessoes, busca hibrida", "asyncpg / SSL")
```

---

## Detalhamento dos Containers

### Frontend

| Aspecto | Detalhe |
|---------|---------|
| **Tecnologia** | Next.js 16 + React 19 + TypeScript |
| **Autenticacao** | `@clerk/nextjs` com `ClerkProvider`, `<SignIn />`, `<UserButton />` |
| **Localizacao** | `@clerk/localizations` (pt-BR) |
| **Protecao de rotas** | `clerkMiddleware()` no middleware do Next.js |
| **Comunicacao com Backend** | Bearer JWT via `getToken()` do Clerk em headers `Authorization` |

#### Paginas principais

- **Chat RAG** — Interface de perguntas e respostas com citacoes clicaveis
- **Viewer de PDF** — Visualizacao segura de paginas renderizadas como imagem (PNG)
- **Upload** — Formulario para Admin carregar novos manuais PDF
- **Dashboard** — Metricas de equipamentos, documentos e chunks (Admin)
- **Sessoes** — Listagem e gerenciamento de historico de conversas

### Backend API

| Aspecto | Detalhe |
|---------|---------|
| **Tecnologia** | FastAPI + Python 3.9 |
| **Autenticacao** | `PyJWT` + `PyJWKClient` validando JWKS do Clerk (RS256) |
| **RBAC** | `get_current_user()` e `require_role()` como dependencies FastAPI |
| **Banco de dados** | `SQLAlchemy` async + `asyncpg` com SSL |

#### Routers da API

| Router | Prefixo | Descricao |
|--------|---------|-----------|
| **Chat** | `/chat` | `POST /chat/ask` — pipeline RAG completo |
| **Upload** | `/upload` | `POST /upload/document` — ingestion de PDFs (Admin) |
| **Sessions** | `/sessions` | CRUD de sessoes de chat |
| **Viewer** | `/viewer` | `GET /viewer/page/{version_id}/{page}` — render de PDF como PNG |

#### Servicos internos

| Servico | Responsabilidade |
|---------|-----------------|
| `query_rewriter` | Traduz query PT→EN via gpt-4o-mini, classifica tipo de documento |
| `search` | Busca hibrida: vetorial (pgvector, cosine) + textual (pg_trgm, trigram) com fusao 70/30 |
| `generator` | Gera resposta em PT com citacoes `[Fonte N]` via gpt-4o |
| `ingestion` | Pipeline de 6 etapas: extrair texto, equipamento, documento, upload blob, versao, chunks+embeddings |
| `viewer` | Renderiza pagina de PDF como PNG com watermark dinamico (user_id + timestamp) |
| `pdf_extractor` | Extrai texto de PDFs via PyMuPDF, calcula SHA-256 |
| `embedder` | Gera embeddings via Azure OpenAI (text-embedding-3-small) |
| `storage` | Upload/download de blobs no Azure Blob Storage |
| `repository` | CRUD de equipamentos, documentos, versoes e chunks no PostgreSQL |
| `chat_repository` | CRUD de sessoes e mensagens de chat |

### Banco de Dados (Azure PostgreSQL)

| Aspecto | Detalhe |
|---------|---------|
| **Versao** | PostgreSQL 15+ |
| **Extensoes** | `pgvector` (busca vetorial), `pg_trgm` (busca por trigramas) |
| **Conexao** | `asyncpg` com SSL obrigatorio |
| **Tabelas principais** | `equipments`, `documents`, `document_versions`, `chunks`, `chat_sessions`, `chat_messages` |
| **View** | `current_versions` — versao mais recente de cada documento |

---

## Protocolos de Comunicacao

| Origem | Destino | Protocolo | Detalhes |
|--------|---------|-----------|----------|
| Navegador | Frontend | HTTPS | Aplicacao SPA servida via Next.js |
| Frontend | Clerk | HTTPS | SDK `@clerk/nextjs` para login, sessao, `getToken()` |
| Frontend | Backend | HTTPS / REST | Bearer JWT no header `Authorization` |
| Backend | Clerk | HTTPS | Fetch do JWKS para validacao do JWT (RS256) |
| Backend | Azure OpenAI | HTTPS / REST | API key + endpoint Azure para embeddings e chat completions |
| Backend | Azure Blob Storage | HTTPS | Azure SDK (`azure-storage-blob`) para upload/download |
| Backend | Azure PostgreSQL | asyncpg / SSL | Conexao async com SSL, queries SQL raw via SQLAlchemy |
