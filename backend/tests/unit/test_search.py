"""
Kyotech AI — Testes unitários para app.services.search
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.search import SearchResult, vector_search, text_search, hybrid_search, EQUIPMENT_BOOST, MIN_SCORE_THRESHOLD


# ── Helpers ──

def _make_row(chunk_id="c1", content="texto", page=1, similarity=0.9,
              doc_id="d1", doc_type="manual", equip="equip-a",
              pub_date=date(2024, 1, 1), filename="f.pdf",
              storage="container/blob", version_id="v1", quality_score=0.0,
              equipment_mentions=None):
    return (chunk_id, content, page, similarity, doc_id, doc_type,
            equip, pub_date, filename, storage, version_id, quality_score,
            equipment_mentions or [])


# ── vector_search ──

@pytest.mark.asyncio
async def test_vector_search_returns_search_results(mock_db, make_mock_result):
    rows = [_make_row(), _make_row(chunk_id="c2", similarity=0.8)]
    mock_db.execute = AsyncMock(return_value=make_mock_result(rows=rows))

    with patch("app.services.search.generate_single_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536):
        results = await vector_search(mock_db, "query")

    assert len(results) == 2
    assert all(isinstance(r, SearchResult) for r in results)
    assert results[0].search_type == "vector"
    assert results[0].chunk_id == "c1"


@pytest.mark.asyncio
async def test_vector_search_handles_empty_results(mock_db, make_mock_result):
    mock_db.execute = AsyncMock(return_value=make_mock_result(rows=[]))

    with patch("app.services.search.generate_single_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536):
        results = await vector_search(mock_db, "nothing here")

    assert results == []


@pytest.mark.asyncio
async def test_vector_search_passes_filters(mock_db, make_mock_result):
    mock_db.execute = AsyncMock(return_value=make_mock_result(rows=[]))

    with patch("app.services.search.generate_single_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536):
        await vector_search(mock_db, "q", doc_type="manual", equipment_key="pump-x")

    call_args = mock_db.execute.call_args
    sql_text = str(call_args[0][0].text)
    params = call_args[1] if call_args[1] else call_args[0][1]
    assert "doc_type" in params
    assert "equipment" in params


# ── text_search ──

@pytest.mark.asyncio
async def test_text_search_returns_text_type(mock_db, make_mock_result):
    rows = [_make_row(similarity=0.5)]
    mock_db.execute = AsyncMock(return_value=make_mock_result(rows=rows))

    results = await text_search(mock_db, "code 123")

    assert len(results) == 1
    assert results[0].search_type == "text"


# ── hybrid_search ──

@pytest.mark.asyncio
async def test_hybrid_search_merges_and_deduplicates(mock_db, make_mock_result):
    """Same chunk_id in both searches → search_type becomes 'hybrid'."""
    shared_row = _make_row(chunk_id="shared", similarity=0.9)
    vector_only = _make_row(chunk_id="vec-only", similarity=0.7)
    text_only = _make_row(chunk_id="txt-only", similarity=0.6)

    vector_result = make_mock_result(rows=[shared_row, vector_only])
    text_result = make_mock_result(rows=[shared_row, text_only])

    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return vector_result
        return text_result

    mock_db.execute = AsyncMock(side_effect=side_effect)

    with patch("app.services.search.generate_single_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536):
        results = await hybrid_search(mock_db, "query en", "query pt")

    chunk_ids = [r.chunk_id for r in results]
    # No duplicates
    assert len(chunk_ids) == len(set(chunk_ids))
    # shared chunk should be "hybrid"
    shared = [r for r in results if r.chunk_id == "shared"]
    assert len(shared) == 1
    assert shared[0].search_type == "hybrid"


@pytest.mark.asyncio
async def test_hybrid_search_respects_limit(mock_db, make_mock_result):
    rows = [_make_row(chunk_id=f"c{i}", similarity=0.9 - i * 0.1) for i in range(5)]
    mock_db.execute = AsyncMock(return_value=make_mock_result(rows=rows))

    with patch("app.services.search.generate_single_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536):
        results = await hybrid_search(mock_db, "q", "q", limit=3)

    assert len(results) <= 3


@pytest.mark.asyncio
async def test_hybrid_search_boosts_matching_equipment(mock_db, make_mock_result):
    """Chunks from the queried equipment get a score boost."""
    matching = _make_row(chunk_id="match", similarity=0.5, equip="frontier-780")
    other = _make_row(chunk_id="other", similarity=0.5, equip="frontier-590")

    mock_db.execute = AsyncMock(return_value=make_mock_result(rows=[matching, other]))

    with patch("app.services.search.generate_single_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536):
        results = await hybrid_search(mock_db, "q", "q", equipment_key="frontier-780")

    assert results[0].chunk_id == "match"
    assert results[0].similarity > results[1].similarity


@pytest.mark.asyncio
async def test_hybrid_search_filters_low_scores(mock_db, make_mock_result):
    """Results below MIN_SCORE_THRESHOLD are excluded."""
    good = _make_row(chunk_id="good", similarity=0.8)
    bad = _make_row(chunk_id="bad", similarity=0.05)

    mock_db.execute = AsyncMock(return_value=make_mock_result(rows=[good, bad]))

    with patch("app.services.search.generate_single_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536):
        results = await hybrid_search(mock_db, "q", "q")

    chunk_ids = [r.chunk_id for r in results]
    assert "good" in chunk_ids
    assert "bad" not in chunk_ids


class TestIncludeAllVersions:
    @pytest.mark.asyncio
    async def test_vector_search_uses_current_versions_by_default(self, mock_db, make_mock_result):
        mock_db.execute = AsyncMock(return_value=make_mock_result(rows=[]))
        with patch("app.services.search.generate_single_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536):
            await vector_search(mock_db, "query")
        sql_text = str(mock_db.execute.call_args[0][0].text)
        assert "current_versions" in sql_text
        assert "document_versions" not in sql_text.replace("current_versions", "")

    @pytest.mark.asyncio
    async def test_vector_search_uses_document_versions_when_flag_true(self, mock_db, make_mock_result):
        mock_db.execute = AsyncMock(return_value=make_mock_result(rows=[]))
        with patch("app.services.search.generate_single_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536):
            await vector_search(mock_db, "query", include_all_versions=True)
        sql_text = str(mock_db.execute.call_args[0][0].text)
        assert "document_versions" in sql_text
        assert "current_versions" not in sql_text

    @pytest.mark.asyncio
    async def test_text_search_uses_document_versions_when_flag_true(self, mock_db, make_mock_result):
        mock_db.execute = AsyncMock(return_value=make_mock_result(rows=[]))
        await text_search(mock_db, "query", include_all_versions=True)
        sql_text = str(mock_db.execute.call_args[0][0].text)
        assert "document_versions" in sql_text
        assert "current_versions" not in sql_text

    @pytest.mark.asyncio
    async def test_hybrid_search_passes_flag_to_sub_searches(self, mock_db, make_mock_result):
        mock_db.execute = AsyncMock(return_value=make_mock_result(rows=[]))
        with patch("app.services.search.vector_search", new_callable=AsyncMock, return_value=[]) as mock_v, \
             patch("app.services.search.text_search", new_callable=AsyncMock, return_value=[]) as mock_t:
            await hybrid_search(mock_db, "q_en", "q_pt", include_all_versions=True)
        mock_v.assert_called_once()
        assert mock_v.call_args.kwargs.get("include_all_versions") is True
        mock_t.assert_called_once()
        assert mock_t.call_args.kwargs.get("include_all_versions") is True


@pytest.mark.asyncio
async def test_hybrid_search_boosts_equipment_mentions(mock_db, make_mock_result):
    """Chunk sem equipment_key mas com equipment_mentions recebe boost."""
    mention_row = _make_row(
        chunk_id="mention", similarity=0.5, equip=None,
        equipment_mentions=["ec-720r/l"]
    )
    tagged_row = _make_row(
        chunk_id="tagged", similarity=0.5, equip="ec-720r/l",
        equipment_mentions=[]
    )
    other_row = _make_row(
        chunk_id="other", similarity=0.5, equip="ec-530",
        equipment_mentions=[]
    )

    mock_db.execute = AsyncMock(
        return_value=make_mock_result(rows=[mention_row, tagged_row, other_row])
    )

    with patch("app.services.search.generate_single_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536):
        results = await hybrid_search(mock_db, "q", "q", equipment_key="ec-720r/l")

    ids_in_order = [r.chunk_id for r in results]
    assert ids_in_order.index("other") > ids_in_order.index("mention")
    assert ids_in_order.index("other") > ids_in_order.index("tagged")


@pytest.mark.asyncio
async def test_hybrid_search_boosts_content_mention(mock_db, make_mock_result):
    """Chunk sem equipment_key nem equipment_mentions, mas com o equipment_key no conteúdo, recebe boost."""
    content_row = _make_row(
        chunk_id="content", similarity=0.5, equip=None,
        content="Repair manual for EC-720R/L endoscope light guide lens adhesive.",
        equipment_mentions=[]
    )
    other_row = _make_row(
        chunk_id="other", similarity=0.5, equip=None,
        content="Unrelated content about something else.",
        equipment_mentions=[]
    )

    mock_db.execute = AsyncMock(
        return_value=make_mock_result(rows=[content_row, other_row])
    )

    with patch("app.services.search.generate_single_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536):
        results = await hybrid_search(mock_db, "q", "q", equipment_key="ec-720r/l")

    ids_in_order = [r.chunk_id for r in results]
    assert ids_in_order.index("other") > ids_in_order.index("content")


@pytest.mark.asyncio
async def test_hybrid_search_uses_pool_of_30(mock_db, make_mock_result):
    """hybrid_search deve passar limit=30 para vector_search e text_search."""
    mock_db.execute = AsyncMock(return_value=make_mock_result(rows=[]))

    with patch("app.services.search.vector_search", new_callable=AsyncMock, return_value=[]) as mock_v, \
         patch("app.services.search.text_search", new_callable=AsyncMock, return_value=[]) as mock_t:
        await hybrid_search(mock_db, "q_en", "q_pt", limit=8)

    assert mock_v.call_args.kwargs.get("limit") == 30
    assert mock_t.call_args.kwargs.get("limit") == 30
