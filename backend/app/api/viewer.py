"""
Kyotech AI — API de Viewer (Proxy de PDF como imagem)

Endpoint que renderiza páginas de PDF como imagens PNG com watermark.
Nenhum PDF ou SAS URL é exposto ao frontend.

Cache LRU em memória para evitar re-download do mesmo PDF
ao navegar entre páginas (TTL de 5 minutos, máximo 10 PDFs).
"""
from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, get_current_user
from app.core.database import get_db
from app.services.repository import get_version_info
from app.services.storage import download_blob
from app.services.viewer import render_page_as_image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/viewer", tags=["Viewer"])

# Cache LRU simples: {storage_path: (pdf_bytes, timestamp)}
_pdf_cache: OrderedDict[str, tuple[bytes, float]] = OrderedDict()
_CACHE_MAX_SIZE = 10
_CACHE_TTL_SECONDS = 300  # 5 minutos


async def _get_pdf_bytes(storage_path: str) -> bytes:
    """Obtém bytes do PDF com cache LRU em memória."""
    now = time.monotonic()

    # Verificar cache
    if storage_path in _pdf_cache:
        pdf_bytes, cached_at = _pdf_cache[storage_path]
        if now - cached_at < _CACHE_TTL_SECONDS:
            _pdf_cache.move_to_end(storage_path)
            logger.debug(f"Cache hit para {storage_path}")
            return pdf_bytes
        else:
            del _pdf_cache[storage_path]

    # Download do blob
    pdf_bytes = await download_blob(storage_path)

    # Guardar no cache
    _pdf_cache[storage_path] = (pdf_bytes, now)
    if len(_pdf_cache) > _CACHE_MAX_SIZE:
        _pdf_cache.popitem(last=False)  # Remove o mais antigo

    return pdf_bytes


class ViewerInfoResponse(BaseModel):
    version_id: str
    source_filename: str
    equipment_key: Optional[str]
    doc_type: Optional[str]
    published_date: str
    total_pages: int


@router.get("/info/{version_id}")
async def get_document_info(
    version_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ViewerInfoResponse:
    """
    Retorna metadados do documento (total de páginas, nome, etc.)
    sem expor storage_path ou URL do blob.
    """
    info = await get_version_info(db, version_id)
    if not info:
        raise HTTPException(status_code=404, detail="Versão não encontrada.")

    # Contar páginas do PDF real (baixar via cache e verificar)
    try:
        pdf_bytes = await _get_pdf_bytes(info["storage_path"])
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = len(doc)
        doc.close()
    except Exception as e:
        logger.error(f"Erro ao obter total de páginas: {e}")
        raise HTTPException(status_code=500, detail="Erro ao acessar documento.")

    return ViewerInfoResponse(
        version_id=str(version_id),
        source_filename=info["source_filename"],
        equipment_key=info["equipment_key"],
        doc_type=info["doc_type"],
        published_date=str(info["published_date"]),
        total_pages=total_pages,
    )


@router.get("/page/{version_id}/{page_number}")
async def get_page_image(
    version_id: UUID,
    page_number: int,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Renderiza uma página do PDF como imagem PNG com watermark dinâmico.

    O PDF é baixado server-side do Azure Blob Storage, renderizado em memória
    com PyMuPDF, e a imagem resultante é retornada ao frontend.
    Nenhum PDF, SAS URL ou storage_path é exposto.
    """
    # Buscar info da versão no banco
    info = await get_version_info(db, version_id)
    if not info:
        raise HTTPException(status_code=404, detail="Versão não encontrada.")

    # Baixar PDF do Azure Blob via cache (server-side, sem SAS URL)
    try:
        pdf_bytes = await _get_pdf_bytes(info["storage_path"])
    except Exception as e:
        logger.error(f"Erro ao baixar PDF (version={version_id}): {e}")
        raise HTTPException(status_code=500, detail="Erro ao acessar documento.")

    # Renderizar página como imagem PNG com watermark
    try:
        png_bytes, total_pages = render_page_as_image(
            pdf_bytes=pdf_bytes,
            page_number=page_number,
            user_id=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao renderizar página {page_number} (version={version_id}): {e}")
        raise HTTPException(status_code=500, detail="Erro ao renderizar página.")

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "X-Total-Pages": str(total_pages),
            "X-Content-Type-Options": "nosniff",
        },
    )
