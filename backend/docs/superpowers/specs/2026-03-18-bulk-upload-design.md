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
- `doc_type: str = Form(...)` → `Optional[str] = Form(None)` — validar apenas se fornecido (`manual` | `informativo`)
- `published_date: date = Form(...)` → `Optional[date] = Form(None)`
- Limite de tamanho: lido de `settings.max_upload_size_mb` (valor: 200)

**Regras de validação mantidas:**
- Arquivo deve ter extensão `.pdf`
- Arquivo não pode ser vazio (`len(file_bytes) == 0`)
- Tamanho máximo: `settings.max_upload_size_mb * 1024 * 1024` bytes
- Role `Admin` obrigatória

**Validação de `equipment_key`:** o service layer aceita qualquer string — a regex `^[a-z0-9][a-z0-9-]*$` é aplicada apenas no frontend como guarda de UX. O backend não valida o formato (comportamento atual preservado).

**Sem mudança no service layer** — `ingest_document` já aceita todos os campos como `Optional` desde IA-93.

### 2. Batch insert de chunks

**Arquivo:** `backend/app/services/repository.py` — função `insert_chunks_with_embeddings`

**Problema atual:** loop com `execute()` individual por chunk = N round trips ao banco.

**Solução:** substituir o loop por um único `INSERT` multi-row construído em Python, usando o mesmo formato de string de embedding já existente no código (`"[v1, v2, ...]"`). Evita arrays de tipo `vector[]` e compatibilidade com asyncpg:

```python
# Construir VALUES dinâmico com parâmetros nomeados por índice
params = {"version_id": str(version_id)}
value_rows = []
for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
    value_rows.append(
        f"(:version_id, :{i}_page, :{i}_idx, :{i}_content, :{i}_emb::vector)"
    )
    params[f"{i}_page"] = chunk.page_number
    params[f"{i}_idx"] = chunk.chunk_index
    params[f"{i}_content"] = chunk.content
    params[f"{i}_emb"] = embedding_str

sql = f"""
    INSERT INTO chunks
        (document_version_id, page_number, chunk_index, content, embedding)
    VALUES {', '.join(value_rows)}
    ON CONFLICT (document_version_id, page_number, chunk_index) DO UPDATE
    SET content = EXCLUDED.content, embedding = EXCLUDED.embedding
"""
await db.execute(text(sql), params)
```

Resultado: **1 execute()** em vez de N, sem usar `vector[]` nem `unnest` (compatível com asyncpg + pg_vector existente).

**Ordem e transação:** os embeddings são gerados ANTES do insert (comportamento atual). A função recebe `chunks: List[TextChunk]` e `embeddings: List[List[float]]` já pareados por índice (`zip(chunks, embeddings)`). O DELETE existente + o INSERT em lote ficam dentro da mesma sessão de banco (sem commit explícito intermediário) — o commit ocorre no caller (`ingestion.py`). Sem risco de mismatch.

**Embeddings já em batch:** `generate_embeddings` em `embedder.py` já processa em lotes de 50. Sem mudança necessária.

### 3. Settings — limite de tamanho

**Arquivo:** `backend/app/core/config.py`

Adicionar: `max_upload_size_mb: int = 200`

Usar em `upload.py` substituindo o valor hardcoded `100 * 1024 * 1024`.

### 4. Formato de erro

O backend já retorna `{"detail": "mensagem"}` em erros HTTP. A função `parseApiError` em `frontend/src/lib/api.ts` já trata este formato e mapeia status codes para mensagens em PT-BR. Nenhuma mudança no contrato de erro.

### 5. Detecção de duplicata

A detecção ocorre no service layer por `source_hash` (SHA-256 do conteúdo do PDF). Não é escopo desta entrega mudar a lógica de duplicata. O campo `was_duplicate: bool` já existe no `IngestionResult` e é retornado ao frontend. Comportamento: arquivo duplicado → status `concluído` no frontend com nota "(duplicata)".

### 6. Testes backend

**Arquivos:**
- `tests/integration/test_upload_api.py` — novos casos para campos opcionais
- `tests/unit/test_repository.py` — verificar batch insert

Novos casos de teste:
- Upload sem `equipment_key`, sem `doc_type`, sem `published_date` → 200 com sucesso (mock de `ingest_document`)
- Upload com `doc_type` inválido quando fornecido (`"invalido"`) → 400
- Upload com arquivo de 0 bytes → 400
- Upload com arquivo > 200MB → 400
- `insert_chunks_with_embeddings` com 300 chunks → verifica que `execute` é chamado **1 vez** (não 300)

