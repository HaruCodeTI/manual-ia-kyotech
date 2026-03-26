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
from dataclasses import dataclass, field
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
    equipment_key: Optional[str]
    published_date: date
    source_filename: str
    storage_path: str
    search_type: str  # "vector", "text", or "hybrid"
    document_version_id: str = ""  # ID da versão para o viewer seguro
    quality_score: float = 0.0
    equipment_mentions: list = field(default_factory=list)


async def vector_search(
    db: AsyncSession,
    query_text: str,
    limit: int = 10,
    doc_type: Optional[str] = None,
    equipment_key: Optional[str] = None,
    include_all_versions: bool = False,
) -> List[SearchResult]:
    """
    Busca vetorial com cosine similarity via pgvector.
    Busca apenas nas versões atuais (mais recentes).
    Retorna document_version_id para o viewer seguro.
    """
    embedding = await generate_single_embedding(query_text)
    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

    filters = []
    params: Dict = {"embedding": embedding_str, "limit": limit}

    if doc_type:
        filters.append("d.doc_type = :doc_type")
        params["doc_type"] = doc_type
    if equipment_key:
        filters.append("d.equipment_key = :equipment")
        params["equipment"] = equipment_key

    where_clause = ""
    if filters:
        where_clause = "AND " + " AND ".join(filters)

    version_source = "document_versions" if include_all_versions else "current_versions"

    result = await db.execute(
        text(f"""
            SELECT
                c.id AS chunk_id,
                c.content,
                c.page_number,
                1 - (c.embedding <=> cast(:embedding AS vector)) AS similarity,
                d.id AS document_id,
                d.doc_type,
                d.equipment_key,
                cv.published_date,
                cv.source_filename,
                cv.storage_path,
                cv.id AS version_id,
                c.quality_score,
                c.equipment_mentions
            FROM chunks c
            JOIN {version_source} cv ON c.document_version_id = cv.id
            JOIN documents d ON cv.document_id = d.id
            WHERE 1=1
            {where_clause}
            ORDER BY c.embedding <=> cast(:embedding AS vector)
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
            document_version_id=str(row[10]),
            quality_score=float(row[11] or 0.0),
            equipment_mentions=row[12] or [],
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
    include_all_versions: bool = False,
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

    version_source = "document_versions" if include_all_versions else "current_versions"

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
                cv.storage_path,
                cv.id AS version_id,
                c.quality_score,
                c.equipment_mentions
            FROM chunks c
            JOIN {version_source} cv ON c.document_version_id = cv.id
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
            document_version_id=str(row[10]),
            quality_score=float(row[11] or 0.0),
            equipment_mentions=row[12] or [],
            search_type="text",
        )
        for row in rows
    ]


EQUIPMENT_BOOST = 0.10
DOC_TYPE_BOOST = 0.08
MIN_SCORE_THRESHOLD = 0.15
QUALITY_WEIGHT = 0.15


async def hybrid_search(
    db: AsyncSession,
    query_en: str,
    query_original: str,
    limit: int = 8,
    doc_type: Optional[str] = None,
    equipment_key: Optional[str] = None,
    vector_weight: float = 0.65,
    text_weight: float = 0.35,
    include_all_versions: bool = False,
) -> List[SearchResult]:
    """
    Busca híbrida: combina vetorial (query em EN) + textual (query original PT).

    A busca vetorial usa a query em inglês (melhor match com manuais EN).
    A busca textual usa a query original (pega códigos, números exatos).

    Resultados são fundidos por chunk_id com score ponderado.
    doc_type e equipment_key aplicam boost (não filtro hard) — documentos
    sem metadados ainda são retornados se forem semanticamente relevantes.
    """
    # Executa ambas as buscas sem filtros de metadados para não excluir
    # documentos sem doc_type ou equipment_key definidos
    vector_results = await vector_search(db, query_en, limit=30, include_all_versions=include_all_versions)
    text_results = await text_search(db, query_original, limit=30, include_all_versions=include_all_versions)

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

    # Boost para documentos do equipamento mencionado
    if equipment_key:
        equipment_key_lower = equipment_key.lower()
        for chunk_id, result in merged.items():
            if result.equipment_key and result.equipment_key == equipment_key:
                scores[chunk_id] += EQUIPMENT_BOOST
            elif equipment_key in (result.equipment_mentions or []):
                scores[chunk_id] += EQUIPMENT_BOOST
            elif equipment_key_lower in result.content.lower():
                scores[chunk_id] += EQUIPMENT_BOOST

    # Boost para documentos do tipo correto
    if doc_type:
        for chunk_id, result in merged.items():
            if result.doc_type and result.doc_type == doc_type:
                scores[chunk_id] += DOC_TYPE_BOOST

    # Boost por quality_score acumulado via feedback
    # ATENÇÃO: deve ficar antes de "sorted_ids = sorted(scores, ...)" para afetar o ranking
    for chunk_id, result in merged.items():
        if result.quality_score != 0.0:
            scores[chunk_id] += result.quality_score * QUALITY_WEIGHT

    # Ordena por score combinado
    sorted_ids = sorted(scores, key=lambda k: scores[k], reverse=True)

    results = []
    for chunk_id in sorted_ids[:limit]:
        score = scores[chunk_id]
        if score < MIN_SCORE_THRESHOLD:
            continue
        result = merged[chunk_id]
        result.similarity = score
        results.append(result)

    logger.info(
        f"Busca híbrida final: {len(results)} resultados (threshold={MIN_SCORE_THRESHOLD})"
    )

    return results
