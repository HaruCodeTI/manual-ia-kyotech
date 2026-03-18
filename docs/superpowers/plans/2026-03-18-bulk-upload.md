# Bulk Upload — Até 10 Arquivos por Vez Sem Chave de Equipamento

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir upload de até 10 PDFs simultaneamente, removendo os campos obrigatórios de `equipment_key` e `doc_type` do formulário — o documento agora é independente de equipamento, refletindo a realidade de que um manual pode referenciar múltiplos modelos.

**Architecture:** Novo endpoint `POST /api/v1/upload/batch` que recebe N arquivos com uma única `published_date`. O schema do banco tem `equipment_key` e `doc_type` tornados nullable em `documents`. A ingestion processa os arquivos sequencialmente (não paralelo) para não sobrecarregar a Azure OpenAI. O frontend troca o formulário atual por um multi-file dropzone com barra de progresso por arquivo. O endpoint legado `/upload/document` é mantido para backward compat.

**Tech Stack:** FastAPI (UploadFile list), PostgreSQL migration (ALTER COLUMN), Next.js (input multiple + estado por arquivo), Shadcn/ui Progress component.

---

## Mapa de Arquivos

| Ação | Arquivo |
|---|---|
| Criar | `backend/migrations/003_bulk_upload.sql` |
| Modificar | `backend/app/api/upload.py` |
| Modificar | `backend/app/services/ingestion.py` |
| Modificar | `backend/app/services/repository.py` |
| Modificar | `backend/app/services/search.py` |
| Criar | `frontend/src/components/upload/BulkUploadForm.tsx` |
| Modificar | `frontend/src/app/upload/page.tsx` |
| Modificar | `frontend/src/lib/api.ts` |
| Modificar | `frontend/src/types/index.ts` |
| Criar | `backend/tests/test_bulk_upload.py` |

---

## Task 1: Migration do Banco de Dados

**Files:**
- Create: `backend/migrations/003_bulk_upload.sql`

- [ ] **Step 1: Escrever a migration**

  ```sql
  -- backend/migrations/003_bulk_upload.sql
  -- Kyotech AI — Fase 3: equipment_key e doc_type tornam-se opcionais em documents

  -- Remover constraint UNIQUE antiga (doc_type, equipment_key)
  ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_doc_type_equipment_key_key;

  -- Tornar colunas nullable
  ALTER TABLE documents ALTER COLUMN equipment_key DROP NOT NULL;
  ALTER TABLE documents ALTER COLUMN doc_type DROP NOT NULL;

  -- Nova constraint: unique por (source_filename hash) não é necessária aqui
  -- documents agora pode ter múltiplas linhas sem equipment_key
  -- A unicidade é controlada via document_versions.source_hash

  -- Atualizar a view current_versions para lidar com equipment_key nullable
  DROP VIEW IF EXISTS current_versions;
  CREATE VIEW current_versions AS
  SELECT DISTINCT ON (document_id)
      id,
      document_id,
      published_date,
      source_hash,
      source_filename,
      storage_path
  FROM document_versions
  ORDER BY document_id, published_date DESC;
  ```

- [ ] **Step 2: Executar a migration no banco de desenvolvimento**

  ```bash
  cd backend
  source .venv/bin/activate
  psql $DATABASE_URL -f migrations/003_bulk_upload.sql
  ```

  Esperado: `ALTER TABLE`, `ALTER TABLE`, `CREATE VIEW` sem erros

- [ ] **Step 3: Verificar no psql**

  ```sql
  \d documents
  ```

  Esperado: colunas `equipment_key` e `doc_type` mostradas como `character varying` sem `not null`

- [ ] **Step 4: Commit**

  ```bash
  git add backend/migrations/003_bulk_upload.sql
  git commit -m "feat(db): tornar equipment_key e doc_type opcionais em documents"
  ```

---

## Task 2: Adaptar o Serviço de Ingestion

**Files:**
- Modify: `backend/app/services/ingestion.py`
- Modify: `backend/app/services/repository.py`

