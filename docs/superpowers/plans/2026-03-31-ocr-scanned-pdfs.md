# OCR para PDFs Escaneados — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que PDFs escaneados (imagem) sejam ingeridos automaticamente usando OCR via Azure Document Intelligence, e melhorar a resiliência do batch upload com retry para erros transientes.

**Architecture:** O `pdf_extractor.py` ganha fallback assíncrono: PyMuPDF primeiro (rápido, grátis), Document Intelligence para páginas sem texto. Um novo serviço `ocr.py` encapsula a API. O `IngestionResult` ganha campo `retryable` para o frontend oferecer retry seletivo.

**Tech Stack:** Azure Document Intelligence (prebuilt-read), azure-ai-documentintelligence SDK, Python asyncio, React/TypeScript frontend

**Spec:** `docs/superpowers/specs/2026-03-31-ocr-scanned-pdfs-design.md`

---

## File Structure

| Arquivo | Ação | Responsabilidade |
|---------|------|-----------------|
| `backend/app/services/ocr.py` | **Criar** | Chamada ao Azure Document Intelligence |
| `backend/tests/unit/test_ocr.py` | **Criar** | Testes do serviço OCR |
| `backend/app/services/pdf_extractor.py` | Modificar | Fallback para OCR, tornar async |
| `backend/tests/unit/test_pdf_extractor.py` | Modificar | Testes para o novo fluxo async + OCR |
| `backend/app/services/ingestion.py` | Modificar | await no extractor, campo retryable |
| `backend/app/core/config.py` | Modificar | Variáveis Document Intelligence |
| `backend/app/api/upload.py` | Modificar | Retornar retryable na response |
| `backend/requirements.txt` | Modificar | azure-ai-documentintelligence |
| `frontend/src/types/index.ts` | Modificar | retryable no UploadResponse |
| `frontend/src/components/upload/FileProgressItem.tsx` | Modificar | Botão retry |
| `frontend/src/components/upload/BulkUploadForm.tsx` | Modificar | Lógica retry automático |

---

### Task 1: Provisionar Azure Document Intelligence

**Files:** Nenhum arquivo de código — infra via CLI.

- [ ] **Step 1: Identificar resource group**

```bash
az cognitiveservices account show --name aoai-kyotech --query "resourceGroup" -o tsv
```

- [ ] **Step 2: Criar recurso Document Intelligence**

```bash
az cognitiveservices account create \
  --name docint-kyotech \
  --resource-group <RESOURCE_GROUP_DO_STEP_1> \
  --kind FormRecognizer \
  --sku S0 \
  --location eastus2 \
  --yes
```

- [ ] **Step 3: Obter endpoint e chave**

```bash
az cognitiveservices account show --name docint-kyotech --resource-group <RG> --query "properties.endpoint" -o tsv
az cognitiveservices account keys list --name docint-kyotech --resource-group <RG> --query "key1" -o tsv
```

- [ ] **Step 4: Adicionar ao config e requirements**

Em `backend/app/core/config.py`, adicionar dentro da classe `Settings` (após linha 23, depois de `azure_storage_container_processed`):

```python
    azure_document_intelligence_endpoint: str = ""
    azure_document_intelligence_key: str = ""
```

Em `backend/requirements.txt`, adicionar após a linha `openai>=1.59.2`:

```
azure-ai-documentintelligence>=1.0.0
```

- [ ] **Step 5: Configurar .env local**

Adicionar ao `.env` do backend:

```
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=<endpoint_do_step_3>
AZURE_DOCUMENT_INTELLIGENCE_KEY=<key_do_step_3>
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/config.py backend/requirements.txt
git commit -m "chore: add Azure Document Intelligence config and dependency"
```

---

### Task 2: Serviço OCR (`ocr.py`)

**Files:**
- Create: `backend/app/services/ocr.py`
- Create: `backend/tests/unit/test_ocr.py`

- [ ] **Step 1: Escrever testes do serviço OCR**

Criar `backend/tests/unit/test_ocr.py`:

