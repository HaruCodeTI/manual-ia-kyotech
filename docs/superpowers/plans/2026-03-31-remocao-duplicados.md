# Remoção de Documentos Duplicados — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar funcionalidade para Admin escanear e remover documentos duplicados (mesmo SHA-256) na página de upload.

**Architecture:** Dois novos endpoints REST (GET scan + DELETE remove) no router de upload, com funções no repository e storage. Novo componente React `DuplicateScanner` na página de upload. Migration para índice no `source_hash`.

**Tech Stack:** Python/FastAPI, SQLAlchemy (raw SQL), Azure Blob Storage, React/Next.js, TypeScript, Tailwind CSS, lucide-react

---

### Task 1: Migration — índice no source_hash

**Files:**
- Create: `backend/migrations/008_source_hash_index.sql`

- [ ] **Step 1: Criar migration**

```sql
CREATE INDEX IF NOT EXISTS idx_document_versions_source_hash
ON document_versions(source_hash);
```

- [ ] **Step 2: Verificar que a migration é executada**

Run: `cd backend && python -c "import pathlib; files = sorted(pathlib.Path('migrations').glob('*.sql')); print([f.name for f in files])"`
Expected: lista inclui `008_source_hash_index.sql`

- [ ] **Step 3: Commit**

```bash
git add backend/migrations/008_source_hash_index.sql
git commit -m "feat(db): add index on document_versions.source_hash for duplicate scan"
```

---

### Task 2: Storage — função delete_blob

**Files:**
- Modify: `backend/app/services/storage.py` (adicionar após linha 92)
- Test: `backend/tests/unit/test_storage.py`

- [ ] **Step 1: Escrever teste para delete_blob**

Adicionar ao final de `backend/tests/unit/test_storage.py`:

```python
# ── delete_blob ──

@pytest.mark.asyncio
async def test_delete_blob_splits_path_and_deletes(mock_blob_client):
    with patch("app.services.storage.get_blob_client", return_value=mock_blob_client):
        await delete_blob("my-container/some/blob.pdf")

    mock_blob_client.get_blob_client.assert_called_once_with(
        container="my-container", blob="some/blob.pdf"
    )
    mock_blob_client.get_blob_client.return_value.delete_blob.assert_called_once()
```

Atualizar o import no topo do arquivo:

```python
from app.services.storage import upload_pdf, download_blob, generate_signed_url, delete_blob
```

- [ ] **Step 2: Rodar teste para verificar que falha**

Run: `cd backend && python -m pytest tests/unit/test_storage.py::test_delete_blob_splits_path_and_deletes -v`
Expected: FAIL — `ImportError: cannot import name 'delete_blob'`

- [ ] **Step 3: Implementar delete_blob**

Adicionar ao final de `backend/app/services/storage.py` (após a função `generate_signed_url`):

```python
def _delete_blob_sync(container: str, blob_name: str) -> None:
    """Deleta um blob do Azure Blob Storage (execução síncrona)."""
    client = get_blob_client()
    blob_client = client.get_blob_client(container=container, blob=blob_name)
    blob_client.delete_blob()
    logger.info(f"Blob deleted: {container}/{blob_name}")


async def delete_blob(storage_path: str) -> None:
    """
    Deleta um arquivo do Azure Blob Storage pelo storage_path (container/blob).
    """
    parts = storage_path.split("/", 1)
    container_name = parts[0]
    blob_name = parts[1] if len(parts) > 1 else ""

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        partial(_delete_blob_sync, container_name, blob_name),
    )
```

- [ ] **Step 4: Rodar teste para verificar que passa**

Run: `cd backend && python -m pytest tests/unit/test_storage.py::test_delete_blob_splits_path_and_deletes -v`
Expected: PASS

- [ ] **Step 5: Atualizar mock_blob_client no conftest**

O `mock_blob_client` no `conftest.py` já retorna um MagicMock para `get_blob_client().get_blob_client()`, que já aceita `delete_blob()` automaticamente (MagicMock). Nenhuma mudança necessária.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/storage.py backend/tests/unit/test_storage.py
git commit -m "feat(storage): add delete_blob function for Azure Blob Storage"
```

---

### Task 3: Repository — função find_duplicate_groups

**Files:**
- Modify: `backend/app/services/repository.py` (adicionar ao final)
- Test: `backend/tests/unit/test_repository.py`

- [ ] **Step 1: Escrever teste**

Adicionar ao final de `backend/tests/unit/test_repository.py`:

```python
from app.services.repository import find_duplicate_groups


