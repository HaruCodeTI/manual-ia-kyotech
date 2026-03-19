"""
Kyotech AI — API de Feedback
"""
from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.auth import CurrentUser, get_current_user
from app.core.database import get_db
from app.services.feedback_repository import record_feedback
from app.services.semantic_cache import cache_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Feedback"])


class FeedbackRequest(BaseModel):
    message_id: str
    rating: Literal["thumbs_up", "thumbs_down"]


class FeedbackResponse(BaseModel):
    accepted: bool
    message: str


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        message_id = UUID(request.message_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="message_id inválido")

    # Verifica que a mensagem pertence a uma sessão do usuário (segurança)
    ownership = await db.execute(
        text("""
            SELECT cm.id, cm.content, cm.citations, cm.metadata,
                   -- busca a pergunta do usuário (mensagem anterior)
                   (SELECT content FROM chat_messages
                    WHERE session_id = cm.session_id
                      AND role = 'user'
                      AND created_at < cm.created_at
                    ORDER BY created_at DESC LIMIT 1) AS user_question
            FROM chat_messages cm
            JOIN chat_sessions cs ON cm.session_id = cs.id
            WHERE cm.id = :msg_id
              AND cs.user_id = :user_id
              AND cm.role = 'assistant'
        """),
        {"msg_id": str(message_id), "user_id": user.id},
    )
    row = ownership.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail="Mensagem não encontrada ou sem permissão"
        )

    answer = row[1]
    citations = row[2] or []
    metadata = row[3] or {}
    user_question = row[4]

    # Salvar feedback + atualizar quality_score em transação única
    inserted = await record_feedback(db, message_id, request.rating)
    if not inserted:
        return FeedbackResponse(
            accepted=False,
            message="Feedback já registrado para esta mensagem"
        )

    # Se 👍 e há pergunta do usuário: cachear a resposta
    if request.rating == "thumbs_up" and user_question:
        query_rewritten = metadata.get("query_rewritten", "")
        model_used = metadata.get("model_used", "")
        try:
            await cache_response(
                db=db,
                question=user_question,
                answer=answer,
                citations=citations,
                query_rewritten=query_rewritten,
                model_used=model_used,
            )
        except Exception as e:
            # Não falha o feedback se o cache falhar
            logger.error(f"Erro ao cachear resposta: {e}")

    logger.info(
        f"[{user.id}] Feedback '{request.rating}' registrado para mensagem {message_id}"
    )
    return FeedbackResponse(accepted=True, message="Feedback registrado com sucesso")