```python
"""Tests for app.services.ocr — Azure Document Intelligence OCR."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.pdf_extractor import PageContent


class TestOcrPdf:
    @pytest.mark.anyio
    async def test_returns_page_contents_from_ocr(self):
        """OCR should return PageContent list with text from each page."""
        from app.services.ocr import ocr_pdf

        # Mock do resultado do Document Intelligence
        mock_page_1 = MagicMock()
        mock_page_1.page_number = 1
        mock_line_1a = MagicMock()
        mock_line_1a.content = "Texto da página 1 linha 1"
        mock_line_1b = MagicMock()
        mock_line_1b.content = "Texto da página 1 linha 2"
        mock_page_1.lines = [mock_line_1a, mock_line_1b]

        mock_page_2 = MagicMock()
        mock_page_2.page_number = 2
        mock_line_2 = MagicMock()
        mock_line_2.content = "Texto da página 2"
        mock_page_2.lines = [mock_line_2]

        mock_result = MagicMock()
        mock_result.pages = [mock_page_1, mock_page_2]

        mock_poller = AsyncMock()
        mock_poller.result.return_value = mock_result

        mock_client = MagicMock()
        mock_client.begin_analyze_document = AsyncMock(return_value=mock_poller)
        mock_client.close = AsyncMock()

        with patch("app.services.ocr._get_client", return_value=mock_client):
            pages = await ocr_pdf(b"fake-pdf-bytes")

        assert len(pages) == 2
        assert pages[0].page_number == 1
        assert "Texto da página 1 linha 1" in pages[0].text
        assert "Texto da página 1 linha 2" in pages[0].text
        assert pages[1].page_number == 2
        assert pages[1].text == "Texto da página 2"

    @pytest.mark.anyio
    async def test_filters_by_page_numbers(self):
        """When page_numbers is provided, only return those pages."""
        from app.services.ocr import ocr_pdf

        mock_page_1 = MagicMock()
        mock_page_1.page_number = 1
        mock_page_1.lines = [MagicMock(content="Page 1")]

        mock_page_2 = MagicMock()
        mock_page_2.page_number = 2
        mock_page_2.lines = [MagicMock(content="Page 2")]

        mock_page_3 = MagicMock()
        mock_page_3.page_number = 3
        mock_page_3.lines = [MagicMock(content="Page 3")]

        mock_result = MagicMock()
        mock_result.pages = [mock_page_1, mock_page_2, mock_page_3]

        mock_poller = AsyncMock()
        mock_poller.result.return_value = mock_result

        mock_client = MagicMock()
        mock_client.begin_analyze_document = AsyncMock(return_value=mock_poller)
        mock_client.close = AsyncMock()

        with patch("app.services.ocr._get_client", return_value=mock_client):
            pages = await ocr_pdf(b"fake-pdf-bytes", page_numbers=[1, 3])

        assert len(pages) == 2
        assert pages[0].page_number == 1
        assert pages[1].page_number == 3

    @pytest.mark.anyio
    async def test_returns_empty_for_pages_without_lines(self):
        """Pages with no lines (blank scans) should be skipped."""
        from app.services.ocr import ocr_pdf

        mock_page = MagicMock()
        mock_page.page_number = 1
        mock_page.lines = []

        mock_result = MagicMock()
        mock_result.pages = [mock_page]

        mock_poller = AsyncMock()
        mock_poller.result.return_value = mock_result

        mock_client = MagicMock()
        mock_client.begin_analyze_document = AsyncMock(return_value=mock_poller)
        mock_client.close = AsyncMock()

        with patch("app.services.ocr._get_client", return_value=mock_client):
            pages = await ocr_pdf(b"fake-pdf-bytes")

        assert len(pages) == 0

    @pytest.mark.anyio
    async def test_raises_on_missing_config(self):
        """Should raise ValueError when endpoint/key not configured."""
        from app.services.ocr import ocr_pdf

        with patch("app.services.ocr.settings") as mock_settings:
            mock_settings.azure_document_intelligence_endpoint = ""
            mock_settings.azure_document_intelligence_key = ""

            with pytest.raises(ValueError, match="Document Intelligence não configurado"):
                await ocr_pdf(b"fake-pdf-bytes")
```

- [ ] **Step 2: Rodar testes para verificar que falham**

```bash
cd backend && python -m pytest tests/unit/test_ocr.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.ocr'`

- [ ] **Step 3: Implementar `ocr.py`**

