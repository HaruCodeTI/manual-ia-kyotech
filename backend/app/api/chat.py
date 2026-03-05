"""
Kyotech AI — API de Chat (RAG)
"""
from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, get_current_user
from app.core.database import get_db
from app.services.query_rewriter import rewrite_query
from app.services.search import hybrid_search
from app.services.generator import generate_response, Citation
from app.services.storage import generate_signed_url
from app.services import chat_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat RAG"])


class ChatRequest(BaseModel):
    question: str
    equipment_filter: Optional[str] = None
    session_id: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "question": "Como trocar o rolo de pressão?",
                "equipment_filter": None,
                "session_id": None,
            }
        }


class CitationResponse(BaseModel):
    source_index: int
    source_filename: str
    page_number: int
    equipment_key: str
    doc_type: str
    published_date: str
    storage_path: str
    document_version_id: str = ""


class ChatResponse(BaseModel):
    answer: str
    citations: List[CitationResponse]
    query_original: str
    query_rewritten: str
    total_sources: int
    model_used: str
    session_id: str


@router.post("/ask", response_model=ChatResponse)
async def ask_question(
    request: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    question = request.question.strip()
    logger.info(f"[{user.id}] Pergunta: {question}")

    # Resolver sessão
    if request.session_id:
        session_id = UUID(request.session_id)
    else:
        title = question[:80] + ("…" if len(question) > 80 else "")
        session_id = await chat_repository.create_session(db, user.id, title)

    # Persistir mensagem do usuário
    await chat_repository.add_message(db, session_id, "user", question)

    # RAG pipeline
    rewritten = await rewrite_query(question)
    logger.info(
        f"Query reescrita: '{rewritten.query_en}' "
        f"(tipo: {rewritten.doc_type}, equip: {rewritten.equipment_hint})"
    )

    equipment_filter = request.equipment_filter or rewritten.equipment_hint

    results = await hybrid_search(
        db=db,
        query_en=rewritten.query_en,
        query_original=question,
        limit=8,
        doc_type=None,
        equipment_key=equipment_filter,
    )
    logger.info(f"Resultados encontrados: {len(results)}")

    rag_response = await generate_response(
        question=question,
        query_rewritten=rewritten.query_en,
        search_results=results,
    )

    citations = [
        CitationResponse(
            source_index=c.source_index,
            source_filename=c.source_filename,
            page_number=c.page_number,
            equipment_key=c.equipment_key,
            doc_type=c.doc_type,
            published_date=c.published_date,
            storage_path=c.storage_path,
            document_version_id=c.document_version_id,
        )
        for c in rag_response.citations
    ]

    # Persistir resposta do assistente
    citations_json = [c.model_dump() for c in citations]
    metadata_json = {
        "query_rewritten": rag_response.query_rewritten,
        "total_sources": rag_response.total_sources,
        "model_used": rag_response.model_used,
    }
    await chat_repository.add_message(
        db, session_id, "assistant", rag_response.answer,
        citations=citations_json, metadata=metadata_json,
    )

    return ChatResponse(
        answer=rag_response.answer,
        citations=citations,
        query_original=rag_response.query_original,
        query_rewritten=rag_response.query_rewritten,
        total_sources=rag_response.total_sources,
        model_used=rag_response.model_used,
        session_id=str(session_id),
    )


@router.get("/pdf-url")
async def get_pdf_url(
    storage_path: str,
    page: int = 1,
    _user: CurrentUser = Depends(get_current_user),
):
    try:
        url = generate_signed_url(storage_path, expiry_hours=1)
        return {"url": f"{url}#page={page}"}
    except Exception as e:
        logger.error(f"Erro ao gerar SAS URL: {e}")
        raise HTTPException(status_code=500, detail="Erro ao gerar link do PDF.")
