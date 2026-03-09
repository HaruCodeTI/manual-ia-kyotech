"""
Kyotech AI — Testes unitarios para app.services.chat_repository
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.chat_repository import (
    create_session,
    list_sessions,
    get_session_with_messages,
    delete_session,
    add_message,
)


# ── create_session ──

@pytest.mark.asyncio
async def test_create_session_returns_uuid(mock_db, make_mock_result):
    session_id = uuid4()
    mock_db.execute = AsyncMock(
        return_value=make_mock_result(rows=[(session_id,)])
    )
    result = await create_session(mock_db, "user-1", title="Test")
    assert result == session_id
    mock_db.commit.assert_awaited_once()


# ── list_sessions ──

@pytest.mark.asyncio
async def test_list_sessions_returns_formatted_list(mock_db, make_mock_result):
    now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    sid = uuid4()
    mock_db.execute = AsyncMock(
        return_value=make_mock_result(rows=[(sid, "Chat 1", now, now)])
    )
    result = await list_sessions(mock_db, "user-1")
    assert len(result) == 1
    assert result[0]["id"] == str(sid)
    assert result[0]["title"] == "Chat 1"
    assert "created_at" in result[0]
    assert "updated_at" in result[0]


@pytest.mark.asyncio
async def test_list_sessions_handles_empty(mock_db, make_mock_result):
    mock_db.execute = AsyncMock(
        return_value=make_mock_result(rows=[])
    )
    result = await list_sessions(mock_db, "user-1")
    assert result == []


# ── get_session_with_messages ──

@pytest.mark.asyncio
async def test_get_session_with_messages_returns_dict(mock_db, make_mock_result):
    now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    sid = uuid4()
    mid = uuid4()

    session_result = make_mock_result(rows=[(sid, "Chat", now)])
    messages_result = make_mock_result(
        rows=[(mid, "user", "Hello", None, None, now)]
    )

    mock_db.execute = AsyncMock(side_effect=[session_result, messages_result])

    result = await get_session_with_messages(mock_db, sid, "user-1")

    assert result is not None
    assert result["id"] == str(sid)
    assert result["title"] == "Chat"
    assert len(result["messages"]) == 1
    assert result["messages"][0]["role"] == "user"
    assert result["messages"][0]["content"] == "Hello"


@pytest.mark.asyncio
async def test_get_session_not_found_returns_none(mock_db, make_mock_result):
    mock_db.execute = AsyncMock(
        return_value=make_mock_result(rows=[])
    )
    result = await get_session_with_messages(mock_db, uuid4(), "user-1")
    assert result is None


# ── delete_session ──

@pytest.mark.asyncio
async def test_delete_session_true_when_found(mock_db, make_mock_result):
    res = make_mock_result(rows=[("x",)])  # rowcount=1
    mock_db.execute = AsyncMock(return_value=res)
    assert await delete_session(mock_db, uuid4(), "user-1") is True


@pytest.mark.asyncio
async def test_delete_session_false_when_not_found(mock_db, make_mock_result):
    res = make_mock_result(rows=[])  # rowcount=0
    mock_db.execute = AsyncMock(return_value=res)
    assert await delete_session(mock_db, uuid4(), "user-1") is False


# ── add_message ──

@pytest.mark.asyncio
async def test_add_message_returns_uuid(mock_db, make_mock_result):
    msg_id = uuid4()
    mock_db.execute = AsyncMock(
        return_value=make_mock_result(rows=[(msg_id,)])
    )
    result = await add_message(mock_db, uuid4(), "user", "Hello!")
    assert result == msg_id
    # At least 2 execute calls: INSERT message + UPDATE session updated_at
    assert mock_db.execute.call_count >= 2
    mock_db.commit.assert_awaited_once()
