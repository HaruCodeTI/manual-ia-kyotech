# Bulk Upload — Implementation Plan (IA-94 + IA-95)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar campos de metadata opcionais no endpoint de upload, adicionar batch insert eficiente de chunks, e substituir o formulário de upload por uma versão com suporte a múltiplos arquivos, fila de concorrência (máx 3) e progresso individual por arquivo em PT-BR.

**Architecture:** Backend: o endpoint `POST /upload/document` recebe campos opcionais alinhados com IA-93; `insert_chunks_with_embeddings` usa um único INSERT multi-row. Frontend: `BulkUploadForm` envia uma request por arquivo com `XMLHttpRequest` para acompanhar progresso de bytes; `FileProgressItem` renderiza o estado de cada arquivo.

**Tech Stack:** FastAPI, SQLAlchemy async, asyncpg, pg_vector, Next.js 16, React 19, TypeScript, Tailwind CSS, shadcn/ui, Lucide React

**Spec:** `docs/superpowers/specs/2026-03-18-bulk-upload-design.md`

---

## Estrutura de Arquivos

```
backend/
  app/
    core/
      config.py                     ← ADD: max_upload_size_mb: int = 200
    api/
      upload.py                     ← MODIFY: campos opcionais, usar settings.max_upload_size_mb
    services/
      repository.py                 ← MODIFY: insert_chunks_with_embeddings → batch INSERT
  tests/
    integration/
      test_upload_api.py            ← ADD: 4 novos casos (campos opcionais, validações)
    unit/
      test_repository.py            ← MODIFY: test_insert_chunks_inserts_all (call count 4→2)

frontend/
  src/
    types/
      index.ts                      ← MODIFY: UploadResponse.document_id/version_id → optional
    lib/
      api.ts                        ← ADD: uploadDocumentWithProgress (XHR)
    components/
      upload/
        FileProgressItem.tsx        ← CREATE: linha de progresso por arquivo
        BulkUploadForm.tsx          ← CREATE: formulário principal com fila
        UploadForm.tsx              ← DELETE: substituído por BulkUploadForm
    app/
      upload/
        page.tsx                    ← MODIFY: trocar UploadForm → BulkUploadForm
```

---

## Task 1: Backend — Adicionar `max_upload_size_mb` ao Settings

**Files:**
- Modify: `backend/app/core/config.py`
- Test: verificação manual via `python -c "from app.core.config import settings; print(settings.max_upload_size_mb)"`

- [ ] **Step 1: Adicionar campo ao Settings**

Abrir `backend/app/core/config.py` e adicionar `max_upload_size_mb` logo após `chunk_overlap`:

```python
chunk_size: int = 800
chunk_overlap: int = 200
max_upload_size_mb: int = 200
```

- [ ] **Step 2: Verificar que o settings carrega**

```bash
cd backend
python -c "from app.core.config import settings; print(settings.max_upload_size_mb)"
```

Expected: `200`

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/config.py
git commit -m "feat(config): adicionar max_upload_size_mb (200MB)"
```

---

## Task 2: Backend — Campos Opcionais no Endpoint de Upload

**Files:**
- Modify: `backend/app/api/upload.py`
- Test: `backend/tests/integration/test_upload_api.py`

### Passo TDD

- [ ] **Step 1: Escrever os testes que devem passar**

Abrir `backend/tests/integration/test_upload_api.py` e adicionar ao final:

```python
@pytest.mark.anyio
async def test_upload_without_metadata_succeeds(async_client, sample_pdf_bytes):
    """Upload sem equipment_key, doc_type e published_date deve ser aceito."""
    from app.services.ingestion import IngestionResult

    mock_result = IngestionResult(
        success=True,
        message="Documento ingerido.",
        document_id="doc-999",
        version_id="ver-999",
        total_pages=1,
        total_chunks=5,
    )

    with patch("app.api.upload.ingest_document", new_callable=AsyncMock, return_value=mock_result):
        resp = await async_client.post(
            "/api/v1/upload/document",
            files={"file": ("sem-meta.pdf", sample_pdf_bytes, "application/pdf")},
            data={},
        )

    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.anyio
