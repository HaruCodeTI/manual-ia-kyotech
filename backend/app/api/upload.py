"""
Kyotech AI — API de Upload de Documentos
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, get_current_user, require_role
from app.core.database import get_db
from app.services.ingestion import ingest_document, IngestionResult
from app.services import repository

router = APIRouter(prefix="/upload", tags=["Upload"])


class UploadResponse(BaseModel):
    success: bool
    message: str
    document_id: Optional[str] = None
    version_id: Optional[str] = None
    total_pages: int = 0
    total_chunks: int = 0
    was_duplicate: bool = False


class StatsResponse(BaseModel):
    equipments: int
    documents: int
    versions: int
    chunks: int


@router.post("/document", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(..., description="Arquivo PDF"),
    equipment_key: str = Form(..., description="ID do equipamento (ex: frontier-780)"),
    doc_type: str = Form(..., description="Tipo: 'manual' ou 'informativo'"),
    published_date: date = Form(..., description="Data de publicação (YYYY-MM-DD)"),
    equipment_display_name: Optional[str] = Form(None, description="Nome de exibição do equipamento"),
    _user: CurrentUser = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos.")

    if doc_type not in ("manual", "informativo"):
        raise HTTPException(status_code=400, detail="doc_type deve ser 'manual' ou 'informativo'.")

    file_bytes = await file.read()

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    if len(file_bytes) > 100 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Arquivo excede 100MB.")

    result: IngestionResult = await ingest_document(
        db=db,
        file_bytes=file_bytes,
        filename=file.filename,
        equipment_key=equipment_key.lower().strip(),
        doc_type=doc_type,
        published_date=published_date,
        display_name=equipment_display_name,
    )

    if not result.success:
        raise HTTPException(status_code=422, detail=result.message)

    return UploadResponse(
        success=result.success,
        message=result.message,
        document_id=result.document_id,
        version_id=result.version_id,
        total_pages=result.total_pages,
        total_chunks=result.total_chunks,
        was_duplicate=result.was_duplicate,
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
