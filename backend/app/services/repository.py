"""
Kyotech AI — Repositório de Dados
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chunker import TextChunk

logger = logging.getLogger(__name__)


async def find_or_create_equipment(
    db: AsyncSession,
    equipment_key: str,
    display_name: Optional[str] = None,
) -> str:
    result = await db.execute(
        text("SELECT equipment_key FROM equipments WHERE equipment_key = :key"),
        {"key": equipment_key},
    )
    row = result.fetchone()

    if row:
        return row[0]

    name = display_name or equipment_key.replace("-", " ").title()
    await db.execute(
        text("""
            INSERT INTO equipments (equipment_key, display_name, aliases)
            VALUES (:key, :name, :aliases)
        """),
        {"key": equipment_key, "name": name, "aliases": []},
    )
    logger.info(f"Equipamento criado: {equipment_key} ({name})")
    return equipment_key


async def find_or_create_document(
    db: AsyncSession,
    doc_type: str,
    equipment_key: str,
) -> UUID:
    result = await db.execute(
        text("""
            SELECT id FROM documents
            WHERE doc_type = :doc_type AND equipment_key = :equipment_key
        """),
        {"doc_type": doc_type, "equipment_key": equipment_key},
    )
    row = result.fetchone()

    if row:
        return row[0]

    result = await db.execute(
        text("""
            INSERT INTO documents (doc_type, equipment_key)
            VALUES (:doc_type, :equipment_key)
            RETURNING id
        """),
        {"doc_type": doc_type, "equipment_key": equipment_key},
    )
    doc_id = result.fetchone()[0]
    logger.info(f"Documento criado: {doc_type} / {equipment_key} → {doc_id}")
    return doc_id


async def check_version_exists(
    db: AsyncSession,
    document_id: UUID,
    source_hash: str,
) -> bool:
    result = await db.execute(
        text("""
            SELECT id FROM document_versions
            WHERE document_id = :doc_id AND source_hash = :hash
        """),
        {"doc_id": str(document_id), "hash": source_hash},
    )
    return result.fetchone() is not None


async def create_version(
    db: AsyncSession,
    document_id: UUID,
    published_date: date,
    source_hash: str,
    source_filename: str,
    storage_path: str,
) -> UUID:
    result = await db.execute(
        text("""
            INSERT INTO document_versions
                (document_id, published_date, source_hash, source_filename, storage_path)
            VALUES
                (:doc_id, :pub_date, :hash, :filename, :path)
            ON CONFLICT (document_id, published_date) DO UPDATE
            SET source_hash = EXCLUDED.source_hash,
                source_filename = EXCLUDED.source_filename,
                storage_path = EXCLUDED.storage_path
            RETURNING id
        """),
        {
            "doc_id": str(document_id),
            "pub_date": published_date,
            "hash": source_hash,
            "filename": source_filename,
            "path": storage_path,
        },
    )
    version_id = result.fetchone()[0]
    logger.info(f"Versão criada: {source_filename} ({published_date}) → {version_id}")
    return version_id


async def insert_chunks_with_embeddings(
    db: AsyncSession,
    version_id: UUID,
    chunks: List[TextChunk],
    embeddings: List[List[float]],
) -> int:
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"Mismatch: {len(chunks)} chunks vs {len(embeddings)} embeddings"
        )

    await db.execute(
        text("DELETE FROM chunks WHERE document_version_id = :vid"),
        {"vid": str(version_id)},
    )

    for chunk, embedding in zip(chunks, embeddings):
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

        await db.execute(
            text("""
                INSERT INTO chunks
                    (document_version_id, page_number, chunk_index, content, embedding)
                VALUES
                    (:version_id, :page, :idx, :content, :embedding)
                ON CONFLICT (document_version_id, page_number, chunk_index) DO UPDATE
                SET content = EXCLUDED.content, embedding = EXCLUDED.embedding
            """),
            {
                "version_id": str(version_id),
                "page": chunk.page_number,
                "idx": chunk.chunk_index,
                "content": chunk.content,
                "embedding": embedding_str,
            },
        )

    await db.commit()
    logger.info(f"Inseridos {len(chunks)} chunks para versão {version_id}")
    return len(chunks)


async def get_version_info(
    db: AsyncSession,
    version_id: UUID,
) -> Optional[Dict]:
    """Busca storage_path e total_pages de uma versão pelo ID."""
    result = await db.execute(
        text("""
            SELECT
                dv.storage_path,
                dv.source_filename,
                dv.published_date,
                d.equipment_key,
                d.doc_type,
                (SELECT COUNT(*) FROM chunks WHERE document_version_id = dv.id) AS total_chunks
            FROM document_versions dv
            JOIN documents d ON dv.document_id = d.id
            WHERE dv.id = :version_id
        """),
        {"version_id": str(version_id)},
    )
    row = result.fetchone()
    if not row:
        return None
    return {
        "storage_path": row[0],
        "source_filename": row[1],
        "published_date": row[2],
        "equipment_key": row[3],
        "doc_type": row[4],
        "total_chunks": row[5],
    }


async def list_equipments(db: AsyncSession) -> List[Dict[str, str]]:
    result = await db.execute(
        text("SELECT equipment_key, display_name FROM equipments ORDER BY display_name")
    )
    return [{"key": row[0], "name": row[1]} for row in result.fetchall()]


async def get_ingestion_stats(db: AsyncSession) -> Dict[str, int]:
    result = await db.execute(text("""
        SELECT
            (SELECT COUNT(*) FROM equipments) AS total_equipments,
            (SELECT COUNT(*) FROM documents) AS total_documents,
            (SELECT COUNT(*) FROM document_versions) AS total_versions,
            (SELECT COUNT(*) FROM chunks) AS total_chunks
    """))
    row = result.fetchone()
    return {
        "equipments": row[0],
        "documents": row[1],
        "versions": row[2],
        "chunks": row[3],
    }