async def test_upload_invalid_doc_type_when_provided(async_client, sample_pdf_bytes):
    """doc_type inválido quando fornecido deve retornar 400."""
    resp = await async_client.post(
        "/api/v1/upload/document",
        files={"file": ("manual.pdf", sample_pdf_bytes, "application/pdf")},
        data={"doc_type": "invalido"},
    )
    assert resp.status_code == 400
    assert "doc_type" in resp.json()["detail"]


@pytest.mark.anyio
async def test_upload_rejects_empty_file(async_client):
    """Arquivo de 0 bytes deve retornar 400."""
    resp = await async_client.post(
        "/api/v1/upload/document",
        files={"file": ("vazio.pdf", b"", "application/pdf")},
        data={},
    )
    assert resp.status_code == 400
    assert "vazio" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_upload_rejects_oversized_file(async_client):
    """Arquivo acima do limite deve retornar 400."""
    # patch.object no singleton de settings — garante restauração mesmo em falha
    from unittest.mock import patch
    import app.api.upload as upload_module

    with patch.object(upload_module.settings, "max_upload_size_mb", 0):
        # 0MB → qualquer arquivo não-vazio excede o limite
        resp = await async_client.post(
            "/api/v1/upload/document",
            files={"file": ("grande.pdf", b"PDF content", "application/pdf")},
            data={},
        )

    assert resp.status_code == 400
    assert "excede" in resp.json()["detail"].lower()
```

- [ ] **Step 2: Rodar testes para confirmar que falham**

```bash
cd backend
pytest tests/integration/test_upload_api.py::test_upload_without_metadata_succeeds \
       tests/integration/test_upload_api.py::test_upload_invalid_doc_type_when_provided \
       tests/integration/test_upload_api.py::test_upload_rejects_empty_file \
       tests/integration/test_upload_api.py::test_upload_rejects_oversized_file \
       -v
```

Expected: 3–4 FAILED

- [ ] **Step 3: Implementar campos opcionais no endpoint**

Primeiro, adicionar o import de `settings` no topo de `backend/app/api/upload.py` (junto aos demais imports):

```python
from app.core.config import settings
```

Depois, substituir a função `upload_document`:

```python
@router.post("/document", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(..., description="Arquivo PDF"),
    equipment_key: Optional[str] = Form(None, description="ID do equipamento (ex: frontier-780)"),
    doc_type: Optional[str] = Form(None, description="Tipo: 'manual' ou 'informativo'"),
    published_date: Optional[date] = Form(None, description="Data de publicação (YYYY-MM-DD)"),
    equipment_display_name: Optional[str] = Form(None, description="Nome de exibição do equipamento"),
    _user: CurrentUser = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos.")

    if doc_type is not None and doc_type not in ("manual", "informativo"):
        raise HTTPException(status_code=400, detail="doc_type deve ser 'manual' ou 'informativo'.")

    file_bytes = await file.read()

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"Arquivo excede {settings.max_upload_size_mb}MB.",
        )

    result: IngestionResult = await ingest_document(
        db=db,
        file_bytes=file_bytes,
        filename=file.filename,
        equipment_key=equipment_key.lower().strip() if equipment_key else None,
        doc_type=doc_type,
        published_date=published_date,
        display_name=equipment_display_name,
    )

    if not result.success:
        raise HTTPException(status_code=422, detail=result.message)

    return UploadResponse(
        success=result.success,
        message=result.message,
        document_id=result.document_id,
        version_id=result.version_id,
        total_pages=result.total_pages,
        total_chunks=result.total_chunks,
        was_duplicate=result.was_duplicate,
    )
```

- [ ] **Step 4: Rodar todos os testes de upload**

```bash
cd backend
pytest tests/integration/test_upload_api.py -v
```

Expected: todos os testes PASSED (incluindo os 4 novos + os 7 existentes)

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/upload.py backend/tests/integration/test_upload_api.py
git commit -m "feat(upload): campos opcionais + limite 200MB configurável (IA-94)"
```

---

## Task 3: Backend — Batch Insert de Chunks

