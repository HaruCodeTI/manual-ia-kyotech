"""
Kyotech AI — Testes de integração da API de Sessões
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest


@pytest.mark.anyio
async def test_list_sessions(async_client):
    sessions = [
        {"id": str(uuid4()), "title": "Sessão 1", "created_at": "2025-01-01T00:00:00"},
        {"id": str(uuid4()), "title": "Sessão 2", "created_at": "2025-01-02T00:00:00"},
    ]

    with patch("app.api.sessions.chat_repository.list_sessions", new_callable=AsyncMock, return_value=sessions):
        resp = await async_client.get("/api/v1/sessions")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["title"] == "Sessão 1"


@pytest.mark.anyio
async def test_get_session_found(async_client):
    session_id = uuid4()
    session_data = {
        "id": str(session_id),
        "title": "Sessão de teste",
        "messages": [{"role": "user", "content": "Olá"}],
    }

    with patch(
        "app.api.sessions.chat_repository.get_session_with_messages",
        new_callable=AsyncMock,
        return_value=session_data,
    ):
        resp = await async_client.get(f"/api/v1/sessions/{session_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(session_id)
    assert len(data["messages"]) == 1


@pytest.mark.anyio
async def test_get_session_not_found(async_client):
    session_id = uuid4()

    with patch(
        "app.api.sessions.chat_repository.get_session_with_messages",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await async_client.get(f"/api/v1/sessions/{session_id}")

    assert resp.status_code == 404


@pytest.mark.anyio
async def test_create_session(async_client):
    new_id = uuid4()

    with patch("app.api.sessions.chat_repository.create_session", new_callable=AsyncMock, return_value=new_id):
        resp = await async_client.post("/api/v1/sessions", params={"title": "Nova sessão"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(new_id)


@pytest.mark.anyio
async def test_delete_session_found(async_client):
    session_id = uuid4()

    with patch("app.api.sessions.chat_repository.delete_session", new_callable=AsyncMock, return_value=True):
        resp = await async_client.delete(f"/api/v1/sessions/{session_id}")

    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.anyio
async def test_delete_session_not_found(async_client):
    session_id = uuid4()

    with patch("app.api.sessions.chat_repository.delete_session", new_callable=AsyncMock, return_value=False):
        resp = await async_client.delete(f"/api/v1/sessions/{session_id}")

    assert resp.status_code == 404