# ── find_duplicate_groups ──

@pytest.mark.asyncio
async def test_find_duplicate_groups_returns_grouped(mock_db, make_mock_result):
    """Deve retornar grupos com keep (mais antigo) e duplicates (demais)."""
    from datetime import date, datetime

    # Simula query de hashes duplicados
    hash_rows = [("hash_abc", 2)]
    # Simula query de versões por hash
    version_rows = [
        (
            "ver-1", "doc-1", "manual.pdf", "frontier-780", "manual",
            date(2025, 1, 15), datetime(2025, 1, 15, 10, 0, 0),
            "container/path1.pdf", 10,
        ),
        (
            "ver-2", "doc-2", "manual.pdf", "frontier-780", "manual",
            date(2025, 3, 1), datetime(2025, 3, 1, 14, 30, 0),
            "container/path2.pdf", 10,
        ),
    ]

    mock_db.execute = AsyncMock(
        side_effect=[
            make_mock_result(rows=hash_rows),
            make_mock_result(rows=version_rows),
        ]
    )

    result = await find_duplicate_groups(mock_db)

    assert result["total_groups"] == 1
    assert result["total_removable"] == 1
    assert result["groups"][0]["keep"]["version_id"] == "ver-1"
    assert len(result["groups"][0]["duplicates"]) == 1
    assert result["groups"][0]["duplicates"][0]["version_id"] == "ver-2"


@pytest.mark.asyncio
async def test_find_duplicate_groups_empty(mock_db, make_mock_result):
    """Sem duplicatas, deve retornar lista vazia."""
    mock_db.execute = AsyncMock(
        return_value=make_mock_result(rows=[])
    )

    result = await find_duplicate_groups(mock_db)

    assert result["total_groups"] == 0
    assert result["total_removable"] == 0
    assert result["groups"] == []
```

- [ ] **Step 2: Rodar teste para verificar que falha**

Run: `cd backend && python -m pytest tests/unit/test_repository.py::test_find_duplicate_groups_returns_grouped -v`
Expected: FAIL — `ImportError: cannot import name 'find_duplicate_groups'`

- [ ] **Step 3: Implementar find_duplicate_groups**

Adicionar ao final de `backend/app/services/repository.py`:

```python
async def find_duplicate_groups(db: AsyncSession) -> Dict:
    """Busca grupos de document_versions com mesmo source_hash."""
    # Passo 1: hashes com mais de uma versão
    dup_result = await db.execute(text("""
        SELECT source_hash, COUNT(*) as cnt
        FROM document_versions
        GROUP BY source_hash
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
    """))
    dup_hashes = dup_result.fetchall()

    if not dup_hashes:
        return {"groups": [], "total_groups": 0, "total_removable": 0}

    groups = []
    total_removable = 0

    for hash_row in dup_hashes:
        source_hash = hash_row[0]

        # Passo 2: buscar versões desse hash, ordenadas por created_at
        ver_result = await db.execute(
            text("""
                SELECT
                    dv.id, dv.document_id, dv.source_filename,
                    d.equipment_key, d.doc_type,
                    dv.published_date, dv.created_at,
                    dv.storage_path,
                    (SELECT COUNT(*) FROM chunks WHERE document_version_id = dv.id) AS chunk_count
                FROM document_versions dv
                JOIN documents d ON dv.document_id = d.id
                WHERE dv.source_hash = :hash
                ORDER BY dv.created_at ASC
            """),
            {"hash": source_hash},
        )
        versions = ver_result.fetchall()

        if len(versions) < 2:
            continue

        def _version_dict(row):
            return {
                "version_id": str(row[0]),
                "document_id": str(row[1]),
                "filename": row[2],
                "equipment_key": row[3],
                "doc_type": row[4],
                "published_date": row[5].isoformat() if row[5] else None,
                "created_at": row[6].isoformat() if row[6] else None,
                "storage_path": row[7],
                "chunk_count": row[8],
            }

        keep = _version_dict(versions[0])
        duplicates = [_version_dict(v) for v in versions[1:]]
        total_removable += len(duplicates)

        groups.append({
            "source_hash": source_hash,
            "keep": keep,
            "duplicates": duplicates,
        })

    return {
        "groups": groups,
        "total_groups": len(groups),
        "total_removable": total_removable,
    }