**Files:**
- Modify: `backend/app/services/repository.py`
- Test: `backend/tests/unit/test_repository.py`

O teste existente `test_insert_chunks_inserts_all` verifica `mock_db.execute.call_count == 4` (1 DELETE + 3 INSERTs individuais). Após a mudança, deve ser `== 2` (1 DELETE + 1 INSERT em lote).

- [ ] **Step 1: Atualizar o teste existente para o novo comportamento**

Em `backend/tests/unit/test_repository.py`, localizar `test_insert_chunks_inserts_all` e alterar o assert:

```python
@pytest.mark.asyncio
async def test_insert_chunks_inserts_all(mock_db, make_mock_result):
    mock_db.execute = AsyncMock(return_value=make_mock_result())
    chunks = [
        TextChunk(page_number=1, chunk_index=0, content="chunk 0"),
        TextChunk(page_number=1, chunk_index=1, content="chunk 1"),
        TextChunk(page_number=2, chunk_index=0, content="chunk 2"),
    ]
    embeddings = [[0.1] * 10, [0.2] * 10, [0.3] * 10]

    count = await insert_chunks_with_embeddings(mock_db, uuid4(), chunks, embeddings)

    assert count == 3
    # 1 DELETE + 1 INSERT em lote = 2 execute calls (era 4 antes do batch)
    assert mock_db.execute.call_count == 2
    mock_db.commit.assert_awaited_once()
```

Adicionar também um teste para lista vazia (edge case):

```python
@pytest.mark.asyncio
async def test_insert_chunks_empty_list(mock_db, make_mock_result):
    """Lista vazia deve fazer apenas o DELETE e retornar 0."""
    mock_db.execute = AsyncMock(return_value=make_mock_result())

    count = await insert_chunks_with_embeddings(mock_db, uuid4(), [], [])

    assert count == 0
    # Apenas o DELETE é executado — sem INSERT
    assert mock_db.execute.call_count == 1
    mock_db.commit.assert_awaited_once()
```

- [ ] **Step 2: Rodar testes para confirmar que falham**

```bash
cd backend
pytest tests/unit/test_repository.py::test_insert_chunks_inserts_all \
       tests/unit/test_repository.py::test_insert_chunks_empty_list \
       -v
```

Expected: `test_insert_chunks_inserts_all` FAILED (call_count é 4, esperado 2); `test_insert_chunks_empty_list` FAILED (função não existe ou retorna errado)

- [ ] **Step 3: Implementar batch insert**

Substituir a função `insert_chunks_with_embeddings` em `backend/app/services/repository.py`:

```python
async def insert_chunks_with_embeddings(
    db: AsyncSession,
    version_id: UUID,
    chunks: List[TextChunk],
    embeddings: List[List[float]],
) -> int:
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"Mismatch: {len(chunks)} chunks vs {len(embeddings)} embeddings"
        )

    await db.execute(
        text("DELETE FROM chunks WHERE document_version_id = :vid"),
        {"vid": str(version_id)},
    )

    if not chunks:
        await db.commit()
        return 0

    params: dict = {"version_id": str(version_id)}
    value_rows: list[str] = []

    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        # Seguro: valores de embedding são passados como parâmetros nomeados (:N_emb),
        # não interpolados diretamente na string SQL — sem risco de SQL injection.
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
        value_rows.append(
            f"(:version_id, :{i}_page, :{i}_idx, :{i}_content, :{i}_emb::vector)"
        )
        params[f"{i}_page"] = chunk.page_number
        params[f"{i}_idx"] = chunk.chunk_index
        params[f"{i}_content"] = chunk.content
        params[f"{i}_emb"] = embedding_str

    await db.execute(
        text(f"""
            INSERT INTO chunks
                (document_version_id, page_number, chunk_index, content, embedding)
            VALUES {", ".join(value_rows)}
            ON CONFLICT (document_version_id, page_number, chunk_index) DO UPDATE
            SET content = EXCLUDED.content, embedding = EXCLUDED.embedding
        """),
        params,
    )

    await db.commit()
    logger.info(f"Inseridos {len(chunks)} chunks para versão {version_id}")
    return len(chunks)
```

