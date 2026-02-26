# Claude Code — Kyotech AI Frontend

## Contexto do Projeto

Você está trabalhando no projeto **Kyotech AI**, um sistema RAG (Retrieval-Augmented Generation) interno e privado para a empresa Kyotech. O sistema permite que técnicos de campo consultem manuais e informativos confidenciais da Fujifilm (equipamentos de impressão) via chat em português, com citações rastreáveis e visualização direta do PDF na página citada.

O projeto é da **HaruCode** e está organizado como monorepo em `~/HaruCode/apps/kyotech-ai/`.

---

## Estrutura Atual do Monorepo

```
~/HaruCode/apps/kyotech-ai/
├── backend/                    # ✅ PRONTO — FastAPI + Python 3.9
│   ├── app/
│   │   ├── main.py             # App FastAPI principal
│   │   ├── api/
│   │   │   ├── upload.py       # POST /api/v1/upload/document
│   │   │   └── chat.py         # POST /api/v1/chat/ask
│   │   ├── core/
│   │   │   ├── config.py       # Settings via .env (pydantic-settings)
│   │   │   └── database.py     # SQLAlchemy async + asyncpg
│   │   └── services/
│   │       ├── pdf_extractor.py    # PyMuPDF — extrai texto por página
│   │       ├── chunker.py          # Chunks com overlap preservando página
│   │       ├── embedder.py         # Azure OpenAI text-embedding-3-small
│   │       ├── storage.py          # Azure Blob Storage + URLs assinadas
│   │       ├── repository.py       # CRUD PostgreSQL
│   │       ├── ingestion.py        # Orquestrador do pipeline
│   │       ├── query_rewriter.py   # PT→EN com gpt-4o-mini
│   │       ├── search.py           # Busca híbrida (vetorial + textual)
│   │       └── generator.py        # Resposta com citações via gpt-4o
│   ├── .env                    # Variáveis de ambiente (NÃO commitar)
│   ├── .env.example
│   ├── requirements.txt
│   └── README.md
├── frontend/                   # ⬜ A CRIAR — React/Next.js
├── docs/
│   ├── infra-ia-kyotech.md     # Documento de arquitetura original
│   ├── estado-atual.md         # Estado atual da implementação
│   └── steps.md                # Passos e decisões tomadas
└── ...
```

---

## Backend API — Endpoints Disponíveis

O backend roda em `http://localhost:8000`. Swagger em `http://localhost:8000/docs`.

### 1. Health Check
```
GET /health
Response: { "status": "ok", "service": "kyotech-ai" }
```

### 2. Upload de Documento
```
POST /api/v1/upload/document
Content-Type: multipart/form-data

Campos:
- file: arquivo PDF (obrigatório)
- equipment_key: string (ex: "frontier-780") — obrigatório
- doc_type: "manual" ou "informativo" — obrigatório
- published_date: "YYYY-MM-DD" — obrigatório
- equipment_display_name: string (opcional)

Response (200):
{
  "success": true,
  "message": "Documento 'manual.pdf' ingerido com sucesso.",
  "document_id": "uuid",
  "version_id": "uuid",
  "total_pages": 5,
  "total_chunks": 6,
  "was_duplicate": false
}
```

### 3. Estatísticas da Base
```
GET /api/v1/upload/stats
Response:
{
  "equipments": 1,
  "documents": 1,
  "versions": 1,
  "chunks": 6
}
```

### 4. Chat RAG (endpoint principal)
```
POST /api/v1/chat/ask
Content-Type: application/json

Body:
{
  "question": "Como trocar o rolo de pressão?",
  "equipment_filter": null  // opcional: filtra por equipamento
}

Response (200):
{
  "answer": "Resposta em português com citações [Fonte 1]...",
  "citations": [
    {
      "source_index": 1,
      "source_filename": "manual_frontier.pdf",
      "page_number": 42,
      "equipment_key": "frontier-780",
      "doc_type": "manual",
      "published_date": "2025-01-15",
      "storage_path": "pdfs-originais/frontier-780/2025-01-15/manual_frontier.pdf"
    }
  ],
  "query_original": "Como trocar o rolo de pressão?",
  "query_rewritten": "How to replace pressure roller Frontier 780",
  "total_sources": 3,
  "model_used": "gpt-4o"
}
```

### CORS
O backend já aceita requests de `http://localhost:3000` e `http://localhost:5173`.

---

## O Que o Frontend Deve Ter

### Tela 1: Chat (tela principal)
- Interface de chat estilo assistente (mensagens do técnico à direita, respostas à esquerda)
- Campo de input para perguntar em português
- Botão de enviar (e Enter para enviar)
- Enquanto aguarda resposta, mostrar indicador de loading
- Respostas devem renderizar Markdown (negrito, listas, etc.)
- Citações `[Fonte N]` devem ser clicáveis
- Ao clicar em uma citação, abrir o PDF na página correspondente (ver Viewer abaixo)
- Exibir metadados das fontes abaixo da resposta (arquivo, página, equipamento, data)
- Histórico de mensagens na sessão (não precisa persistir entre reloads no MVP)

### Tela 2: Upload de Documentos
- Formulário para upload de PDF com campos:
  - File picker para PDF
  - Equipment key (input texto)
  - Doc type (select: Manual / Informativo)
  - Published date (date picker)
  - Equipment display name (opcional)
