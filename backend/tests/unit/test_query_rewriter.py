"""Tests for app.services.query_rewriter — rewrite_query."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.query_rewriter import RewrittenQuery, rewrite_query


def _make_chat_response(content: str):
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.fixture(autouse=True)
def _patch_openai_client():
    mock_client = AsyncMock()
    with patch("app.services.query_rewriter.get_openai_client", return_value=mock_client):
        yield mock_client


class TestRewriteQuery:
    @pytest.mark.asyncio
    async def test_valid_json_parses(self, _patch_openai_client):
        payload = {
            "query_en": "How to replace pressure roller",
            "doc_type": "manual",
            "equipment_hint": "Frontier 780",
        }
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(payload))
        )
        result = await rewrite_query("Como trocar o rolo de pressao?")
        assert isinstance(result, RewrittenQuery)
        assert result.query_en == "How to replace pressure roller"
        assert result.doc_type == "manual"
        assert result.equipment_hint == "frontier-780"

    @pytest.mark.asyncio
    async def test_doc_type_both_becomes_none(self, _patch_openai_client):
        payload = {
            "query_en": "query",
            "doc_type": "both",
            "equipment_hint": None,
        }
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(payload))
        )
        result = await rewrite_query("pergunta")
        assert result.doc_type is None

    @pytest.mark.asyncio
    async def test_equipment_hint_null_string_becomes_none(self, _patch_openai_client):
        payload = {
            "query_en": "query",
            "doc_type": "manual",
            "equipment_hint": "null",
        }
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(payload))
        )
        result = await rewrite_query("pergunta")
        assert result.equipment_hint is None

    @pytest.mark.asyncio
    async def test_equipment_hint_normalized(self, _patch_openai_client):
        payload = {
            "query_en": "query",
            "doc_type": "manual",
            "equipment_hint": "Frontier DE 100",
        }
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(payload))
        )
        result = await rewrite_query("pergunta")
        assert result.equipment_hint == "frontier-de-100"

    @pytest.mark.asyncio
    async def test_invalid_json_falls_back(self, _patch_openai_client):
        _patch_openai_client.chat.completions.create = AsyncMock(
            return_value=_make_chat_response("this is not json at all")
        )
        result = await rewrite_query("pergunta original")
        assert result.query_en == "pergunta original"
        assert result.doc_type is None
        assert result.equipment_hint is None
        assert result.original == "pergunta original"
