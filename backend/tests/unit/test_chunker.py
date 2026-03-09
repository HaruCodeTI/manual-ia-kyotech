"""Tests for app.services.chunker — chunk_text and chunk_pages."""
from __future__ import annotations

import pytest

from app.services.chunker import TextChunk, chunk_pages, chunk_text
from app.services.pdf_extractor import PageContent


# ── chunk_text ──


class TestChunkTextShort:
    """Short text that fits in a single chunk."""

    def test_returns_single_chunk(self):
        result = chunk_text("Hello world", chunk_size=100, chunk_overlap=20)
        assert result == ["Hello world"]

    def test_exact_size_returns_single_chunk(self):
        text = "a" * 50
        result = chunk_text(text, chunk_size=50, chunk_overlap=10)
        assert result == [text]


class TestChunkTextLong:
    """Long text must be split into multiple chunks."""

    def test_multiple_chunks_produced(self):
        text = "word " * 200  # 1000 chars
        result = chunk_text(text, chunk_size=100, chunk_overlap=0)
        assert len(result) > 1

    def test_all_content_present(self):
        words = [f"w{i}" for i in range(100)]
        text = " ".join(words)
        chunks = chunk_text(text, chunk_size=50, chunk_overlap=0)
        combined = " ".join(chunks)
        for w in words:
            assert w in combined


class TestChunkTextOverlap:
    """Overlap creates shared content between consecutive chunks."""

    def test_overlap_shares_content(self):
        text = "A" * 200
        chunks = chunk_text(text, chunk_size=100, chunk_overlap=30)
        assert len(chunks) >= 2
        # With overlap, the end of chunk 0 should share chars with the start of chunk 1
        tail = chunks[0][-30:]
        head = chunks[1][:30]
        assert tail == head


class TestChunkTextEmpty:
    """Empty or whitespace-only text returns empty list."""

    def test_empty_string(self):
        assert chunk_text("", chunk_size=100, chunk_overlap=10) == [""]

    def test_whitespace_only(self):
        # chunk_text does not strip input — returns the whitespace as a chunk
        result = chunk_text("   ", chunk_size=100, chunk_overlap=10)
        assert len(result) == 1


class TestChunkTextBreaks:
    """Prefers newline/space breaks over hard cuts."""

    def test_prefers_newline_break(self):
        line = "a" * 40
        text = f"{line}\n{line}\n{line}"
        chunks = chunk_text(text, chunk_size=50, chunk_overlap=0)
        # First chunk should end at the newline boundary
        assert chunks[0].endswith(line)

    def test_prefers_space_break(self):
        text = "hello " * 20  # 120 chars
        chunks = chunk_text(text, chunk_size=50, chunk_overlap=0)
        for chunk in chunks:
            # No word should be cut mid-way (no leading/trailing partial words)
            assert chunk == chunk.strip()


# ── chunk_pages ──


class TestChunkPages:
    def test_skips_empty_pages(self):
        pages = [
            PageContent(page_number=1, text="Some text here."),
            PageContent(page_number=2, text="   "),
            PageContent(page_number=3, text="More text here."),
        ]
        result = chunk_pages(pages, chunk_size=800, chunk_overlap=200)
        page_numbers = {c.page_number for c in result}
        assert 2 not in page_numbers
        assert 1 in page_numbers
        assert 3 in page_numbers

    def test_returns_textchunk_dataclass(self):
        pages = [PageContent(page_number=5, text="Content for page five.")]
        result = chunk_pages(pages, chunk_size=800, chunk_overlap=200)
        assert len(result) >= 1
        chunk = result[0]
        assert isinstance(chunk, TextChunk)
        assert chunk.page_number == 5
        assert chunk.chunk_index == 0
        assert "Content for page five" in chunk.content

    def test_multiple_chunks_per_page(self):
        long_text = "word " * 400
        pages = [PageContent(page_number=1, text=long_text)]
        result = chunk_pages(pages, chunk_size=100, chunk_overlap=20)
        assert len(result) > 1
        assert all(c.page_number == 1 for c in result)
        # chunk_index should be sequential
        indices = [c.chunk_index for c in result]
        assert indices == list(range(len(result)))