- [ ] **Step 4: Rodar todos os testes unitários do repository**

```bash
cd backend
pytest tests/unit/test_repository.py -v
```

Expected: todos PASSED

- [ ] **Step 5: Rodar suite completa de backend**

```bash
cd backend
pytest -v
```

Expected: todos os testes PASSED (os números totais devem ser ≥ 109 — 105 anteriores + 4 novos de upload + 1 novo de repository)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/repository.py backend/tests/unit/test_repository.py
git commit -m "perf(repository): batch insert de chunks — 1 execute em vez de N (IA-94)"
```

---

## Task 4: Frontend — Corrigir Tipos TypeScript

**Files:**
- Modify: `frontend/src/types/index.ts`

`UploadResponse.document_id` e `version_id` são `Optional` no backend (são `None` em caso de duplicata). O TypeScript precisa refletir isso.

- [ ] **Step 1: Tornar campos opcionais na interface**

Em `frontend/src/types/index.ts`, alterar `UploadResponse`:

```typescript
export interface UploadResponse {
  success: boolean;
  message: string;
  document_id?: string;   // None quando was_duplicate=true
  version_id?: string;    // None quando was_duplicate=true
  total_pages: number;
  total_chunks: number;
  was_duplicate: boolean;
}
```

- [ ] **Step 2: Verificar que o TypeScript compila sem erros**

```bash
cd frontend
npx tsc --noEmit
```

Expected: sem erros de tipo

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "fix(types): UploadResponse.document_id e version_id opcionais (IA-95)"
```

---

## Task 5: Frontend — `uploadDocumentWithProgress` no API Client

**Files:**
- Modify: `frontend/src/lib/api.ts`

Adiciona função XHR que entrega progresso real de bytes durante o upload.

- [ ] **Step 1: Adicionar função ao final de `frontend/src/lib/api.ts`**

```typescript
export async function uploadDocumentWithProgress(
  formData: FormData,
  onProgress: (percent: number) => void,
  onProcessing: () => void,
  signal?: AbortSignal, // reservado — sem lógica de cancelamento nesta versão
): Promise<UploadResponse> {
  const auth = await authHeaders();

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) {
        // Cap em 99% — 100% sinaliza que o servidor está processando
        onProgress(Math.min(99, Math.round((e.loaded / e.total) * 100)));
      }
    });

    xhr.upload.addEventListener("load", () => {
      onProgress(100);
      onProcessing(); // Muda status para "processando" no componente
    });

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as UploadResponse);
        } catch {
          reject(new Error("Resposta inválida do servidor."));
        }
      } else {
        // Reutiliza parseApiError criando um Response sintético a partir do XHR
        const fakeResponse = new Response(xhr.responseText, {
          status: xhr.status,
        });
        parseApiError(fakeResponse).then((msg) => reject(new Error(msg)));
      }
    });

    xhr.addEventListener("error", () => {
      reject(
        new Error(
          "Não foi possível conectar ao servidor. Verifique se o backend está rodando.",
        ),
      );
    });

    xhr.addEventListener("timeout", () => {
      reject(
        new Error(
          "A operação demorou mais que o esperado. Para documentos grandes, isso pode levar alguns minutos — tente novamente.",
        ),
      );
    });

    xhr.timeout = 600_000;
    xhr.open("POST", `${API_BASE}/api/v1/upload/document`);

    if (auth["Authorization"]) {
      xhr.setRequestHeader("Authorization", auth["Authorization"]);
    }

    xhr.send(formData);
  });
}
```

- [ ] **Step 2: Verificar que o TypeScript compila sem erros**

```bash
cd frontend
npx tsc --noEmit
```

Expected: sem erros

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(api): uploadDocumentWithProgress com XHR e progresso de bytes (IA-95)"
```

---

## Task 6: Frontend — Componente `FileProgressItem`

**Files:**
- Create: `frontend/src/components/upload/FileProgressItem.tsx`

Componente stateless que renderiza o estado de um único arquivo.

- [ ] **Step 1: Criar o arquivo**

```typescript
// frontend/src/components/upload/FileProgressItem.tsx
"use client";