---

## Frontend (IA-95)

### Componentes

#### Novo: `BulkUploadForm.tsx`

**Arquivo:** `frontend/src/components/upload/BulkUploadForm.tsx`

Substitui `UploadForm.tsx` na página de upload. Componente principal com:
- Dropzone de seleção múltipla (1–10 arquivos PDF, drag-and-drop + clique)
- Campos de metadata opcionais (aplicados a todos os arquivos do lote)
- Lista de progresso por arquivo (renderiza `FileProgressItem`)
- Lógica de concorrência (máx 3 simultâneos, controlada no frontend)
- Bloqueio de novos uploads enquanto `isUploading === true`

**Estado por arquivo:**
```typescript
type FileStatus = 'pendente' | 'enviando' | 'processando' | 'concluído' | 'erro';

interface FileUploadState {
  id: string;           // crypto.randomUUID() gerado no frontend — chave de UI apenas, não enviado ao backend
  file: File;
  status: FileStatus;
  progress: number;     // 0–100, usado apenas no estado 'enviando'
  result?: UploadResponse;
  error?: string;
}
```

**Fluxo:**
1. Usuário seleciona arquivos → validação client-side imediata → exibe lista com status `pendente`
2. Clica "Enviar" → `isUploading = true`, interface bloqueada para novos uploads
3. Até 3 arquivos passam para `enviando`; restantes ficam `pendente`
4. Ao concluir um arquivo (sucesso ou erro), próximo `pendente` inicia automaticamente
5. Ao final de todos: exibe resumo `X de Y concluídos com sucesso`
6. Botão "Novo upload" reseta todo o estado (`isUploading = false`, lista vazia)

**Validações client-side (antes de enviar):**
- Máx 10 arquivos por sessão (excedente é ignorado com alerta)
- Apenas arquivos com extensão `.pdf`
- Tamanho máximo por arquivo: `200MB` (`200 * 1024 * 1024` bytes)
- `doc_type` se fornecido: apenas `manual` ou `informativo` (select restrito)
- `equipment_key` se fornecido: regex `^[a-z0-9][a-z0-9-]*$`

**Concorrência:** controlada inteiramente no frontend via contagem de arquivos com status `enviando` ou `processando`. Sem coordenação cross-tab — múltiplas abas são tratadas como sessões independentes pelo backend (cada request é autônoma).

#### Novo: `FileProgressItem.tsx`

**Arquivo:** `frontend/src/components/upload/FileProgressItem.tsx`

Componente de linha da lista de progresso. Recebe `FileUploadState` e renderiza:
- Nome do arquivo (truncado se > 40 chars com `...` no meio)
- Badge de status em PT-BR
- Barra de progresso (`<progress>` ou div com width %) — visível apenas em `enviando`
- Resultado em `concluído`: `"N chunks · M páginas"` + `"(duplicata)"` se `was_duplicate`
- Mensagem de erro em `erro`

**Labels de status (PT-BR):**
```
pendente     → badge cinza
enviando     → badge azul  + barra de progresso %
processando  → badge amarelo + spinner (upload concluiu, aguardando resposta)
concluído    → badge verde
erro         → badge vermelho
```

**Estado `processando`:** ocorre após `xhr.upload.onload` (bytes enviados) e antes de `xhr.onload` (resposta recebida). Para documentos grandes, este estado pode durar minutos (chunking + embeddings + insert). O spinner informa que o servidor está trabalhando — não há timeout específico além do timeout total da request (600s).

### API client

**Arquivo:** `frontend/src/lib/api.ts`

Adicionar função `uploadDocumentWithProgress` usando `XMLHttpRequest` (não `fetch`) para acesso a `xhr.upload.onprogress`:

```typescript
export function uploadDocumentWithProgress(
  formData: FormData,
  onProgress: (percent: number) => void,
  onProcessing: () => void,   // chamado quando upload termina, antes da resposta
  signal?: AbortSignal        // reservado para uso futuro (cancelamento)
): Promise<UploadResponse>
```

