"""
Kyotech AI — API de Upload de Documentos
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, get_current_user, require_role
from app.core.limiter import limiter
from app.core.config import settings
from app.core.database import get_db
from app.services.ingestion import ingest_document, IngestionResult
from app.services import repository
from app.services.storage import delete_blob
from app.services.semantic_cache import invalidate_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["Upload"])


class UploadResponse(BaseModel):
    success: bool
    message: str
    document_id: Optional[str] = None
    version_id: Optional[str] = None
    total_pages: int = 0
    total_chunks: int = 0
    was_duplicate: bool = False
    retryable: bool = False


class StatsResponse(BaseModel):
    equipments: int
    documents: int
    versions: int
    chunks: int
    docs_without_chunks: int  # novo


class UsageStatsResponse(BaseModel):
    total_sessions: int
    total_messages: int
    thumbs_up: int
    thumbs_down: int


@router.post("/document", response_model=UploadResponse)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(..., description="Arquivo PDF"),
    equipment_key: Optional[str] = Form(None, description="ID do equipamento (ex: frontier-780)"),
    doc_type: Optional[str] = Form(None, description="Tipo: 'manual' ou 'informativo'"),
    published_date: Optional[date] = Form(None, description="Data de publicação (YYYY-MM-DD)"),
    equipment_display_name: Optional[str] = Form(None, description="Nome de exibição do equipamento"),
    _user: CurrentUser = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos.")

    if doc_type is not None and doc_type not in ("manual", "informativo"):
        raise HTTPException(status_code=400, detail="doc_type deve ser 'manual' ou 'informativo'.")

    file_bytes = await file.read()

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    if not file_bytes.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Arquivo inválido: não é um PDF válido")

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"Arquivo excede {settings.max_upload_size_mb}MB.",
        )

    result: IngestionResult = await ingest_document(
        db=db,
        file_bytes=file_bytes,
        filename=file.filename,
        equipment_key=equipment_key.lower().strip() if equipment_key else None,
        doc_type=doc_type,
        published_date=published_date,
        display_name=equipment_display_name,
    )

    if not result.success:
        status_code = 503 if result.retryable else 422
        raise HTTPException(status_code=status_code, detail=result.message)

    return UploadResponse(
        success=result.success,
        message=result.message,
        document_id=result.document_id,
        version_id=result.version_id,
        total_pages=result.total_pages,
        total_chunks=result.total_chunks,
        was_duplicate=result.was_duplicate,
        retryable=result.retryable,
    )


@router.get("/equipments")
async def list_equipments(
    _user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await repository.list_equipments(db)


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    _user: CurrentUser = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    stats = await repository.get_ingestion_stats(db)
    return StatsResponse(**stats)


@router.get("/stats/usage", response_model=UsageStatsResponse)
async def get_usage_stats(
    _user: CurrentUser = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    stats = await repository.get_usage_stats(db)
    return UsageStatsResponse(**stats)


class DocumentVersionItem(BaseModel):
    version_id: str
    source_filename: str
    published_date: Optional[str] = None
    ingested_at: Optional[str] = None
    total_pages: int = 0
    total_chunks: int = 0
    equipment_key: Optional[str] = None
    doc_type: Optional[str] = None
    storage_path: Optional[str] = None


class DocumentListResponse(BaseModel):
    versions: list[DocumentVersionItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class UpdateFilenameRequest(BaseModel):
    source_filename: str


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    _user: CurrentUser = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    result = await repository.list_document_versions(db, page=page, page_size=page_size)
    return DocumentListResponse(**result)


@router.patch("/documents/{version_id}")
async def update_document_filename(
    version_id: str,
    body: UpdateFilenameRequest,
    _user: CurrentUser = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    filename = body.source_filename.strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Nome do arquivo não pode ser vazio.")

    updated = await repository.update_document_version_filename(db, version_id, filename)
    if not updated:
        raise HTTPException(status_code=404, detail="Versão não encontrada.")

    try:
        await invalidate_cache(db)
    except Exception as e:
        logger.warning(f"Falha ao invalidar cache após rename (não crítico): {e}")

    return {"success": True, "version_id": version_id, "source_filename": filename}


class DeleteDuplicatesRequest(BaseModel):
    version_ids: list[str]


class DeleteDuplicatesResponse(BaseModel):
    deleted: int
    skipped: int
    orphan_documents_deleted: int
    message: str


@router.get("/duplicates")
@limiter.limit("10/minute")
async def get_duplicates(
    request: Request,
    _user: CurrentUser = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    return await repository.find_duplicate_groups(db)


@router.delete("/duplicates", response_model=DeleteDuplicatesResponse)
@limiter.limit("5/minute")
async def delete_duplicates(
    request: Request,
    body: DeleteDuplicatesRequest,
    _user: CurrentUser = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    if not body.version_ids:
        raise HTTPException(status_code=400, detail="Nenhuma versão informada.")

    result = await repository.delete_duplicate_versions(db, body.version_ids)
    await db.commit()

    # Deletar blobs do Azure (fora da transação SQL)
    for path in result["storage_paths"]:
        try:
            await delete_blob(path)
        except Exception as e:
            logger.warning(f"Falha ao deletar blob {path}: {e}")

    # Invalidar cache semântico
    try:
        await invalidate_cache(db)
    except Exception as e:
        logger.warning(f"Falha ao invalidar cache (não crítico): {e}")

    return DeleteDuplicatesResponse(
        deleted=result["deleted"],
        skipped=result["skipped"],
        orphan_documents_deleted=result["orphan_documents_deleted"],
        message=f"{result['deleted']} duplicata(s) removida(s).",
    )
