# C4 — Diagrama de Contexto: Kyotech AI

| Campo        | Valor                                       |
|--------------|---------------------------------------------|
| **Data**     | 2026-03-09                                  |
| **Autor**    | HaruCode (Equipe Kyotech AI)                |
| **Jira**     | IA-61                                       |

---

## Visão Geral

O diagrama de contexto mostra o sistema **Kyotech AI** e suas interações com atores humanos e sistemas externos. O Kyotech AI e um sistema RAG (Retrieval-Augmented Generation) projetado para consulta inteligente de manuais tecnicos Fujifilm por tecnicos de campo.

---

## Diagrama

```mermaid
C4Context
    title Diagrama de Contexto — Kyotech AI

    Person(tecnico, "Tecnico de Campo", "Consulta manuais tecnicos Fujifilm via chat com IA. Visualiza PDFs com citacoes.")
    Person(admin, "Gerente / Admin", "Carrega documentos PDF, gerencia base de conhecimento, visualiza metricas de uso.")

    System(kyotech, "Kyotech AI", "Sistema RAG para consulta inteligente de manuais tecnicos Fujifilm. Chat com citacoes, busca hibrida, viewer seguro de PDFs.")

    System_Ext(clerk, "Clerk", "Provedor SaaS de autenticacao. Emite JWTs, gerencia sessoes e RBAC via public_metadata.")
    System_Ext(azure_openai, "Azure OpenAI", "Servico de IA generativa. Fornece embeddings (text-embedding-3-small) e LLMs (gpt-4o, gpt-4o-mini).")
    System_Ext(azure_blob, "Azure Blob Storage", "Armazenamento de objetos para PDFs dos manuais tecnicos Fujifilm.")
    System_Ext(azure_pg, "Azure PostgreSQL", "Banco de dados relacional com extensoes pgvector (busca vetorial) e pg_trgm (busca textual por trigramas).")

    Rel(tecnico, kyotech, "Faz perguntas tecnicas, visualiza respostas com citacoes e PDFs", "HTTPS")
    Rel(admin, kyotech, "Carrega PDFs, visualiza metricas de equipamentos e documentos", "HTTPS")

    Rel(kyotech, clerk, "Valida tokens JWT via JWKS endpoint publico", "HTTPS / RS256")
    Rel(kyotech, azure_openai, "Gera embeddings, reescreve queries (gpt-4o-mini), gera respostas (gpt-4o)", "HTTPS / REST")
    Rel(kyotech, azure_blob, "Upload e download de PDFs dos manuais", "HTTPS / Azure SDK")
    Rel(kyotech, azure_pg, "Armazena documentos, chunks, embeddings, sessoes de chat", "asyncpg / SSL")
```

---

## Descricao dos Elementos

### Atores

| Ator | Descricao | Papel (Role) |
|------|-----------|--------------|
| **Tecnico de Campo** | Profissional que realiza manutencao em equipamentos Fujifilm. Usa o chat para consultar procedimentos, codigos de pecas e boletins tecnicos. | `Technician` |
| **Gerente / Admin** | Responsavel pela gestao da base de conhecimento. Carrega novos manuais, acompanha metricas de uso e gerencia equipamentos. | `Admin` |

### Sistema Central

| Sistema | Descricao |
|---------|-----------|
| **Kyotech AI** | Aplicacao web RAG que permite consulta inteligente de manuais tecnicos Fujifilm. Combina busca hibrida (vetorial + textual), geracao de respostas com citacoes rastreavels e visualizacao segura de PDFs com watermark. |

### Sistemas Externos

| Sistema | Funcao no Kyotech AI |
|---------|---------------------|
| **Clerk** | Autenticacao e autorizacao. Emite JWTs validados no backend via JWKS. Roles (`Admin` / `Technician`) configurados via `public_metadata`. |
| **Azure OpenAI** | Modelo `text-embedding-3-small` para embeddings de chunks. Modelo `gpt-4o-mini` para reescrita de queries (PT→EN). Modelo `gpt-4o` para geracao de respostas com citacoes. |
| **Azure Blob Storage** | Armazenamento dos PDFs originais dos manuais. Organizado por `equipment_key/published_date/filename`. |
| **Azure PostgreSQL** | Banco de dados principal com `pgvector` para busca por similaridade coseno e `pg_trgm` para busca textual por trigramas. Armazena documentos, versoes, chunks com embeddings e sessoes de chat. |

---

## Fluxos Principais

1. **Consulta RAG:** Tecnico faz pergunta → Kyotech AI reescreve query → busca hibrida no PostgreSQL → gera resposta via Azure OpenAI → retorna com citacoes
2. **Upload de documento:** Admin carrega PDF → Kyotech AI extrai texto, gera embeddings via Azure OpenAI → armazena PDF no Blob Storage → insere chunks no PostgreSQL
3. **Visualizacao segura:** Tecnico clica em citacao → Kyotech AI baixa PDF do Blob Storage → renderiza pagina como PNG com watermark → retorna imagem (PDF nunca exposto)
4. **Autenticacao:** Usuario faz login via Clerk → recebe JWT → frontend envia Bearer token → backend valida via JWKS do Clerk
