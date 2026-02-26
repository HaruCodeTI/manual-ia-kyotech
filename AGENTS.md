# AGENTS.md

## Cursor Cloud specific instructions

### Architecture

Monorepo with two services (see `README.md` for full details):

| Service | Dir | Stack | Port |
|---|---|---|---|
| Backend | `backend/` | FastAPI + SQLAlchemy (async) + asyncpg | 8000 |
| Frontend | `frontend/` | Next.js 16 + React 19 + Tailwind 4 | 3000 |

External dependencies: PostgreSQL 16 (pgvector + pg_trgm), Azure OpenAI, Azure Blob Storage.

### Local PostgreSQL (Cloud Agent)

PostgreSQL 16 with `pgvector` and `pg_trgm` extensions is installed locally. Start it with:

```bash
sudo pg_ctlcluster 16 main start
```

Database: `kyotech_db`, user: `postgres`, password: `postgres`, host: `127.0.0.1:5432`. Schema is pre-created.

### Critical: DATABASE_URL override

Cloud agent secrets inject a `DATABASE_URL` env var pointing to the production Azure PostgreSQL (private endpoint, not accessible from this VM). You **must** override it when running the backend locally:

```bash
cd /workspace/backend && source .venv/bin/activate
DATABASE_URL='postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/kyotech_db' uvicorn app.main:app --reload --port 8000
```

Without this override, all DB-connected endpoints will fail with `ConnectionResetError` during SSL negotiation.

### Running services

- **Backend**: `cd /workspace/backend && source .venv/bin/activate && DATABASE_URL='postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/kyotech_db' uvicorn app.main:app --reload --port 8000`
- **Frontend**: `cd /workspace/frontend && npm run dev`
- **Swagger UI**: http://localhost:8000/docs

### Lint / Build / Test

- **Frontend lint**: `cd /workspace/frontend && npx eslint .` (2 pre-existing warnings about `set-state-in-effect` — not introduced by agents)
- **Frontend build**: `cd /workspace/frontend && npm run build`
- **Backend**: No automated test suite exists in the codebase. Test via Swagger UI or curl.

### Azure services

The RAG pipeline (chat, upload) requires Azure OpenAI and Azure Blob Storage credentials. These are injected as env vars by the cloud agent. Chat and upload functionality will only work if the Azure endpoints are reachable from this VM. The `/health`, `/api/v1/upload/stats`, and `/api/v1/upload/equipments` endpoints work without Azure credentials.