Criar `backend/app/services/ocr.py`:

```python
"""
Kyotech AI — Serviço de OCR via Azure Document Intelligence
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Optional

from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError

from app.core.config import settings
from app.services.pdf_extractor import PageContent

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 120
_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds


def _get_client() -> DocumentIntelligenceClient:
    if not settings.azure_document_intelligence_endpoint or not settings.azure_document_intelligence_key:
        raise ValueError(
            "Document Intelligence não configurado. "
            "Defina AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT e AZURE_DOCUMENT_INTELLIGENCE_KEY."
        )
    return DocumentIntelligenceClient(
        endpoint=settings.azure_document_intelligence_endpoint,
        credential=AzureKeyCredential(settings.azure_document_intelligence_key),
    )


async def ocr_pdf(
    file_bytes: bytes,
    page_numbers: Optional[List[int]] = None,
) -> List[PageContent]:
    """
    Extrai texto de PDF escaneado via Azure Document Intelligence (prebuilt-read).

    Args:
        file_bytes: bytes do PDF
        page_numbers: se fornecido, filtra apenas essas páginas do resultado

    Returns:
        Lista de PageContent com texto extraído por OCR
    """
    client = _get_client()
    start = time.monotonic()

    try:
        result = await _analyze_with_retry(client, file_bytes)
    finally:
        await client.close()

    elapsed = round(time.monotonic() - start, 1)
    page_filter = set(page_numbers) if page_numbers else None

    pages: List[PageContent] = []
    for page in result.pages:
        if page_filter and page.page_number not in page_filter:
            continue
        if not page.lines:
            continue
        text = "\n".join(line.content for line in page.lines)
        pages.append(PageContent(page_number=page.page_number, text=text))

    logger.info(f"OCR completo: {len(pages)} páginas processadas em {elapsed}s")
    return pages


async def _analyze_with_retry(client: DocumentIntelligenceClient, file_bytes: bytes):
    """Chama begin_analyze_document com retry para erros transientes (429, 503)."""
    last_error = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            poller = await client.begin_analyze_document(
                "prebuilt-read",
                analyze_request=file_bytes,
                content_type="application/pdf",
            )
            return await poller.result()
        except HttpResponseError as e:
            last_error = e
            if e.status_code in (429, 503) and attempt < _MAX_RETRIES:
                wait = _BACKOFF_BASE ** attempt
                logger.warning(f"OCR retry {attempt}/{_MAX_RETRIES} (status {e.status_code}), aguardando {wait}s")
                await asyncio.sleep(wait)
            else:
                raise
    raise last_error  # unreachable, but satisfies type checker
```

- [ ] **Step 4: Rodar testes para verificar que passam**

```bash
cd backend && python -m pytest tests/unit/test_ocr.py -v
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ocr.py backend/tests/unit/test_ocr.py
git commit -m "feat: add OCR service via Azure Document Intelligence"
```

---

### Task 3: Tornar `pdf_extractor.py` async com fallback OCR

**Files:**
- Modify: `backend/app/services/pdf_extractor.py`
- Modify: `backend/tests/unit/test_pdf_extractor.py`

- [ ] **Step 1: Atualizar testes existentes para async e adicionar testes de fallback**

Substituir todo o conteúdo de `backend/tests/unit/test_pdf_extractor.py`:

