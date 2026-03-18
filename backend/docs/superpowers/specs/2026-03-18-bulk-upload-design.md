# Bulk Upload — Design (IA-94 + IA-95)

> **For agentic workers:** implementar com superpowers:writing-plans ou superpowers:executing-plans.

**Goal:** Permitir o upload de até 10 PDFs simultâneos com acompanhamento de progresso individual por arquivo, tornando todos os campos de metadata opcionais em backend e frontend.

**Tickets Jira:** IA-94 (backend) + IA-95 (frontend)

---

## Contexto

IA-93 tornou `equipment_key`, `doc_type` e `published_date` opcionais no service layer (`ingest_document`). O endpoint `POST /upload/document` e o formulário frontend ainda os exigem como obrigatórios. Esta entrega alinha o endpoint e o frontend com o service layer e adiciona o fluxo de bulk upload.

---

## Arquitetura

### Abordagem: Requests paralelas (frontend-driven)

O frontend dispara uma request por arquivo em paralelo (máx 3 simultâneas). Cada arquivo tem seu próprio ciclo de progresso via `XMLHttpRequest.upload.onprogress`. O backend não precisa de um endpoint batch — o mesmo `/upload/document` atende uploads individuais e em lote.

**Justificativa:** SSE seria infraestrutura nova sem ganho real. Batch único não permite progresso por arquivo. Requests paralelas entregam o UX desejado com a stack existente.

---

## Backend (IA-94)

### 1. `POST /api/v1/upload/document` — campos opcionais

**Arquivo:** `backend/app/api/upload.py`

Mudanças:
- `equipment_key: str = Form(...)` → `Optional[str] = Form(None)`
- `doc_type: str = Form(...)` → `Optional[str] = Form(None)` — validar apenas se fornecido
- `published_date: date = Form(...)` → `Optional[date] = Form(None)`
- Limite de tamanho: `100MB` → `200MB` (alinhado com manuais técnicos Fujifilm)
- Remover validação obrigatória de `doc_type` quando `None`; manter quando fornecido (`manual` | `informativo`)

**Regras de validação mantidas:**
- Arquivo deve ter extensão `.pdf`
- Arquivo não pode ser vazio
- Tamanho máximo: 200MB
- Role `Admin` obrigatória

**Sem mudança no service layer** — `ingest_document` já aceita todos os campos como `Optional` desde IA-93.

### 2. Batch insert de chunks

**Arquivo:** `backend/app/services/repository.py` — função `insert_chunks_with_embeddings`

Problema atual: loop com `execute()` individual por chunk = N round trips ao banco. Para um PDF grande (400+ chunks) isso é lento e segura conexões.

Solução: substituir o loop por `executemany` / insert em lote usando `VALUES` multi-row. Usar um único `DELETE` + um `INSERT` com N linhas via `unnest` ou batch de N rows.

**Embeddings já em batch:** `generate_embeddings` em `embedder.py` já processa em lotes de 50. Sem mudança necessária.

### 3. Settings — limite de tamanho

**Arquivo:** `backend/app/core/config.py`

Adicionar: `max_upload_size_mb: int = 200`

Usar em `upload.py` para evitar hardcode.

### 4. Testes backend

**Arquivos:**
- `tests/integration/test_upload_api.py` — novos casos para campos opcionais
- `tests/unit/test_repository.py` — verificar batch insert

Novos casos de teste:
- Upload sem `equipment_key`, `doc_type`, `published_date` → sucesso
- Upload com `doc_type` inválido quando fornecido → 400
- Upload com arquivo de 0 bytes → 400
- Upload com arquivo > 200MB → 400

---

## Frontend (IA-95)

### Componentes

#### Novo: `BulkUploadForm.tsx`

**Arquivo:** `frontend/src/components/upload/BulkUploadForm.tsx`

Substitui `UploadForm.tsx` na página de upload. Componente principal com:
- Dropzone de seleção múltipla (1–10 arquivos PDF, drag-and-drop + clique)
- Campos de metadata opcionais (aplicados a todos os arquivos do lote)
- Lista de progresso por arquivo
- Lógica de concorrência (máx 3 simultâneos)
- Bloqueio de novos uploads durante processamento

**Estado por arquivo:**
```typescript
type FileStatus = 'pendente' | 'enviando' | 'processando' | 'concluído' | 'erro';

interface FileUploadState {
  id: string;           // uuid gerado no frontend
  file: File;
  status: FileStatus;
  progress: number;     // 0-100, relevante em 'enviando'
  result?: UploadResponse;
  error?: string;
}
```

**Fluxo:**
1. Usuário seleciona arquivos → validação client-side imediata
2. Clica "Enviar" → interface bloqueada para novos uploads
3. Até 3 arquivos passam para `enviando`, restantes ficam `pendente`
4. Ao concluir um, próximo `pendente` inicia
5. Ao final de todos: resumo `X de Y concluídos`
6. Botão "Novo upload" reseta o estado