```

- [ ] **Step 4: Rodar testes para verificar que passam**

Run: `cd backend && python -m pytest tests/unit/test_repository.py::test_find_duplicate_groups_returns_grouped tests/unit/test_repository.py::test_find_duplicate_groups_empty -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/repository.py backend/tests/unit/test_repository.py
git commit -m "feat(repository): add find_duplicate_groups for duplicate detection"
```

---

### Task 4: Repository — função delete_duplicate_versions

**Files:**
- Modify: `backend/app/services/repository.py` (adicionar ao final)
- Test: `backend/tests/unit/test_repository.py`

- [ ] **Step 1: Escrever teste**

Adicionar ao final de `backend/tests/unit/test_repository.py`:

```python
from app.services.repository import delete_duplicate_versions


# ── delete_duplicate_versions ──

@pytest.mark.asyncio
async def test_delete_duplicate_versions(mock_db, make_mock_result):
    """Deve deletar chunks, versão e documento órfão."""
    version_id = "ver-to-delete"

    mock_db.execute = AsyncMock(
        side_effect=[
            # 1. SELECT version info (storage_path, document_id, source_hash)
            make_mock_result(rows=[("container/path.pdf", "doc-1", "hash_abc")]),
            # 2. SELECT count de versões com mesmo hash (validação: > 1)
            make_mock_result(rows=[(2,)]),
            # 3. DELETE chunks
            make_mock_result(),
            # 4. DELETE document_version
            make_mock_result(),
            # 5. SELECT count de versões restantes no document
            make_mock_result(rows=[(0,)]),
            # 6. DELETE document órfão
            make_mock_result(),
        ]
    )

    result = await delete_duplicate_versions(mock_db, [version_id])

    assert result["deleted"] == 1
    assert result["storage_paths"] == ["container/path.pdf"]
    assert result["orphan_documents_deleted"] == 1


@pytest.mark.asyncio
async def test_delete_duplicate_versions_skips_non_duplicate(mock_db, make_mock_result):
    """Se a versão não é mais duplicata (hash único), deve pular."""
    version_id = "ver-unique"

    mock_db.execute = AsyncMock(
        side_effect=[
            # 1. SELECT version info
            make_mock_result(rows=[("container/path.pdf", "doc-1", "hash_abc")]),
            # 2. SELECT count = 1 (não é mais duplicata)
            make_mock_result(rows=[(1,)]),
        ]
    )

    result = await delete_duplicate_versions(mock_db, [version_id])

    assert result["deleted"] == 0
    assert result["skipped"] == 1


@pytest.mark.asyncio
async def test_delete_duplicate_versions_skips_not_found(mock_db, make_mock_result):
    """Se a versão não existe, deve pular."""
    mock_db.execute = AsyncMock(
        return_value=make_mock_result(rows=[])
    )

    result = await delete_duplicate_versions(mock_db, ["nonexistent"])

    assert result["deleted"] == 0
    assert result["skipped"] == 1
```

- [ ] **Step 2: Rodar teste para verificar que falha**

Run: `cd backend && python -m pytest tests/unit/test_repository.py::test_delete_duplicate_versions -v`
Expected: FAIL — `ImportError: cannot import name 'delete_duplicate_versions'`

- [ ] **Step 3: Implementar delete_duplicate_versions**

Adicionar ao final de `backend/app/services/repository.py`:

```python
async def delete_duplicate_versions(
    db: AsyncSession,
    version_ids: List[str],
) -> Dict:
    """
    Deleta versões duplicadas e seus chunks.
    Retorna paths dos blobs a deletar (caller é responsável pelo storage).
    Re-valida que cada versão ainda é duplicata antes de deletar.
    """
    deleted = 0
    skipped = 0
    storage_paths: List[str] = []
    orphan_documents_deleted = 0

    for vid in version_ids:
        # 1. Buscar info da versão
        result = await db.execute(
            text("""
                SELECT storage_path, document_id, source_hash
                FROM document_versions
                WHERE id = :vid
            """),
            {"vid": vid},
        )
        row = result.fetchone()
        if not row:
            skipped += 1
            continue

        storage_path, document_id, source_hash = row[0], str(row[1]), row[2]

        # 2. Re-validar que ainda é duplicata
        count_result = await db.execute(
            text("""
                SELECT COUNT(*) FROM document_versions
                WHERE source_hash = :hash
            """),
            {"hash": source_hash},
        )
        count = count_result.fetchone()[0]
        if count <= 1:
            skipped += 1
            continue

        # 3. Deletar chunks
        await db.execute(
            text("DELETE FROM chunks WHERE document_version_id = :vid"),
            {"vid": vid},
        )

        # 4. Deletar versão
        await db.execute(
            text("DELETE FROM document_versions WHERE id = :vid"),
            {"vid": vid},
        )

        storage_paths.append(storage_path)
        deleted += 1

        # 5. Verificar se o documento ficou órfão
        orphan_result = await db.execute(
            text("""
                SELECT COUNT(*) FROM document_versions
                WHERE document_id = :doc_id
            """),
            {"doc_id": str(document_id)},
        )
        remaining = orphan_result.fetchone()[0]
        if remaining == 0:
            await db.execute(
                text("DELETE FROM documents WHERE id = :doc_id"),
                {"doc_id": str(document_id)},
            )
            orphan_documents_deleted += 1

    return {
        "deleted": deleted,
        "skipped": skipped,
        "storage_paths": storage_paths,
        "orphan_documents_deleted": orphan_documents_deleted,
    }