```python
"""Tests for app.services.pdf_extractor — compute_file_hash and extract_text_from_pdf."""
from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import pytest

from app.services.pdf_extractor import (
    PDFExtraction,
    PageContent,
    compute_file_hash,
    extract_text_from_pdf,
)


class TestComputeFileHash:
    def test_sha256_correctness(self):
        data = b"hello world"
        expected = hashlib.sha256(data).hexdigest()
        assert compute_file_hash(data) == expected

    def test_different_data_different_hash(self):
        assert compute_file_hash(b"a") != compute_file_hash(b"b")

    def test_deterministic(self):
        data = b"same content"
        assert compute_file_hash(data) == compute_file_hash(data)


class TestExtractTextFromPdf:
    @pytest.mark.anyio
    async def test_extracts_text(self, sample_pdf_bytes):
        result = await extract_text_from_pdf(sample_pdf_bytes, "test.pdf")
        assert isinstance(result, PDFExtraction)
        assert result.filename == "test.pdf"
        assert len(result.pages) == 2
        assert result.total_pages == 2

    @pytest.mark.anyio
    async def test_pages_have_correct_numbers(self, sample_pdf_bytes):
        result = await extract_text_from_pdf(sample_pdf_bytes, "test.pdf")
        assert result.pages[0].page_number == 1
        assert result.pages[1].page_number == 2

    @pytest.mark.anyio
    async def test_pages_contain_text(self, sample_pdf_bytes):
        result = await extract_text_from_pdf(sample_pdf_bytes, "test.pdf")
        assert "Page 1" in result.pages[0].text
        assert "sample text" in result.pages[0].text

    @pytest.mark.anyio
    async def test_source_hash_matches(self, sample_pdf_bytes):
        result = await extract_text_from_pdf(sample_pdf_bytes, "test.pdf")
        assert result.source_hash == compute_file_hash(sample_pdf_bytes)

    @pytest.mark.anyio
    async def test_raises_on_invalid_bytes(self):
        with pytest.raises(Exception):
            await extract_text_from_pdf(b"not a pdf", "bad.pdf")


class TestExtractTextFallbackOcr:
    @pytest.mark.anyio
    async def test_falls_back_to_ocr_for_blank_pdf(self):
        """A PDF with no text should trigger OCR fallback."""
        import fitz

        doc = fitz.open()
        doc.new_page(width=595, height=842)
        pdf_bytes = doc.tobytes()
        doc.close()

        ocr_pages = [PageContent(page_number=1, text="OCR extracted text")]
        with patch("app.services.pdf_extractor.ocr_pdf", new_callable=AsyncMock, return_value=ocr_pages):
            result = await extract_text_from_pdf(pdf_bytes, "scanned.pdf")

        assert len(result.pages) == 1
        assert result.pages[0].text == "OCR extracted text"
        assert result.total_pages == 1

    @pytest.mark.anyio
    async def test_ocr_only_for_blank_pages_in_mixed_pdf(self):
        """Mixed PDF: digital pages kept, OCR only called for blank pages."""
        import fitz

        doc = fitz.open()
        # Page 1: has text
        p1 = doc.new_page(width=595, height=842)
        p1.insert_text(fitz.Point(72, 72), "Digital text page 1", fontsize=12)
        # Page 2: blank (scanned)
        doc.new_page(width=595, height=842)
        pdf_bytes = doc.tobytes()
        doc.close()

        ocr_pages = [PageContent(page_number=2, text="OCR text page 2")]
        mock_ocr = AsyncMock(return_value=ocr_pages)
        with patch("app.services.pdf_extractor.ocr_pdf", mock_ocr):
            result = await extract_text_from_pdf(pdf_bytes, "mixed.pdf")

        # Verifica que OCR foi chamado apenas para página 2
        mock_ocr.assert_called_once()
        call_kwargs = mock_ocr.call_args
        assert call_kwargs[1]["page_numbers"] == [2]

        assert len(result.pages) == 2
        assert "Digital text" in result.pages[0].text
        assert "OCR text" in result.pages[1].text

    @pytest.mark.anyio
    async def test_raises_if_ocr_also_returns_empty(self):
        """If OCR also finds nothing, should still raise ValueError."""
        import fitz

        doc = fitz.open()
        doc.new_page(width=595, height=842)
        pdf_bytes = doc.tobytes()
        doc.close()

        with patch("app.services.pdf_extractor.ocr_pdf", new_callable=AsyncMock, return_value=[]):
            with pytest.raises(ValueError, match="não contém texto extraível mesmo após OCR"):
                await extract_text_from_pdf(pdf_bytes, "empty.pdf")

    @pytest.mark.anyio
    async def test_skips_ocr_when_all_pages_have_text(self, sample_pdf_bytes):
        """Should NOT call OCR when all pages have text."""
        mock_ocr = AsyncMock()
        with patch("app.services.pdf_extractor.ocr_pdf", mock_ocr):
            result = await extract_text_from_pdf(sample_pdf_bytes, "digital.pdf")

        mock_ocr.assert_not_called()
        assert len(result.pages) == 2
```

