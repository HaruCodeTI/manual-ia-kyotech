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
        search_type="vector",
        document_version_id="v1",
        storage_path="docs/manual.pdf",
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


def test_build_clarification_from_weak_results():
    from app.services.generator import build_clarification_from_weak_results
    result = build_clarification_from_weak_results("pergunta qualquer")
    assert isinstance(result, str)
    assert len(result) > 0
    # Deve ser em português
    assert any(word in result.lower() for word in ["encontrei", "detalhes", "equipamento", "precisas"])


def _make_llm_response(content: str):
    """Helper para mockar resposta do LLM em test_generator.py."""
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.fixture
def _patch_openai_client():
    mock_client = AsyncMock()
    with patch("app.services.generator.get_openai_client", return_value=mock_client):
        yield mock_client


class TestDiagnosticMode:
    @pytest.mark.asyncio
    async def test_diagnostic_mode_uses_diagnostic_prompt(self, _patch_openai_client):
        """diagnostic_mode=True → system message contém 'Análise dos Sintomas'."""
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_llm_response("## Análise dos Sintomas\nTexto [Fonte 1].\n## Possíveis Causas\nCausas.\n## Próximos Passos\nPassos.")
        )
        await generate_response(
            question="Atola papel e dá erro E-05",
            query_rewritten="paper jam and E-05 error",
            search_results=[_make_result()],
            diagnostic_mode=True,
        )
        call_kwargs = _patch_openai_client.chat.completions.create.call_args.kwargs
        system_content = call_kwargs["messages"][0]["content"]
        assert "Análise dos Sintomas" in system_content

    @pytest.mark.asyncio
    async def test_diagnostic_mode_uses_2500_tokens(self, _patch_openai_client):
        """diagnostic_mode=True → max_tokens=2500."""
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_llm_response("resposta diagnóstica [Fonte 1]")
        )
        await generate_response(
            question="pergunta",
            query_rewritten="query",
            search_results=[_make_result()],
            diagnostic_mode=True,
        )
        call_kwargs = _patch_openai_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 2500

    @pytest.mark.asyncio
    async def test_normal_mode_uses_1500_tokens(self, _patch_openai_client):
        """diagnostic_mode=False (default) → max_tokens=1500."""
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_llm_response("resposta normal [Fonte 1]")
        )
        await generate_response(
            question="pergunta",
            query_rewritten="query",
            search_results=[_make_result()],
        )
        call_kwargs = _patch_openai_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 1500

    @pytest.mark.asyncio
    async def test_normal_mode_uses_original_prompt(self, _patch_openai_client):
        """diagnostic_mode=False → system message NÃO contém 'Análise dos Sintomas'."""
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_llm_response("resposta normal [Fonte 1]")
        )
        await generate_response(
            question="pergunta",
            query_rewritten="query",
            search_results=[_make_result()],
        )
        call_kwargs = _patch_openai_client.chat.completions.create.call_args.kwargs
        system_content = call_kwargs["messages"][0]["content"]
        assert "Análise dos Sintomas" not in system_content


class TestVersionDiffInGenerator:
    @pytest.mark.asyncio
    async def test_no_diff_uses_default_prompt(self, _patch_openai_client):
        """Sem version_diff: comportamento atual preservado."""
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_llm_response("resposta normal [Fonte 1]")
        )
        resp = await generate_response(
            question="Como trocar o rolo?",
            query_rewritten="How to replace roller",
            search_results=[_make_result()],
            version_diff=None,
            is_comparison_query=False,
        )
        assert resp.answer is not None
        call_args = _patch_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]
        assert "Diferenças entre versões" not in system_msg

    @pytest.mark.asyncio
    async def test_with_diff_explicit_query_uses_comparison_prompt(self, _patch_openai_client):
        from app.services.version_comparator import DiffItem, VersionDiff
        diff = VersionDiff(
            version_old="2024-07-01",
            version_new="2025-01-15",
            diff_items=[DiffItem("modified", "Torque", "10 Nm", "12 Nm")],
            has_changes=True,
        )
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_llm_response("O torque foi modificado [Fonte 1]")
        )
        resp = await generate_response(
            question="O que mudou?",
            query_rewritten="What changed?",
            search_results=[_make_result()],
            version_diff=diff,
            is_comparison_query=True,
        )
        assert resp.answer is not None
        call_args = _patch_openai_client.chat.completions.create.call_args
        system_msg = call_args.kwargs["messages"][0]["content"]
        assert "omparaç" in system_msg or "Diferenças" in system_msg

    @pytest.mark.asyncio
    async def test_no_changes_diff_ignores_diff(self, _patch_openai_client):
        from app.services.version_comparator import VersionDiff
        diff = VersionDiff(
            version_old="2024-07-01",
            version_new="2025-01-15",
            diff_items=[],
            has_changes=False,
        )
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_llm_response("documentos idênticos [Fonte 1]")
        )
        resp = await generate_response(
            question="O que mudou?",
            query_rewritten="What changed?",
            search_results=[_make_result()],
            version_diff=diff,
            is_comparison_query=True,
        )
        assert resp.answer is not None
        call_args = _patch_openai_client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][-1]["content"]
        assert "DIFERENÇAS DETECTADAS" not in user_msg

    @pytest.mark.asyncio
    async def test_implicit_diff_injects_note_in_user_message(self, _patch_openai_client):
        """is_comparison_query=False mas has_changes=True → diff injetado + nota no user message."""
        from app.services.version_comparator import DiffItem, VersionDiff
        diff = VersionDiff(
            version_old="2024-07-01",
            version_new="2025-01-15",
            diff_items=[DiffItem("modified", "Torque", "10 Nm", "12 Nm")],
            has_changes=True,
        )
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_llm_response("O torque foi atualizado [Fonte 1]")
        )
        resp = await generate_response(
            question="Fale sobre o torque",
            query_rewritten="About torque",
            search_results=[_make_result()],
            version_diff=diff,
            is_comparison_query=False,
        )
        assert resp.answer is not None
        call_args = _patch_openai_client.chat.completions.create.call_args
        user_msg = call_args.kwargs["messages"][-1]["content"]
        assert "DIFERENÇAS DETECTADAS" in user_msg
        assert "Integre essas informações" in user_msg
        # Sistema normal usado (não COMPARISON_SYSTEM_PROMPT)
        system_msg = call_args.kwargs["messages"][0]["content"]
        assert "Diferenças entre versões" not in system_msg

    @pytest.mark.asyncio
    async def test_comparison_query_uses_2500_tokens(self, _patch_openai_client):
        """is_comparison_query=True → max_tokens=2500."""
        from app.services.version_comparator import DiffItem, VersionDiff
        diff = VersionDiff(
            version_old="2024-07-01",
            version_new="2025-01-15",
            diff_items=[DiffItem("modified", "Torque", "10 Nm", "12 Nm")],
            has_changes=True,
        )
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_llm_response("resposta [Fonte 1]")
        )
        await generate_response(
            question="O que mudou?",
            query_rewritten="What changed?",
            search_results=[_make_result()],
            version_diff=diff,
            is_comparison_query=True,
        )
        call_kwargs = _patch_openai_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 2500
