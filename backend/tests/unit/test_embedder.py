"""Tests for app.services.embedder — generate_embeddings and generate_single_embedding."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.embedder import generate_embeddings, generate_single_embedding


def _make_embedding_response(count: int = 1, dim: int = 1536):
    """Build a mock embedding response with `count` items of dimension `dim`."""
    items = []
    for _ in range(count):
        item = MagicMock()
        item.embedding = [0.1] * dim
        items.append(item)
    response = MagicMock()
    response.data = items
    return response


@pytest.fixture(autouse=True)
def _patch_embedder_client():
    """Patch the module-level _client so get_openai_client returns our mock."""
    mock_client = AsyncMock()
    mock_client.embeddings.create = AsyncMock(
        side_effect=lambda **kw: _make_embedding_response(count=len(kw["input"]))
    )
    with patch("app.services.embedder._client", mock_client), \
         patch("app.services.embedder.get_openai_client", return_value=mock_client):
        yield mock_client


class TestGenerateEmbeddings:
    @pytest.mark.asyncio
    async def test_single_text_returns_1536(self, _patch_embedder_client):
        result = await generate_embeddings(["hello"])
        assert len(result) == 1
        assert len(result[0]) == 1536

    @pytest.mark.asyncio
    async def test_batching(self, _patch_embedder_client):
        """120 texts with batch_size=50 should produce 3 API calls."""
        texts = [f"text-{i}" for i in range(120)]
        result = await generate_embeddings(texts, batch_size=50)
        assert len(result) == 120
        assert _patch_embedder_client.embeddings.create.call_count == 3

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self, _patch_embedder_client):
        result = await generate_embeddings([])
        assert result == []
        _patch_embedder_client.embeddings.create.assert_not_called()


class TestGenerateSingleEmbedding:
    @pytest.mark.asyncio
    async def test_returns_vector(self, _patch_embedder_client):
        result = await generate_single_embedding("query text")
        assert len(result) == 1536
        assert isinstance(result, list)