- [ ] **Step 1: Escrever o teste**

  Criar `backend/tests/test_bulk_upload.py`:

  ```python
  # backend/tests/test_bulk_upload.py
  import pytest
  from unittest.mock import AsyncMock, patch, MagicMock
  from datetime import date
  from app.services.ingestion import ingest_document

  @pytest.mark.asyncio
  async def test_ingest_without_equipment_key():
      """Ingestion deve funcionar sem equipment_key."""
      mock_db = AsyncMock()
      fake_pdf = b"%PDF-1.4 fake"

      with patch("app.services.ingestion.extract_text_from_pdf") as mock_extract, \
           patch("app.services.ingestion.repository") as mock_repo, \
           patch("app.services.ingestion.upload_pdf") as mock_upload, \
           patch("app.services.ingestion.chunk_pages") as mock_chunk, \
           patch("app.services.ingestion.generate_embeddings") as mock_embed:

          mock_extract.return_value = MagicMock(
              total_pages=5,
              pages=[],
              source_hash="abc123"
          )
          mock_repo.find_or_create_document = AsyncMock(return_value="doc-uuid")
          mock_repo.check_version_exists = AsyncMock(return_value=False)
          mock_upload.return_value = "2026-01-01/test.pdf"
          mock_repo.create_version = AsyncMock(return_value="ver-uuid")
          mock_chunk.return_value = []
          mock_embed.return_value = []

          result = await ingest_document(
              db=mock_db,
              file_bytes=fake_pdf,
              filename="test.pdf",
              published_date=date(2026, 1, 1),
              equipment_key=None,  # sem equipamento
              doc_type=None,       # sem tipo
          )

          assert result.success is True
          # find_or_create_equipment NÃO deve ser chamado quando equipment_key é None
          mock_repo.find_or_create_equipment.assert_not_called()
  ```

- [ ] **Step 2: Rodar o teste para ver falhar**

  ```bash
  cd backend && pytest tests/test_bulk_upload.py -v
  ```

  Esperado: FAIL — `ingest_document` ainda exige `equipment_key`

- [ ] **Step 3: Adaptar `ingestion.py` para aceitar parâmetros opcionais**

  Em `backend/app/services/ingestion.py`, alterar a assinatura e o passo 2:

  ```python
  async def ingest_document(
      db: AsyncSession,
      file_bytes: bytes,
      filename: str,
      published_date: date,
      equipment_key: Optional[str] = None,   # agora opcional
      doc_type: Optional[str] = None,         # agora opcional
      display_name: Optional[str] = None,
  ) -> IngestionResult:
      try:
          logger.info(f"[1/6] Extraindo texto: {filename}")
          extraction = extract_text_from_pdf(file_bytes, filename)

          # Passo 2: Equipamento — apenas se fornecido
          if equipment_key:
              logger.info(f"[2/6] Verificando equipamento: {equipment_key}")
              await repository.find_or_create_equipment(db, equipment_key, display_name)
          else:
              logger.info("[2/6] Sem equipamento especificado — documento geral")

          # Passo 3: Documento
          document_id = await repository.find_or_create_document(
              db, doc_type=doc_type, equipment_key=equipment_key
          )

          # Storage path: sem equipment_key usa "geral/"
          prefix = equipment_key or "geral"
          storage_path = f"{prefix}/{published_date.isoformat()}/{filename}"

          # ... resto do pipeline sem mudanças
  ```

