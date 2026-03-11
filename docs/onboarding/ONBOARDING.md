# Kyotech AI — Onboarding Dev

Bem-vindo ao projeto **Kyotech AI**, um sistema RAG (Retrieval-Augmented Generation) para consulta de manuais e informativos técnicos Fujifilm.

---

## 1. Visão Geral do Projeto

O Kyotech AI permite que técnicos e gerentes da Fujifilm façam perguntas em linguagem natural sobre manuais de equipamentos. O sistema busca nos documentos indexados e gera respostas com citações das fontes.

### Stack

| Camada | Tecnologia |
|--------|-----------|
| Backend | Python 3.9 · FastAPI · SQLAlchemy async · pgvector |
| Frontend | Next.js 16 · React 19 · TypeScript · Tailwind CSS 4 · shadcn/ui |
| Autenticação | Clerk (JWT/JWKS) |
| IA | Azure OpenAI (gpt-4o, gpt-4o-mini, text-embedding-3-small) |
| Storage | Azure Blob Storage |
| Banco | PostgreSQL 17 com pgvector + pg_trgm |
| CI/CD | GitHub Actions → Azure Container Apps |

### Arquitetura Simplificada

```
Usuário → Frontend (Next.js) → Backend (FastAPI) → Azure OpenAI
                                      ↓
                              PostgreSQL (pgvector)
                                      ↓
                              Azure Blob Storage
```

---

## 2. Leitura Obrigatória (antes de codar)

Leia estes documentos nesta ordem:

1. **`backend/README.md`** — Estrutura do backend, como rodar, como testar
2. **`docs/architecture/c4-context.md`** — Diagrama C4 de contexto (visão macro)
3. **`docs/architecture/c4-container.md`** — Diagrama C4 de containers (componentes)
4. **`docs/adrs/ADR-002-clerk-auth.md`** — Como funciona a autenticação
5. **`docs/use-cases/UC01-UC06.md`** — Casos de uso do sistema
6. **`docs/database/DATA_MODEL.md`** — Modelo de dados

---

## 3. Setup Local

### Pré-requisitos

- Python 3.9+
- Node.js 20+
- Git

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt -r requirements-dev.txt

# Configurar variáveis de ambiente
cp .env.example .env
# Peça ao Arthur os valores reais do .env

# Rodar
uvicorn app.main:app --reload --port 8000
```

- API Docs (Scalar): http://localhost:8000/docs
- Health check: http://localhost:8000/health

### Frontend

```bash
cd frontend
npm install

# Configurar variáveis de ambiente
# Peça ao Arthur o .env.local com as chaves do Clerk

# Rodar
npm run dev
```

- App: http://localhost:3000

### Rodar Testes (Backend)

```bash
cd backend
python3 -m pytest -v                                    # Todos os testes
python3 -m pytest tests/unit/ -v                        # Unitários
python3 -m pytest tests/integration/ -v                 # Integração
python3 -m pytest --cov=app --cov-report=term-missing   # Com cobertura
```

Os testes usam mocks — **não precisam de banco ou serviços Azure**.

---

## 4. Estrutura do Projeto

```
kyotech-ai/
├── backend/
│   ├── app/
│   │   ├── main.py              # App FastAPI
│   │   ├── api/                 # Endpoints (chat, upload, sessions, viewer)
│   │   ├── core/                # Auth (Clerk), config, database
│   │   └── services/            # Lógica de negócio (RAG, storage, etc.)
│   └── tests/
│       ├── conftest.py          # Fixtures compartilhadas
│       ├── unit/                # 11 módulos de teste
│       └── integration/         # 5 módulos de teste
├── frontend/
│   └── src/
│       ├── app/                 # Rotas Next.js (pages)
│       ├── components/          # Componentes React
│       │   ├── ui/              # Primitivos shadcn/ui
│       │   ├── chat/            # Chat (mensagens, input, citações)
│       │   ├── viewer/          # Visualizador seguro de PDF
│       │   ├── upload/          # Upload de documentos
│       │   ├── dashboard/       # Cards de estatísticas
│       │   └── layout/          # Header, Sidebar, AppShell
│       ├── lib/                 # API client, hooks, utils
│       └── types/               # TypeScript types
├── docs/                        # Documentação completa
└── .github/workflows/           # CI/CD
```

---

## 5. Padrões do Projeto

### Backend

- **Async everywhere**: Todos os endpoints e serviços são `async`
- **Dependency injection**: FastAPI `Depends()` para auth e DB
- **Testes com mocks**: `AsyncMock` para banco, OpenAI e Blob Storage
- **Sem acesso direto ao banco nos testes**: Sempre via mock

### Frontend

- **App Router** (Next.js): Rotas em `src/app/`
- **shadcn/ui**: Componentes em `src/components/ui/` — use esses primitivos
- **Tailwind CSS 4**: Estilização via classes utilitárias
- **Context API**: `ChatContext` e `ViewerContext` para estado global

### Git

- Commits em inglês com prefixo: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`
- Branch `main` é protegida — CI roda testes antes do deploy
- Sempre rodar `pytest` antes de commitar mudanças no backend

