"""
Testes de integração — comparação de versões no pipeline de chat.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.generator import RAGResponse, Citation
from app.services.query_rewriter import RewrittenQuery
from app.services.search import SearchResult
from app.services.version_comparator import DiffItem, VersionDiff


def _make_search_result(
    chunk_id="c1",
    document_id="doc-a",
    document_version_id="ver-1",
    published_date=date(2024, 7, 1),
    content="conteúdo de teste",
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        content=content,
        page_number=1,
        similarity=0.9,
        document_id=document_id,
        doc_type="manual",
        equipment_key="frontier-780",
        published_date=published_date,
        source_filename="manual.pdf",
        storage_path="container/blob",
        search_type="vector",
        document_version_id=document_version_id,
    )


def _multi_version_results():
    """Chunks de duas versões diferentes do mesmo documento."""
    return [
        _make_search_result(chunk_id="c1", document_version_id="ver-1", published_date=date(2024, 7, 1)),
        _make_search_result(chunk_id="c2", document_version_id="ver-2", published_date=date(2025, 1, 15)),
    ]


def _make_diff() -> VersionDiff:
    return VersionDiff(
        version_old="2024-07-01",
        version_new="2025-01-15",
        diff_items=[DiffItem("modified", "Torque", "10 Nm", "12 Nm")],
        has_changes=True,
    )


def _make_comparison_rewritten() -> RewrittenQuery:
    return RewrittenQuery(
        original="O que mudou no manual?",
        query_en="What changed in the manual?",
        doc_type=None,
        equipment_hint=None,
        needs_clarification=False,
        clarification_question=None,
        is_comparison_query=True,
    )


def _make_normal_rewritten() -> RewrittenQuery:
    return RewrittenQuery(
        original="Como trocar o rolo?",
        query_en="How to replace roller",
        doc_type="manual",
        equipment_hint=None,
        needs_clarification=False,
        clarification_question=None,
        is_comparison_query=False,
    )


def _make_rag_response(answer: str = "Resposta de teste") -> RAGResponse:
    return RAGResponse(
        answer=answer,
        citations=[],
        query_original="pergunta",
        query_rewritten="question",
        total_sources=0,
        model_used="gpt-4o",
    )


@pytest.mark.anyio
async def test_comparison_query_bypasses_semantic_cache(async_client):
    """Quando is_comparison_query=True, o cache semântico não é consultado."""
    session_id = uuid4()

    with (
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_comparison_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=_multi_version_results()),
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock) as mock_cache,
        patch("app.api.chat.compare_versions", new_callable=AsyncMock, return_value=_make_diff()),
        patch("app.api.chat.detect_multi_version", return_value=True),
        patch("app.api.chat.group_chunks_by_version", return_value={"2024-07-01": [], "2025-01-15": []}),
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()),
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock, return_value=uuid4()),
        patch("app.api.chat.chat_repository.get_recent_messages", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.chat_repository.get_session_summary", new_callable=AsyncMock, return_value={"history_summary": None, "last_summarized_at": None}),
    ):
        response = await async_client.post("/api/v1/chat/ask", json={"question": "O que mudou no manual?"})

    assert response.status_code == 200
    mock_cache.assert_not_called()


@pytest.mark.anyio
async def test_comparison_fallback_when_comparator_raises(async_client):
    """Se compare_versions levanta exceção, resposta é gerada normalmente sem diff."""
    session_id = uuid4()

    with (
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_comparison_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=_multi_version_results()),
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.compare_versions", new_callable=AsyncMock, side_effect=ValueError("LLM error")),
        patch("app.api.chat.detect_multi_version", return_value=True),
        patch("app.api.chat.group_chunks_by_version", return_value={"2024-07-01": [], "2025-01-15": []}),
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()) as mock_gen,
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock, return_value=uuid4()),
        patch("app.api.chat.chat_repository.get_recent_messages", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.chat_repository.get_session_summary", new_callable=AsyncMock, return_value={"history_summary": None, "last_summarized_at": None}),
    ):
        response = await async_client.post("/api/v1/chat/ask", json={"question": "O que mudou no manual?"})

    assert response.status_code == 200
    call_kwargs = mock_gen.call_args.kwargs
    assert call_kwargs.get("version_diff") is None


@pytest.mark.anyio
async def test_normal_query_unaffected(async_client):
    """Query normal não aciona o pipeline de comparação."""
    session_id = uuid4()

    with (
        patch("app.api.chat.rewrite_query", new_callable=AsyncMock, return_value=_make_normal_rewritten()),
        patch("app.api.chat.hybrid_search", new_callable=AsyncMock, return_value=[_make_search_result()]) as mock_search,
        patch("app.api.chat.get_cached_response", new_callable=AsyncMock, return_value=None),
        patch("app.api.chat.compare_versions", new_callable=AsyncMock) as mock_compare,
        patch("app.api.chat.generate_response", new_callable=AsyncMock, return_value=_make_rag_response()) as mock_gen,
        patch("app.api.chat._maybe_update_summary", new_callable=AsyncMock),
        patch("app.api.chat.chat_repository.create_session", new_callable=AsyncMock, return_value=session_id),
        patch("app.api.chat.chat_repository.add_message", new_callable=AsyncMock, return_value=uuid4()),
        patch("app.api.chat.chat_repository.get_recent_messages", new_callable=AsyncMock, return_value=[]),
        patch("app.api.chat.chat_repository.get_session_summary", new_callable=AsyncMock, return_value={"history_summary": None, "last_summarized_at": None}),
    ):
        response = await async_client.post("/api/v1/chat/ask", json={"question": "Como trocar o rolo?"})

    assert response.status_code == 200
    mock_compare.assert_not_called()
    search_kwargs = mock_search.call_args.kwargs
    assert search_kwargs.get("include_all_versions", False) is False
