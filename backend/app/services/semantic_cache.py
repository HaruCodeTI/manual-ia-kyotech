"""
Kyotech AI — Semantic Cache
Armazena respostas aprovadas (👍) indexadas pelo embedding da pergunta.
Perguntas similares (cosine similarity >= 0.92) recebem resposta cacheada
sem chamar OpenAI nem fazer busca vetorial.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embedder import generate_single_embedding

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.92
CACHE_TTL_DAYS = 7


async def get_cached_response(
    db: AsyncSession,
    question: str,
) -> Optional[Dict[str, Any]]:
    """
    Busca uma resposta cacheada para a pergunta.
    Retorna None se não há cache válido (threshold ou TTL não atingidos).
    """
    embedding = await generate_single_embedding(question)
    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

    result = await db.execute(
        text(f"""
            SELECT
                id,
                answer,
                citations,
                question_original,
                query_rewritten,
                model_used,
                1 - (question_embedding <=> CAST(:emb AS vector)) AS similarity
            FROM semantic_cache
            WHERE created_at > NOW() - INTERVAL '{CACHE_TTL_DAYS} days'
            ORDER BY question_embedding <=> CAST(:emb AS vector)
            LIMIT 1
        """),
        # Nota: CACHE_TTL_DAYS é uma constante inteira do módulo (valor=7), não input do usuário.
        # PostgreSQL INTERVAL não aceita bind parameter, então f-string é segura aqui.
        {"emb": embedding_str},
    )
    row = result.fetchone()

    if not row:
        return None

    similarity = float(row[6])
    if similarity < SIMILARITY_THRESHOLD:
        logger.debug(f"Cache miss: melhor similaridade={similarity:.3f} < {SIMILARITY_THRESHOLD}")
        return None

    # Incrementa hit_count — métrica não crítica, falha não deve bloquear a resposta
    try:
        await db.execute(
            text("UPDATE semantic_cache SET hit_count = hit_count + 1 WHERE id = :id"),
            {"id": row[0]},
        )
        await db.commit()
    except Exception as e:
        logger.warning(f"Falha ao incrementar hit_count (não crítico): {e}")

    logger.info(f"Cache HIT: similarity={similarity:.3f}, pergunta='{question[:60]}'")
    return {
        "answer": row[1],
        "citations": row[2] or [],
        "query_original": row[3],
        "query_rewritten": row[4] or "",
        "model_used": (row[5] or "") + " (cached)",
    }


async def cache_response(
    db: AsyncSession,
    question: str,
    answer: str,
    citations: List[Dict],
    query_rewritten: str,
    model_used: str,
) -> None:
    """
    Armazena uma resposta aprovada (👍) no cache semântico.
    Chamado pelo endpoint de feedback quando rating == 'thumbs_up'.
    """
    embedding = await generate_single_embedding(question)
    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"

    await db.execute(
        text("""
            INSERT INTO semantic_cache
                (question_embedding, question_original, answer, citations, query_rewritten, model_used)
            VALUES
                (CAST(:emb AS vector), :question, :answer, :citations, :query_rewritten, :model_used)
        """),
        {
            "emb": embedding_str,
            "question": question,
            "answer": answer,
            "citations": json.dumps(citations),
            "query_rewritten": query_rewritten,
            "model_used": model_used,
        },
    )
    await db.commit()
    logger.info(f"Resposta cacheada: '{question[:60]}'")


async def invalidate_cache(db: AsyncSession) -> int:
    """
    Limpa todo o cache semântico.
    Chamado após upload de novos documentos — respostas antigas podem estar incompletas.
    Retorna número de entradas removidas.
    """
    result = await db.execute(text("DELETE FROM semantic_cache"))
    await db.commit()
    count = result.rowcount
    if count:
        logger.info(f"Cache semântico invalidado: {count} entradas removidas")
    return count