---

## 6. Suas Tarefas

As tarefas abaixo estão no Jira (projeto IA) e são delimitadas para execução independente. Siga a ordem sugerida.

### Tarefa 1: Familiarização (Dia 1)

- [ ] Ler a documentação listada na seção 2
- [ ] Clonar o repo e rodar backend + frontend localmente
- [ ] Acessar Scalar docs (`/docs`) e testar o endpoint `/health`
- [ ] Rodar a suite de testes do backend (103 testes, todos passando)
- [ ] Navegar pelo frontend: login, chat, upload, stats

### Tarefa 2: Melhorias de UI/UX — IA-78 (subtasks)

Tarefas isoladas de frontend, baixo risco:

- [ ] **Loading states**: Adicionar skeleton loading no `ChatWindow` enquanto aguarda resposta da IA
- [ ] **Empty states**: Mensagem amigável quando não há sessões de chat ou documentos
- [ ] **Responsividade**: Testar e ajustar layout mobile (sidebar colapsável já existe)
- [ ] **Acessibilidade**: Adicionar `aria-labels` nos botões de ação, garantir contraste adequado

**Referência**: Componentes em `frontend/src/components/`, primitivos em `frontend/src/components/ui/`

### Tarefa 3: Dashboard de Métricas — IA-77

Criar página de métricas de uso do sistema:

**Backend:**
- Novo endpoint `GET /api/v1/metrics` retornando:
  - Total de perguntas feitas (count de mensagens com role=user)
  - Perguntas por dia (últimos 30 dias)
  - Top 5 equipamentos mais consultados
  - Tempo médio de resposta (se disponível)
- Seguir padrão dos endpoints existentes em `backend/app/api/`
- Usar `chat_repository.py` como referência para queries

**Frontend:**
- Nova página `/metrics` seguindo padrão de `/stats`
- Cards com totais + gráfico simples de uso diário
- Usar shadcn/ui para componentes, Tailwind para layout

**Teste:**
- Unitário: mock do banco, testar retorno do endpoint
- Integração: testar via `async_client` (seguir `tests/integration/test_sessions_api.py`)

### Tarefa 4: Testes de Qualidade RAG — IA-75 (parte de implementação)

> O Arthur vai definir a estratégia e o dataset. Você implementa os testes.

- [ ] Criar `tests/quality/` com testes parametrizados
- [ ] Cada caso de teste: pergunta → resposta esperada (parcial match)
- [ ] Validar que citações `[Fonte N]` estão presentes nas respostas
- [ ] Validar que respostas a prompt injection são recusadas

**Aguarde orientação do Arthur antes de iniciar esta tarefa.**

---

## 7. Como Pedir Ajuda

- **Dúvidas de código**: Olhe os testes existentes — eles documentam o comportamento esperado
- **Dúvidas de arquitetura**: Consulte os ADRs em `docs/adrs/`
- **Dúvidas de negócio**: Pergunte ao Arthur
- **Stuck em algo por mais de 30min**: Pergunte. Não fique travado.

---

## 8. Checklist Antes de Abrir PR

- [ ] Testes passando (`python3 -m pytest -v`)
- [ ] Sem secrets no código (use `.env`)
- [ ] Código segue os padrões do projeto (async, typing, mocks)
- [ ] Commit message com prefixo correto (`feat:`, `fix:`, etc.)
- [ ] Descrição clara no PR do que mudou e por quê
