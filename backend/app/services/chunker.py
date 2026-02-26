"""
Kyotech AI — Serviço de Chunking
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from app.services.pdf_extractor import PageContent


@dataclass
class TextChunk:
    page_number: int
    chunk_index: int
    content: str


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks: List[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end < len(text):
            newline_pos = text.rfind("\n", start + chunk_size // 2, end)
            if newline_pos != -1:
                end = newline_pos + 1
            else:
                space_pos = text.rfind(" ", start + chunk_size // 2, end)
                if space_pos != -1:
                    end = space_pos + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - chunk_overlap if end < len(text) else end

    return chunks


def chunk_pages(
    pages: List[PageContent],
    chunk_size: int = 800,
    chunk_overlap: int = 200,
) -> List[TextChunk]:
    all_chunks: List[TextChunk] = []

    for page in pages:
        text = page.text.strip()
        if not text:
            continue

        page_chunks = chunk_text(text, chunk_size, chunk_overlap)

        for idx, content in enumerate(page_chunks):
            all_chunks.append(TextChunk(
                page_number=page.page_number,
                chunk_index=idx,
                content=content,
            ))

    return all_chunks
