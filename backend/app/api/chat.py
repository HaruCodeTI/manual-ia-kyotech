"""
Kyotech AI — API de Chat (RAG)
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional, Union
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, get_current_user
from app.core.config import settings
from app.core.database import get_db, async_session
from app.services.embedder import get_openai_client
from app.services.query_rewriter import rewrite_query
from app.services.diagnostic_analyzer import decompose_problems, is_diagnostic_query
from app.services.search import hybrid_search, SearchResult
from app.services.generator import generate_response, Citation, build_clarification_from_weak_results
from app.services.version_comparator import (
    compare_versions,
    detect_multi_version,
    group_chunks_by_version,
)
from app.services.storage import generate_signed_url
from app.services import chat_repository
from app.services.semantic_cache import get_cached_response

logger = logging.getLogger(__name__)

CLARIFICATION_THRESHOLD = 0.25

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
    equipment_key: Optional[str] = None
    doc_type: Optional[str] = None
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
    message_id: str
    needs_clarification: bool = False  # NEW


def _build_conversation_context(
    history_messages: list,
    history_summary: Optional[str],
) -> Optional[str]:
    """Formata histórico como string para o query rewriter."""
    if not history_messages and not history_summary:
        return None
    parts = []
    if history_summary:
        parts.append(f"Resumo anterior: {history_summary}")
    for m in history_messages:
        role = "User" if m["role"] == "user" else "Assistant"
        parts.append(f"{role}: {m['content']}")
    return "\n".join(parts)


async def _generate_summary(
    messages: list,
    existing_summary: Optional[str] = None,
) -> str:
    """Gera summary incremental usando gpt-4o-mini."""
    formatted = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
        for m in messages
    )

    if existing_summary:
        prompt = (
            f"Você tem um resumo existente de uma conversa técnica e novas mensagens para incorporar.\n"
            f"Atualize o resumo incluindo os novos tópicos. Máximo 5 frases. Português brasileiro.\n\n"
            f"Resumo existente:\n{existing_summary}\n\n"
            f"Novas mensagens:\n{formatted}"
        )
    else:
        prompt = (
            f"Resuma em 3-5 frases os principais tópicos técnicos discutidos.\n"
            f"Inclua: equipamentos mencionados, problemas identificados, soluções discutidas.\n"
            f"Seja conciso e factual. Responda em português brasileiro.\n\n"
            f"Conversa:\n{formatted}"
        )

    client = get_openai_client()
    response = await client.chat.completions.create(
        model=settings.azure_openai_mini_deployment,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=300,
    )
    return response.choices[0].message.content.strip()


async def _maybe_update_summary(session_id: Union[UUID, str]) -> None:
    """
    Verifica se precisa sumarizar e persiste o resultado.
    Abre sua própria sessão DB — NÃO reutiliza a sessão da request.
    """
    if not isinstance(session_id, UUID):
        session_id = UUID(str(session_id))

    async with async_session() as db:
        try:
            session_info = await chat_repository.get_session_summary(db, session_id)
            last_summarized = session_info.get("last_summarized_at")
            unsummarized_count = await chat_repository.count_messages_since(
                db, session_id, since=last_summarized
            )
            if unsummarized_count < 6:
                return
            new_messages = await chat_repository.get_messages_before_recent(
                db, session_id, skip_last=6, since=last_summarized
            )
            if not new_messages:
                return
            summary = await _generate_summary(
                new_messages,
                existing_summary=session_info.get("history_summary"),
            )
            await chat_repository.update_history_summary(db, session_id, summary)
            logger.info(f"Summary atualizado para sessão {session_id}")
        except Exception as e:
            logger.error(f"Erro ao atualizar summary da sessão {session_id}: {e}")
            await db.rollback()


@router.post("/ask", response_model=ChatResponse)
async def ask_question(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
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

    # Buscar histórico ANTES de inserir a mensagem atual
    history_messages = []
    history_summary = None
    if request.session_id:
        history_messages = await chat_repository.get_recent_messages(db, session_id, limit=6)
        session_info = await chat_repository.get_session_summary(db, session_id)
        history_summary = session_info.get("history_summary")

    # Persistir mensagem do usuário
    await chat_repository.add_message(db, session_id, "user", question)

    # RAG pipeline
    conversation_context = _build_conversation_context(history_messages, history_summary)
    rewritten = await rewrite_query(question, conversation_context=conversation_context)
    logger.info(
        f"Query reescrita: '{rewritten.query_en}' "
        f"(tipo: {rewritten.doc_type}, equip: {rewritten.equipment_hint}, "
        f"clarification: {rewritten.needs_clarification}, "
        f"comparison: {rewritten.is_comparison_query})"
    )

    # Verificar semantic cache — bypass para queries de comparação (diff muda com novas versões)
    cached = None
    if not rewritten.is_comparison_query:
        cached = await get_cached_response(db, question)
    if cached:
        logger.info(f"[{user.id}] Cache HIT — retornando resposta cacheada")
        cached_metadata = {
            "query_rewritten": cached["query_rewritten"],
            "total_sources": len(cached["citations"]),
            "model_used": cached["model_used"],
        }
        assistant_msg_id = await chat_repository.add_message(
            db, session_id, "assistant", cached["answer"],
            citations=cached["citations"], metadata=cached_metadata,
        )
        cached_citations = [
            CitationResponse(
                source_index=c.get("source_index", 0),
                source_filename=c.get("source_filename", ""),
                page_number=c.get("page_number", 0),
                equipment_key=c.get("equipment_key"),
                doc_type=c.get("doc_type"),
                published_date=c.get("published_date", ""),
                storage_path=c.get("storage_path", ""),
                document_version_id=c.get("document_version_id", ""),
            )
            for c in cached["citations"]
        ] if cached["citations"] else []
        background_tasks.add_task(_maybe_update_summary, session_id)
        return ChatResponse(
            answer=cached["answer"],
            citations=cached_citations,
            query_original=question,
            query_rewritten=cached["query_rewritten"],
            total_sources=len(cached_citations),
            model_used=cached["model_used"],
            session_id=str(session_id),
            message_id=str(assistant_msg_id),
        )

    # Ponto de saída 1: rewriter detectou ambiguidade
    if rewritten.needs_clarification and rewritten.clarification_question:
        clarification_msg_id = await chat_repository.add_message(
            db, session_id, "assistant", rewritten.clarification_question,
            metadata={"is_clarification": True},
        )
        background_tasks.add_task(_maybe_update_summary, session_id)
        return ChatResponse(
            answer=rewritten.clarification_question,
            citations=[],
            query_original=question,
            query_rewritten=rewritten.query_en,
            total_sources=0,
            model_used=settings.azure_openai_mini_deployment,
            session_id=str(session_id),
            message_id=str(clarification_msg_id),
            needs_clarification=True,
        )

    equipment_filter = request.equipment_filter or rewritten.equipment_hint

    diagnostic_mode = False
    try:
        if is_diagnostic_query(question):
            sub_queries = await decompose_problems(question)
            per_query_limit = max(4, 8 // len(sub_queries))
            all_results = await asyncio.gather(*[
                hybrid_search(
                    db=db,
                    query_en=q,
                    query_original=question,
                    limit=per_query_limit,
                    doc_type=rewritten.doc_type,
                    equipment_key=equipment_filter,
                )
                for q in sub_queries
            ])
            merged: dict[str, SearchResult] = {}
            for batch in all_results:
                for r in batch:
                    if r.chunk_id not in merged or r.similarity > merged[r.chunk_id].similarity:
                        merged[r.chunk_id] = r
            results = sorted(merged.values(), key=lambda r: r.similarity, reverse=True)[:8]
            diagnostic_mode = True
            logger.info(f"Pipeline diagnóstico: {len(sub_queries)} sub-queries, {len(results)} resultados fundidos")
        else:
            results = await hybrid_search(
                db=db,
                query_en=rewritten.query_en,
                query_original=question,
                limit=8,
                doc_type=rewritten.doc_type,
                equipment_key=equipment_filter,
                include_all_versions=rewritten.is_comparison_query,
            )
    except Exception as exc:
        logger.warning(f"Falha no pipeline diagnóstico, usando pipeline normal: {exc}")
        # Fallback não repassa include_all_versions — diagnóstico e comparação são mutuamente exclusivos
        results = await hybrid_search(
            db=db,
            query_en=rewritten.query_en,
            query_original=question,
            limit=8,
            doc_type=rewritten.doc_type,
            equipment_key=equipment_filter,
        )
        diagnostic_mode = False

    logger.info(f"Resultados encontrados: {len(results)}")

    # Ponto de saída 2: resultados fracos
    top_score = max((r.similarity for r in results), default=0.0)
    if results and top_score < CLARIFICATION_THRESHOLD:
        clarification = build_clarification_from_weak_results(question)
        clarification_msg_id = await chat_repository.add_message(
            db, session_id, "assistant", clarification,
            metadata={"is_clarification": True},
        )
        background_tasks.add_task(_maybe_update_summary, session_id)
        return ChatResponse(
            answer=clarification,
            citations=[],
            query_original=question,
            query_rewritten=rewritten.query_en,
            total_sources=0,
            model_used="deterministic",
            session_id=str(session_id),
            message_id=str(clarification_msg_id),
            needs_clarification=True,
        )

    # Pipeline de comparação de versões (opcional — fallback se falhar)
    version_diff = None
    try:
        if rewritten.is_comparison_query and detect_multi_version(results):
            grouped = group_chunks_by_version(results)
            version_diff = await compare_versions(grouped)
            logger.info(
                f"Version diff: {version_diff.version_old} → {version_diff.version_new} | "
                f"has_changes={version_diff.has_changes} | items={len(version_diff.diff_items)}"
            )
    except Exception as exc:
        logger.warning(f"Comparação de versões falhou, seguindo sem diff: {exc}")
        version_diff = None

    rag_response = await generate_response(
        question=question,
        query_rewritten=rewritten.query_en,
        search_results=results,
        history_messages=history_messages,
        history_summary=history_summary,
        diagnostic_mode=diagnostic_mode,
        version_diff=version_diff,
        is_comparison_query=rewritten.is_comparison_query,
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
        "diagnostic_mode": diagnostic_mode,
    }
    assistant_msg_id = await chat_repository.add_message(
        db, session_id, "assistant", rag_response.answer,
        citations=citations_json, metadata=metadata_json,
    )

    background_tasks.add_task(_maybe_update_summary, session_id)
    return ChatResponse(
        answer=rag_response.answer,
        citations=citations,
        query_original=rag_response.query_original,
        query_rewritten=rag_response.query_rewritten,
        total_sources=rag_response.total_sources,
        model_used=rag_response.model_used,
        session_id=str(session_id),
        message_id=str(assistant_msg_id),
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
