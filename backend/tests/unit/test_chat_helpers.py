"""Tests for chat.py helper functions."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_maybe_update_summary_skips_when_below_threshold():
    """Se unsummarized_count < 6, não gera summary."""
    session_id = uuid4()
    mock_db = AsyncMock()

    with (
        patch("app.api.chat.async_session") as mock_session_local,
        patch("app.api.chat.chat_repository.get_session_summary", new_callable=AsyncMock,
              return_value={"history_summary": None, "last_summarized_at": None}),
        patch("app.api.chat.chat_repository.count_messages_since", new_callable=AsyncMock,
              return_value=3),
        patch("app.api.chat.chat_repository.get_messages_before_recent", new_callable=AsyncMock) as mock_get_msgs,
        patch("app.api.chat._generate_summary", new_callable=AsyncMock) as mock_gen,
    ):
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.api.chat import _maybe_update_summary
        await _maybe_update_summary(session_id)

    mock_get_msgs.assert_not_awaited()
    mock_gen.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_update_summary_generates_when_at_threshold():
    """Se unsummarized_count >= 6, gera e persiste o summary."""
    session_id = uuid4()
    mock_db = AsyncMock()
    messages = [{"role": "user", "content": "pergunta"}]

    with (
        patch("app.api.chat.async_session") as mock_session_local,
        patch("app.api.chat.chat_repository.get_session_summary", new_callable=AsyncMock,
              return_value={"history_summary": None, "last_summarized_at": None}),
        patch("app.api.chat.chat_repository.count_messages_since", new_callable=AsyncMock,
              return_value=6),
        patch("app.api.chat.chat_repository.get_messages_before_recent", new_callable=AsyncMock,
              return_value=messages),
        patch("app.api.chat._generate_summary", new_callable=AsyncMock,
              return_value="Resumo gerado.") as mock_gen,
        patch("app.api.chat.chat_repository.update_history_summary", new_callable=AsyncMock) as mock_update,
    ):
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.api.chat import _maybe_update_summary
        await _maybe_update_summary(session_id)

    mock_gen.assert_awaited_once()
    mock_update.assert_awaited_once()