- [ ] **Step 4: Adaptar `repository.find_or_create_document` para nullable**

  Em `backend/app/services/repository.py`:

  ```python
  async def find_or_create_document(
      db: AsyncSession,
      doc_type: Optional[str],
      equipment_key: Optional[str],
  ) -> UUID:
      # Buscar por filename hash seria ideal, mas usamos doc_type + equipment_key
      # Com ambos nullable, cada upload sem equipamento cria um documento novo
      result = await db.execute(
          text("""
              SELECT id FROM documents
              WHERE
                  (doc_type = :doc_type OR (doc_type IS NULL AND :doc_type IS NULL))
                  AND
                  (equipment_key = :equipment_key OR (equipment_key IS NULL AND :equipment_key IS NULL))
              LIMIT 1
          """),
          {"doc_type": doc_type, "equipment_key": equipment_key},
      )
      row = result.fetchone()
      if row:
          return row[0]

      result = await db.execute(
          text("""
              INSERT INTO documents (doc_type, equipment_key)
              VALUES (:doc_type, :equipment_key)
              RETURNING id
          """),
          {"doc_type": doc_type, "equipment_key": equipment_key},
      )
      return result.fetchone()[0]
  ```

- [ ] **Step 5: Rodar o teste para ver passar**

  ```bash
  pytest tests/test_bulk_upload.py -v
  ```

  Esperado: PASS

- [ ] **Step 6: Commit**

  ```bash
  git add backend/app/services/ingestion.py backend/app/services/repository.py backend/tests/test_bulk_upload.py
  git commit -m "feat(ingestion): equipment_key e doc_type opcionais na ingestion"
  ```

---

## Task 3: Novo Endpoint de Batch Upload

**Files:**
- Modify: `backend/app/api/upload.py`

- [ ] **Step 1: Escrever o teste do endpoint**

  Em `backend/tests/test_bulk_upload.py`, adicionar:

  ```python
  from fastapi.testclient import TestClient
  from unittest.mock import patch, AsyncMock
  from app.main import app

  client = TestClient(app)

  def test_batch_upload_rejects_more_than_10():
      """Batch upload deve rejeitar mais de 10 arquivos."""
      files = [
          ("files", (f"doc{i}.pdf", b"%PDF fake", "application/pdf"))
          for i in range(11)
      ]
      response = client.post(
          "/api/v1/upload/batch",
          files=files,
          data={"published_date": "2026-01-01"},
          headers={"Authorization": "Bearer fake"},  # dev mode ignora
      )
      assert response.status_code == 400
      assert "10" in response.json()["detail"]

  def test_batch_upload_rejects_non_pdf():
      """Batch upload deve rejeitar arquivos não-PDF."""
      files = [("files", ("doc.txt", b"text content", "text/plain"))]
      response = client.post(
          "/api/v1/upload/batch",
          files=files,
          data={"published_date": "2026-01-01"},
          headers={"Authorization": "Bearer fake"},
      )
      assert response.status_code == 400
  ```

- [ ] **Step 2: Rodar para ver falhar**

  ```bash
  pytest tests/test_bulk_upload.py::test_batch_upload_rejects_more_than_10 -v
  ```

  Esperado: FAIL — endpoint não existe

- [ ] **Step 3: Implementar o endpoint `/upload/batch`**

  Em `backend/app/api/upload.py`, adicionar:

  ```python
  from typing import List
  from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
  # (imports já existentes mantidos)

  class BatchUploadResult(BaseModel):
      filename: str
      success: bool
      message: str
      document_id: Optional[str] = None
      version_id: Optional[str] = None
      total_pages: int = 0
      total_chunks: int = 0
      was_duplicate: bool = False

  class BatchUploadResponse(BaseModel):
      total: int
      succeeded: int
      failed: int
      results: List[BatchUploadResult]


  @router.post("/batch", response_model=BatchUploadResponse)
  async def upload_batch(
      files: List[UploadFile] = File(..., description="Até 10 arquivos PDF"),
      published_date: date = Form(..., description="Data de publicação (YYYY-MM-DD)"),
      _user: CurrentUser = Depends(require_role("Admin")),
      db: AsyncSession = Depends(get_db),
  ):
      if len(files) > 10:
          raise HTTPException(status_code=400, detail="Máximo de 10 arquivos por upload.")
      if len(files) == 0:
          raise HTTPException(status_code=400, detail="Envie pelo menos 1 arquivo.")

      for f in files:
          if not f.filename or not f.filename.lower().endswith(".pdf"):
              raise HTTPException(
                  status_code=400,
                  detail=f"Arquivo '{f.filename}' não é um PDF válido."
              )

      results = []
      for upload_file in files:
          file_bytes = await upload_file.read()
          if len(file_bytes) == 0:
              results.append(BatchUploadResult(
                  filename=upload_file.filename,
                  success=False,
                  message="Arquivo vazio.",
              ))
              continue
          if len(file_bytes) > 100 * 1024 * 1024:
              results.append(BatchUploadResult(
                  filename=upload_file.filename,
                  success=False,
                  message="Arquivo excede 100MB.",
              ))
              continue

          result = await ingest_document(
              db=db,
              file_bytes=file_bytes,
              filename=upload_file.filename,
              published_date=published_date,
              equipment_key=None,
              doc_type=None,
          )
          results.append(BatchUploadResult(
              filename=upload_file.filename,
              success=result.success,
              message=result.message,
              document_id=result.document_id,
              version_id=result.version_id,
              total_pages=result.total_pages,
              total_chunks=result.total_chunks,
              was_duplicate=result.was_duplicate,
          ))

      succeeded = sum(1 for r in results if r.success)
      return BatchUploadResponse(
          total=len(results),
          succeeded=succeeded,
          failed=len(results) - succeeded,
          results=results,
      )
  ```