- [ ] **Step 2: Rodar testes para verificar que falham**

```bash
cd backend && python -m pytest tests/unit/test_pdf_extractor.py -v
```

Expected: FAIL — `extract_text_from_pdf` não é async, testes novos falham.

- [ ] **Step 3: Implementar fallback OCR no `pdf_extractor.py`**

Substituir todo o conteúdo de `backend/app/services/pdf_extractor.py`:

```python
"""
Kyotech AI — Serviço de Extração de Texto de PDF
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


@dataclass
class PageContent:
    page_number: int
    text: str


@dataclass
class PDFExtraction:
    filename: str
    source_hash: str
    total_pages: int
    pages: List[PageContent]


def compute_file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def _extract_with_pymupdf(file_bytes: bytes) -> Tuple[List[PageContent], int]:
    """Extrai texto via PyMuPDF (rápido, sem custo). Retorna (pages, total_pages)."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages: List[PageContent] = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text").strip()
        if text:
            pages.append(PageContent(page_number=page_num + 1, text=text))

    total_pages = len(doc)
    doc.close()
    return pages, total_pages


async def extract_text_from_pdf(file_bytes: bytes, filename: str) -> PDFExtraction:
    source_hash = compute_file_hash(file_bytes)

    # 1. Tenta PyMuPDF (rápido, sem custo)
    pages, total_pages = _extract_with_pymupdf(file_bytes)

    # 2. Identifica páginas sem texto
    pages_with_text = {p.page_number for p in pages}
    pages_without_text = [i + 1 for i in range(total_pages) if (i + 1) not in pages_with_text]

    # 3. Se há páginas sem texto, fallback para OCR
    if pages_without_text:
        logger.info(
            f"PDF escaneado detectado ({len(pages_without_text)}/{total_pages} "
            f"páginas sem texto), usando OCR via Document Intelligence"
        )
        from app.services.ocr import ocr_pdf

        ocr_pages = await ocr_pdf(file_bytes, page_numbers=pages_without_text)
        pages.extend(ocr_pages)
        pages.sort(key=lambda p: p.page_number)

    # 4. Se ainda sem texto após OCR, erro
    if not pages:
        raise ValueError(
            f"PDF '{filename}' não contém texto extraível mesmo após OCR."
        )

    return PDFExtraction(
        filename=filename,
        source_hash=source_hash,
        total_pages=total_pages,
        pages=pages,
    )
```

- [ ] **Step 4: Rodar testes para verificar que passam**

```bash
cd backend && python -m pytest tests/unit/test_pdf_extractor.py tests/unit/test_ocr.py -v
```

Expected: Todos os testes PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/pdf_extractor.py backend/tests/unit/test_pdf_extractor.py
git commit -m "feat: add OCR fallback for scanned PDFs in text extraction"
```

---

### Task 4: Atualizar `ingestion.py` com await e campo retryable

**Files:**
- Modify: `backend/app/services/ingestion.py`

- [ ] **Step 1: Atualizar `ingestion.py`**

No `backend/app/services/ingestion.py`, fazer 3 alterações:

**Alteração 1** — Adicionar `retryable` ao `IngestionResult` (linha 28, após `was_duplicate`):

```python
@dataclass
class IngestionResult:
    success: bool
    message: str
    document_id: Optional[str] = None
    version_id: Optional[str] = None
    total_pages: int = 0
    total_chunks: int = 0
    was_duplicate: bool = False
    retryable: bool = False
```

**Alteração 2** — Adicionar `await` na chamada do extrator (linha 49):

Mudar:
```python
        extraction = extract_text_from_pdf(file_bytes, filename)
```
Para:
```python
        extraction = await extract_text_from_pdf(file_bytes, filename)
```

**Alteração 3** — No `except Exception` (linha ~133), marcar como retryable para erros transientes:

Mudar:
```python
    except Exception as e:
        logger.error(f"Erro inesperado: {e}", exc_info=True)
        await db.rollback()
        return IngestionResult(
            success=False,
            message=f"Erro ao processar '{filename}'. Tente novamente ou contate o suporte.",
        )