**Validações client-side:**
- Máx 10 arquivos por sessão
- Apenas arquivos `.pdf`
- Tamanho máximo por arquivo: 200MB
- `doc_type` se fornecido: apenas `manual` ou `informativo`
- `equipment_key` se fornecido: regex `^[a-z0-9][a-z0-9-]*$`

#### Novo: `FileProgressItem.tsx`

**Arquivo:** `frontend/src/components/upload/FileProgressItem.tsx`

Componente de linha da lista de progresso. Exibe:
- Nome do arquivo (truncado se longo)
- Badge de status em PT-BR
- Barra de progresso (visível em `enviando`)
- Resultado (chunks, páginas) em `concluído`
- Mensagem de erro em `erro`

**Labels de status (PT-BR):**
```
pendente     → badge cinza
enviando     → badge azul + barra de progresso %
processando  → badge amarelo + spinner
concluído    → badge verde + "N chunks · M páginas"
erro         → badge vermelho + mensagem do erro
```

### API client

**Arquivo:** `frontend/src/lib/api.ts`

Adicionar função `uploadDocumentWithProgress`:
```typescript
export function uploadDocumentWithProgress(
  formData: FormData,
  onProgress: (percent: number) => void,
  signal: AbortSignal
): Promise<UploadResponse>
```

Usar `XMLHttpRequest` (não `fetch`) para ter acesso a `xhr.upload.onprogress`. O `signal` do AbortController permite cancelamento futuro.

Fases de progresso mapeadas para status:
- `xhr.upload.onprogress` ativo → status `enviando`, progress 0–99%
- Upload completo (`xhr.upload.onload`) → status `processando`, progress 100%
- `xhr.onload` com resposta → status `concluído` ou `erro`

### Página

**Arquivo:** `frontend/src/app/upload/page.tsx`

Trocar `<UploadForm />` por `<BulkUploadForm />`. `UploadForm.tsx` pode ser removido ou mantido (não utilizado).

### Types

**Arquivo:** `frontend/src/types/index.ts`

Verificar se `UploadResponse` já contempla todos os campos necessários. Sem mudança esperada.

---

## Concorrência e Performance

| Cenário | Comportamento |
|---|---|
| 1 arquivo | Upload direto, sem fila |
| 2–3 arquivos | Todos em paralelo imediatamente |
| 4–10 arquivos | 3 iniciam, restantes ficam `pendente` |
| Erro em 1 arquivo | Demais continuam normalmente |
| Arquivo duplicado | `was_duplicate: true` → status `concluído` com nota |

**Timeout por arquivo:** 600s (mesmo que upload atual — manuais grandes podem ter muitos chunks).

---

## Regras de Negócio Consolidadas

| Regra | Backend | Frontend |
|---|---|---|
| Apenas PDFs | ✅ extensão + content | ✅ input accept + validação |
| Máx 200MB por arquivo | ✅ `settings.max_upload_size_mb` | ✅ `file.size` check |
| Máx 10 arquivos por lote | ❌ não se aplica (1 req por vez) | ✅ limitação no dropzone |
| Campos opcionais | ✅ `Form(None)` | ✅ labels "(opcional)" |
| doc_type quando fornecido | ✅ valida `manual`/`informativo` | ✅ select restrito |
| equipment_key quando fornecido | ✅ service layer | ✅ regex validation |
| Role Admin | ✅ `require_role("Admin")` | ✅ acesso à página |
| Bloqueio durante upload | ❌ não se aplica | ✅ estado `isUploading` |
| Estados em PT-BR | ❌ não se aplica | ✅ labels explícitos |

---

## Estrutura de Arquivos

```
backend/
  app/
    api/
      upload.py                     ← modificar (campos opcionais, 200MB)
    core/
      config.py                     ← adicionar max_upload_size_mb
    services/
      repository.py                 ← otimizar insert_chunks_with_embeddings
  tests/
    integration/
      test_upload_api.py            ← novos casos campos opcionais

frontend/
  src/
    components/
      upload/
        BulkUploadForm.tsx          ← novo (componente principal)
        FileProgressItem.tsx        ← novo (linha da lista de progresso)
        UploadForm.tsx              ← remover (substituído)
    app/
      upload/
        page.tsx                    ← trocar UploadForm → BulkUploadForm
    lib/
      api.ts                        ← adicionar uploadDocumentWithProgress (XHR)
```

---

## O que NÃO está no escopo

- Endpoint `/upload/batch` separado (desnecessário com abordagem de requests paralelas)
- SSE ou WebSocket para progresso server-side
- Cancelamento de uploads individuais após iniciar
- Retry automático em caso de erro
- Preview de PDF antes do upload
- Upload para usuários não-Admin
