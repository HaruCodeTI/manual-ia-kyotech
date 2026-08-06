"""
Kyotech AI — Repositório de Dados
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from datetime import date
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chunker import TextChunk

logger = logging.getLogger(__name__)

# Sufixos de revisão que não fazem parte da identidade do documento:
# "_V2.0", " Ver.1.7", "-ver 4.2", " (1)", " copy", "cópia de ".
# Nota: nada de \b depois do separador — "_" é caractere de palavra, então
# não existe fronteira entre "_" e "V" e o sufixo "_V2.0" escapava.
_VERSION_SUFFIX = re.compile(
    r"(?:(?:^|[\s_\-]+)v(?:er)?\.?\s*\d+(?:[._]\d+)*)"
    r"|(?:\s*\(\d+\))"
    r"|(?:(?:^|[\s_\-]+)cop(?:y|ia)(?=[\s_\-]|$))",
    re.IGNORECASE,
)


def normalize_doc_key(filename: str) -> str:
    """
    Identidade estável de um documento a partir do nome do arquivo.

    É a chave de versionamento: dois arquivos com o mesmo doc_key são a mesma
    obra em revisões diferentes; doc_keys diferentes são documentos distintos.
    Não usamos (doc_type, equipment_key) para isso — são grosseiros demais e
    fundiam arquivos sem relação na mesma versão. Também não usamos
    source_hash, que muda a cada revisão, que é justamente o que queremos
    reconhecer como "mesmo documento".
    """
    stem = os.path.splitext(filename)[0]
    # "cópia de X" / "copy of X" viram só X
    stem = re.sub(r"^\s*(?:c[oó]pia\s+de|copy\s+of)\s+", "", stem, flags=re.IGNORECASE)
    stem = unicodedata.normalize("NFKD", stem)
    stem = "".join(c for c in stem if not unicodedata.combining(c))
    stem = _VERSION_SUFFIX.sub(" ", stem)
    stem = re.sub(r"[^a-z0-9]+", " ", stem.lower()).strip()
    # Nome degenerado (só versão/números) — cai no arquivo inteiro para não
    # colapsar documentos distintos numa chave vazia.
    return stem or re.sub(r"[^a-z0-9]+", " ", filename.lower()).strip()


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
    source_filename: str,
) -> UUID:
    """
    Resolve a identidade do documento pelo nome de arquivo normalizado.

    A versão anterior agrupava por (doc_type, equipment_key), o que fundia
    arquivos sem relação nenhuma: todo upload com doc_type='manual' e sem
    equipamento caía no mesmo document_id e, via ON CONFLICT em create_version,
    na mesma linha de versão. Uma única versão em prod acumulou 373 chunks de
    cinco documentos diferentes, exibidos sob o nome de quem gravou por último.
    doc_type e equipment_key seguem existindo, mas só como metadado de boost
    no ranking — nunca como identidade.
    """
    doc_key = normalize_doc_key(source_filename)

    result = await db.execute(
        text("SELECT id FROM documents WHERE doc_key = :doc_key"),
        {"doc_key": doc_key},
    )
    row = result.fetchone()
    if row:
        # Preenche metadado que faltava em uploads anteriores, sem sobrescrever
        # o que já existe com um valor nulo.
        await db.execute(
            text("""
                UPDATE documents
                SET doc_type = COALESCE(doc_type, :doc_type),
                    equipment_key = COALESCE(equipment_key, :equipment_key)
                WHERE id = :id
            """),
            {"doc_type": doc_type, "equipment_key": equipment_key, "id": row[0]},
        )
        return row[0]

    result = await db.execute(
        text("""
            INSERT INTO documents (doc_type, equipment_key, doc_key)
            VALUES (:doc_type, :equipment_key, :doc_key)
            ON CONFLICT (doc_key) DO UPDATE SET doc_key = EXCLUDED.doc_key
            RETURNING id
        """),
        {"doc_type": doc_type, "equipment_key": equipment_key, "doc_key": doc_key},
    )
    doc_id = result.fetchone()[0]
    logger.info(f"Documento criado: {doc_key!r} ({doc_type} / {equipment_key}) → {doc_id}")
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
    """
    Cria a versão. O conflito é por conteúdo (source_hash), não por data.

    A chave anterior — (document_id, published_date) — fundia arquivos
    distintos: published_date cai em date.today() quando não vem no upload
    (ingestion.py), então tudo que subia no mesmo dia sob o mesmo documento
    colidia e sobrescrevia a linha anterior, deixando os chunks do arquivo
    antigo apontando para um nome de arquivo que não é o deles.

    Com (document_id, source_hash) o conflito só acontece no reenvio do
    mesmo arquivo, e aí é no-op — não sobrescreve nada.
    """
    result = await db.execute(
        text("""
            INSERT INTO document_versions
                (document_id, published_date, source_hash, source_filename, storage_path)
            VALUES
                (:doc_id, :pub_date, :hash, :filename, :path)
            ON CONFLICT (document_id, source_hash) DO UPDATE
            SET source_filename = document_versions.source_filename
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
                ORDER BY COALESCE(dv.created_at, dv.published_date) DESC
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


async def list_document_versions(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
) -> Dict:
    offset = (page - 1) * page_size

    total_result = await db.execute(text("SELECT COUNT(*) FROM document_versions"))
    total = total_result.fetchone()[0]

    result = await db.execute(
        text("""
            SELECT
                dv.id, dv.source_filename, dv.published_date,
                dv.ingested_at,
                COUNT(c.id) AS total_chunks,
                COUNT(DISTINCT c.page_number) AS total_pages,
                d.equipment_key, d.doc_type, dv.storage_path
            FROM document_versions dv
            JOIN documents d ON dv.document_id = d.id
            LEFT JOIN chunks c ON c.document_version_id = dv.id
            GROUP BY dv.id, dv.source_filename, dv.published_date,
                     dv.ingested_at, d.equipment_key, d.doc_type, dv.storage_path
            ORDER BY dv.ingested_at DESC NULLS LAST
            LIMIT :limit OFFSET :offset
        """),
        {"limit": page_size, "offset": offset},
    )
    rows = result.fetchall()

    versions = [
        {
            "version_id": str(row[0]),
            "source_filename": row[1],
            "published_date": row[2].isoformat() if row[2] else None,
            "ingested_at": row[3].isoformat() if row[3] else None,
            "total_chunks": int(row[4]),
            "total_pages": int(row[5]),
            "equipment_key": row[6],
            "doc_type": row[7],
            "storage_path": row[8],
        }
        for row in rows
    ]

    return {
        "versions": versions,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


async def update_document_version_filename(
    db: AsyncSession,
    version_id: str,
    new_filename: str,
) -> bool:
    result = await db.execute(
        text("""
            UPDATE document_versions
            SET source_filename = :filename
            WHERE id = :vid
            RETURNING id
        """),
        {"filename": new_filename, "vid": version_id},
    )
    updated = result.fetchone()
    if not updated:
        return False
    await db.commit()
    return True
