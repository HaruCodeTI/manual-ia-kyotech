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


# Resíduo de paginação (números de página soltos, cabeçalhos, sobra de
# overlap) gera fragmentos curtos que poluíam o topo da busca textual — o
# score do pg_trgm era normalizado por tamanho, então quanto menor o chunk,
# maior o score. Havia 454 chunks abaixo desse corte em prod.
#
# O descarte é conservador de propósito: nunca elimina o conteúdo inteiro de
# uma página. Se todos os fragmentos de uma página ficarem abaixo do corte, a
# página é preservada como um único chunk — perder conteúdo indexável seria
# pior que o ruído que estamos removendo.
MIN_CHUNK_CHARS = 40


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

        kept = [c for c in page_chunks if len(c.strip()) >= MIN_CHUNK_CHARS]
        if not kept:
            # Página curta de verdade — preserva em vez de descartar.
            kept = [text]

        # chunk_index precisa ser contíguo: é parte da chave única uq_chunk
        # (document_version_id, page_number, chunk_index).
        for idx, content in enumerate(kept):
            all_chunks.append(TextChunk(
                page_number=page.page_number,
                chunk_index=idx,
                content=content,
            ))

    return all_chunks
