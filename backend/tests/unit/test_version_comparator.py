"""Tests for app.services.version_comparator."""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.search import SearchResult
from app.services.version_comparator import (
    DiffItem,
    VersionDiff,
    compare_versions,
    detect_multi_version,
    group_chunks_by_version,
)


# ── Helpers ──

def _make_result(
    chunk_id="c1",
    document_id="doc-a",
    document_version_id="ver-1",
    published_date=date(2024, 7, 1),
    content="texto de teste",
    similarity=0.9,
) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        content=content,
        page_number=1,
        similarity=similarity,
        document_id=document_id,
        doc_type="manual",
        equipment_key="frontier-780",
        published_date=published_date,
        source_filename=f"manual_{published_date}.pdf",
        storage_path="container/blob",
        search_type="vector",
        document_version_id=document_version_id,
    )


def _make_chat_response(content: str):
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ── detect_multi_version ──

class TestDetectMultiVersion:
    def test_false_when_empty(self):
        assert detect_multi_version([]) is False

    def test_false_when_single_version(self):
        results = [
            _make_result(chunk_id="c1", document_id="doc-a", document_version_id="ver-1"),
            _make_result(chunk_id="c2", document_id="doc-a", document_version_id="ver-1"),
        ]
        assert detect_multi_version(results) is False

    def test_false_when_different_documents(self):
        # Chunks de doc_ids diferentes não ativam comparação
        results = [
            _make_result(chunk_id="c1", document_id="doc-a", document_version_id="ver-1"),
            _make_result(chunk_id="c2", document_id="doc-b", document_version_id="ver-2"),
        ]
        assert detect_multi_version(results) is False

    def test_true_when_same_doc_different_versions(self):
        results = [
            _make_result(chunk_id="c1", document_id="doc-a", document_version_id="ver-1"),
            _make_result(chunk_id="c2", document_id="doc-a", document_version_id="ver-2"),
        ]
        assert detect_multi_version(results) is True

    def test_true_with_three_versions_same_doc(self):
        results = [
            _make_result(chunk_id="c1", document_id="doc-a", document_version_id="ver-1"),
            _make_result(chunk_id="c2", document_id="doc-a", document_version_id="ver-2"),
            _make_result(chunk_id="c3", document_id="doc-a", document_version_id="ver-3"),
        ]
        assert detect_multi_version(results) is True


# ── group_chunks_by_version ──

class TestGroupChunksByVersion:
    def test_groups_by_published_date(self):
        results = [
            _make_result(chunk_id="c1", document_version_id="ver-1", published_date=date(2024, 7, 1)),
            _make_result(chunk_id="c2", document_version_id="ver-2", published_date=date(2025, 1, 15)),
        ]
        grouped = group_chunks_by_version(results)
        assert "2024-07-01" in grouped
        assert "2025-01-15" in grouped
        assert grouped["2024-07-01"][0].chunk_id == "c1"

    def test_ordered_chronologically_oldest_first(self):
        results = [
            _make_result(chunk_id="c2", document_version_id="ver-2", published_date=date(2025, 1, 15)),
            _make_result(chunk_id="c1", document_version_id="ver-1", published_date=date(2024, 7, 1)),
        ]
        grouped = group_chunks_by_version(results)
        keys = list(grouped.keys())
        assert keys[0] == "2024-07-01"
        assert keys[1] == "2025-01-15"

    def test_multiple_chunks_same_version(self):
        results = [
            _make_result(chunk_id="c1", document_version_id="ver-1", published_date=date(2024, 7, 1)),
            _make_result(chunk_id="c2", document_version_id="ver-1", published_date=date(2024, 7, 1)),
            _make_result(chunk_id="c3", document_version_id="ver-2", published_date=date(2025, 1, 15)),
        ]
        grouped = group_chunks_by_version(results)
        assert len(grouped["2024-07-01"]) == 2
        assert len(grouped["2025-01-15"]) == 1


# ── compare_versions ──

@pytest.fixture()
def _patch_openai():
    mock_client = AsyncMock()
    with patch("app.services.version_comparator.get_openai_client", return_value=mock_client):
        yield mock_client


class TestCompareVersions:
    @pytest.mark.asyncio
    async def test_has_changes_returns_diff_items(self, _patch_openai):
        diff_payload = {
            "diff_items": [
                {"change_type": "modified", "topic": "Torque", "old_value": "10 Nm", "new_value": "12 Nm"}
            ],
            "has_changes": True,
        }
        _patch_openai.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(diff_payload))
        )
        grouped = {
            "2024-07-01": [_make_result(chunk_id="c1", published_date=date(2024, 7, 1))],
            "2025-01-15": [_make_result(chunk_id="c2", published_date=date(2025, 1, 15))],
        }
        result = await compare_versions(grouped)
        assert isinstance(result, VersionDiff)
        assert result.has_changes is True
        assert len(result.diff_items) == 1
        assert result.diff_items[0].change_type == "modified"
        assert result.diff_items[0].topic == "Torque"
        assert result.version_old == "2024-07-01"
        assert result.version_new == "2025-01-15"

    @pytest.mark.asyncio
    async def test_no_changes(self, _patch_openai):
        diff_payload = {"diff_items": [], "has_changes": False}
        _patch_openai.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(diff_payload))
        )
        grouped = {
            "2024-07-01": [_make_result(chunk_id="c1", published_date=date(2024, 7, 1))],
            "2025-01-15": [_make_result(chunk_id="c2", published_date=date(2025, 1, 15))],
        }
        result = await compare_versions(grouped)
        assert result.has_changes is False
        assert result.diff_items == []

    @pytest.mark.asyncio
    async def test_malformed_json_raises(self, _patch_openai):
        _patch_openai.chat.completions.create = AsyncMock(
            return_value=_make_chat_response("não é json válido")
        )
        grouped = {
            "2024-07-01": [_make_result(chunk_id="c1", published_date=date(2024, 7, 1))],
            "2025-01-15": [_make_result(chunk_id="c2", published_date=date(2025, 1, 15))],
        }
        with pytest.raises(json.JSONDecodeError):
            await compare_versions(grouped)

    @pytest.mark.asyncio
    async def test_uses_mini_model(self, _patch_openai):
        from app.core.config import settings
        diff_payload = {"diff_items": [], "has_changes": False}
        _patch_openai.chat.completions.create = AsyncMock(
            return_value=_make_chat_response(json.dumps(diff_payload))
        )
        grouped = {
            "2024-07-01": [_make_result(chunk_id="c1", published_date=date(2024, 7, 1))],
            "2025-01-15": [_make_result(chunk_id="c2", published_date=date(2025, 1, 15))],
        }
        await compare_versions(grouped)
        call_kwargs = _patch_openai.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == settings.azure_openai_mini_deployment