- Feedback visual do progresso (uploading → processando → sucesso/erro)
- Após sucesso, mostrar resumo (páginas, chunks gerados)
- Validação client-side: apenas .pdf, campos obrigatórios

### Tela 3: Dashboard / Estatísticas (simples)
- Chamar GET /api/v1/upload/stats
- Mostrar cards com: total de equipamentos, documentos, versões, chunks
- Pode ser uma sidebar ou seção na tela principal

### Componente: Viewer de PDF
- Quando o técnico clica em uma citação, abrir o PDF
- O `storage_path` da citação é o caminho no Blob Storage
- Por enquanto, usar uma URL direta ou iframe com pdf.js
- No futuro, o backend vai gerar URLs assinadas (SAS)
- O viewer deve abrir na página específica (#page=N)

### Navegação
- Sidebar ou tabs simples: Chat | Upload | Stats
- Header com logo/nome "Kyotech AI"
- Não precisa de autenticação no MVP (Entra ID vem na Fase 2)

---

## Requisitos Técnicos

### Stack
- **React 18+** com TypeScript
- **Next.js 14+** (App Router) OU Vite + React Router — escolha o que for mais simples para MVP
- **Tailwind CSS** para estilização
- **Shadcn/ui** para componentes base (botões, inputs, cards, etc.)
- **react-markdown** para renderizar respostas
- **fetch** ou **axios** para chamadas API

### Organização do Frontend
```
frontend/
├── src/
│   ├── app/ (ou pages/)
│   ├── components/
│   │   ├── chat/
│   │   │   ├── ChatWindow.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   ├── CitationBadge.tsx
│   │   │   └── ChatInput.tsx
│   │   ├── upload/
│   │   │   └── UploadForm.tsx
│   │   ├── dashboard/
│   │   │   └── StatsCards.tsx
│   │   ├── pdf/
│   │   │   └── PdfViewer.tsx
│   │   └── layout/
│   │       ├── Sidebar.tsx
│   │       └── Header.tsx
│   ├── lib/
│   │   └── api.ts           # Funções para chamar o backend
│   └── types/
│       └── index.ts          # Tipos TypeScript
├── package.json
├── tsconfig.json
├── tailwind.config.ts
└── ...
```

### Conexão com Backend
```typescript
// lib/api.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function askQuestion(question: string, equipmentFilter?: string) {
  const res = await fetch(`${API_BASE}/api/v1/chat/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, equipment_filter: equipmentFilter }),
  });
  return res.json();
}

export async function uploadDocument(formData: FormData) {
  const res = await fetch(`${API_BASE}/api/v1/upload/document`, {
    method: "POST",
    body: formData, // multipart/form-data automático
  });
  return res.json();
}

export async function getStats() {
  const res = await fetch(`${API_BASE}/api/v1/upload/stats`);
  return res.json();
}
```

---

## Design e UX

### Tom Visual
- Profissional e limpo, estilo painel administrativo
- Cores neutras com acento em azul (Fujifilm/tech)
- Dark mode não é necessário no MVP, mas prepare os tokens de cor para futuro
- Fontes: Inter ou sistema

### Referências de Layout
- Estilo similar ao ChatGPT / Claude (chat à esquerda/centro, sidebar à esquerda)
- Upload pode ser uma página separada ou modal
- Cards de estatísticas no topo ou sidebar

### Citações — UX Importante
- Na resposta, cada `[Fonte N]` deve virar um badge clicável colorido
- Ao clicar, mostrar tooltip ou painel com metadados (arquivo, página, equipamento)
- Botão "Ver PDF" que abre o viewer na página correta
- Ao final da resposta, listar todas as fontes com links

---

## Restrições

- **Python 3.9** no backend (já tratado — não mexer no backend)
- **Sem autenticação no MVP** — vem na Fase 2
- **Sem persistência de chat** — histórico é apenas na sessão do browser
- **PDFs são confidenciais** — não expor URLs públicas (no MVP, o viewer abre via URL direta do Blob, na Fase 2 usaremos SAS URLs)
- **Comunicação com técnicos em português** — toda a interface em PT-BR

---

## Como Rodar

### Backend (já funcionando)
```bash
cd ~/HaruCode/apps/kyotech-ai/backend
source .venv/bin/activate.fish  # Fish shell
uvicorn app.main:app --reload --port 8000
```

### Frontend (a criar)
```bash
cd ~/HaruCode/apps/kyotech-ai/frontend
npm install
npm run dev  # deve rodar na porta 3000 ou 5173
```

---

## Prioridades de Implementação

1. **Chat funcional** — poder perguntar e ver resposta com citações (mais importante)
2. **Upload funcional** — poder subir PDFs com metadados
3. **Stats dashboard** — mostrar números da base
4. **PDF Viewer** — abrir PDF na página citada
5. **Polish visual** — refinamentos de UI/UX

---

## Notas Adicionais

- O backend usa asyncpg com SQLAlchemy async. Toda a comunicação é via REST JSON.
- Os embeddings são gerados pelo Azure OpenAI (text-embedding-3-small, 1536 dimensões).
- A busca é híbrida: vetorial (cosine similarity via pgvector) + textual (trigram via pg_trgm).
- O query rewriter traduz perguntas PT→EN usando gpt-4o-mini para melhor match contra manuais em inglês.
- A resposta final é gerada pelo gpt-4o com citações obrigatórias no formato [Fonte N].
- Cada citação tem storage_path, page_number e source_filename para rastreabilidade completa.

Comece pelo chat — é o core da experiência do técnico.