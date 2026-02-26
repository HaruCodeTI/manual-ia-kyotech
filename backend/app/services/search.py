"""
Kyotech AI — Busca Híbrida
Conforme Seção 7: busca vetorial (pgvector) + textual (pg_trgm).

Estratégia:
1. Busca vetorial: semelhança de embedding (captura significado)
2. Busca textual: trigram matching (captura termos exatos, códigos de peça)
3. Fusão: combina resultados com pesos configuráveis
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embedder import generate_single_embedding

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    chunk_id: str
    content: str
    page_number: int
    similarity: float
    document_id: str
    doc_type: str
    equipment_key: str
    published_date: date
    source_filename: str
    storage_path: str
    search_type: str  # "vector", "text", or "hybrid"


async def vector_search(
    db: AsyncSession,
    query_text: str,
    limit: int = 10,
    doc_type: Optional[str] = None,
    equipment_key: Optional[str] = None,
) -> List[SearchResult]:
    """
    Busca vetorial usando a função search_current_chunks do banco.
    Busca apenas nas versões atuais (mais recentes).
    """
    embedding = await generate_single_embedding(query_text)
    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

    result = await db.execute(
        text("""
            SELECT
                chunk_id, content, page_number, similarity,
                document_id, doc_type, equipment_key,
                published_date, source_filename, storage_path
            FROM search_current_chunks(
                cast(:embedding AS vector),
                :limit,
                :doc_type,
                :equipment
            )
        """),
        {
            "embedding": embedding_str,
            "limit": limit,
            "doc_type": doc_type,
            "equipment": equipment_key,
        },
    )

    rows = result.fetchall()
    return [
        SearchResult(
            chunk_id=str(row[0]),
            content=row[1],
            page_number=row[2],
            similarity=float(row[3]),
            document_id=str(row[4]),
            doc_type=row[5],
            equipment_key=row[6],
            published_date=row[7],
            source_filename=row[8],
            storage_path=row[9],
            search_type="vector",
        )
        for row in rows
    ]


async def text_search(
    db: AsyncSession,
    query_text: str,
    limit: int = 5,
    doc_type: Optional[str] = None,
    equipment_key: Optional[str] = None,
) -> List[SearchResult]:
    """
    Busca textual usando pg_trgm (trigram similarity).
    Boa para códigos de peça, números de erro, termos exatos.
    """
    # Filtra apenas versões atuais via JOIN com current_versions
    filters = []
    params: Dict = {"query": query_text, "limit": limit}

    if doc_type:
        filters.append("d.doc_type = :doc_type")
        params["doc_type"] = doc_type
    if equipment_key:
        filters.append("d.equipment_key = :equipment")
        params["equipment"] = equipment_key

    where_clause = ""
    if filters:
        where_clause = "AND " + " AND ".join(filters)

    result = await db.execute(
        text(f"""
            SELECT
                c.id AS chunk_id,
                c.content,
                c.page_number,
                similarity(c.content, :query) AS sim,
                d.id AS document_id,
                d.doc_type,
                d.equipment_key,
                cv.published_date,
                cv.source_filename,
                cv.storage_path
            FROM chunks c
            JOIN current_versions cv ON c.document_version_id = cv.id
            JOIN documents d ON cv.document_id = d.id
            WHERE similarity(c.content, :query) > 0.05
            {where_clause}
            ORDER BY sim DESC
            LIMIT :limit
        """),
        params,
    )

    rows = result.fetchall()
    return [
        SearchResult(
            chunk_id=str(row[0]),
            content=row[1],
            page_number=row[2],
            similarity=float(row[3]),
            document_id=str(row[4]),
            doc_type=row[5],
            equipment_key=row[6],
            published_date=row[7],
            source_filename=row[8],
            storage_path=row[9],
            search_type="text",
        )
        for row in rows
    ]


async def hybrid_search(
    db: AsyncSession,
    query_en: str,
    query_original: str,
    limit: int = 8,
    doc_type: Optional[str] = None,
    equipment_key: Optional[str] = None,
    vector_weight: float = 0.7,
    text_weight: float = 0.3,
) -> List[SearchResult]:
    """
    Busca híbrida: combina vetorial (query em EN) + textual (query original PT).
    
    A busca vetorial usa a query em inglês (melhor match com manuais EN).
    A busca textual usa a query original (pega códigos, números exatos).
    
    Resultados são fundidos por chunk_id com score ponderado.
    """
    # Executa ambas as buscas
    vector_results = await vector_search(
        db, query_en, limit=limit, doc_type=doc_type, equipment_key=equipment_key
    )
    text_results = await text_search(
        db, query_original, limit=limit, doc_type=doc_type, equipment_key=equipment_key
    )

    logger.info(
        f"Busca híbrida: {len(vector_results)} vetorial + {len(text_results)} textual"
    )

    # Fusão por chunk_id
    merged: Dict[str, SearchResult] = {}
    scores: Dict[str, float] = {}

    for r in vector_results:
        merged[r.chunk_id] = r
        scores[r.chunk_id] = r.similarity * vector_weight

    for r in text_results:
        if r.chunk_id in merged:
            scores[r.chunk_id] += r.similarity * text_weight
            merged[r.chunk_id].search_type = "hybrid"
        else:
            merged[r.chunk_id] = r
            scores[r.chunk_id] = r.similarity * text_weight

    # Ordena por score combinado
    sorted_ids = sorted(scores, key=lambda k: scores[k], reverse=True)

    results = []
    for chunk_id in sorted_ids[:limit]:
        result = merged[chunk_id]
        result.similarity = scores[chunk_id]
        results.append(result)

    return results
