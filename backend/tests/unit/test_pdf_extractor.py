"""Tests for app.services.pdf_extractor — compute_file_hash and extract_text_from_pdf."""
from __future__ import annotations

import hashlib

import pytest

from app.services.pdf_extractor import (
    PDFExtraction,
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
    def test_extracts_text(self, sample_pdf_bytes):
        result = extract_text_from_pdf(sample_pdf_bytes, "test.pdf")
        assert isinstance(result, PDFExtraction)
        assert result.filename == "test.pdf"
        assert len(result.pages) == 2
        assert result.total_pages == 2

    def test_pages_have_correct_numbers(self, sample_pdf_bytes):
        result = extract_text_from_pdf(sample_pdf_bytes, "test.pdf")
        assert result.pages[0].page_number == 1
        assert result.pages[1].page_number == 2

    def test_pages_contain_text(self, sample_pdf_bytes):
        result = extract_text_from_pdf(sample_pdf_bytes, "test.pdf")
        assert "Page 1" in result.pages[0].text
        assert "sample text" in result.pages[0].text

    def test_source_hash_matches(self, sample_pdf_bytes):
        result = extract_text_from_pdf(sample_pdf_bytes, "test.pdf")
        assert result.source_hash == compute_file_hash(sample_pdf_bytes)

    def test_raises_on_empty_pdf(self):
        """A PDF with pages but no extractable text should raise ValueError."""
        import fitz

        doc = fitz.open()
        doc.new_page(width=595, height=842)  # blank page, no text
        pdf_bytes = doc.tobytes()
        doc.close()

        with pytest.raises(ValueError, match="não contém texto"):
            extract_text_from_pdf(pdf_bytes, "empty.pdf")

    def test_raises_on_invalid_bytes(self):
        with pytest.raises(Exception):
            extract_text_from_pdf(b"not a pdf", "bad.pdf")
