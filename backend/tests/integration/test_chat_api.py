"""
Kyotech AI — Testes de integração da API de Chat (RAG)
"""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.generator import Citation, RAGResponse
from app.services.query_rewriter import RewrittenQuery


def _make_rewritten(question: str = "test question") -> RewrittenQuery:
    return RewrittenQuery(
        original=question,
        query_en="how to replace the pressure roller",
        doc_type="manual",
        equipment_hint=None,
    )


def _make_rag_response(question: str = "test question") -> RAGResponse:
    return RAGResponse(
        answer="Resposta de teste com [Fonte 1].",
        citations=[
            Citation(
                source_index=1,
                source_filename="manual_frontier.pdf",
                page_number=5,
                equipment_key="frontier-780",
                doc_type="manual",
                published_date="2025-01-15",
                storage_path="documents/frontier-780/manual_frontier.pdf",
                document_version_id="ver-123",
            ),
        ],
        query_original=question,
        query_rewritten="how to replace the pressure roller",
        total_sources=1,
        model_used="gpt-4o",
    )


@pytest.mark.anyio
async def test_ask_creates_new_session(async_client):
    session_id = uuid4()

    with (
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()),
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
    ):
        resp = await async_client.post(
            "/api/v1/chat/ask",
            json={"question": "Como trocar o rolo de pressão?"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "Resposta de teste com [Fonte 1]."
    assert len(data["citations"]) == 1
    assert data["session_id"] == str(session_id)
    assert data["model_used"] == "gpt-4o"
    assert data["total_sources"] == 1


@pytest.mark.anyio
async def test_ask_with_existing_session(async_client):
    session_id = uuid4()

    with (
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()),
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock) as mock_create,
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
    ):
        resp = await async_client.post(
            "/api/v1/chat/ask",
            json={
                "question": "Como trocar o rolo de pressão?",
                "session_id": str(session_id),
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == str(session_id)
    mock_create.assert_not_awaited()


@pytest.mark.anyio
async def test_ask_with_equipment_filter(async_client):
    session_id = uuid4()

    with (
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]) as mock_search,
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()),
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
    ):
        resp = await async_client.post(
            "/api/v1/chat/ask",
            json={
                "question": "Como trocar o rolo de pressão?",
                "equipment_filter": "versant-180",
            },
        )

    assert resp.status_code == 200
    # Verify hybrid_search was called with the equipment_filter
    call_kwargs = mock_search.call_args
    assert call_kwargs.kwargs.get("equipment_key") == "versant-180"


@pytest.mark.anyio
async def test_get_pdf_url(async_client):
    fake_url = "https://fakeaccount.blob.core.windows.net/documents/manual.pdf?sv=2025"

    with patch("app.api.chat.generate_signed_url", return_value=fake_url):
        resp = await async_client.get(
            "/api/v1/chat/pdf-url",
            params={"storage_path": "documents/manual.pdf", "page": 5},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "#page=5" in data["url"]
    assert data["url"].startswith(fake_url)