```

- [ ] **Step 4: Rodar testes para verificar que passam**

Run: `cd backend && python -m pytest tests/unit/test_repository.py -k "delete_duplicate" -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/repository.py backend/tests/unit/test_repository.py
git commit -m "feat(repository): add delete_duplicate_versions with safety re-validation"
```

---

### Task 5: API — endpoints GET e DELETE /upload/duplicates

**Files:**
- Modify: `backend/app/api/upload.py`
- Test: `backend/tests/integration/test_upload_api.py`

- [ ] **Step 1: Escrever testes de integração**

Adicionar ao final de `backend/tests/integration/test_upload_api.py`:

```python
# ── Duplicates API ──

@pytest.mark.anyio
async def test_get_duplicates_returns_groups(async_client):
    mock_groups = {
        "groups": [
            {
                "source_hash": "abc123",
                "keep": {
                    "version_id": "ver-1",
                    "document_id": "doc-1",
                    "filename": "manual.pdf",
                    "equipment_key": "frontier-780",
                    "doc_type": "manual",
                    "published_date": "2025-01-15",
                    "created_at": "2025-01-15T10:00:00",
                    "storage_path": "container/path1.pdf",
                    "chunk_count": 10,
                },
                "duplicates": [
                    {
                        "version_id": "ver-2",
                        "document_id": "doc-2",
                        "filename": "manual.pdf",
                        "equipment_key": "frontier-780",
                        "doc_type": "manual",
                        "published_date": "2025-03-01",
                        "created_at": "2025-03-01T14:30:00",
                        "storage_path": "container/path2.pdf",
                        "chunk_count": 10,
                    }
                ],
            }
        ],
        "total_groups": 1,
        "total_removable": 1,
    }

    with patch(
        "app.api.upload.repository.find_duplicate_groups",
        new_callable=AsyncMock,
        return_value=mock_groups,
    ):
        resp = await async_client.get("/api/v1/upload/duplicates")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_groups"] == 1
    assert data["total_removable"] == 1
    assert data["groups"][0]["keep"]["version_id"] == "ver-1"


@pytest.mark.anyio
async def test_get_duplicates_empty(async_client):
    mock_groups = {"groups": [], "total_groups": 0, "total_removable": 0}

    with patch(
        "app.api.upload.repository.find_duplicate_groups",
        new_callable=AsyncMock,
        return_value=mock_groups,
    ):
        resp = await async_client.get("/api/v1/upload/duplicates")

    assert resp.status_code == 200
    assert resp.json()["total_groups"] == 0