**Implementação:**
```typescript
// Fases mapeadas:
xhr.upload.addEventListener('progress', (e) => {
  if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 99));
});
xhr.upload.addEventListener('load', () => {
  onProgress(100);
  onProcessing(); // → status 'processando' no componente
});
xhr.addEventListener('load', () => {
  if (xhr.status >= 200 && xhr.status < 300) {
    resolve(JSON.parse(xhr.responseText));
  } else {
    // Reutilizar parseApiError: criar Response sintético a partir do XHR
    const fakeResponse = new Response(xhr.responseText, { status: xhr.status });
    parseApiError(fakeResponse).then((msg) => reject(new Error(msg)));
  }
});
xhr.addEventListener('error', () => reject(new Error('Erro de conexão.')));
xhr.addEventListener('timeout', () => reject(new Error('Tempo limite excedido.')));
xhr.timeout = 600_000;
```

**Nota:** o parâmetro `signal` é recebido mas apenas prepara o XHR para cancelamento futuro (sem lógica de cancelamento implementada nesta entrega). Isso evita refatoração posterior da assinatura.

### Página

**Arquivo:** `frontend/src/app/upload/page.tsx`

Trocar `<UploadForm />` por `<BulkUploadForm />`.

**`UploadForm.tsx` deve ser removido** — verificar que não há outros imports antes da remoção:
```bash
grep -r "UploadForm" frontend/src --include="*.tsx" --include="*.ts"
```

### Types

**Arquivo:** `frontend/src/types/index.ts`

Verificar se `UploadResponse` já contempla todos os campos necessários (`success`, `message`, `document_id`, `version_id`, `total_pages`, `total_chunks`, `was_duplicate`). Sem mudança esperada.

---

## Concorrência e Casos de Borda

| Cenário | Comportamento |
|---|---|
| 1 arquivo | Upload direto, sem fila |
| 2–3 arquivos | Todos em paralelo imediatamente |
| 4–10 arquivos | 3 iniciam, restantes ficam `pendente` |
| Erro em 1 arquivo | Status `erro` neste arquivo; demais continuam normalmente |
| Arquivo duplicado | `was_duplicate: true` → status `concluído` com nota "(duplicata)" |
| Arquivo vazio | Rejeitado na validação client-side antes de enviar |
| Arquivo > 200MB | Rejeitado na validação client-side antes de enviar |
| Arquivo não-PDF | Rejeitado na validação client-side antes de enviar |
| Timeout (> 600s) | Status `erro` com mensagem de timeout |

---

## Regras de Negócio Consolidadas

| Regra | Backend | Frontend |
|---|---|---|
| Apenas PDFs | ✅ extensão `.pdf` | ✅ `accept=".pdf"` + validação |
| Máx 200MB por arquivo | ✅ `settings.max_upload_size_mb` | ✅ `file.size` check |
| Máx 10 arquivos por lote | ❌ não se aplica (1 req por vez) | ✅ limitação no dropzone |
| Campos opcionais | ✅ `Form(None)` | ✅ labels "(opcional)", sem required |
| doc_type quando fornecido | ✅ valida `manual`/`informativo` | ✅ select restrito |
| equipment_key quando fornecido | ❌ sem validação de formato | ✅ regex `^[a-z0-9][a-z0-9-]*$` |
| Role Admin | ✅ `require_role("Admin")` | ✅ acesso à página |
| Bloqueio durante upload | ❌ não se aplica | ✅ `isUploading` state |
| Estados em PT-BR | ❌ não se aplica | ✅ labels explícitos |

---

## Estrutura de Arquivos

```
backend/
  app/
    api/
      upload.py                     ← modificar (campos opcionais, max_upload_size_mb)
    core/
      config.py                     ← adicionar max_upload_size_mb: int = 200
    services/
      repository.py                 ← otimizar insert_chunks_with_embeddings (batch SQL)
  tests/
    integration/
      test_upload_api.py            ← novos casos para campos opcionais
    unit/
      test_repository.py            ← verificar batch insert (execute chamado 1x)

frontend/
  src/
    components/
      upload/
        BulkUploadForm.tsx          ← novo (componente principal)
        FileProgressItem.tsx        ← novo (linha da lista de progresso)
        UploadForm.tsx              ← remover (verificar imports antes)
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
- Cancelamento de uploads individuais após iniciar (signal reservado para uso futuro)
- Retry automático em caso de erro
- Preview de PDF antes do upload
- Upload para usuários não-Admin
- Coordenação de concorrência cross-tab
- Validação de formato de `equipment_key` no backend
