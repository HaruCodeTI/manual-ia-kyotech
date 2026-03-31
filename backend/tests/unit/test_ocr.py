"""Tests for app.services.ocr — Azure Document Intelligence OCR."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.pdf_extractor import PageContent


class TestOcrPdf:
    @pytest.mark.anyio
    async def test_returns_page_contents_from_ocr(self):
        """OCR should return PageContent list with text from each page."""
        from app.services.ocr import ocr_pdf

        mock_page_1 = MagicMock()
        mock_page_1.page_number = 1
        mock_line_1a = MagicMock()
        mock_line_1a.content = "Texto da página 1 linha 1"
        mock_line_1b = MagicMock()
        mock_line_1b.content = "Texto da página 1 linha 2"
        mock_page_1.lines = [mock_line_1a, mock_line_1b]

        mock_page_2 = MagicMock()
        mock_page_2.page_number = 2
        mock_line_2 = MagicMock()
        mock_line_2.content = "Texto da página 2"
        mock_page_2.lines = [mock_line_2]

        mock_result = MagicMock()
        mock_result.pages = [mock_page_1, mock_page_2]

        mock_poller = AsyncMock()
        mock_poller.result.return_value = mock_result

        mock_client = MagicMock()
        mock_client.begin_analyze_document = AsyncMock(return_value=mock_poller)
        mock_client.close = AsyncMock()

        with patch("app.services.ocr._get_client", return_value=mock_client):
            pages = await ocr_pdf(b"fake-pdf-bytes")

        assert len(pages) == 2
        assert pages[0].page_number == 1
        assert "Texto da página 1 linha 1" in pages[0].text
        assert "Texto da página 1 linha 2" in pages[0].text
        assert pages[1].page_number == 2
        assert pages[1].text == "Texto da página 2"

    @pytest.mark.anyio
    async def test_filters_by_page_numbers(self):
        """When page_numbers is provided, only return those pages."""
        from app.services.ocr import ocr_pdf

        mock_page_1 = MagicMock()
        mock_page_1.page_number = 1
        mock_page_1.lines = [MagicMock(content="Page 1")]

        mock_page_2 = MagicMock()
        mock_page_2.page_number = 2
        mock_page_2.lines = [MagicMock(content="Page 2")]

        mock_page_3 = MagicMock()
        mock_page_3.page_number = 3
        mock_page_3.lines = [MagicMock(content="Page 3")]

        mock_result = MagicMock()
        mock_result.pages = [mock_page_1, mock_page_2, mock_page_3]

        mock_poller = AsyncMock()
        mock_poller.result.return_value = mock_result

        mock_client = MagicMock()
        mock_client.begin_analyze_document = AsyncMock(return_value=mock_poller)
        mock_client.close = AsyncMock()

        with patch("app.services.ocr._get_client", return_value=mock_client):
            pages = await ocr_pdf(b"fake-pdf-bytes", page_numbers=[1, 3])

        assert len(pages) == 2
        assert pages[0].page_number == 1
        assert pages[1].page_number == 3

    @pytest.mark.anyio
    async def test_returns_empty_for_pages_without_lines(self):
        """Pages with no lines (blank scans) should be skipped."""
        from app.services.ocr import ocr_pdf

        mock_page = MagicMock()
        mock_page.page_number = 1
        mock_page.lines = []

        mock_result = MagicMock()
        mock_result.pages = [mock_page]

        mock_poller = AsyncMock()
        mock_poller.result.return_value = mock_result

        mock_client = MagicMock()
        mock_client.begin_analyze_document = AsyncMock(return_value=mock_poller)
        mock_client.close = AsyncMock()

        with patch("app.services.ocr._get_client", return_value=mock_client):
            pages = await ocr_pdf(b"fake-pdf-bytes")

        assert len(pages) == 0

    @pytest.mark.anyio
    async def test_raises_on_missing_config(self):
        """Should raise ValueError when endpoint/key not configured."""
        from app.services.ocr import ocr_pdf

        with patch("app.services.ocr.settings") as mock_settings:
            mock_settings.azure_document_intelligence_endpoint = ""
            mock_settings.azure_document_intelligence_key = ""

            with pytest.raises(ValueError, match="Document Intelligence não configurado"):
                await ocr_pdf(b"fake-pdf-bytes")
