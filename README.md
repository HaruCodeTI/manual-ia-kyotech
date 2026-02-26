# Kyotech AI

Sistema RAG (Retrieval-Augmented Generation) interno para consulta de manuais e informativos técnicos Fujifilm via chat em português, com citações rastreáveis e visualização direta do PDF na página citada.

**Desenvolvido por [HaruCode](https://harucode.com.br)**

---

## Visão Geral

Técnicos de campo consultam manuais de equipamentos de impressão Fujifilm através de um chat inteligente. O sistema:

- Recebe perguntas em português
- Reescreve a query para inglês (gpt-4o-mini) para melhor match com manuais
- Busca híbrida: vetorial (pgvector) + textual (pg_trgm)
- Gera resposta em português (gpt-4o) com citações `[Fonte N]`
- Cada citação aponta para o PDF original na página exata

---

## Estrutura do Monorepo

```
kyotech-ai/
├── backend/          # FastAPI + Python 3.9
│   ├── app/
│   │   ├── main.py
│   │   ├── api/          # Endpoints (chat, upload)
│   │   ├── core/         # Config, database
│   │   └── services/     # Lógica de negócio (RAG pipeline)
│   ├── .env.example
│   └── requirements.txt
├── frontend/         # Next.js 16 + React 19 + Tailwind + Shadcn/ui
│   ├── src/
│   │   ├── app/          # Pages (chat, upload, stats)
│   │   ├── components/   # UI components
│   │   ├── lib/          # API client, hooks
│   │   └── types/        # TypeScript types
│   └── package.json
└── docs/             # Documentação de arquitetura
```

---

## Pré-requisitos

| Dependência | Versão |
|---|---|
| Python | 3.9+ |
| Node.js | 18+ |
| PostgreSQL | 15+ com extensões `pgvector` e `pg_trgm` |
| Azure OpenAI | Deployments: `gpt-4o`, `gpt-4o-mini`, `embedding-small` |
| Azure Blob Storage | Container para PDFs originais |

---

## Setup

### 1. Variáveis de Ambiente (Backend)

```bash
cd backend
cp .env.example .env
```

Edite o `.env` com suas credenciais:

- `DATABASE_URL` — Connection string do PostgreSQL (asyncpg + SSL)
- `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` — Azure OpenAI
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` — Nome do deployment de embeddings
- `AZURE_OPENAI_CHAT_DEPLOYMENT` — Nome do deployment do gpt-4o
- `AZURE_OPENAI_MINI_DEPLOYMENT` — Nome do deployment do gpt-4o-mini
- `AZURE_STORAGE_CONNECTION_STRING` — Azure Blob Storage
- `AZURE_STORAGE_CONTAINER_ORIGINALS` — Nome do container de PDFs

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

O backend roda em `http://localhost:8000`. Swagger disponível em `http://localhost:8000/docs`.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

O frontend roda em `http://localhost:3000` (ou 3001 se a porta estiver ocupada).

Variável opcional no frontend:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000  # padrão se não definida
```

---

## Endpoints da API

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/chat/ask` | Chat RAG — pergunta + resposta com citações |
| `GET` | `/api/v1/chat/pdf-url` | Gera URL assinada (SAS) para visualizar PDF |
| `POST` | `/api/v1/upload/document` | Upload de PDF com metadados |
| `GET` | `/api/v1/upload/stats` | Estatísticas da base (equipamentos, docs, chunks) |
| `GET` | `/api/v1/upload/equipments` | Lista equipamentos cadastrados |

---

## Funcionalidades

### Chat (tela principal)
- Interface estilo assistente com mensagens em bolhas
- Markdown rendering nas respostas (listas, negrito, headings)
- Citações `[Fonte N]` clicáveis com popover de metadados
- Botão "Ver PDF" abre o documento na página exata via SAS URL
- Filtro por equipamento
- Histórico na sessão (não persiste entre reloads)

### Upload de Documentos
- File picker para PDF com validação client-side
- Campos: equipment key, tipo (manual/informativo), data de publicação
- Feedback visual: uploading → sucesso/erro com resumo (páginas, chunks)

### Dashboard
- Cards com totais: equipamentos, documentos, versões, chunks

### Tema
- Suporte a tema claro, escuro e sistema (toggle no header)
- Acento azul (identidade Fujifilm/tech)

---

## Troubleshooting

### CORS — "OPTIONS 400 Bad Request"

O backend aceita requests de `localhost:3000`, `localhost:3001`, `127.0.0.1:3000`, `127.0.0.1:3001` e `127.0.0.1:5173`. Se o frontend rodar em outra porta, adicione-a em `backend/app/main.py` no array `allow_origins` do `CORSMiddleware`.

### Upload demora muito / timeout

Documentos grandes (>5MB) podem levar alguns minutos para processar (upload para Azure Blob + extração + chunking + embeddings). O frontend tem timeout de 10 minutos para uploads. Se o backend retornar sucesso mas o frontend mostrar erro, verifique os logs do backend — o documento provavelmente foi processado.

### "Não foi possível conectar ao servidor"

1. Verifique se o backend está rodando (`uvicorn app.main:app --port 8000`)
2. Verifique se a porta está correta no `NEXT_PUBLIC_API_URL`
3. Verifique se não há firewall bloqueando `localhost:8000`

### Chat sem resposta / travado

O Azure OpenAI pode demorar até 90 segundos para responder. O client tem timeout de 90s e 2 retries automáticos. Se persistir:

1. Verifique os logs do backend para erros da Azure OpenAI
2. Confirme que os deployments (`gpt-4o`, `gpt-4o-mini`, `embedding-small`) existem no seu recurso Azure OpenAI
3. Verifique quota/rate limits no portal Azure

### PostgreSQL — ConnectionResetError

Conexões podem ficar stale. O backend recicla conexões a cada 5 minutos e usa TCP keepalive. Se o erro persistir:

1. Verifique a conectividade com o PostgreSQL
2. Confirme que o SSL está habilitado na connection string (`?ssl=require`)
3. Reinicie o backend

### Extensões do PostgreSQL

O banco precisa das extensões `pgvector` e `pg_trgm`. Para ativá-las:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

---

## Stack Técnica

### Backend
- **FastAPI** — Framework web async
- **SQLAlchemy** (async) + **asyncpg** — ORM e driver PostgreSQL
- **pgvector** — Busca vetorial por similaridade de cosseno
- **pg_trgm** — Busca textual por trigramas
- **Azure OpenAI** — Embeddings (text-embedding-3-small) e chat (gpt-4o, gpt-4o-mini)
- **Azure Blob Storage** — Armazenamento de PDFs com SAS URLs
- **PyMuPDF** — Extração de texto de PDFs

### Frontend
- **Next.js 16** (App Router) + **React 19** + **TypeScript**
- **Tailwind CSS 4** + **Shadcn/ui** — Estilização e componentes
- **react-markdown** — Rendering de Markdown nas respostas
- **lucide-react** — Ícones

---

## Licença

Projeto proprietário — HaruCode. Todos os direitos reservados.
