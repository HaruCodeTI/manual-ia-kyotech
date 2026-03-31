"""
Kyotech AI — Testes unitarios para app.services.repository
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.chunker import TextChunk
from app.services.repository import (
    find_or_create_equipment,
    find_or_create_document,
    check_version_exists,
    insert_chunks_with_embeddings,
    get_ingestion_stats,
    list_equipments,
    find_duplicate_groups,
)


# ── find_or_create_equipment ──

@pytest.mark.asyncio
async def test_find_equipment_existing(mock_db, make_mock_result):
    mock_db.execute = AsyncMock(
        return_value=make_mock_result(rows=[("pump-x",)])
    )
    key = await find_or_create_equipment(mock_db, "pump-x")
    assert key == "pump-x"


@pytest.mark.asyncio
async def test_create_equipment_auto_display_name(mock_db, make_mock_result):
    # First call returns nothing (not found), second call is the INSERT
    mock_db.execute = AsyncMock(
        side_effect=[
            make_mock_result(rows=[]),  # SELECT finds nothing
            make_mock_result(),          # INSERT
        ]
    )
    key = await find_or_create_equipment(mock_db, "pump-model-x")
    assert key == "pump-model-x"
    # INSERT was called (second execute call)
    assert mock_db.execute.call_count == 2


# ── find_or_create_document ──

@pytest.mark.asyncio
async def test_find_document_existing(mock_db, make_mock_result):
    doc_id = uuid4()
    mock_db.execute = AsyncMock(
        return_value=make_mock_result(rows=[(doc_id,)])
    )
    result = await find_or_create_document(mock_db, "manual", "pump-x")
    assert result == doc_id


@pytest.mark.asyncio
async def test_create_document_returns_id(mock_db, make_mock_result):
    new_id = uuid4()
    mock_db.execute = AsyncMock(
        side_effect=[
            make_mock_result(rows=[]),          # SELECT finds nothing
            make_mock_result(rows=[(new_id,)]), # INSERT RETURNING
        ]
    )
    result = await find_or_create_document(mock_db, "manual", "pump-x")
    assert result == new_id


# ── check_version_exists ──

@pytest.mark.asyncio
async def test_check_version_exists_true(mock_db, make_mock_result):
    mock_db.execute = AsyncMock(
        return_value=make_mock_result(rows=[(uuid4(),)])
    )
    assert await check_version_exists(mock_db, uuid4(), "abc123") is True


@pytest.mark.asyncio
async def test_check_version_exists_false(mock_db, make_mock_result):
    mock_db.execute = AsyncMock(
        return_value=make_mock_result(rows=[])
    )
    assert await check_version_exists(mock_db, uuid4(), "xyz") is False


# ── insert_chunks_with_embeddings ──

@pytest.mark.asyncio
async def test_insert_chunks_inserts_all(mock_db, make_mock_result):
    mock_db.execute = AsyncMock(return_value=make_mock_result())
    chunks = [
        TextChunk(page_number=1, chunk_index=0, content="chunk 0"),
        TextChunk(page_number=1, chunk_index=1, content="chunk 1"),
        TextChunk(page_number=2, chunk_index=0, content="chunk 2"),
    ]
    embeddings = [[0.1] * 10, [0.2] * 10, [0.3] * 10]

    count = await insert_chunks_with_embeddings(mock_db, uuid4(), chunks, embeddings)

    assert count == 3
    # 1 DELETE + 1 INSERT em lote = 2 execute calls (era 4 antes do batch)
    assert mock_db.execute.call_count == 2
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_insert_chunks_empty_list(mock_db, make_mock_result):
    """Lista vazia deve fazer apenas o DELETE e retornar 0."""
    mock_db.execute = AsyncMock(return_value=make_mock_result())

    count = await insert_chunks_with_embeddings(mock_db, uuid4(), [], [])

    assert count == 0
    # Apenas o DELETE é executado — sem INSERT
    assert mock_db.execute.call_count == 1
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_insert_chunks_raises_on_mismatch(mock_db):
    chunks = [TextChunk(page_number=1, chunk_index=0, content="c")]
    embeddings = [[0.1] * 10, [0.2] * 10]  # 2 embeddings for 1 chunk

    with pytest.raises(ValueError, match="Mismatch"):
        await insert_chunks_with_embeddings(mock_db, uuid4(), chunks, embeddings)


# ── get_ingestion_stats ──

@pytest.mark.asyncio
async def test_get_ingestion_stats(mock_db, make_mock_result):
    mock_db.execute = AsyncMock(
        return_value=make_mock_result(rows=[(5, 10, 15, 200, 2)])
    )
    stats = await get_ingestion_stats(mock_db)
    assert stats == {
        "equipments": 5,
        "documents": 10,
        "versions": 15,
        "chunks": 200,
        "docs_without_chunks": 2,
    }


# ── list_equipments ──

@pytest.mark.asyncio
async def test_list_equipments(mock_db, make_mock_result):
    mock_db.execute = AsyncMock(
        return_value=make_mock_result(rows=[("pump-a", "Pump A"), ("motor-b", "Motor B")])
    )
    result = await list_equipments(mock_db)
    assert result == [
        {"key": "pump-a", "name": "Pump A"},
        {"key": "motor-b", "name": "Motor B"},
    ]


# ── find_duplicate_groups ──

@pytest.mark.asyncio
async def test_find_duplicate_groups_returns_grouped(mock_db, make_mock_result):
    """Deve retornar grupos com keep (mais antigo) e duplicates (demais)."""
    from datetime import date, datetime

    # Simula query de hashes duplicados
    hash_rows = [("hash_abc", 2)]
    # Simula query de versões por hash
    version_rows = [
        (
            "ver-1", "doc-1", "manual.pdf", "frontier-780", "manual",
            date(2025, 1, 15), datetime(2025, 1, 15, 10, 0, 0),
            "container/path1.pdf", 10,
        ),
        (
            "ver-2", "doc-2", "manual.pdf", "frontier-780", "manual",
            date(2025, 3, 1), datetime(2025, 3, 1, 14, 30, 0),
            "container/path2.pdf", 10,
        ),
    ]

    mock_db.execute = AsyncMock(
        side_effect=[
            make_mock_result(rows=hash_rows),
            make_mock_result(rows=version_rows),
        ]
    )

    result = await find_duplicate_groups(mock_db)

    assert result["total_groups"] == 1
    assert result["total_removable"] == 1
    assert result["groups"][0]["keep"]["version_id"] == "ver-1"
    assert len(result["groups"][0]["duplicates"]) == 1
    assert result["groups"][0]["duplicates"][0]["version_id"] == "ver-2"


@pytest.mark.asyncio
async def test_find_duplicate_groups_empty(mock_db, make_mock_result):
    """Sem duplicatas, deve retornar lista vazia."""
    mock_db.execute = AsyncMock(
        return_value=make_mock_result(rows=[])
    )

    result = await find_duplicate_groups(mock_db)

    assert result["total_groups"] == 0
    assert result["total_removable"] == 0
    assert result["groups"] == []