```
Para:
```python
    except Exception as e:
        logger.error(f"Erro inesperado: {e}", exc_info=True)
        await db.rollback()
        retryable = _is_retryable(e)
        return IngestionResult(
            success=False,
            message=f"Erro ao processar '{filename}'. Tente novamente ou contate o suporte.",
            retryable=retryable,
        )
```

**Adicionar** a função helper no topo do arquivo (antes de `ingest_document`):

```python
def _is_retryable(error: Exception) -> bool:
    """Erros transientes que podem ser resolvidos com retry."""
    from azure.core.exceptions import HttpResponseError
    if isinstance(error, HttpResponseError) and error.status_code in (429, 503):
        return True
    if isinstance(error, (TimeoutError, ConnectionError, OSError)):
        return True
    return False
```

- [ ] **Step 2: Rodar testes existentes**

```bash
cd backend && python -m pytest tests/ -v --timeout=30
```

Expected: Todos os testes PASS (os testes de integração mockam `ingest_document`, então a mudança de assinatura não os afeta diretamente)

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/ingestion.py
git commit -m "feat: add await for async extractor and retryable field to IngestionResult"
```

---

### Task 5: Atualizar API de upload com retryable

**Files:**
- Modify: `backend/app/api/upload.py`

- [ ] **Step 1: Adicionar `retryable` ao `UploadResponse`**

Em `backend/app/api/upload.py`, adicionar campo ao `UploadResponse` (linha 30, após `was_duplicate`):

```python
class UploadResponse(BaseModel):
    success: bool
    message: str
    document_id: Optional[str] = None
    version_id: Optional[str] = None
    total_pages: int = 0
    total_chunks: int = 0
    was_duplicate: bool = False
    retryable: bool = False
```

- [ ] **Step 2: Atualizar o handler para passar retryable no erro**

Em `backend/app/api/upload.py`, mudar o bloco de erro (linhas 91-92):

De:
```python
    if not result.success:
        raise HTTPException(status_code=422, detail=result.message)
```
Para:
```python
    if not result.success:
        status_code = 503 if result.retryable else 422
        raise HTTPException(status_code=status_code, detail=result.message)
```

E atualizar o return para incluir `retryable` (após `was_duplicate`):

```python
    return UploadResponse(
        success=result.success,
        message=result.message,
        document_id=result.document_id,
        version_id=result.version_id,
        total_pages=result.total_pages,
        total_chunks=result.total_chunks,
        was_duplicate=result.was_duplicate,
        retryable=result.retryable,
    )
```

- [ ] **Step 3: Rodar testes de integração da API**

```bash
cd backend && python -m pytest tests/integration/test_upload_api.py -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/upload.py
git commit -m "feat: return retryable flag and 503 status for transient upload errors"
```

---

### Task 6: Frontend — retryable no tipo e retry no upload

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/upload/FileProgressItem.tsx`
- Modify: `frontend/src/components/upload/BulkUploadForm.tsx`

- [ ] **Step 1: Adicionar `retryable` ao tipo `UploadResponse`**

Em `frontend/src/types/index.ts`, adicionar ao `UploadResponse` (após `was_duplicate`):

```typescript
export interface UploadResponse {
  success: boolean;
  message: string;
  document_id?: string;
  version_id?: string;
  total_pages: number;
  total_chunks: number;
  was_duplicate: boolean;
  retryable?: boolean;
}
```

- [ ] **Step 2: Adicionar botão retry no `FileProgressItem`**

Em `frontend/src/components/upload/FileProgressItem.tsx`:

Adicionar import do `RotateCw`:

```typescript
import { FileText, Loader2, RotateCw } from "lucide-react";
```

Adicionar `onRetry` à interface Props e ao componente:

```typescript
interface Props {
  state: FileUploadState;
  onRetry?: () => void;
}

export function FileProgressItem({ state, onRetry }: Props) {
```

Atualizar o bloco de erro (substituir o bloco final `{status === "erro" && ...}`):

```tsx
      {status === "erro" && error && (
        <div className="ml-8 flex items-center gap-2">
          <p className="flex-1 text-xs text-destructive">{error}</p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-950"
            >
              <RotateCw className="h-3 w-3" />
              Tentar novamente
            </button>
          )}
        </div>
      )}
