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
        needs_clarification=False,
        clarification_question=None,
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
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()),
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
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
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()),
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock) as mock_create,
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
        patch("app.api.chat.chat_repository.get_recent_messages", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.chat_repository.get_session_summary", new_callable=AsyncMock, return_value={"history_summary": None, "last_summarized_at": None}),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
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
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]) as mock_search,
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()),
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
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


@pytest.mark.anyio
async def test_ask_second_message_fetches_history(async_client):
    """Segunda pergunta na mesma sessão deve buscar histórico."""
    session_id = uuid4()

    with (
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
        patch("app.api.chat.chat_repository.get_recent_messages", new_callable=AsyncMock, return_value=[]) as mock_history,
        patch("app.api.chat.chat_repository.get_session_summary", new_callable=AsyncMock, return_value={"history_summary": None, "last_summarized_at": None}),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
    ):
        resp = await async_client.post(
            "/api/v1/chat/ask",
            json={"question": "E o procedimento?", "session_id": str(session_id)},
        )

    assert resp.status_code == 200
    mock_history.assert_awaited_once()


@pytest.mark.anyio
async def test_ask_first_message_no_history_fetch(async_client):
    """Primeira pergunta (sem session_id) não busca histórico."""
    session_id = uuid4()

    with (
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()),
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
        patch("app.api.chat.chat_repository.get_recent_messages", new_callable=AsyncMock, return_value=[]) as mock_history,
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
    ):
        resp = await async_client.post(
            "/api/v1/chat/ask",
            json={"question": "Como trocar o rolo?"},
        )

    assert resp.status_code == 200
    mock_history.assert_not_awaited()


@pytest.mark.anyio
async def test_ask_passes_history_to_generate_response(async_client):
    """Com histórico, generate_response deve receber history_messages."""
    session_id = uuid4()
    history = [
        {"role": "user", "content": "Frontier-780"},
        {"role": "assistant", "content": "Sim, tenho informações."},
    ]

    with (
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()) as mock_gen,
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
        patch("app.api.chat.chat_repository.get_recent_messages", new_callable=AsyncMock, return_value=history),
        patch("app.api.chat.chat_repository.get_session_summary", new_callable=AsyncMock, return_value={"history_summary": None, "last_summarized_at": None}),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
    ):
        resp = await async_client.post(
            "/api/v1/chat/ask",
            json={"question": "E a manutenção?", "session_id": str(session_id)},
        )

    assert resp.status_code == 200
    call_kwargs = mock_gen.call_args.kwargs
    assert call_kwargs.get("history_messages") == history
    assert "history_summary" in call_kwargs  # also forwarded (None in this case)


@pytest.mark.anyio
async def test_clarification_from_rewriter(async_client):
    """rewrite_query retorna needs_clarification=True → retorna clarificação sem RAG."""
    from app.services.query_rewriter import RewrittenQuery
    clarification_rewritten = RewrittenQuery(
        original="Como trocar o rolo?",
        query_en="pressure roller replacement",
        doc_type="manual",
        equipment_hint=None,
        needs_clarification=True,
        clarification_question="Para qual equipamento você está buscando essa informação?",
    )
    session_id = uuid4()

    with (
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=clarification_rewritten),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock) as mock_search,
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
    ):
        resp = await async_client.post(
            "/api/v1/chat/ask",
            json={"question": "Como trocar o rolo?"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_clarification"] is True
    assert data["citations"] == []
    assert "equipamento" in data["answer"].lower()
    # RAG não deve ter sido chamado
    mock_search.assert_not_awaited()


@pytest.mark.anyio
async def test_clarification_from_weak_score(async_client):
    """Score do melhor resultado < 0.45 → retorna clarificação."""
    from app.services.search import SearchResult
    from datetime import date as dt

    weak_result = SearchResult(
        chunk_id="c1", content="texto", page_number=1, similarity=0.3,
        document_id="d1", doc_type="manual", equipment_key="equip-a",
        published_date=dt(2024, 1, 1), source_filename="f.pdf",
        storage_path="container/blob", search_type="vector",
        document_version_id="v1", quality_score=0.0,
    )
    session_id = uuid4()

    with (
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[weak_result]),
        patch("app.api.chat.generate_response", new_callable=AsyncMock) as mock_gen,
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
    ):
        resp = await async_client.post(
            "/api/v1/chat/ask",
            json={"question": "não funciona"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_clarification"] is True
    assert data["citations"] == []
    # generate_response não deve ter sido chamado
    mock_gen.assert_not_awaited()


@pytest.mark.anyio
async def test_good_score_proceeds_normally(async_client):
    """Score >= 0.45 → pipeline normal, needs_clarification=False."""
    session_id = uuid4()

    with (
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()) as mock_gen,
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
    ):
        resp = await async_client.post(
            "/api/v1/chat/ask",
            json={"question": "Como trocar o rolo do Frontier-780?"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_clarification"] is False
    mock_gen.assert_awaited_once()


@pytest.mark.anyio
async def test_clarification_answer_proceeds_normally(async_client):
    """Sessão com clarificação anterior → resposta do técnico → RAG normal."""
    session_id = uuid4()
    history_with_clarification = [
        {"role": "user", "content": "Como trocar o rolo?"},
        {"role": "assistant", "content": "Para qual equipamento você está buscando essa informação?"},
        {"role": "user", "content": "Frontier-780"},
    ]

    with (
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_rewritten()) as mock_rewrite,
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock),
        patch("app.api.chat.chat_repository.get_recent_messages", new_callable=AsyncMock, return_value=history_with_clarification),
        patch("app.api.chat.chat_repository.get_session_summary", new_callable=AsyncMock, return_value={"history_summary": None, "last_summarized_at": None}),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
    ):
        resp = await async_client.post(
            "/api/v1/chat/ask",
            json={"question": "Frontier-780", "session_id": str(session_id)},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_clarification"] is False
    # Verificar que rewrite_query recebeu o contexto da conversa
    call_kwargs = mock_rewrite.call_args.kwargs
    assert call_kwargs.get("conversation_context") is not None
