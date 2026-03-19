"""
Kyotech AI — Repositório de sessões e mensagens de chat
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def create_session(
    db: AsyncSession,
    user_id: str,
    title: Optional[str] = None,
) -> UUID:
    result = await db.execute(
        text("""
            INSERT INTO chat_sessions (user_id, title)
            VALUES (:user_id, :title)
            RETURNING id
        """),
        {"user_id": user_id, "title": title},
    )
    await db.commit()
    return result.fetchone()[0]


async def list_sessions(
    db: AsyncSession,
    user_id: str,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT id, title, created_at, updated_at
            FROM chat_sessions
            WHERE user_id = :user_id
            ORDER BY updated_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {"user_id": user_id, "limit": limit, "offset": offset},
    )
    return [
        {
            "id": str(row[0]),
            "title": row[1],
            "created_at": row[2].isoformat(),
            "updated_at": row[3].isoformat(),
        }
        for row in result.fetchall()
    ]


async def get_session_with_messages(
    db: AsyncSession,
    session_id: UUID,
    user_id: str,
) -> Optional[Dict[str, Any]]:
    session = await db.execute(
        text("SELECT id, title, created_at FROM chat_sessions WHERE id = :id AND user_id = :uid"),
        {"id": str(session_id), "uid": user_id},
    )
    row = session.fetchone()
    if not row:
        return None

    messages = await db.execute(
        text("""
            SELECT id, role, content, citations, metadata, created_at
            FROM chat_messages
            WHERE session_id = :sid
            ORDER BY created_at
        """),
        {"sid": str(session_id)},
    )

    return {
        "id": str(row[0]),
        "title": row[1],
        "created_at": row[2].isoformat(),
        "messages": [
            {
                "id": str(m[0]),
                "role": m[1],
                "content": m[2],
                "citations": m[3],
                "metadata": m[4],
                "created_at": m[5].isoformat(),
            }
            for m in messages.fetchall()
        ],
    }


async def add_message(
    db: AsyncSession,
    session_id: UUID,
    role: str,
    content: str,
    citations: Optional[List] = None,
    metadata: Optional[Dict] = None,
) -> UUID:
    result = await db.execute(
        text("""
            INSERT INTO chat_messages (session_id, role, content, citations, metadata)
            VALUES (:sid, :role, :content, :citations, :metadata)
            RETURNING id
        """),
        {
            "sid": str(session_id),
            "role": role,
            "content": content,
            "citations": json.dumps(citations) if citations else None,
            "metadata": json.dumps(metadata) if metadata else None,
        },
    )
    await db.execute(
        text("UPDATE chat_sessions SET updated_at = NOW() WHERE id = :sid"),
        {"sid": str(session_id)},
    )
    await db.commit()
    return result.fetchone()[0]


async def update_session_title(
    db: AsyncSession,
    session_id: UUID,
    title: str,
) -> None:
    await db.execute(
        text("UPDATE chat_sessions SET title = :title WHERE id = :id"),
        {"title": title, "id": str(session_id)},
    )
    await db.commit()


async def delete_session(
    db: AsyncSession,
    session_id: UUID,
    user_id: str,
) -> bool:
    result = await db.execute(
        text("DELETE FROM chat_sessions WHERE id = :id AND user_id = :uid"),
        {"id": str(session_id), "uid": user_id},
    )
    await db.commit()
    return result.rowcount > 0


async def get_recent_messages(
    db: AsyncSession,
    session_id: UUID,
    limit: int = 6,
) -> List[Dict[str, str]]:
    """Retorna as últimas N mensagens em ordem cronológica. Chamar ANTES de add_message."""
    result = await db.execute(
        text("""
            SELECT id, role, content, created_at FROM (
                SELECT id, role, content, created_at
                FROM chat_messages
                WHERE session_id = :sid
                ORDER BY created_at DESC
                LIMIT :limit
            ) sub
            ORDER BY created_at ASC
        """),
        {"sid": str(session_id), "limit": limit},
    )
    rows = result.fetchall()
    # Retorna em ordem cronológica (mais antiga primeiro)
    return [
        {"role": row[1], "content": row[2]}
        for row in rows
    ]


async def get_session_summary(
    db: AsyncSession,
    session_id: UUID,
) -> Dict[str, Any]:
    """Retorna history_summary e last_summarized_at da sessão."""
    result = await db.execute(
        text("""
            SELECT history_summary, last_summarized_at
            FROM chat_sessions
            WHERE id = :id
        """),
        {"id": str(session_id)},
    )
    row = result.fetchone()
    if not row:
        return {"history_summary": None, "last_summarized_at": None}
    return {"history_summary": row[0], "last_summarized_at": row[1]}


async def count_messages_since(
    db: AsyncSession,
    session_id: UUID,
    since: Optional[datetime] = None,
) -> int:
    """Conta mensagens da sessão. Se since fornecido, conta apenas após essa data."""
    if since is not None:
        result = await db.execute(
            text("""
                SELECT COUNT(*) FROM chat_messages
                WHERE session_id = :sid AND created_at > :since
            """),
            {"sid": str(session_id), "since": since},
        )
    else:
        result = await db.execute(
            text("SELECT COUNT(*) FROM chat_messages WHERE session_id = :sid"),
            {"sid": str(session_id)},
        )
    return result.scalar() or 0


async def get_messages_before_recent(
    db: AsyncSession,
    session_id: UUID,
    skip_last: int = 6,
    since: Optional[datetime] = None,
) -> List[Dict[str, str]]:
    """
    Retorna mensagens antigas exceto as últimas skip_last.
    Se since fornecido, considera apenas mensagens após essa data.
    Usado para gerar summary incremental.
    """
    if since is not None:
        result = await db.execute(
            text("""
                SELECT id, role, content, created_at FROM (
                    SELECT id, role, content, created_at,
                           ROW_NUMBER() OVER (ORDER BY created_at DESC) as rn
                    FROM chat_messages
                    WHERE session_id = :sid AND created_at > :since
                ) sub
                WHERE rn > :skip
                ORDER BY created_at
            """),
            {"sid": str(session_id), "since": since, "skip": skip_last},
        )
    else:
        result = await db.execute(
            text("""
                SELECT id, role, content, created_at FROM (
                    SELECT id, role, content, created_at,
                           ROW_NUMBER() OVER (ORDER BY created_at DESC) as rn
                    FROM chat_messages
                    WHERE session_id = :sid
                ) sub
                WHERE rn > :skip
                ORDER BY created_at
            """),
            {"sid": str(session_id), "skip": skip_last},
        )
    return [{"role": row[1], "content": row[2]} for row in result.fetchall()]


async def update_history_summary(
    db: AsyncSession,
    session_id: UUID,
    summary: str,
) -> None:
    """Persiste o summary e atualiza last_summarized_at = NOW()."""
    await db.execute(
        text("""
            UPDATE chat_sessions
            SET history_summary = :summary,
                last_summarized_at = NOW()
            WHERE id = :id
        """),
        {"summary": summary, "id": str(session_id)},
    )
    await db.commit()