- [ ] **Step 4: Rodar todos os testes**

  ```bash
  pytest tests/test_bulk_upload.py -v
  ```

  Esperado: todos PASS

- [ ] **Step 5: Testar manualmente via Swagger**

  Abrir `http://localhost:8000/docs` → `POST /api/v1/upload/batch` → Try it out
  Enviar 2 PDFs com `published_date: 2026-01-01`
  Verificar resposta JSON com `results` por arquivo

- [ ] **Step 6: Commit**

  ```bash
  git add backend/app/api/upload.py
  git commit -m "feat(api): endpoint /upload/batch para até 10 PDFs sem equipment_key"
  ```

---

## Task 4: Adaptar Busca para equipment_key Nullable

**Files:**
- Modify: `backend/app/services/search.py`

- [ ] **Step 1: Verificar que a busca funciona com documentos sem equipment_key**

  O SQL já usa `d.equipment_key` nas queries. Com nullable, as queries funcionam — mas o `equipment_boost` vai comparar com `None` e nunca boostar. Isso é o comportamento correto.

  Em `search.py`, verificar o trecho do boost:

  ```python
  # Linha ~241: já trata o caso
  if result.equipment_key and result.equipment_key == equipment_key:
      scores[chunk_id] += EQUIPMENT_BOOST
  ```

  O `if result.equipment_key` já protege contra `None`. Nenhuma mudança necessária aqui.

- [ ] **Step 2: Adaptar `build_context` no generator para nullable**

  Em `backend/app/services/generator.py`, linha ~48:

  ```python
  context_parts.append(
      f"[Fonte {i}] Arquivo: {r.source_filename} | "
      f"Página: {r.page_number} | "
      f"Tipo: {r.doc_type or 'geral'} | "        # <-- adicionar fallback
      f"Equipamento: {r.equipment_key or 'geral'} | "  # <-- adicionar fallback
      f"Data: {r.published_date}\n"
      f"Conteúdo:\n{r.content}\n"
  )
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add backend/app/services/generator.py
  git commit -m "fix(generator): fallback para equipment_key e doc_type nullable"
  ```

---

## Task 5: Frontend — BulkUploadForm

