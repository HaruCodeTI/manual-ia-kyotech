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
    doc_type: Optional[str],
    equipment_key: Optional[str],
) -> UUID:
    # Quando ambos os metadados são nulos, cada upload cria um documento
    # independente para evitar que arquivos distintos compartilhem o mesmo
    # version_id e sobrescrevam chunks uns dos outros.
    if doc_type is not None or equipment_key is not None:
        result = await db.execute(
            text("""
                SELECT id FROM documents
                WHERE doc_type IS NOT DISTINCT FROM :doc_type
                  AND equipment_key IS NOT DISTINCT FROM :equipment_key
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

    if not chunks:
        await db.commit()
        return 0

    params: dict = {"version_id": str(version_id)}
    value_rows: list = []

    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        # Seguro: valores de embedding são passados como parâmetros nomeados (:cN_emb),
        # não interpolados diretamente na string SQL — sem risco de SQL injection.
        # Prefixo "c" obrigatório: asyncpg rejeita parâmetros nomeados iniciando com dígito.
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
        value_rows.append(
            f"(:version_id, :c{i}_page, :c{i}_idx, :c{i}_content, CAST(:c{i}_emb AS vector))"
        )
        params[f"c{i}_page"] = chunk.page_number
        params[f"c{i}_idx"] = chunk.chunk_index
        params[f"c{i}_content"] = chunk.content
        params[f"c{i}_emb"] = embedding_str

    await db.execute(
        text(f"""
            INSERT INTO chunks
                (document_version_id, page_number, chunk_index, content, embedding)
            VALUES {", ".join(value_rows)}
            ON CONFLICT (document_version_id, page_number, chunk_index) DO UPDATE
            SET content = EXCLUDED.content, embedding = EXCLUDED.embedding
        """),
        params,
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
            (SELECT COUNT(*) FROM chunks) AS total_chunks,
            (
                SELECT COUNT(*) FROM document_versions dv
                WHERE NOT EXISTS (
                    SELECT 1 FROM chunks c WHERE c.document_version_id = dv.id
                )
            ) AS docs_without_chunks
    """))
    row = result.fetchone()
    return {
        "equipments": row[0],
        "documents": row[1],
        "versions": row[2],
        "chunks": row[3],
        "docs_without_chunks": row[4],
    }


async def get_usage_stats(db: AsyncSession) -> Dict[str, int]:
    result = await db.execute(text("""
        SELECT
            (SELECT COUNT(*) FROM chat_sessions) AS total_sessions,
            (SELECT COUNT(*) FROM chat_messages WHERE role = 'user') AS total_messages,
            (SELECT COUNT(*) FROM message_feedback WHERE rating = 'thumbs_up') AS thumbs_up,
            (SELECT COUNT(*) FROM message_feedback WHERE rating = 'thumbs_down') AS thumbs_down
    """))
    row = result.fetchone()
    return {
        "total_sessions": row[0],
        "total_messages": row[1],
        "thumbs_up": row[2],
        "thumbs_down": row[3],
    }


async def find_duplicate_groups(db: AsyncSession) -> Dict:
    """Busca grupos de document_versions com mesmo source_hash."""
    # Passo 1: hashes com mais de uma versão
    dup_result = await db.execute(text("""
        SELECT source_hash, COUNT(*) as cnt
        FROM document_versions
        GROUP BY source_hash
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
    """))
    dup_hashes = dup_result.fetchall()

    if not dup_hashes:
        return {"groups": [], "total_groups": 0, "total_removable": 0}

    groups = []
    total_removable = 0

    for hash_row in dup_hashes:
        source_hash = hash_row[0]

        # Passo 2: buscar versões desse hash, ordenadas por created_at
        ver_result = await db.execute(
            text("""
                SELECT
                    dv.id, dv.document_id, dv.source_filename,
                    d.equipment_key, d.doc_type,
                    dv.published_date, dv.created_at,
                    dv.storage_path,
                    (SELECT COUNT(*) FROM chunks WHERE document_version_id = dv.id) AS chunk_count
                FROM document_versions dv
                JOIN documents d ON dv.document_id = d.id
                WHERE dv.source_hash = :hash
                ORDER BY COALESCE(dv.created_at, dv.published_date) ASC
            """),
            {"hash": source_hash},
        )
        versions = ver_result.fetchall()

        if len(versions) < 2:
            continue

        def _version_dict(row):
            return {
                "version_id": str(row[0]),
                "document_id": str(row[1]),
                "filename": row[2],
                "equipment_key": row[3],
                "doc_type": row[4],
                "published_date": row[5].isoformat() if row[5] else None,
                "created_at": row[6].isoformat() if row[6] else None,
                "storage_path": row[7],
                "chunk_count": row[8],
            }

        keep = _version_dict(versions[0])
        duplicates = [_version_dict(v) for v in versions[1:]]
        total_removable += len(duplicates)

        groups.append({
            "source_hash": source_hash,
            "keep": keep,
            "duplicates": duplicates,
        })

    return {
        "groups": groups,
        "total_groups": len(groups),
        "total_removable": total_removable,
    }


async def delete_duplicate_versions(
    db: AsyncSession,
    version_ids: List[str],
) -> Dict:
    """
    Deleta versões duplicadas e seus chunks.
    Retorna paths dos blobs a deletar (caller é responsável pelo storage).
    Re-valida que cada versão ainda é duplicata antes de deletar.
    """
    deleted = 0
    skipped = 0
    storage_paths: List[str] = []
    orphan_documents_deleted = 0

    for vid in version_ids:
        # 1. Buscar info da versão
        result = await db.execute(
            text("""
                SELECT storage_path, document_id, source_hash
                FROM document_versions
                WHERE id = :vid
            """),
            {"vid": vid},
        )
        row = result.fetchone()
        if not row:
            skipped += 1
            continue

        storage_path, document_id, source_hash = row[0], str(row[1]), row[2]

        # 2. Re-validar que ainda é duplicata
        count_result = await db.execute(
            text("""
                SELECT COUNT(*) FROM document_versions
                WHERE source_hash = :hash
            """),
            {"hash": source_hash},
        )
        count = count_result.fetchone()[0]
        if count <= 1:
            skipped += 1
            continue

        # 3. Deletar chunks
        await db.execute(
            text("DELETE FROM chunks WHERE document_version_id = :vid"),
            {"vid": vid},
        )

        # 4. Deletar versão
        await db.execute(
            text("DELETE FROM document_versions WHERE id = :vid"),
            {"vid": vid},
        )

        storage_paths.append(storage_path)
        deleted += 1

        # 5. Verificar se o documento ficou órfão
        orphan_result = await db.execute(
            text("""
                SELECT COUNT(*) FROM document_versions
                WHERE document_id = :doc_id
            """),
            {"doc_id": str(document_id)},
        )
        remaining = orphan_result.fetchone()[0]
        if remaining == 0:
            await db.execute(
                text("DELETE FROM documents WHERE id = :doc_id"),
                {"doc_id": str(document_id)},
            )
            orphan_documents_deleted += 1

    return {
        "deleted": deleted,
        "skipped": skipped,
        "storage_paths": storage_paths,
        "orphan_documents_deleted": orphan_documents_deleted,
    }
