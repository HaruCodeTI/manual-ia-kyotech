# OCR para PDFs Escaneados + Resiliência de Upload

**Data:** 2026-03-31  
**Status:** Aprovado  
**Contexto:** PDFs escaneados (imagens sem texto extraível) são frequentes nos uploads dos clientes. O pipeline atual rejeita esses documentos com erro "necessário OCR (Fase 3)".

---

## Problema

1. **PDFs escaneados rejeitados** — `pdf_extractor.py` usa PyMuPDF para extrair texto. Se nenhuma página tem texto, lança `ValueError` e o documento é rejeitado.
2. **Mensagem de erro confusa no batch** — quando 1 arquivo falha no meio de um lote, o cliente percebe como "falhou tudo" mesmo que os outros tenham sido processados com sucesso.

### Caso real

- PDF: "ATUALIZACAO VCA 500 .pdf" — 6 páginas, todas imagens escaneadas, zero texto
- Cliente tentou 2x, na segunda tentativa 9/10 funcionaram, 1 falhou (este PDF)

---

## Solução

### 1. OCR via Azure Document Intelligence

Usar o serviço **Azure Document Intelligence** (modelo `prebuilt-read`) como fallback automático quando PyMuPDF não encontra texto.

#### Fluxo de extração (modificação de `pdf_extractor.py`)

```
PyMuPDF extrai texto de todas as páginas
  ├─ Todas as páginas têm texto → retorna PDFExtraction (sem custo, rápido)
  ├─ Nenhuma página tem texto → envia PDF inteiro para Document Intelligence
  └─ Parcial (PDF misto) → OCR apenas nas páginas sem texto
Combina resultados → retorna PDFExtraction unificado
```

O resto do pipeline (chunking, embeddings, storage) não muda — recebe o mesmo `PDFExtraction`.

#### Novo serviço: `app/services/ocr.py`

Responsabilidade única: chamar Document Intelligence e retornar `list[PageContent]`.

```python
async def ocr_pdf(file_bytes: bytes, page_numbers: list[int] | None = None) -> list[PageContent]:
    """
    Extrai texto de PDF escaneado via Azure Document Intelligence.
    
    Args:
        file_bytes: bytes do PDF
        page_numbers: se fornecido, filtra apenas essas páginas do resultado
        
    Returns:
        Lista de PageContent com texto extraído por OCR
    """
```

- SDK: `azure-ai-documentintelligence`
- Modelo: `prebuilt-read` (otimizado para extração de texto, suporta múltiplos idiomas)
- Timeout: 120s (documentos grandes escaneados podem demorar)
- Retry: backoff exponencial para 429/503 (2s, 4s, 8s — máx 3 tentativas)

#### Modificação de `pdf_extractor.py`

A função `extract_text_from_pdf` passa a ser `async` e ganha fallback:

```python
async def extract_text_from_pdf(file_bytes: bytes, filename: str) -> PDFExtraction:
    # 1. Tenta PyMuPDF (rápido, sem custo)
    pages, total_pages = _extract_with_pymupdf(file_bytes)
    
    # 2. Identifica páginas sem texto
    pages_without_text = [i+1 for i in range(total_pages) if i+1 not in {p.page_number for p in pages}]
    
    # 3. Se há páginas sem texto, fallback para OCR
    if pages_without_text:
        logger.info(f"PDF escaneado detectado ({len(pages_without_text)}/{total_pages} páginas sem texto), usando OCR")
        ocr_pages = await ocr_pdf(file_bytes, page_numbers=pages_without_text)
        pages.extend(ocr_pages)
        pages.sort(key=lambda p: p.page_number)
    
    # 4. Se ainda sem texto após OCR, aí sim é erro
    if not pages:
        raise ValueError(f"PDF '{filename}' não contém texto extraível mesmo após OCR.")
    
    return PDFExtraction(...)
```

**Impacto:** como a função passa a ser `async`, o `ingestion.py` que já a chama de forma `await`-compatível precisa de ajuste mínimo (adicionar `await`).

### 2. Resiliência no batch upload

#### Backend (endpoint `POST /upload/document`)

O endpoint atual já processa um arquivo por vez — o batch é orquestrado pelo frontend com concorrência de 3. Isso está bom.

Melhoria no tratamento de erro:
- Diferenciar erros **transientes** (timeout, 429 do OCR) de erros **permanentes** (PDF corrompido, sem texto mesmo após OCR)
- Para erros transientes, o `IngestionResult.message` deve indicar que retry pode resolver
- Adicionar campo `retryable: bool` ao `IngestionResult`

```python
@dataclass
class IngestionResult:
    success: bool
    message: str
    retryable: bool = False  # novo
    # ... resto igual
```

#### Frontend (`BulkUploadForm.tsx`)

O frontend já tem boa infraestrutura (concorrência, progresso, persistência em session). Melhorias:

- Quando `retryable=True`, mostrar botão "Tentar novamente" no `FileProgressItem` ao invés de só "Erro"
- Retry automático (1x) para erros transientes antes de mostrar como falha

### 3. Infraestrutura

#### Provisionamento Azure

- Recurso: **FormRecognizer** (Document Intelligence)
- Nome: `docint-kyotech`
- SKU: **S0** (Standard) — 15 req/s, ~$1.50/1000 páginas
- Região: `eastus2` (mesma do `aoai-kyotech`)
- Resource group: mesmo do `aoai-kyotech`

#### Novas variáveis de ambiente

Em `app/core/config.py`:

```python
azure_document_intelligence_endpoint: str = ""
azure_document_intelligence_key: str = ""
```

#### Dependências

Adicionar ao `requirements.txt`:
```
azure-ai-documentintelligence>=1.0.0
```

### 4. Logging

- `INFO`: "PDF escaneado detectado ({N}/{total} páginas sem texto), usando OCR via Document Intelligence"
- `INFO`: "OCR completo: {filename} → {N} páginas processadas em {tempo}s"
- `WARNING`: "OCR retry {attempt}/3 para {filename} (status {code})"
- `ERROR`: "PDF '{filename}' não contém texto extraível mesmo após OCR" (PDF vazio/corrompido)

---

## Arquivos a modificar/criar

| Arquivo | Ação | Descrição |
|---------|------|-----------|
| `backend/app/services/ocr.py` | **Criar** | Serviço OCR via Document Intelligence |
| `backend/app/services/pdf_extractor.py` | Modificar | Adicionar fallback para OCR, tornar async |
| `backend/app/services/ingestion.py` | Modificar | Ajustar para `await extract_text_from_pdf`, adicionar `retryable` |
| `backend/app/core/config.py` | Modificar | Adicionar variáveis Document Intelligence |
| `backend/app/api/upload.py` | Modificar | Incluir `retryable` no response |
| `backend/requirements.txt` | Modificar | Adicionar `azure-ai-documentintelligence` |
| `frontend/src/components/upload/FileProgressItem.tsx` | Modificar | Botão retry para erros transientes |
| `frontend/src/components/upload/BulkUploadForm.tsx` | Modificar | Lógica de retry automático |

---

## Fora de escopo

- OCR de imagens soltas (não-PDF)
- Tradução de texto extraído
- Preview do texto extraído antes de confirmar ingestão
- Suporte a PDF protegido por senha
