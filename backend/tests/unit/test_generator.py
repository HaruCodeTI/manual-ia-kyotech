"""Tests for app.services.generator — build_context and generate_response."""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.generator import Citation, RAGResponse, build_context, generate_response
from app.services.search import SearchResult


def _make_result(**overrides) -> SearchResult:
    defaults = dict(
        chunk_id="c1",
        content="Sample content.",
        page_number=1,
        similarity=0.92,
        document_id="d1",
        doc_type="manual",
        equipment_key="frontier-780",
        published_date=date(2024, 1, 15),
        source_filename="manual.pdf",
        storage_path="docs/manual.pdf",
        search_type="vector",
        document_version_id="v1",
    )
    defaults.update(overrides)
    return SearchResult(**defaults)


class TestBuildContext:
    def test_formats_fonte_with_metadata(self):
        results = [
            _make_result(source_filename="a.pdf", page_number=3, content="AAA"),
            _make_result(source_filename="b.pdf", page_number=7, content="BBB"),
        ]
        ctx = build_context(results)
        assert "[Fonte 1]" in ctx
        assert "[Fonte 2]" in ctx
        assert "a.pdf" in ctx
        assert "b.pdf" in ctx
        assert "AAA" in ctx
        assert "BBB" in ctx
        assert "Página: 3" in ctx
        assert "Página: 7" in ctx


class TestGenerateResponse:
    @pytest.mark.asyncio
    async def test_empty_results_fallback(self):
        result = await generate_response(
            question="teste",
            query_rewritten="test",
            search_results=[],
        )
        assert isinstance(result, RAGResponse)
        assert "Não encontrei" in result.answer
        assert result.citations == []
        assert result.total_sources == 0

    @pytest.mark.asyncio
    async def test_with_results_returns_citations(self):
        mock_client = AsyncMock()
        choice = MagicMock()
        choice.message.content = "A resposta eh X [Fonte 1]. Veja tambem [Fonte 2]."
        chat_resp = MagicMock()
        chat_resp.choices = [choice]
        mock_client.chat.completions.create = AsyncMock(return_value=chat_resp)

        results = [
            _make_result(source_filename="a.pdf", page_number=1),
            _make_result(source_filename="b.pdf", page_number=5),
        ]

        with patch("app.services.generator.get_openai_client", return_value=mock_client):
            resp = await generate_response(
                question="pergunta",
                query_rewritten="question",
                search_results=results,
            )

        assert "[Fonte 1]" in resp.answer
        assert len(resp.citations) == 2
        assert resp.citations[0].source_filename == "a.pdf"
        assert resp.citations[1].source_filename == "b.pdf"
        assert resp.total_sources == 2

    @pytest.mark.asyncio
    async def test_unreferenced_sources_excluded(self):
        mock_client = AsyncMock()
        choice = MagicMock()
        # Only references Fonte 1, not Fonte 2
        choice.message.content = "Resposta baseada em [Fonte 1] apenas."
        chat_resp = MagicMock()
        chat_resp.choices = [choice]
        mock_client.chat.completions.create = AsyncMock(return_value=chat_resp)

        results = [
            _make_result(source_filename="referenced.pdf"),
            _make_result(source_filename="unreferenced.pdf"),
        ]

        with patch("app.services.generator.get_openai_client", return_value=mock_client):
            resp = await generate_response(
                question="pergunta",
                query_rewritten="question",
                search_results=results,
            )

        assert len(resp.citations) == 1
        assert resp.citations[0].source_filename == "referenced.pdf"
        assert resp.total_sources == 2


class TestGenerateResponseWithHistory:
    @pytest.mark.asyncio
    async def test_no_history_uses_simple_array(self):
        """Sem histórico: messages = [system, user]"""
        mock_client = AsyncMock()
        choice = MagicMock()
        choice.message.content = "Resposta [Fonte 1]."
        chat_resp = MagicMock()
        chat_resp.choices = [choice]
        mock_client.chat.completions.create = AsyncMock(return_value=chat_resp)

        with patch("app.services.generator.get_openai_client", return_value=mock_client):
            await generate_response(
                question="pergunta",
                query_rewritten="question",
                search_results=[_make_result()],
            )

        messages = mock_client.chat.completions.create.call_args[1]["messages"]
        roles = [m["role"] for m in messages]
        assert roles == ["system", "user"]

    @pytest.mark.asyncio
    async def test_with_history_uses_multiturn_array(self):
        """Com histórico: messages = [system, user1, assistant1, user_atual]"""
        mock_client = AsyncMock()
        choice = MagicMock()
        choice.message.content = "Resposta [Fonte 1]."
        chat_resp = MagicMock()
        chat_resp.choices = [choice]
        mock_client.chat.completions.create = AsyncMock(return_value=chat_resp)

        history = [
            {"role": "user", "content": "pergunta anterior"},
            {"role": "assistant", "content": "resposta anterior"},
        ]

        with patch("app.services.generator.get_openai_client", return_value=mock_client):
            await generate_response(
                question="nova pergunta",
                query_rewritten="new question",
                search_results=[_make_result()],
                history_messages=history,
            )

        messages = mock_client.chat.completions.create.call_args[1]["messages"]
        roles = [m["role"] for m in messages]
        assert roles == ["system", "user", "assistant", "user"]
        assert messages[1]["content"] == "pergunta anterior"
        assert messages[2]["content"] == "resposta anterior"

    @pytest.mark.asyncio
    async def test_with_summary_adds_system_message(self):
        """Com summary: messages = [system, system(summary), user]"""
        mock_client = AsyncMock()
        choice = MagicMock()
        choice.message.content = "Resposta [Fonte 1]."
        chat_resp = MagicMock()
        chat_resp.choices = [choice]
        mock_client.chat.completions.create = AsyncMock(return_value=chat_resp)

        with patch("app.services.generator.get_openai_client", return_value=mock_client):
            await generate_response(
                question="pergunta",
                query_rewritten="question",
                search_results=[_make_result()],
                history_summary="Técnico perguntou sobre Frontier-780.",
            )

        messages = mock_client.chat.completions.create.call_args[1]["messages"]
        roles = [m["role"] for m in messages]
        assert roles == ["system", "system", "user"]
        assert "Resumo do contexto anterior" in messages[1]["content"]
        assert "Frontier-780" in messages[1]["content"]

    @pytest.mark.asyncio
    async def test_with_summary_and_history(self):
        """Com summary e histórico: [system, system(summary), user1, assistant1, user]"""
        mock_client = AsyncMock()
        choice = MagicMock()
        choice.message.content = "Resposta [Fonte 1]."
        chat_resp = MagicMock()
        chat_resp.choices = [choice]
        mock_client.chat.completions.create = AsyncMock(return_value=chat_resp)

        history = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]

        with patch("app.services.generator.get_openai_client", return_value=mock_client):
            await generate_response(
                question="pergunta",
                query_rewritten="question",
                search_results=[_make_result()],
                history_messages=history,
                history_summary="Resumo.",
            )

        messages = mock_client.chat.completions.create.call_args[1]["messages"]
        roles = [m["role"] for m in messages]
        assert roles == ["system", "system", "user", "assistant", "user"]
