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

_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds: 2, 4, 8


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
            if e.status_code in (429, 503) and attempt <= _MAX_RETRIES:
                wait = _BACKOFF_BASE ** attempt
                logger.warning(f"OCR retry {attempt}/{_MAX_RETRIES} (status {e.status_code}), aguardando {wait}s")
                await asyncio.sleep(wait)
            else:
                raise
    raise last_error  # unreachable, satisfies type checker
