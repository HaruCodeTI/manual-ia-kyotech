# Design: Testes & Qualidade + Documentação — Kyotech AI

| Campo       | Valor                              |
|-------------|------------------------------------|
| **Data**    | 2026-03-09                         |
| **Autor**   | HaruCode (Equipe Kyotech AI)      |
| **Jira**    | IA-74, IA-61, IA-62, IA-64, IA-65, IA-66 |
| **Fase**    | Pré-Hardening                      |

---

## 1. Objetivo

Estabelecer cobertura de testes robusta no backend e documentação técnica completa antes da fase de hardening (IA-81). Testes de qualidade RAG e prompt injection (IA-75) ficam para fase posterior.

## 2. Decisões

- **Testes:** Backend only (pytest), mocks robustos sem banco real
- **API Docs:** Scalar (substitui Swagger UI), OpenAPI auto-gerada pelo FastAPI
- **Documentação arquitetural:** Markdown + Mermaid, versionada no git
- **CI:** Step de testes no GitHub Actions antes do deploy

---

## 3. Estrutura de Testes

```
backend/
├── pytest.ini
├── requirements-dev.txt
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_chunker.py
│   │   ├── test_pdf_extractor.py
│   │   ├── test_query_rewriter.py
│   │   ├── test_generator.py
│   │   ├── test_search.py
│   │   ├── test_embedder.py
│   │   ├── test_storage.py
│   │   ├── test_viewer_service.py
│   │   ├── test_auth.py
│   │   ├── test_repository.py
│   │   └── test_chat_repository.py
│   └── integration/
│       ├── test_chat_api.py
│       ├── test_upload_api.py
│       ├── test_sessions_api.py
│       ├── test_viewer_api.py
│       └── test_health.py
```

### 3.1 Fixtures Centrais (`conftest.py`)

| Fixture | Descrição |
|---------|-----------|
| `mock_db` | `AsyncMock` de `AsyncSession` com `.execute()` configurável |
| `mock_openai_client` | Patcha `get_openai_client()` com respostas tipadas |
| `mock_blob_client` | Patcha `get_blob_client()` para upload/download |
| `fake_user_admin` | `CurrentUser(id="test-admin", role="Admin")` |
| `fake_user_tech` | `CurrentUser(id="test-tech", role="Technician")` |
| `test_app` | FastAPI app com dependency overrides |
| `async_client` | `httpx.AsyncClient` apontando para `test_app` |
| `sample_pdf_bytes` | PDF mínimo gerado com PyMuPDF |

### 3.2 Cobertura por Módulo

**Unitários — Lógica pura e serviços isolados:**

| Módulo | Testes |
|--------|--------|
| `chunker` | chunk_text com textos curtos/longos, boundary de overlap, chunk_pages com páginas vazias |
| `pdf_extractor` | Extração de texto, hash SHA-256, PDF sem texto (ValueError), PDF corrompido |
| `query_rewriter` | Rewrite com JSON válido, JSON inválido (fallback), doc_type "both" → None |
| `generator` | build_context formatação, generate_response com/sem resultados, parse de citações |
| `search` | vector_search com filtros, text_search, hybrid_search fusão e pesos |
| `embedder` | generate_embeddings batching, generate_single_embedding |
| `storage` | upload_pdf, download_blob (split container/blob), generate_signed_url |
| `viewer` | render_page_as_image com página válida/inválida, watermark |
| `auth` | JWT válido, expirado, inválido, dev mode (sem JWKS), _extract_role, require_role |
| `repository` | find_or_create_equipment/document, check_version_exists, create_version, insert_chunks |
| `chat_repository` | create_session, list_sessions, get_session_with_messages, add_message, delete_session |

**Integração — Endpoints HTTP:**

| Endpoint | Testes |
|----------|--------|
| `GET /health` | Status 200, body correto |
| `POST /chat/ask` | Auth obrigatória, resposta com citações, sessão nova vs existente |
| `GET /chat/pdf-url` | SAS URL gerada, auth obrigatória |
| `POST /upload/document` | Apenas Admin, validação PDF, duplicata, sucesso |
| `GET /upload/stats` | Apenas Admin |
| `GET /upload/equipments` | Auth obrigatória |
| `GET/POST/DELETE /sessions` | CRUD completo, isolamento por user_id |
| `GET /viewer/info/{id}` | Metadados, 404 para versão inexistente |
| `GET /viewer/page/{id}/{n}` | Imagem PNG, página inválida → 400 |

### 3.3 Dependências de Teste

```
# requirements-dev.txt
pytest>=8.0
pytest-asyncio>=0.24
pytest-cov>=6.0
respx>=0.22
```

`httpx` já existe em `requirements.txt`.

---

## 4. Scalar API Docs

- Instalar `scalar-fastapi` e integrar no `main.py`
- Substituir Swagger UI padrão do FastAPI
- Enriquecer routers com `summary`, `description`, `responses` detalhados
- Adicionar `json_schema_extra` nos Pydantic models para exemplos
- OpenAPI spec auto-gerada cobre IA-66

---

## 5. Documentação Arquitetural

| Arquivo | Jira | Conteúdo |
|---------|------|----------|
| `docs/architecture/c4-context.md` | IA-61 | Diagrama C4 Context (Mermaid) |
| `docs/architecture/c4-container.md` | IA-61 | Diagrama C4 Container (Mermaid) |
| `docs/architecture/sequence-auth.md` | IA-62 | Sequência: fluxo de autenticação Clerk |
| `docs/architecture/sequence-upload.md` | IA-62 | Sequência: upload + pipeline de ingestão |
| `docs/architecture/sequence-rag.md` | IA-62 | Sequência: consulta RAG (rewrite → search → generate) |
| `docs/use-cases/UC01-UC06.md` | IA-64 | Casos de uso formais |
| `docs/adrs/ADR-001-azure-infra.md` | IA-65 | ADR infra Azure (retroativo) |
| `docs/adrs/ADR-003-rag-hybrid-search.md` | IA-65 | ADR busca híbrida vetorial + textual |
| `docs/adrs/ADR-004-pdf-viewer-security.md` | IA-65 | ADR viewer seguro sem exposição de PDF |

---

## 6. CI/CD

Adicionar job `test-backend` no `.github/workflows/deploy.yml`:

- Python 3.9, instala `requirements.txt` + `requirements-dev.txt`
- Roda `pytest --cov=app --cov-report=term-missing -v`
- Sem banco real — tudo com mocks
- Jobs de deploy passam a depender de `test-backend`

---

## 7. Atualizações em Artefatos

| Artefato | Mudança |
|----------|---------|
| `requirements.txt` | Adicionar `scalar-fastapi` |
| `requirements-dev.txt` | Novo arquivo com deps de teste |
| `backend/app/main.py` | Integrar Scalar, desabilitar Swagger UI |
| `.github/workflows/deploy.yml` | Adicionar job `test-backend` |
| `README.md` | Seções: rodar testes, acessar API docs, estrutura do projeto |
| Routers (`chat.py`, `upload.py`, etc.) | Enriquecer metadata OpenAPI |

---

## 8. Fora do Escopo (Fase Posterior)

- IA-75: Testes de qualidade RAG + prompt injection
- Testes frontend (Vitest/Jest)
- Testes com banco PostgreSQL real (docker-compose)
