"""Tests for app.services.diagnostic_analyzer."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.services.diagnostic_analyzer import decompose_problems, is_diagnostic_query


class TestIsDiagnosticQuery:
    def test_two_weak_patterns_activates(self):
        # "e também" + "também" → 2 weak matches → True
        assert is_diagnostic_query("Não imprime e também trava, também dá erro") is True

    def test_e_tambem_with_second_weak_activates(self):
        assert is_diagnostic_query("O papel não alimenta e também além disso dá erro") is True

    def test_single_tambem_does_not_activate(self):
        # Apenas 1 padrão fraco → False
        assert is_diagnostic_query("Também quero saber a torque do parafuso") is False

    def test_enumeration_strong_pattern_activates(self):
        # "1. sintoma 2. sintoma" — padrão forte, ativa sozinho
        assert is_diagnostic_query("1. não imprime 2. dá erro E-05") is True

    def test_comma_list_strong_pattern_activates(self):
        # 3+ itens substanciais separados por vírgula
        assert is_diagnostic_query(
            "não alimenta o papel, apresenta erro E-05 na tela, trava no final"
        ) is True

    def test_simple_question_does_not_activate(self):
        assert is_diagnostic_query("Como trocar o rolo de pressão da Frontier 780?") is False

    def test_empty_string_does_not_activate(self):
        assert is_diagnostic_query("") is False

    def test_single_symptom_does_not_activate(self):
        assert is_diagnostic_query("O papel está atolando na entrada") is False


def _make_chat_response(content: str):
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.fixture()
def _patch_openai_client():
    mock_client = AsyncMock()
    with patch("app.services.diagnostic_analyzer.get_openai_client", return_value=mock_client):
        yield mock_client


class TestDecomposeProblems:
    @pytest.mark.asyncio
    async def test_valid_json_returns_list(self, _patch_openai_client):
        sub_queries = ["paper jam troubleshooting", "E-05 error code diagnosis"]
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(sub_queries))
        )
        result = await decompose_problems("Atola papel e dá erro E-05")
        assert isinstance(result, list)
        assert result == sub_queries

    @pytest.mark.asyncio
    async def test_invalid_json_falls_back_to_original(self, _patch_openai_client):
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response("não é json válido")
        )
        question = "Atola papel e dá erro E-05"
        result = await decompose_problems(question)
        assert result == [question]

    @pytest.mark.asyncio
    async def test_single_item_returned_as_is(self, _patch_openai_client):
        # 1 item → continua em modo diagnóstico (não faz fallback para original)
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(["paper jam troubleshooting"]))
        )
        result = await decompose_problems("Atola papel")
        assert result == ["paper jam troubleshooting"]

    @pytest.mark.asyncio
    async def test_max_4_items_enforced(self, _patch_openai_client):
        many = ["q1", "q2", "q3", "q4", "q5", "q6"]
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(many))
        )
        result = await decompose_problems("pergunta com muitos problemas")
        assert len(result) <= 4

    @pytest.mark.asyncio
    async def test_empty_list_falls_back_to_original(self, _patch_openai_client):
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response("[]")
        )
        question = "Atola papel e dá erro E-05"
        result = await decompose_problems(question)
        assert result == [question]

    @pytest.mark.asyncio
    async def test_uses_correct_model(self, _patch_openai_client):
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(["q1"]))
        )
        await decompose_problems("pergunta")
        call_kwargs = _patch_openai_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == settings.azure_openai_mini_deployment
