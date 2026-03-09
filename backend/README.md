# Kyotech AI — Backend

Sistema RAG para consulta de manuais e informativos Fujifilm.

## Estrutura do Projeto

```
backend/
├── app/
│   ├── main.py                    # App FastAPI + Scalar docs
│   ├── api/
│   │   ├── chat.py                # RAG query endpoint
│   │   ├── upload.py              # Upload de PDFs
│   │   ├── sessions.py            # CRUD sessões de chat
│   │   └── viewer.py              # Viewer seguro (PDF → PNG)
│   ├── core/
│   │   ├── auth.py                # Autenticação Clerk (JWT/JWKS)
│   │   ├── config.py              # Configurações (.env)
│   │   └── database.py            # Conexão PostgreSQL async
│   └── services/
│       ├── pdf_extractor.py       # Extração de texto (PyMuPDF)
│       ├── chunker.py             # Divisão em chunks com overlap
│       ├── embedder.py            # Embeddings (Azure OpenAI)
│       ├── query_rewriter.py      # Rewrite PT → EN (gpt-4o-mini)
│       ├── search.py              # Busca híbrida (vector + text)
│       ├── generator.py           # Geração de resposta (gpt-4o)
│       ├── storage.py             # Azure Blob Storage
│       ├── repository.py          # CRUD documentos/equipamentos
│       ├── chat_repository.py     # CRUD sessões/mensagens
│       ├── viewer.py              # Render PDF → PNG com watermark
│       └── ingestion.py           # Orquestrador do pipeline
├── tests/
│   ├── conftest.py                # Fixtures compartilhadas
│   ├── unit/                      # Testes unitários (11 módulos)
│   └── integration/               # Testes de integração (5 endpoints)
├── requirements.txt               # Dependências de produção
├── requirements-dev.txt           # Dependências de teste
├── pytest.ini                     # Configuração do pytest
├── .env.example                   # Template de variáveis
└── Dockerfile
```

## Setup Local

### Pré-requisitos

- Python 3.9+
- PostgreSQL com pgvector (ou acesso ao Azure PostgreSQL)
- Conta Azure com OpenAI e Blob Storage configurados

### Instalar dependências

```bash
cd backend
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite .env com seus valores reais
```

### Rodar o servidor

```bash
uvicorn app.main:app --reload --port 8000
```

## API Docs (Scalar)

Acesse `http://localhost:8000/docs` para a documentação interativa da API (Scalar).

O schema OpenAPI é gerado automaticamente pelo FastAPI.

## Rodar Testes

```bash
# Instalar dependências de teste
pip install -r requirements-dev.txt

# Rodar todos os testes
python -m pytest -v

# Com cobertura
python -m pytest --cov=app --cov-report=term-missing -v

# Apenas unitários
python -m pytest tests/unit/ -v

# Apenas integração
python -m pytest tests/integration/ -v
```

Os testes usam mocks robustos (AsyncMock) — não precisam de banco de dados ou serviços Azure.

## Documentação

- **API Docs:** `http://localhost:8000/docs` (Scalar)
- **Diagramas C4:** `docs/architecture/c4-context.md`, `docs/architecture/c4-container.md`
- **Diagramas de Sequência:** `docs/architecture/sequence-*.md`
- **Casos de Uso:** `docs/use-cases/UC01-UC06.md`
- **ADRs:** `docs/adrs/ADR-*.md`
- **Modelo de Dados:** `docs/database/DATA_MODEL.md`

## Pipeline de Ingestion

```
PDF Upload → Extração de Texto (PyMuPDF) → SHA-256 Dedup
    → Upload Blob Storage → Chunking (800/200)
    → Embeddings (text-embedding-3-small) → PostgreSQL + pgvector
```

## Pipeline RAG

```
Pergunta (PT) → Query Rewrite (gpt-4o-mini: PT→EN)
    → Busca Híbrida (70% vector + 30% trigram)
    → Geração de Resposta (gpt-4o com citações [Fonte N])
```