import { FileText, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { UploadResponse } from "@/types";

export type FileStatus =
  | "pendente"
  | "enviando"
  | "processando"
  | "concluído"
  | "erro";

export interface FileUploadState {
  id: string; // crypto.randomUUID() — chave de UI, não enviada ao backend
  file: File;
  status: FileStatus;
  progress: number; // 0–100, usado apenas em "enviando"
  result?: UploadResponse;
  error?: string;
}

const STATUS_LABELS: Record<FileStatus, string> = {
  pendente: "Pendente",
  enviando: "Enviando",
  processando: "Processando",
  concluído: "Concluído",
  erro: "Erro",
};

const STATUS_BADGE_CLASS: Record<FileStatus, string> = {
  pendente: "bg-muted text-muted-foreground",
  enviando: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  processando:
    "bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300",
  concluído:
    "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300",
  erro: "bg-destructive/10 text-destructive",
};

function truncateFilename(name: string, maxLen = 40): string {
  if (name.length <= maxLen) return name;
  const half = Math.floor((maxLen - 3) / 2);
  return `${name.slice(0, half)}...${name.slice(name.length - half)}`;
}

interface Props {
  state: FileUploadState;
}

export function FileProgressItem({ state }: Props) {
  const { file, status, progress, result, error } = state;

  return (
    <div className="flex flex-col gap-1.5 rounded-lg border p-3">
      <div className="flex items-center gap-3">
        <FileText className="h-5 w-5 shrink-0 text-muted-foreground" />
        <span
          className="flex-1 truncate text-sm font-medium"
          title={file.name}
        >
          {truncateFilename(file.name)}
        </span>
        <span
          className={cn(
            "flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
            STATUS_BADGE_CLASS[status],
          )}
        >
          {status === "processando" && (
            <Loader2 className="h-3 w-3 animate-spin" />
          )}
          {STATUS_LABELS[status]}
        </span>
      </div>

      {status === "enviando" && (
        <div className="ml-8">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-blue-500 transition-all duration-200"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="mt-0.5 text-right text-xs text-muted-foreground">
            {progress}%
          </p>
        </div>
      )}

      {status === "concluído" && result && (
        <p className="ml-8 text-xs text-muted-foreground">
          {result.total_chunks} chunks · {result.total_pages} página
          {result.total_pages !== 1 ? "s" : ""}
          {result.was_duplicate && " · (duplicata)"}
        </p>
      )}

      {status === "erro" && error && (
        <p className="ml-8 text-xs text-destructive">{error}</p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verificar que o TypeScript compila sem erros**

```bash
cd frontend
npx tsc --noEmit
```

Expected: sem erros

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/upload/FileProgressItem.tsx
git commit -m "feat(upload): componente FileProgressItem com estados em PT-BR (IA-95)"
```

---

## Task 7: Frontend — Componente `BulkUploadForm`

**Files:**
- Create: `frontend/src/components/upload/BulkUploadForm.tsx`

Componente principal com dropzone, fila de uploads, estados por arquivo e resumo final.

- [ ] **Step 1: Criar o arquivo**

```typescript
// frontend/src/components/upload/BulkUploadForm.tsx
"use client";

import { useState, useRef, useCallback } from "react";
import { uploadDocumentWithProgress } from "@/lib/api";
import { FileProgressItem } from "./FileProgressItem";
import type { FileUploadState, FileStatus } from "./FileProgressItem";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Upload, CheckCircle2, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

const MAX_FILES = 10;
const MAX_FILE_SIZE_MB = 200;
const MAX_CONCURRENT = 3;

type Phase = "select" | "uploading" | "done";

interface FieldErrors {
  files?: string;
  equipment_key?: string;
}

function validateFiles(files: File[]): string | null {
  if (files.length === 0) return "Selecione ao menos um arquivo PDF.";
  if (files.length > MAX_FILES)
    return `Máximo de ${MAX_FILES} arquivos por envio.`;
  for (const f of files) {
    if (!f.name.toLowerCase().endsWith(".pdf"))
      return `"${f.name}" não é um PDF.`;
    if (f.size === 0) return `"${f.name}" está vazio.`;
    if (f.size > MAX_FILE_SIZE_MB * 1024 * 1024)
      return `"${f.name}" excede ${MAX_FILE_SIZE_MB}MB.`;
  }
  return null;
}

export function BulkUploadForm() {
  const [phase, setPhase] = useState<Phase>("select");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [fileStates, setFileStates] = useState<FileUploadState[]>([]);
  const [docType, setDocType] = useState("");
  const [equipmentKey, setEquipmentKey] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [isDragging, setIsDragging] = useState(false);

  // Refs para estado mutável que não dispara re-render
  const queueRef = useRef<FileUploadState[]>([]);
  const activeCountRef = useRef(0);
  // Captura os valores de metadata no momento do submit (estáveis durante upload)
  const equipmentKeyRef = useRef("");
  const docTypeRef = useRef("");

  const updateFileState = useCallback(
    (id: string, patch: Partial<FileUploadState>) => {
      setFileStates((prev) =>
        prev.map((s) => (s.id === id ? { ...s, ...patch } : s)),
      );
    },
    [],
  );

  const checkIfDone = useCallback(() => {
    setFileStates((prev) => {
      const allDone = prev.every(
        (s) => s.status === "concluído" || s.status === "erro",
      );
      if (allDone && prev.length > 0) setPhase("done");
      return prev;
    });
  }, []);

  // processFile é memoizado com deps [updateFileState, checkIfDone].
  // A chamada recursiva `processFile(next)` dentro do próprio callback é segura:
  // em JS single-threaded, `queueRef.current.shift()` é atômico e o closure
  // captura sempre a versão atual da função. Não incluímos `processFile` nas deps
  // para evitar loop infinito de recriação.
  const processFile = useCallback(
    async (state: FileUploadState) => {
      updateFileState(state.id, { status: "enviando", progress: 0 });

      const fd = new FormData();
      fd.append("file", state.file);
      if (equipmentKeyRef.current)
        fd.append("equipment_key", equipmentKeyRef.current);
      if (docTypeRef.current) fd.append("doc_type", docTypeRef.current);

      try {
        const result = await uploadDocumentWithProgress(
          fd,
          (pct) => updateFileState(state.id, { progress: pct }),
          () =>
            updateFileState(state.id, { status: "processando", progress: 100 }),
        );
        updateFileState(state.id, { status: "concluído", result });
      } catch (err) {
        updateFileState(state.id, {
          status: "erro",
          error:
            err instanceof Error ? err.message : "Erro desconhecido.",
        });
      } finally {
        activeCountRef.current -= 1;
        const next = queueRef.current.shift();
        if (next) {
          activeCountRef.current += 1;
          processFile(next);
        }
        checkIfDone();
      }
    },
    [updateFileState, checkIfDone],
  );

  function handleFilesChange(files: FileList | null) {
    if (!files || files.length === 0) return;
    const arr = Array.from(files).slice(0, MAX_FILES);
    setSelectedFiles(arr);
    setFieldErrors({});
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    if (phase !== "select") return;
    handleFilesChange(e.dataTransfer?.files ?? null);
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave() {
    setIsDragging(false);
  }

  async function handleSubmit() {
    const fileError = validateFiles(selectedFiles);
    if (fileError) {
      setFieldErrors({ files: fileError });
      return;
    }

    if (
      equipmentKey.trim() &&
      !/^[a-z0-9][a-z0-9-]*$/.test(equipmentKey.trim())
    ) {
      setFieldErrors({
        equipment_key: "Use apenas letras minúsculas, números e hífens.",
      });
      return;
    }

    // Capturar metadata em refs antes de iniciar (imutável durante upload)
    equipmentKeyRef.current = equipmentKey.toLowerCase().trim();
    docTypeRef.current = docType;

    const states: FileUploadState[] = selectedFiles.map((file) => ({
      id: crypto.randomUUID(),
      file,
      status: "pendente" as FileStatus,
      progress: 0,
    }));

    setFileStates(states);
    setPhase("uploading");

    // Arquivos além do limite de concorrência ficam na fila
    queueRef.current = states.slice(MAX_CONCURRENT);
    activeCountRef.current = 0;

    // Inicia o primeiro lote
    states.slice(0, MAX_CONCURRENT).forEach((s) => {
      activeCountRef.current += 1;
      processFile(s);
    });
  }

  function handleReset() {
    setPhase("select");
    setSelectedFiles([]);
    setFileStates([]);
    setDocType("");
    setEquipmentKey("");
    setFieldErrors({});
    queueRef.current = [];
    activeCountRef.current = 0;
  }

  const successCount = fileStates.filter((s) => s.status === "concluído").length;
  const errorCount = fileStates.filter((s) => s.status === "erro").length;

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5" />
            Upload de Documentos
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {phase === "select" && (
            <>
              {/* Dropzone */}
              <div>
                <label className="mb-1.5 block text-sm font-medium">
                  Arquivos PDF{" "}
                  <span className="text-muted-foreground">
                    (máx. {MAX_FILES}, até {MAX_FILE_SIZE_MB}MB cada)
                  </span>
                </label>
                <label
                  onDrop={handleDrop}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  className={cn(
                    "flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed p-6 text-center transition-colors",
                    isDragging
                      ? "border-primary bg-accent"
                      : "hover:border-primary hover:bg-accent",
                    fieldErrors.files && "border-destructive",
                  )}
                >
                  <Upload className="h-8 w-8 text-muted-foreground" />
                  <div className="text-sm text-muted-foreground">
                    {selectedFiles.length > 0 ? (
                      <span className="font-medium text-foreground">
                        {selectedFiles.length} arquivo
                        {selectedFiles.length > 1 ? "s" : ""} selecionado
                        {selectedFiles.length > 1 ? "s" : ""}
                      </span>
                    ) : (
                      <>Arraste arquivos ou clique para selecionar</>
                    )}
                  </div>
                  <input
                    type="file"
                    accept=".pdf"
                    multiple
                    className="hidden"
                    onChange={(e) => handleFilesChange(e.target.files)}
                  />
                </label>
                {fieldErrors.files && (
                  <p className="mt-1 text-xs text-destructive">
                    {fieldErrors.files}
                  </p>
                )}
              </div>

              {/* Metadata opcionais */}
              <div>
                <label className="mb-1.5 block text-sm font-medium">
                  Equipamento{" "}
                  <span className="text-muted-foreground">(opcional)</span>
                </label>
                <Input
                  placeholder="ex: frontier-780"
                  value={equipmentKey}
                  className={cn(
                    fieldErrors.equipment_key && "border-destructive",
                  )}
                  onChange={(e) => {
                    setEquipmentKey(e.target.value);
                    setFieldErrors((p) => ({
                      ...p,
                      equipment_key: undefined,
                    }));
                  }}
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Letras minúsculas, números e hífens
                </p>
                {fieldErrors.equipment_key && (
                  <p className="mt-1 text-xs text-destructive">
                    {fieldErrors.equipment_key}
                  </p>
                )}
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium">
                  Tipo de documento{" "}
                  <span className="text-muted-foreground">(opcional)</span>
                </label>
                <Select value={docType} onValueChange={setDocType}>
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione o tipo" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="manual">Manual</SelectItem>
                    <SelectItem value="informativo">Informativo</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <Button
                className="w-full"
                onClick={handleSubmit}
                disabled={selectedFiles.length === 0}
              >
                <Upload className="mr-2 h-4 w-4" />
                Enviar{" "}
                {selectedFiles.length > 0
                  ? `${selectedFiles.length} arquivo${selectedFiles.length > 1 ? "s" : ""}`
                  : "documentos"}
              </Button>
            </>
          )}

          {(phase === "uploading" || phase === "done") && (
            <div className="space-y-2">
              {fileStates.map((s) => (
                <FileProgressItem key={s.id} state={s} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {phase === "done" && (
        <Card
          className={errorCount === 0 ? "border-green-500" : "border-yellow-500"}
        >
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              {errorCount === 0 ? (
                <CheckCircle2 className="h-5 w-5 shrink-0 text-green-600" />
              ) : (
                <AlertCircle className="h-5 w-5 shrink-0 text-yellow-600" />
              )}
              <div className="flex-1 space-y-3">
                <p className="text-sm font-medium">
                  {successCount} de {fileStates.length} concluído
                  {fileStates.length > 1 ? "s" : ""} com sucesso
                  {errorCount > 0 && ` · ${errorCount} com erro`}
                </p>
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={handleReset}
                >
                  Novo upload
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verificar que o TypeScript compila sem erros**

```bash
cd frontend
npx tsc --noEmit
```

Expected: sem erros

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/upload/BulkUploadForm.tsx
git commit -m "feat(upload): BulkUploadForm com fila, progresso e estados PT-BR (IA-95)"
```

---

## Task 8: Frontend — Trocar Página e Remover `UploadForm`

**Files:**
- Modify: `frontend/src/app/upload/page.tsx`
- Delete: `frontend/src/components/upload/UploadForm.tsx`

- [ ] **Step 1: Verificar que UploadForm não tem outros imports**

```bash
grep -r "UploadForm" frontend/src --include="*.tsx" --include="*.ts"
```

> Executar a partir da raiz do repositório (`/Users/arthurbueno/HaruCode/apps/kyotech-ai`).

Expected: apenas `app/upload/page.tsx` e o próprio `UploadForm.tsx`

- [ ] **Step 2: Atualizar `frontend/src/app/upload/page.tsx`**

```typescript
import { BulkUploadForm } from "@/components/upload/BulkUploadForm";

export default function UploadPage() {
  return (
    <div className="h-full overflow-y-auto p-6">
      <BulkUploadForm />
    </div>
  );
}
```

- [ ] **Step 3: Remover `UploadForm.tsx`**

```bash
rm frontend/src/components/upload/UploadForm.tsx
```

- [ ] **Step 4: Verificar que o TypeScript compila sem erros**

```bash
cd frontend
npx tsc --noEmit
```

Expected: sem erros

- [ ] **Step 5: Verificar que o build do Next.js passa**

```bash
cd frontend
npm run build 2>&1 | tail -20
```

Expected: `✓ Compiled successfully` (ou similar, sem erros de tipo)

- [ ] **Step 6: Commit final**

```bash
git add frontend/src/app/upload/page.tsx
git rm frontend/src/components/upload/UploadForm.tsx
git commit -m "feat(upload): substituir UploadForm por BulkUploadForm — IA-94 + IA-95 concluídos"
```

---

## Verificação Final

- [ ] **Rodar suite completa de testes backend**

```bash
cd backend
pytest -v
```

Expected: todos PASSED, sem regressões

- [ ] **Verificar build do frontend**

```bash
cd frontend
npm run build
```

Expected: build sem erros de tipo ou compilação

- [ ] **Checklist de regras de negócio**

Confirmar que cada regra está implementada:
- [ ] Apenas PDFs aceitos (backend: extensão; frontend: `accept=".pdf"` + validação)
- [ ] Máx 200MB por arquivo (backend: `settings.max_upload_size_mb`; frontend: `file.size`)
- [ ] Máx 10 arquivos (frontend: `slice(0, MAX_FILES)`)
- [ ] Campos opcionais: `equipment_key`, `doc_type`, `published_date` (backend: `Form(None)`; frontend: sem `required`)
- [ ] `doc_type` validado apenas quando fornecido (backend: `if doc_type is not None`)
- [ ] Estados em PT-BR: `pendente`, `enviando`, `processando`, `concluído`, `erro`
- [ ] Max 3 uploads simultâneos (frontend: `MAX_CONCURRENT = 3`)
- [ ] Fila drena automaticamente ao concluir cada arquivo
- [ ] Bloqueio de novo upload durante processamento (frontend: `phase !== "select"`)
- [ ] Resumo final com contagem de sucesso/erro
- [ ] Botão "Novo upload" reseta estado completamente
