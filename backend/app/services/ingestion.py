"""
Kyotech AI — Pipeline de Ingestion (Orquestrador)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.pdf_extractor import extract_text_from_pdf
from app.services.chunker import chunk_pages
from app.services.embedder import generate_embeddings
from app.services.storage import upload_pdf
from app.services.semantic_cache import invalidate_cache
from app.services import repository

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    success: bool
    message: str
    document_id: Optional[str] = None
    version_id: Optional[str] = None
    total_pages: int = 0
    total_chunks: int = 0
    was_duplicate: bool = False


async def ingest_document(
    db: AsyncSession,
    file_bytes: bytes,
    filename: str,
    equipment_key: Optional[str] = None,
    doc_type: Optional[str] = None,
    published_date: Optional[date] = None,
    display_name: Optional[str] = None,
) -> IngestionResult:
    try:
        effective_date = published_date or date.today()

        # Passo 1: Extrair texto
        logger.info(f"[1/6] Extraindo texto: {filename}")
        extraction = extract_text_from_pdf(file_bytes, filename)
        logger.info(f"  → {extraction.total_pages} páginas, {len(extraction.pages)} com texto")

        # Passo 2: Garantir equipamento (apenas se fornecido)
        if equipment_key:
            logger.info(f"[2/6] Verificando equipamento: {equipment_key}")
            await repository.find_or_create_equipment(db, equipment_key, display_name)
        else:
            logger.info("[2/6] Sem equipment_key — pulando criação de equipamento")

        # Passo 3: Buscar/criar documento
        logger.info(f"[3/6] Registrando documento: {doc_type} / {equipment_key}")
        document_id = await repository.find_or_create_document(db, doc_type, equipment_key)

        # Verificar duplicata
        is_duplicate = await repository.check_version_exists(db, document_id, extraction.source_hash)
        if is_duplicate:
            logger.warning(f"  ⚠ Duplicata detectada: {filename}")
            return IngestionResult(
                success=True,
                message=f"Documento '{filename}' já foi ingerido anteriormente.",
                was_duplicate=True,
            )

        # Passo 4: Upload Blob Storage
        logger.info(f"[4/6] Upload para Blob Storage")
        folder = equipment_key or "misc"
        storage_path = f"{folder}/{effective_date.isoformat()}/{filename}"
        full_path = await upload_pdf(file_bytes, storage_path)

        # Passo 5: Criar versão
        logger.info(f"[5/6] Criando versão no banco")
        version_id = await repository.create_version(
            db=db,
            document_id=document_id,
            published_date=effective_date,
            source_hash=extraction.source_hash,
            source_filename=filename,
            storage_path=full_path,
        )
        await db.commit()

        # Passo 6: Chunking + Embeddings
        logger.info(f"[6/6] Chunking e embeddings")
        chunks = chunk_pages(
            extraction.pages,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        logger.info(f"  → {len(chunks)} chunks gerados")

        if chunks:
            texts = [c.content for c in chunks]
            embeddings = await generate_embeddings(texts)
            await repository.insert_chunks_with_embeddings(db, version_id, chunks, embeddings)

        logger.info(f"✅ Ingestion completa: {filename} → {len(chunks)} chunks")

        # Passo 7: Detectar equipamentos nos chunks
        if chunks:
            from app.services.equipment_detector import detect_mentions_for_version
            logger.info(f"[7/7] Detectando equipamentos nos chunks")
            detected = await detect_mentions_for_version(db, str(version_id))
            logger.info(f"  → {detected} chunks com equipamentos detectados")

        # Invalidar cache semântico — novo documento pode melhorar respostas futuras
        # try/except isolado: falha no cache não deve retornar erro de ingestion
        try:
            await invalidate_cache(db)
        except Exception as cache_err:
            logger.warning(f"Falha ao invalidar cache semântico (não crítico): {cache_err}")

        return IngestionResult(
            success=True,
            message=f"Documento '{filename}' ingerido com sucesso.",
            document_id=str(document_id),
            version_id=str(version_id),
            total_pages=extraction.total_pages,
            total_chunks=len(chunks),
        )

    except ValueError as e:
        logger.error(f"Erro de validação: {e}")
        return IngestionResult(success=False, message=str(e))
    except Exception as e:
        logger.error(f"Erro inesperado: {e}", exc_info=True)
        await db.rollback()
        return IngestionResult(
            success=False,
            message=f"Erro ao processar '{filename}'. Tente novamente ou contate o suporte.",
        )
