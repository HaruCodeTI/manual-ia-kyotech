"""Tests for app.services.pdf_extractor — compute_file_hash and extract_text_from_pdf."""
from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import pytest

from app.services.pdf_extractor import (
    PDFExtraction,
    PageContent,
    compute_file_hash,
    extract_text_from_pdf,
)


class TestComputeFileHash:
    def test_sha256_correctness(self):
        data = b"hello world"
        expected = hashlib.sha256(data).hexdigest()
        assert compute_file_hash(data) == expected

    def test_different_data_different_hash(self):
        assert compute_file_hash(b"a") != compute_file_hash(b"b")

    def test_deterministic(self):
        data = b"same content"
        assert compute_file_hash(data) == compute_file_hash(data)


class TestExtractTextFromPdf:
    @pytest.mark.anyio
    async def test_extracts_text(self, sample_pdf_bytes):
        result = await extract_text_from_pdf(sample_pdf_bytes, "test.pdf")
        assert isinstance(result, PDFExtraction)
        assert result.filename == "test.pdf"
        assert len(result.pages) == 2
        assert result.total_pages == 2

    @pytest.mark.anyio
    async def test_pages_have_correct_numbers(self, sample_pdf_bytes):
        result = await extract_text_from_pdf(sample_pdf_bytes, "test.pdf")
        assert result.pages[0].page_number == 1
        assert result.pages[1].page_number == 2

    @pytest.mark.anyio
    async def test_pages_contain_text(self, sample_pdf_bytes):
        result = await extract_text_from_pdf(sample_pdf_bytes, "test.pdf")
        assert "Page 1" in result.pages[0].text
        assert "sample text" in result.pages[0].text

    @pytest.mark.anyio
    async def test_source_hash_matches(self, sample_pdf_bytes):
        result = await extract_text_from_pdf(sample_pdf_bytes, "test.pdf")
        assert result.source_hash == compute_file_hash(sample_pdf_bytes)

    @pytest.mark.anyio
    async def test_raises_on_invalid_bytes(self):
        with pytest.raises(Exception):
            await extract_text_from_pdf(b"not a pdf", "bad.pdf")


class TestExtractTextFallbackOcr:
    @pytest.mark.anyio
    async def test_falls_back_to_ocr_for_blank_pdf(self):
        """A PDF with no text should trigger OCR fallback."""
        import fitz

        doc = fitz.open()
        doc.new_page(width=595, height=842)
        pdf_bytes = doc.tobytes()
        doc.close()

        ocr_pages = [PageContent(page_number=1, text="OCR extracted text")]
        with patch("app.services.ocr.ocr_pdf", new_callable=AsyncMock, return_value=ocr_pages):
            result = await extract_text_from_pdf(pdf_bytes, "scanned.pdf")

        assert len(result.pages) == 1
        assert result.pages[0].text == "OCR extracted text"
        assert result.total_pages == 1

    @pytest.mark.anyio
    async def test_ocr_only_for_blank_pages_in_mixed_pdf(self):
        """Mixed PDF: digital pages kept, OCR only called for blank pages."""
        import fitz

        doc = fitz.open()
        p1 = doc.new_page(width=595, height=842)
        p1.insert_text(fitz.Point(72, 72), "Digital text page 1", fontsize=12)
        doc.new_page(width=595, height=842)
        pdf_bytes = doc.tobytes()
        doc.close()

        ocr_pages = [PageContent(page_number=2, text="OCR text page 2")]
        mock_ocr = AsyncMock(return_value=ocr_pages)
        with patch("app.services.ocr.ocr_pdf", mock_ocr):
            result = await extract_text_from_pdf(pdf_bytes, "mixed.pdf")

        mock_ocr.assert_called_once()
        call_kwargs = mock_ocr.call_args
        assert call_kwargs[1]["page_numbers"] == [2]

        assert len(result.pages) == 2
        assert "Digital text" in result.pages[0].text
        assert "OCR text" in result.pages[1].text

    @pytest.mark.anyio
    async def test_raises_if_ocr_also_returns_empty(self):
        """If OCR also finds nothing, should still raise ValueError."""
        import fitz

        doc = fitz.open()
        doc.new_page(width=595, height=842)
        pdf_bytes = doc.tobytes()
        doc.close()

        with patch("app.services.ocr.ocr_pdf", new_callable=AsyncMock, return_value=[]):
            with pytest.raises(ValueError, match="não contém texto extraível mesmo após OCR"):
                await extract_text_from_pdf(pdf_bytes, "empty.pdf")

    @pytest.mark.anyio
    async def test_skips_ocr_when_all_pages_have_text(self, sample_pdf_bytes):
        """Should NOT call OCR when all pages have text."""
        mock_ocr = AsyncMock()
        with patch("app.services.ocr.ocr_pdf", mock_ocr):
            result = await extract_text_from_pdf(sample_pdf_bytes, "digital.pdf")

        mock_ocr.assert_not_called()
        assert len(result.pages) == 2