@pytest.mark.anyio
async def test_technician_cannot_get_duplicates(async_client_tech):
    resp = await async_client_tech.get("/api/v1/upload/duplicates")
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_delete_duplicates_success(async_client):
    delete_result = {
        "deleted": 2,
        "skipped": 0,
        "storage_paths": ["container/a.pdf", "container/b.pdf"],
        "orphan_documents_deleted": 1,
    }

    with patch(
        "app.api.upload.repository.delete_duplicate_versions",
        new_callable=AsyncMock,
        return_value=delete_result,
    ) as mock_delete, \
    patch(
        "app.api.upload.delete_blob",
        new_callable=AsyncMock,
    ) as mock_blob_delete, \
    patch(
        "app.api.upload.invalidate_cache",
        new_callable=AsyncMock,
    ):
        resp = await async_client.request(
            "DELETE",
            "/api/v1/upload/duplicates",
            json={"version_ids": ["ver-1", "ver-2"]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] == 2
    assert mock_blob_delete.call_count == 2


@pytest.mark.anyio
async def test_delete_duplicates_empty_list(async_client):
    resp = await async_client.request(
        "DELETE",
        "/api/v1/upload/duplicates",
        json={"version_ids": []},
    )
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_technician_cannot_delete_duplicates(async_client_tech):
    resp = await async_client_tech.request(
        "DELETE",
        "/api/v1/upload/duplicates",
        json={"version_ids": ["ver-1"]},
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Rodar testes para verificar que falham**

Run: `cd backend && python -m pytest tests/integration/test_upload_api.py -k "duplicate" -v`
Expected: FAIL — 404 (endpoints não existem)

- [ ] **Step 3: Implementar endpoints**

Adicionar ao topo de `backend/app/api/upload.py`, nos imports:

```python
from app.services.storage import delete_blob
from app.services.semantic_cache import invalidate_cache
```

Adicionar ao final de `backend/app/api/upload.py`:

```python
class DeleteDuplicatesRequest(BaseModel):
    version_ids: list[str]


class DeleteDuplicatesResponse(BaseModel):
    deleted: int
    skipped: int
    orphan_documents_deleted: int
    message: str


@router.get("/duplicates")
@limiter.limit("10/minute")
async def get_duplicates(
    request: Request,
    _user: CurrentUser = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    return await repository.find_duplicate_groups(db)


@router.delete("/duplicates", response_model=DeleteDuplicatesResponse)
@limiter.limit("5/minute")
async def delete_duplicates(
    request: Request,
    body: DeleteDuplicatesRequest,
    _user: CurrentUser = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    if not body.version_ids:
        raise HTTPException(status_code=400, detail="Nenhuma versão informada.")

    result = await repository.delete_duplicate_versions(db, body.version_ids)
    await db.commit()

    # Deletar blobs do Azure (fora da transação SQL)
    for path in result["storage_paths"]:
        try:
            await delete_blob(path)
        except Exception as e:
            logger.warning(f"Falha ao deletar blob {path}: {e}")

    # Invalidar cache semântico
    try:
        await invalidate_cache(db)
    except Exception as e:
        logger.warning(f"Falha ao invalidar cache (não crítico): {e}")

    return DeleteDuplicatesResponse(
        deleted=result["deleted"],
        skipped=result["skipped"],
        orphan_documents_deleted=result["orphan_documents_deleted"],
        message=f"{result['deleted']} duplicata(s) removida(s).",
    )
```

Adicionar import de `logging` (já existe no topo) e instanciar logger se não existir:

```python
import logging
logger = logging.getLogger(__name__)
```

- [ ] **Step 4: Rodar testes para verificar que passam**

Run: `cd backend && python -m pytest tests/integration/test_upload_api.py -k "duplicate" -v`
Expected: 6 PASSED

- [ ] **Step 5: Rodar todos os testes do backend para verificar que nada quebrou**

Run: `cd backend && python -m pytest tests/ -v`
Expected: ALL PASSED

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/upload.py backend/tests/integration/test_upload_api.py
git commit -m "feat(api): add GET and DELETE /upload/duplicates endpoints"
```

---

### Task 6: Frontend — tipos e funções de API

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Adicionar tipos**

Adicionar ao final de `frontend/src/types/index.ts`:

```typescript
export interface DuplicateVersionInfo {
  version_id: string;
  document_id: string;
  filename: string;
  equipment_key: string | null;
  doc_type: string | null;
  published_date: string | null;
  created_at: string | null;
  storage_path: string;
  chunk_count: number;
}

export interface DuplicateGroup {
  source_hash: string;
  keep: DuplicateVersionInfo;
  duplicates: DuplicateVersionInfo[];
}

export interface DuplicateScanResponse {
  groups: DuplicateGroup[];
  total_groups: number;
  total_removable: number;
}

export interface DeleteDuplicatesResponse {
  deleted: number;
  skipped: number;
  orphan_documents_deleted: number;
  message: string;
}
```

- [ ] **Step 2: Adicionar funções de API**

Adicionar ao final de `frontend/src/lib/api.ts`:

```typescript
// --- Duplicates API ---

export async function scanDuplicates(): Promise<DuplicateScanResponse> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/upload/duplicates`,
      { headers: auth },
      30_000
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export async function deleteDuplicates(
  versionIds: string[]
): Promise<DeleteDuplicatesResponse> {
  const auth = await authHeaders();
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${API_BASE}/api/v1/upload/duplicates`,
      {
        method: "DELETE",
        headers: { "Content-Type": "application/json", ...auth },
        body: JSON.stringify({ version_ids: versionIds }),
      },
      60_000
    );
  } catch (err) {
    handleFetchError(err);
  }
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}
```

Adicionar ao import no topo de `frontend/src/lib/api.ts`:

```typescript
import type { ChatResponse, UploadResponse, StatsResponse, UsageStatsResponse, ChatSession, FeedbackRating, DuplicateScanResponse, DeleteDuplicatesResponse } from "@/types";
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts
git commit -m "feat(frontend): add types and API functions for duplicate management"
```

---

### Task 7: Frontend — componente DuplicateScanner

**Files:**
- Create: `frontend/src/components/upload/DuplicateScanner.tsx`
- Modify: `frontend/src/app/upload/page.tsx`

- [ ] **Step 1: Criar componente DuplicateScanner**

```tsx
// frontend/src/components/upload/DuplicateScanner.tsx
"use client";

