"""
Kyotech AI — Testes unitários para app.services.equipment_detector
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.equipment_detector import (
    build_equipment_patterns,
    detect_equipment_mentions,
    detect_mentions_for_version,
)


# ── build_equipment_patterns ──

def test_build_patterns_returns_dict_keyed_by_equipment():
    equipment_list = [("ec-720r/l", ["EC-720R/L", "720R"]), ("ec-530", [])]
    patterns = build_equipment_patterns(equipment_list)
    assert "ec-720r/l" in patterns
    assert "ec-530" in patterns


def test_build_patterns_includes_aliases():
    equipment_list = [("ec-720r/l", ["720R/L", "EC720"])]
    patterns = build_equipment_patterns(equipment_list)
    pattern = patterns["ec-720r/l"]
    assert pattern.search("the 720R/L guide") is not None
    assert pattern.search("EC720 repair") is not None


def test_build_patterns_matches_key_case_insensitive():
    equipment_list = [("ec-530wm", [])]
    patterns = build_equipment_patterns(equipment_list)
    assert patterns["ec-530wm"].search("ec-530WM adhesive") is not None
    assert patterns["ec-530wm"].search("EC-530wm adhesive") is not None


def test_build_patterns_no_partial_match():
    """EC-530 should not match EC-5300."""
    equipment_list = [("ec-530", [])]
    patterns = build_equipment_patterns(equipment_list)
    assert patterns["ec-530"].search("EC-5300 unit") is None


# ── detect_equipment_mentions ──

def test_detect_mentions_returns_matched_keys():
    equipment_list = [("ec-720r/l", ["EC-720R/L"]), ("ec-530", [])]
    patterns = build_equipment_patterns(equipment_list)
    result = detect_equipment_mentions(
        "Use adhesive on EC-720R/L light guide lens.", patterns
    )
    assert result == ["ec-720r/l"]


def test_detect_mentions_returns_empty_for_no_match():
    equipment_list = [("ec-720r/l", []), ("ec-530", [])]
    patterns = build_equipment_patterns(equipment_list)
    result = detect_equipment_mentions("Generic repair procedure.", patterns)
    assert result == []


def test_detect_mentions_deduplicates():
    equipment_list = [("ec-720r/l", ["EC-720R/L"])]
    patterns = build_equipment_patterns(equipment_list)
    result = detect_equipment_mentions(
        "EC-720R/L and EC-720R/L again", patterns
    )
    assert result.count("ec-720r/l") == 1


def test_detect_mentions_finds_multiple_equipments():
    equipment_list = [("ec-720r/l", []), ("ec-530", [])]
    patterns = build_equipment_patterns(equipment_list)
    result = detect_equipment_mentions(
        "Compatible with EC-720R/L and EC-530.", patterns
    )
    assert set(result) == {"ec-720r/l", "ec-530"}


# ── detect_mentions_for_version ──

@pytest.mark.asyncio
async def test_detect_mentions_for_version_updates_chunks(mock_db, make_mock_result):
    chunk_rows = [
        ("chunk-1", "Adhesive for EC-720R/L light guide."),
        ("chunk-2", "Generic endoscope cleaning procedure."),
    ]
    equipment_rows = [("ec-720r/l", []), ("ec-530", [])]

    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_result(rows=equipment_rows)
        return make_mock_result(rows=chunk_rows)

    mock_db.execute = AsyncMock(side_effect=side_effect)

    await detect_mentions_for_version(mock_db, "version-uuid-123")

    assert mock_db.execute.call_count >= 2
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_detect_mentions_for_version_skips_empty_chunks(mock_db, make_mock_result):
    equipment_rows = [("ec-720r/l", [])]
    chunk_rows = []

    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_mock_result(rows=equipment_rows)
        return make_mock_result(rows=chunk_rows)

    mock_db.execute = AsyncMock(side_effect=side_effect)

    await detect_mentions_for_version(mock_db, "version-uuid-123")

    mock_db.commit.assert_not_awaited()