```

- [ ] **Step 3: Adicionar lógica de retry no `BulkUploadForm`**

Em `frontend/src/components/upload/BulkUploadForm.tsx`:

Adicionar `retryCount` ao `FileUploadState` — na verdade, usar um ref separado para não complicar a interface existente. Adicionar um ref para contar retries:

Adicionar após `const docTypeRef = useRef("");` (linha 118):

```typescript
  const retryCountRef = useRef<Record<string, number>>({});
```

Adicionar função `retryFile` após `checkIfDone`:

```typescript
  const retryFile = useCallback(
    (fileState: FileUploadState) => {
      const fileId = fileState.id;
      const count = retryCountRef.current[fileId] ?? 0;
      if (count >= 2) return; // Max 2 retries
      retryCountRef.current[fileId] = count + 1;
      updateFileState(fileId, { status: "pendente", error: undefined, progress: 0 });
      activeCountRef.current += 1;
      processFile(fileState);
    },
    [updateFileState, processFile],
  );
```

No bloco de erro do `processFile` (dentro do `catch`), adicionar auto-retry para status 503:

Substituir o `catch` do `processFile` (linhas 161-165):

```typescript
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Erro desconhecido.";
        const isRetryable = msg.includes("503") || msg.includes("indisponível");
        const retries = retryCountRef.current[state.id] ?? 0;

        if (isRetryable && retries < 1) {
          // Auto-retry uma vez para erros transientes
          retryCountRef.current[state.id] = retries + 1;
          updateFileState(state.id, { status: "pendente", progress: 0 });
          // Re-enqueue
          queueRef.current.push(state);
        } else {
          updateFileState(state.id, {
            status: "erro",
            error: msg,
          });
        }
```

No render do `FileProgressItem`, passar `onRetry`:

Substituir (linha ~358):

```tsx
              {fileStates.map((s) => (
                <FileProgressItem key={s.id} state={s} />
              ))}
```

Por:

```tsx
              {fileStates.map((s) => (
                <FileProgressItem
                  key={s.id}
                  state={s}
                  onRetry={
                    s.status === "erro"
                      ? () => retryFile(s)
                      : undefined
                  }
                />
              ))}
```

- [ ] **Step 4: Verificar build do frontend**

```bash
cd frontend && npm run build
```

Expected: Build sem erros

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/components/upload/FileProgressItem.tsx frontend/src/components/upload/BulkUploadForm.tsx
git commit -m "feat: add retry button and auto-retry for transient upload errors"
```

---

### Task 7: Teste end-to-end com o PDF real

**Files:** Nenhum — teste manual.

- [ ] **Step 1: Instalar dependência**

```bash
cd backend && pip install azure-ai-documentintelligence
```

- [ ] **Step 2: Testar OCR isolado com o PDF real**

```bash
cd backend && python -c "
import asyncio
from app.services.ocr import ocr_pdf

async def test():
    with open('/Users/arthurbueno/Downloads/ATUALIZACAO VCA 500 .pdf', 'rb') as f:
        pages = await ocr_pdf(f.read())
    for p in pages:
        print(f'Page {p.page_number}: {len(p.text)} chars')
        print(f'  Preview: {p.text[:150]}...')

asyncio.run(test())
"
```

Expected: 6 páginas com texto extraído

- [ ] **Step 3: Testar extração completa**

```bash
cd backend && python -c "
import asyncio
from app.services.pdf_extractor import extract_text_from_pdf

async def test():
    with open('/Users/arthurbueno/Downloads/ATUALIZACAO VCA 500 .pdf', 'rb') as f:
        result = await extract_text_from_pdf(f.read(), 'ATUALIZACAO VCA 500 .pdf')
    print(f'Pages: {result.total_pages}, Extracted: {len(result.pages)}')
    for p in result.pages:
        print(f'  Page {p.page_number}: {len(p.text)} chars')

asyncio.run(test())
"
```

Expected: Sucesso, sem ValueError

- [ ] **Step 4: Rodar todos os testes**

```bash
cd backend && python -m pytest tests/ -v --timeout=30
```

Expected: Todos PASS

- [ ] **Step 5: Commit final**

```bash
git add -A
git commit -m "chore: verify OCR integration with real scanned PDF"
```