import { useState } from "react";
import { scanDuplicates, deleteDuplicates } from "@/lib/api";
import type { DuplicateGroup, DuplicateScanResponse } from "@/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Search, Trash2, Loader2, CheckCircle2, AlertCircle, FileText } from "lucide-react";

type Phase = "idle" | "scanning" | "results" | "deleting" | "done" | "error";

export function DuplicateScanner() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [scanResult, setScanResult] = useState<DuplicateScanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);

  async function handleScan() {
    setPhase("scanning");
    setError(null);
    setScanResult(null);

    try {
      const result = await scanDuplicates();
      setScanResult(result);
      setPhase(result.total_groups > 0 ? "results" : "done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao buscar duplicatas.");
      setPhase("error");
    }
  }

  async function handleDelete() {
    if (!scanResult) return;
    setShowConfirm(false);
    setPhase("deleting");

    const versionIds = scanResult.groups.flatMap((g) =>
      g.duplicates.map((d) => d.version_id)
    );

    try {
      const result = await deleteDuplicates(versionIds);
      setDeleteMessage(result.message);
      setScanResult(null);
      setPhase("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao remover duplicatas.");
      setPhase("error");
    }
  }

  function handleReset() {
    setPhase("idle");
    setScanResult(null);
    setError(null);
    setDeleteMessage(null);
    setShowConfirm(false);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Search className="h-4 w-4" />
          Duplicados
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Idle / Error — botão de scan */}
        {(phase === "idle" || phase === "error") && (
          <div className="space-y-2">
            <Button variant="outline" className="w-full" onClick={handleScan}>
              <Search className="mr-2 h-4 w-4" />
              Buscar duplicados
            </Button>
            {phase === "error" && error && (
              <div className="flex items-center gap-2 rounded-lg border border-destructive p-3">
                <AlertCircle className="h-4 w-4 shrink-0 text-destructive" />
                <p className="flex-1 text-sm text-destructive">{error}</p>
              </div>
            )}
          </div>
        )}

        {/* Scanning */}
        {phase === "scanning" && (
          <Button variant="outline" className="w-full" disabled>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Buscando...
          </Button>
        )}

        {/* Results */}
        {phase === "results" && scanResult && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 rounded-lg border border-yellow-500 p-3">
              <AlertCircle className="h-4 w-4 shrink-0 text-yellow-500" />
              <p className="flex-1 text-sm font-medium">
                {scanResult.total_groups} grupo{scanResult.total_groups > 1 ? "s" : ""} de
                duplicatas — {scanResult.total_removable} arquivo{scanResult.total_removable > 1 ? "s" : ""}{" "}
                {scanResult.total_removable > 1 ? "podem" : "pode"} ser removido{scanResult.total_removable > 1 ? "s" : ""}
              </p>
            </div>

            {scanResult.groups.map((group) => (
              <DuplicateGroupCard key={group.source_hash} group={group} />
            ))}

            {!showConfirm ? (
              <Button
                variant="destructive"
                className="w-full"
                onClick={() => setShowConfirm(true)}
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Remover duplicados
              </Button>
            ) : (
              <div className="space-y-2 rounded-lg border border-destructive p-3">
                <p className="text-sm font-medium">
                  Tem certeza? <strong>{scanResult.total_removable} arquivo{scanResult.total_removable > 1 ? "s" : ""}</strong>{" "}
                  {scanResult.total_removable > 1 ? "serão removidos" : "será removido"} permanentemente,
                  incluindo chunks e arquivos de armazenamento. Esta ação não pode ser desfeita.
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={handleDelete}
                  >
                    Confirmar remoção
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowConfirm(false)}
                  >
                    Cancelar
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Deleting */}
        {phase === "deleting" && (
          <Button variant="destructive" className="w-full" disabled>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Removendo...
          </Button>
        )}

        {/* Done */}
        {phase === "done" && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 rounded-lg border border-green-500 p-3">
              <CheckCircle2 className="h-4 w-4 shrink-0 text-green-500" />
              <p className="flex-1 text-sm font-medium">
                {deleteMessage || "Nenhuma duplicata encontrada."}
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={handleReset}>
              Nova busca
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function DuplicateGroupCard({ group }: { group: DuplicateGroup }) {
  return (
    <div className="rounded-lg border p-3 space-y-2">
      {/* Keep */}
      <div className="flex items-start gap-2">
        <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium truncate">{group.keep.filename}</span>
            <Badge variant="outline" className="border-green-500 text-green-600 text-xs shrink-0">
              Manter
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            {group.keep.equipment_key || "Sem equipamento"} · {group.keep.doc_type || "Sem tipo"} · {group.keep.published_date || "—"} · {group.keep.chunk_count} chunks
          </p>
        </div>
      </div>

      {/* Duplicates */}
      {group.duplicates.map((dup) => (
        <div key={dup.version_id} className="flex items-start gap-2 ml-2">
          <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm truncate">{dup.filename}</span>
              <Badge variant="outline" className="border-red-500 text-red-600 text-xs shrink-0">
                Remover
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              {dup.equipment_key || "Sem equipamento"} · {dup.doc_type || "Sem tipo"} · {dup.published_date || "—"} · {dup.chunk_count} chunks
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Atualizar página de upload**

Substituir conteúdo de `frontend/src/app/upload/page.tsx`:

```tsx
import { BulkUploadForm } from "@/components/upload/BulkUploadForm";
import { DuplicateScanner } from "@/components/upload/DuplicateScanner";

export default function UploadPage() {
  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-xl space-y-6">
        <BulkUploadForm />
        <DuplicateScanner />
      </div>
    </div>
  );
}
```

Nota: `BulkUploadForm` tem sua própria wrapper `<div className="mx-auto max-w-xl space-y-6">`. Ao mover o wrapper para a page, precisamos remover o wrapper de dentro do `BulkUploadForm`. Editar `frontend/src/components/upload/BulkUploadForm.tsx` — trocar a div wrapper de retorno:

De:
```tsx
return (
    <div className="mx-auto max-w-xl space-y-6">
      <Card>
```

Para:
```tsx
return (
    <Card>
```

E remover o `</div>` de fechamento correspondente no final do componente (última linha antes do `}`).

- [ ] **Step 3: Verificar que compila**

Run: `cd frontend && npx next build 2>&1 | tail -20`
Expected: Build com sucesso, sem erros de tipo

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/upload/DuplicateScanner.tsx frontend/src/app/upload/page.tsx frontend/src/components/upload/BulkUploadForm.tsx
git commit -m "feat(frontend): add DuplicateScanner component to upload page"
```

---

### Task 8: Teste end-to-end manual

- [ ] **Step 1: Rodar todos os testes do backend**

Run: `cd backend && python -m pytest tests/ -v`
Expected: ALL PASSED

- [ ] **Step 2: Verificar build do frontend**

Run: `cd frontend && npx next build 2>&1 | tail -20`
Expected: Build com sucesso

- [ ] **Step 3: Commit final (se houver ajustes)**

```bash
git add -A
git commit -m "chore: final adjustments for duplicate removal feature"
```
