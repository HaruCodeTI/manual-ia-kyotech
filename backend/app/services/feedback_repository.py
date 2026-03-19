"""
Kyotech AI — Repositório de Feedback e Quality Scoring
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

QUALITY_DELTA_UP = 0.05    # incremento por 👍
QUALITY_DELTA_DOWN = 0.03  # decremento por 👎 (menor para não suprimir conteúdo novo)
QUALITY_MIN = -1.0
QUALITY_MAX = 2.0


async def record_feedback(
    db: AsyncSession,
    message_id: UUID,
    rating: str,  # "thumbs_up" ou "thumbs_down"
) -> bool:
    """
    Salva feedback E atualiza quality_score dos chunks citados em uma única transação.
    Retorna False se já existe feedback para a mensagem (idempotente).

    Usar uma única transação garante que o feedback não seja gravado
    sem que o quality_score seja atualizado (sem falha parcial).
    """
    # Buscar citações da mensagem
    msg_result = await db.execute(
        text("SELECT citations FROM chat_messages WHERE id = :msg_id"),
        {"msg_id": str(message_id)},
    )
    msg_row = msg_result.fetchone()
    if not msg_row:
        return False
    citations = msg_row[0] if msg_row[0] else []

    # INSERT-first: ON CONFLICT DO NOTHING é atômico — elimina race condition TOCTOU.
    # Se rowcount == 0, outra requisição já registrou o feedback (idempotente).
    insert_result = await db.execute(
        text("""
            INSERT INTO message_feedback (message_id, rating)
            VALUES (:message_id, :rating)
            ON CONFLICT (message_id) DO NOTHING
        """),
        {"message_id": str(message_id), "rating": rating},
    )
    if insert_result.rowcount == 0:
        logger.info(f"Feedback já existente para mensagem {message_id}, ignorando")
        return False

    # Atualizar quality_score dos chunks citados (na mesma transação)
    delta = QUALITY_DELTA_UP if rating == "thumbs_up" else -QUALITY_DELTA_DOWN
    total_updated = 0

    pairs = [
        (c["document_version_id"], c["page_number"])
        for c in citations
        if c.get("document_version_id") and c.get("page_number") is not None
    ]

    for version_id, page_number in pairs:
        result = await db.execute(
            text("""
                UPDATE chunks
                SET quality_score = GREATEST(:min, LEAST(:max, quality_score + :delta))
                WHERE document_version_id = :version_id
                  AND page_number = :page_number
            """),
            {
                "delta": delta,
                "min": QUALITY_MIN,
                "max": QUALITY_MAX,
                "version_id": version_id,
                "page_number": page_number,
            },
        )
        total_updated += result.rowcount

    # Commit único — feedback + quality_score juntos ou nenhum
    await db.commit()
    logger.info(
        f"Feedback '{rating}' gravado + {total_updated} chunks atualizados "
        f"(delta={delta:+.2f}, mensagem {message_id})"
    )
    return True


async def get_feedback(
    db: AsyncSession,
    message_id: UUID,
) -> Optional[str]:
    """Retorna o rating atual de uma mensagem, ou None se não há feedback."""
    result = await db.execute(
        text("SELECT rating FROM message_feedback WHERE message_id = :id"),
        {"id": str(message_id)},
    )
    row = result.fetchone()
    return row[0] if row else None
