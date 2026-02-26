# Kyotech AI — Backend

Sistema RAG para consulta de manuais e informativos Fujifilm.

## Estrutura do Projeto

```
kyotech-backend/
├── app/
│   ├── main.py                 # App FastAPI principal
│   ├── api/
│   │   └── upload.py           # Endpoint de upload de PDFs
│   ├── core/
│   │   ├── config.py           # Configurações (.env)
│   │   └── database.py         # Conexão PostgreSQL async
│   └── services/
│       ├── pdf_extractor.py    # Extração de texto (PyMuPDF)
│       ├── chunker.py          # Divisão em chunks com overlap
│       ├── embedder.py         # Geração de vetores (Azure OpenAI)
│       ├── storage.py          # Upload Blob Storage + URLs assinadas
│       ├── repository.py       # Operações de banco (CRUD)
│       └── ingestion.py        # Orquestrador do pipeline
├── .env.example                # Template de variáveis de ambiente
├── requirements.txt            # Dependências Python
└── README.md
```

## Setup Local

### 1. Pré-requisitos

- Python 3.11+
- PostgreSQL com pgvector (ou acesso ao Azure PostgreSQL)
- Conta Azure com OpenAI e Blob Storage configurados

### 2. Instalar dependências

```bash
cd kyotech-backend
python -m venv .venv
source .venv/bin/activate    # Linux/Mac
# .venv\Scripts\activate     # Windows

pip install -r requirements.txt
```

### 3. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite .env com seus valores reais
```

**Valores necessários:**
- `DATABASE_URL` — String de conexão do PostgreSQL
- `AZURE_OPENAI_ENDPOINT` — Endpoint do Azure OpenAI
- `AZURE_OPENAI_API_KEY` — Chave da API
- `AZURE_STORAGE_CONNECTION_STRING` — Connection string do Blob Storage

### 4. Rodar o servidor

```bash
uvicorn app.main:app --reload --port 8000
```

### 5. Testar o upload

Acesse `http://localhost:8000/docs` para a documentação interativa (Swagger).

Ou via curl:
```bash
curl -X POST http://localhost:8000/api/v1/upload/document \
  -F "file=@manual_frontier_780.pdf" \
  -F "equipment_key=frontier-780" \
  -F "doc_type=manual" \
  -F "published_date=2025-01-15"
```

## Pipeline de Ingestion

```
PDF Upload
    │
    ▼
Extração de Texto (PyMuPDF)
    │  → texto por página
    ▼
Detecção de Duplicatas (SHA-256)
    │  → se hash já existe, pula
    ▼
Upload Blob Storage
    │  → container/equipment/date/filename.pdf
    ▼
Chunking (800 chars, 200 overlap)
    │  → preserva número da página
    ▼
Embeddings (Azure OpenAI)
    │  → text-embedding-3-small (1536 dim)
    ▼
PostgreSQL + pgvector
    │  → chunks com vetores indexados
    ▼
✅ Pronto para busca RAG
```