**Files:**
- Create: `frontend/src/components/upload/BulkUploadForm.tsx`
- Modify: `frontend/src/app/upload/page.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Adicionar tipos em `types/index.ts`**

  ```typescript
  export interface BatchUploadFileResult {
    filename: string;
    success: boolean;
    message: string;
    total_pages?: number;
    total_chunks?: number;
    was_duplicate?: boolean;
  }

  export interface BatchUploadResponse {
    total: number;
    succeeded: number;
    failed: number;
    results: BatchUploadFileResult[];
  }
  ```

- [ ] **Step 2: Adicionar `uploadBatch` em `lib/api.ts`**

  ```typescript
  export async function uploadBatch(
    files: File[],
    publishedDate: string
  ): Promise<BatchUploadResponse> {
    const auth = await authHeaders();
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    fd.append("published_date", publishedDate);

    let res: Response;
    try {
      res = await fetchWithTimeout(
        `${API_BASE}/api/v1/upload/batch`,
        { method: "POST", body: fd, headers: auth },
        600_000  // 10 min timeout para múltiplos arquivos
      );
    } catch (err) {
      handleFetchError(err);
    }
    if (!res.ok) throw new Error(await parseApiError(res));
    return res.json();
  }
  ```

- [ ] **Step 3: Criar `BulkUploadForm.tsx`**

  ```tsx
  "use client";

  import { useState, useRef, type DragEvent } from "react";
  import { uploadBatch } from "@/lib/api";
  import type { BatchUploadResponse, BatchUploadFileResult } from "@/types";
  import { Button } from "@/components/ui/button";
  import { Input } from "@/components/ui/input";
  import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
  import { Upload, FileText, CheckCircle2, AlertCircle, Loader2, X } from "lucide-react";
  import { cn } from "@/lib/utils";

  const MAX_FILES = 10;

  export function BulkUploadForm() {
    const [files, setFiles] = useState<File[]>([]);
    const [publishedDate, setPublishedDate] = useState("");
    const [dateError, setDateError] = useState("");
    const [status, setStatus] = useState<"idle" | "uploading" | "done">("idle");
    const [result, setResult] = useState<BatchUploadResponse | null>(null);
    const [globalError, setGlobalError] = useState("");
    const [isDragging, setIsDragging] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    function addFiles(incoming: File[]) {
      const pdfs = incoming.filter((f) => f.name.toLowerCase().endsWith(".pdf"));
      setFiles((prev) => {
        const merged = [...prev, ...pdfs];
        return merged.slice(0, MAX_FILES);
      });
    }

    function removeFile(index: number) {
      setFiles((prev) => prev.filter((_, i) => i !== index));
    }

    function handleDrop(e: DragEvent<HTMLDivElement>) {
      e.preventDefault();
      setIsDragging(false);
      addFiles(Array.from(e.dataTransfer.files));
    }

    async function handleSubmit() {
      setDateError("");
      setGlobalError("");
      if (!publishedDate) {
        setDateError("Informe a data de publicação.");
        return;
      }
      if (files.length === 0) {
        setGlobalError("Selecione pelo menos 1 arquivo PDF.");
        return;
      }

      setStatus("uploading");
      try {
        const data = await uploadBatch(files, publishedDate);
        setResult(data);
        setStatus("done");
        setFiles([]);
        setPublishedDate("");
      } catch (err) {
        setGlobalError(err instanceof Error ? err.message : "Erro ao enviar.");
        setStatus("idle");
      }
    }

    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Upload className="h-5 w-5" />
              Upload de Documentos
            </CardTitle>
            <p className="text-sm text-muted-foreground">
              Arraste ou selecione até {MAX_FILES} arquivos PDF
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Drop zone */}
            <div
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              onClick={() => inputRef.current?.click()}
              className={cn(
                "flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed p-8 transition-colors",
                isDragging
                  ? "border-primary bg-primary/5"
                  : "border-muted-foreground/25 hover:border-primary hover:bg-accent"
              )}
            >
              <Upload className="h-8 w-8 text-muted-foreground" />
              <p className="text-sm text-muted-foreground">
                Clique ou arraste PDFs aqui
              </p>
              <p className="text-xs text-muted-foreground">
                {files.length}/{MAX_FILES} arquivos selecionados
              </p>
              <input
                ref={inputRef}
                type="file"
                accept=".pdf"
                multiple
                className="hidden"
                onChange={(e) => addFiles(Array.from(e.target.files ?? []))}
              />
            </div>

            {/* File list */}
            {files.length > 0 && (
              <ul className="space-y-1">
                {files.map((f, i) => (
                  <li
                    key={i}
                    className="flex items-center gap-2 rounded-md bg-muted px-3 py-2 text-sm"
                  >
                    <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="flex-1 truncate">{f.name}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {(f.size / 1024 / 1024).toFixed(1)} MB
                    </span>
                    <button
                      onClick={(e) => { e.stopPropagation(); removeFile(i); }}
                      className="shrink-0 rounded p-0.5 hover:bg-destructive/20 hover:text-destructive"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {/* Date */}
            <div>
              <label className="mb-1.5 block text-sm font-medium">
                Data de publicação *
              </label>
              <Input
                type="date"
                value={publishedDate}
                onChange={(e) => { setPublishedDate(e.target.value); setDateError(""); }}
                className={cn(dateError && "border-destructive")}
              />
              {dateError && (
                <p className="mt-1 text-xs text-destructive">{dateError}</p>
              )}
              <p className="mt-1 text-xs text-muted-foreground">
                Aplica-se a todos os arquivos deste envio
              </p>
            </div>

            {globalError && (
              <p className="text-sm text-destructive">{globalError}</p>
            )}

            <Button
              onClick={handleSubmit}
              disabled={status === "uploading"}
              className="w-full"
            >
              {status === "uploading" ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Processando {files.length} arquivo{files.length > 1 ? "s" : ""}…
                </>
              ) : (
                <>
                  <Upload className="mr-2 h-4 w-4" />
                  Enviar {files.length > 0 ? `${files.length} arquivo${files.length > 1 ? "s" : ""}` : "documentos"}
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        {/* Results */}
        {result && (
          <Card>
            <CardContent className="pt-6 space-y-3">
              <div className="flex items-center gap-2 text-sm font-medium">
                {result.failed === 0 ? (
                  <CheckCircle2 className="h-5 w-5 text-green-600" />
                ) : (
                  <AlertCircle className="h-5 w-5 text-yellow-600" />
                )}
                <span>
                  {result.succeeded}/{result.total} processados com sucesso
                </span>
              </div>
              <ul className="space-y-1">
                {result.results.map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    {r.success ? (
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green-600" />
                    ) : (
                      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
                    )}
                    <div>
                      <span className="font-medium">{r.filename}</span>
                      {r.success && (
                        <span className="ml-2 text-muted-foreground">
                          {r.total_pages}p · {r.total_chunks} chunks
                          {r.was_duplicate && " (duplicata)"}
                        </span>
                      )}
                      {!r.success && (
                        <span className="ml-2 text-destructive">{r.message}</span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}
      </div>
    );
  }
  ```

- [ ] **Step 4: Atualizar `upload/page.tsx` para usar o novo componente**

  ```tsx
  import { BulkUploadForm } from "@/components/upload/BulkUploadForm";

  export default function UploadPage() {
    return (
      <div className="h-full overflow-y-auto p-6">
        <BulkUploadForm />
      </div>
    );
  }
  ```

- [ ] **Step 5: Testar no browser**

  1. Abrir `/upload`
  2. Arrastar 3 PDFs para a drop zone
  3. Verificar lista de arquivos com botão X
  4. Informar data e clicar "Enviar"
  5. Verificar resultado por arquivo

- [ ] **Step 6: Commit final**

  ```bash
  git add frontend/src/components/upload/BulkUploadForm.tsx \
          frontend/src/app/upload/page.tsx \
          frontend/src/lib/api.ts \
          frontend/src/types/index.ts
  git commit -m "feat(upload): bulk upload de até 10 PDFs sem equipment_key"
  ```

---

## Notas

- O formulário antigo `UploadForm.tsx` pode ser mantido ou removido. Recomendado manter por ora caso haja necessidade de upload com metadados específicos.
- O endpoint legado `/upload/document` continua funcionando sem alteração.
- Para documentos sem `equipment_key`, o chat não filtra por equipamento — o RAG busca em todos os documentos, que é o comportamento desejado.
