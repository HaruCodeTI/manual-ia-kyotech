"""
Kyotech AI — Serviço de Extração de Texto de PDF
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import List, Tuple

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
        text = page.get_text("text").strip().replace('\x00', '')
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
        from app.services import ocr as _ocr_mod

        ocr_pages = await _ocr_mod.ocr_pdf(file_bytes, page_numbers=pages_without_text)
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
