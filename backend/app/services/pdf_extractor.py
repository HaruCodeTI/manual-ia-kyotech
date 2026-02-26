"""
Kyotech AI — Serviço de Extração de Texto de PDF
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List

import fitz  # PyMuPDF


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


def extract_text_from_pdf(file_bytes: bytes, filename: str) -> PDFExtraction:
    source_hash = compute_file_hash(file_bytes)

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages: List[PageContent] = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text").strip()
        if text:
            pages.append(PageContent(page_number=page_num + 1, text=text))

    total_pages = len(doc)
    doc.close()

    if not pages:
        raise ValueError(
            f"PDF '{filename}' não contém texto extraível. "
            "Pode ser um PDF escaneado — necessário OCR (Fase 3)."
        )

    return PDFExtraction(
        filename=filename,
        source_hash=source_hash,
        total_pages=total_pages,
        pages=pages,
    )
