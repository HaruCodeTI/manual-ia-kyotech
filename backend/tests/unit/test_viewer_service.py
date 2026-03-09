"""
Kyotech AI — Testes unitarios para app.services.viewer
"""
from __future__ import annotations

import pytest

from app.services.viewer import render_page_as_image


def test_render_valid_page_returns_png(sample_pdf_bytes):
    png_bytes, total_pages = render_page_as_image(
        sample_pdf_bytes, page_number=1, user_id="test-user"
    )
    # PNG magic bytes
    assert png_bytes[:4] == b"\x89PNG"
    assert isinstance(total_pages, int)
    assert total_pages == 2


def test_render_returns_correct_total_pages(sample_pdf_bytes):
    _, total_pages = render_page_as_image(
        sample_pdf_bytes, page_number=2, user_id="test-user"
    )
    assert total_pages == 2


def test_page_zero_raises_value_error(sample_pdf_bytes):
    with pytest.raises(ValueError, match="inválida"):
        render_page_as_image(sample_pdf_bytes, page_number=0, user_id="test-user")


def test_page_too_high_raises_value_error(sample_pdf_bytes):
    with pytest.raises(ValueError, match="inválida"):
        render_page_as_image(sample_pdf_bytes, page_number=99, user_id="test-user")


def test_custom_watermark_does_not_raise(sample_pdf_bytes):
    png_bytes, _ = render_page_as_image(
        sample_pdf_bytes,
        page_number=1,
        user_id="test-user",
        watermark_text="CONFIDENCIAL",
    )
    assert png_bytes[:4] == b"\x89PNG"
