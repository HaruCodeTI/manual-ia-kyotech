"""
Kyotech AI — API de Sessões de Chat
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser, get_current_user
from app.core.database import get_db
from app.services import chat_repository

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.get("")
async def list_sessions(
    limit: int = 50,
    offset: int = 0,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await chat_repository.list_sessions(db, user.id, limit, offset)


@router.get("/{session_id}")
async def get_session(
    session_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await chat_repository.get_session_with_messages(db, session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    return session


@router.post("")
async def create_session(
    title: Optional[str] = None,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session_id = await chat_repository.create_session(db, user.id, title)
    return {"id": str(session_id)}


@router.delete("/{session_id}")
async def delete_session(
    session_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = await chat_repository.delete_session(db, session_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    return {"ok": True}
