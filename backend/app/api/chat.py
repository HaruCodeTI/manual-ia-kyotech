"""
Kyotech AI — API de Chat (RAG)
Conforme Seção 7 — Fluxo RAG completo:

1. Técnico pergunta em português
2. Query rewriting (PT → EN)
3. Classificação Manual vs Informativo
4. Busca híbrida (vetorial + textual)
5. Geração de resposta em português
6. Citações com documento, versão, página
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.query_rewriter import rewrite_query
from app.services.search import hybrid_search
from app.services.generator import generate_response, Citation
from app.services.storage import generate_signed_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat RAG"])


# ── Request / Response Models ──

class ChatRequest(BaseModel):
    question: str
    equipment_filter: Optional[str] = None  # Filtro opcional por equipamento

    class Config:
        json_schema_extra = {
            "example": {
                "question": "Como trocar o rolo de pressão?",
                "equipment_filter": None,
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


class ChatResponse(BaseModel):
    answer: str
    citations: List[CitationResponse]
    query_original: str
    query_rewritten: str
    total_sources: int
    model_used: str


# ── Endpoint ──

@router.post("/ask", response_model=ChatResponse)
async def ask_question(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint principal do chat RAG.
    
    Recebe uma pergunta em português e retorna resposta com citações.
    O fluxo completo é executado automaticamente:
    rewrite → search → generate.
    """
    question = request.question.strip()
    logger.info(f"Pergunta recebida: {question}")

    # Passo 1: Reescrever query
    rewritten = await rewrite_query(question)
    logger.info(
        f"Query reescrita: '{rewritten.query_en}' "
        f"(tipo: {rewritten.doc_type}, equip: {rewritten.equipment_hint})"
    )

    # Usar filtro explícito do request se fornecido, senão usar o detectado
    equipment_filter = request.equipment_filter or rewritten.equipment_hint

    # Passo 2: Busca híbrida
    # MVP: não filtra por doc_type (poucos documentos, classificação imprecisa)
    # Fase 2: habilitar filtro quando base for maior
    results = await hybrid_search(
        db=db,
        query_en=rewritten.query_en,
        query_original=question,
        limit=8,
        doc_type=None,
        equipment_key=equipment_filter,
    )
    logger.info(f"Resultados encontrados: {len(results)}")

    # Passo 3: Gerar resposta
    rag_response = await generate_response(
        question=question,
        query_rewritten=rewritten.query_en,
        search_results=results,
    )

    # Converter citações
    citations = [
        CitationResponse(
            source_index=c.source_index,
            source_filename=c.source_filename,
            page_number=c.page_number,
            equipment_key=c.equipment_key,
            doc_type=c.doc_type,
            published_date=c.published_date,
            storage_path=c.storage_path,
        )
        for c in rag_response.citations
    ]

    return ChatResponse(
        answer=rag_response.answer,
        citations=citations,
        query_original=rag_response.query_original,
        query_rewritten=rag_response.query_rewritten,
        total_sources=rag_response.total_sources,
        model_used=rag_response.model_used,
    )


@router.get("/pdf-url")
async def get_pdf_url(storage_path: str, page: int = 1):
    """Gera uma URL temporária (SAS) para visualização de um PDF."""
    try:
        url = generate_signed_url(storage_path, expiry_hours=1)
        return {"url": f"{url}#page={page}"}
    except Exception as e:
        logger.error(f"Erro ao gerar SAS URL: {e}")
        raise HTTPException(status_code=500, detail="Erro ao gerar link do PDF.")
